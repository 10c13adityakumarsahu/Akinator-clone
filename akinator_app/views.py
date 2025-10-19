from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import Question, GameSession, Character
from .serializers import QuestionSerializer, CharacterSerializer
from .knowledge_base import best_question
from .ai_data_collector import get_character_info
from django.db.models import Q # Import Q objects for complex queries
from django.shortcuts import render

# NOTE: For full production readiness, this hardcoded map should be replaced
# by the database-driven approach we discussed, where these mappings are
# stored on the Question model itself.
WIKIDATA_TO_QUESTION_MAP = {
    "gender": {
        "male": {"question_id": -1, "answer": "yes"}, # TODO: Replace -1 with the correct Question ID
        "female": {"question_id": -1, "answer": "no"}  # Assuming the question is "Is your character male?"
    },
    # "occupation": {
    #     "singer": {"question_id": -1, "answer": "yes"}
    # }
}


@api_view(['POST'])
def add_character(request):
    name = request.data.get("name")
    if not name:
        return Response({"error": "Name is required."}, status=status.HTTP_400_BAD_REQUEST)
    
    if Character.objects.filter(name__iexact=name).exists():
        return Response({"message": f"Character '{name}' already exists."}, status=status.HTTP_200_OK)

    try:
        data = get_character_info(name)
        initial_features = {}
        details = data.get("details")
        if details:
            for key, value_map in WIKIDATA_TO_QUESTION_MAP.items():
                detail_value = details.get(key)
                if detail_value and detail_value in value_map:
                    mapping = value_map[detail_value]
                    if mapping["question_id"] != -1:
                        initial_features[str(mapping["question_id"])] = mapping["answer"]

        char = Character.objects.create(
            name=data["name"],
            description=data.get("summary", ""),
            features=initial_features,
            added_by="AI Collector"
        )
        return Response(CharacterSerializer(char).data, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({"error": f"Failed to add character: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
@api_view(['GET'])
def index_view(request):
    """
    Serves the main index.html file which contains the game's frontend.
    """
    return render(request, 'akinator_app/index.html')

@api_view(['GET'])
def start_game(request):
    all_character_ids = list(Character.objects.values_list('id', flat=True))
    if not all_character_ids:
        return Response({"error": "No characters in the database to start a game."}, status=status.HTTP_404_NOT_FOUND)

    first_question = best_question(all_character_ids, [], {})
    
    if not first_question:
        first_question = Question.objects.order_by('?').first()
        if not first_question:
            return Response({"error": "No questions in the database."}, status=status.HTTP_404_NOT_FOUND)

    session = GameSession.objects.create(
        current_question=first_question,
        possible_character_ids=all_character_ids,
        answers={}
    )
    return Response({
        "session_id": str(session.session_id),
        "question": QuestionSerializer(first_question).data
    })


@api_view(['POST'])
def answer_question(request):
    session_id = request.data.get("session_id")
    answer = request.data.get("answer")
    question_id = request.data.get("question_id")

    try:
        session = GameSession.objects.get(session_id=session_id)
    except GameSession.DoesNotExist:
        return Response({"error": "Invalid session ID"}, status=status.HTTP_404_NOT_FOUND)

    current_candidates_ids = session.possible_character_ids
    question_id_str = str(question_id)
    
    # --- OPTIMIZED: EFFICIENT DATABASE-SIDE FILTERING ---
    # This block replaces the slow Python loop with a fast database query.
    if current_candidates_ids:
        candidate_chars = Character.objects.filter(id__in=current_candidates_ids)
        
        # This map defines which character answers to exclude based on the user's answer.
        exclusion_map = {
            "yes": ["no", "probably_not"],
            "no": ["yes", "probably"],
            "probably": ["no"],
            "probably_not": ["yes"]
        }
        
        # We build a query only if the user's answer provides clear information.
        # "dont_know" does not filter anyone.
        if answer in exclusion_map:
            # Create a list of Q objects to represent OR conditions for the exclusion.
            # e.g., for a "yes" answer, we want to exclude characters where the feature is 'no' OR 'probably_not'.
            exclude_conditions = [Q(features__contains={question_id_str: val}) for val in exclusion_map[answer]]
            
            # Combine the Q objects with an OR operator.
            final_query = Q()
            for condition in exclude_conditions:
                final_query |= condition
            
            # Execute a single, efficient database query to exclude the mismatches.
            candidate_chars = candidate_chars.exclude(final_query)
        
        # Get the remaining valid character IDs from the optimized database query.
        session.possible_character_ids = list(candidate_chars.values_list('id', flat=True))
    
    # --- END OF OPTIMIZED BLOCK ---
    
    # Save the current answer to the session.
    session.answers[question_id_str] = answer
    
    answers_so_far = session.answers
    asked_question_ids = list(answers_so_far.keys())
    
    # Find the next best question based on the new, smaller pool of candidates.
    next_q = best_question(session.possible_character_ids, asked_question_ids, answers_so_far)

    # End the game if we have no more good questions or are confident in the result.
    if not next_q or (len(session.possible_character_ids) < 2 and len(asked_question_ids) > 5):
        session.is_completed = True
        session.current_question = None
        session.save()
        return Response({"next_question": None})

    session.current_question = next_q
    session.save()
    return Response({"next_question": QuestionSerializer(next_q).data})


@api_view(['GET'])
def get_result(request):
    session_id = request.query_params.get("session_id")
    try:
        session = GameSession.objects.get(session_id=session_id)
    except GameSession.DoesNotExist:
        return Response({"error": "Invalid session ID"}, status=status.HTTP_404_NOT_FOUND)

    candidate_ids = session.possible_character_ids or []
    answers = session.answers or {}
    
    if not candidate_ids:
        return Response({"guessed_character": None, "match_score": 0, "message": "No characters matched your answers."})

    if len(candidate_ids) == 1:
        best_match = Character.objects.get(id=candidate_ids[0])
        return Response({
            "guessed_character": CharacterSerializer(best_match).data,
            "match_score": 100
        })

    best_match = None
    best_score = -1000 
    for char in Character.objects.filter(id__in=candidate_ids):
        score = 0
        features = char.features or {}
        for q_id_str, user_answer in answers.items():
            char_answer = features.get(q_id_str)
            if char_answer:
                if user_answer == char_answer:
                    score += 2
                elif user_answer in ["yes", "no"] and user_answer != char_answer:
                    score -= 2
                elif user_answer == 'dont_know':
                    score -= 1
        if score > best_score:
            best_score = score
            best_match = char
            
    return Response({
        "guessed_character": CharacterSerializer(best_match).data if best_match else None,
        "match_score": best_score
    })


@api_view(['POST'])
def learn_from_feedback(request):
    session_id = request.data.get("session_id")
    was_correct = request.data.get("was_correct")
    guessed_character_id = request.data.get("guessed_character_id")
    
    try:
        session = GameSession.objects.get(session_id=session_id)
        answers = session.answers or {}
    except GameSession.DoesNotExist:
        return Response({"error": "Invalid session ID"}, status=status.HTTP_404_NOT_FOUND)

    if was_correct:
        try:
            character = Character.objects.get(id=guessed_character_id)
            # Use the | operator to merge the session's answers into the character's features.
            character.features = (character.features or {}) | answers
            character.save()
            return Response({"message": f"Thanks for confirming! I've learned more about {character.name}."})
        except Character.DoesNotExist:
            return Response({"error": "Character not found for learning."}, status=status.HTTP_404_NOT_FOUND)
    else:
        correct_name = request.data.get("correct_character_name")
        if not correct_name:
            return Response({"error": "correct_character_name is required when guess is incorrect."}, status=status.HTTP_400_BAD_REQUEST)
        
        character, created = Character.objects.get_or_create(
            name__iexact=correct_name,
            defaults={'name': correct_name, 'added_by': 'user_feedback'}
        )
        
        character.features = (character.features or {}) | answers
        character.save()
        
        message = f"Thanks for teaching me about {character.name}!"
        if created:
            message += " They are new to my knowledge base."
            
        return Response({"message": message})
