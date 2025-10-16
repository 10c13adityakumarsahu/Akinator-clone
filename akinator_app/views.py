from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import Question, GameSession, Character
from .serializers import QuestionSerializer, CharacterSerializer
from .knowledge_base import best_question
from .ai_data_collector import get_character_info
from django.db.models import Q # Import Q objects for complex queries

# This map helps the ai_data_collector populate initial features.
# You MUST update the integer IDs to match the IDs of these questions in your database.
# Example: If "Is your character male?" has an ID of 5, you'd put 5 here.
WIKIDATA_TO_QUESTION_MAP = {
    "gender": {
        "male": {"question_id": -1, "answer": "yes"}, # TODO: Replace -1 with the correct Question ID
        "female": {"question_id": -1, "answer": "no"}   # Assuming the question is "Is your character male?"
    },
    # TODO: Add mappings for occupations, etc.
    # "occupation": {
    #     "singer": {"question_id": -1, "answer": "yes"} # For a question like "Is your character a singer?"
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

        # Use the WIKIDATA_TO_QUESTION_MAP to pre-populate features
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
def start_game(request):
    all_character_ids = list(Character.objects.values_list('id', flat=True))
    if not all_character_ids:
        return Response({"error": "No characters in the database to start a game."}, status=status.HTTP_404_NOT_FOUND)

    # Corrected call to best_question with all three required arguments
    first_question = best_question(all_character_ids, [], {})
    
    if not first_question:
        # Fallback: if entropy calculation fails, just pick a random question
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
    
    # --- DATABASE-AGNOSTIC FILTERING IN PYTHON ---
    if current_candidates_ids:
        candidate_chars = Character.objects.filter(id__in=current_candidates_ids)
        filtered_ids = []
        for char in candidate_chars:
            features = char.features or {}
            char_answer = features.get(question_id_str)
            
            keep_char = True
            if char_answer: # Only filter if the character has a defined feature for this question
                if answer == "yes" and char_answer in ["no", "probably_not"]:
                    keep_char = False
                elif answer == "no" and char_answer in ["yes", "probably"]:
                    keep_char = False
                elif answer == "probably" and char_answer == "no":
                    keep_char = False
                elif answer == "probably_not" and char_answer == "yes":
                    keep_char = False
            
            if keep_char:
                filtered_ids.append(char.id)
        
        session.possible_character_ids = filtered_ids
    
    # --- CORRECTED LOGIC FOR NEXT QUESTION ---
    # 1. Save the current answer first.
    session.answers[question_id_str] = answer
    
    # 2. Get the updated state of the game.
    answers_so_far = session.answers
    asked_question_ids = list(answers_so_far.keys())
    
    # 3. Call best_question ONLY ONCE with the correct, updated information.
    next_q = best_question(session.possible_character_ids, asked_question_ids, answers_so_far)

    # End the game if we have no more questions or have narrowed it down.
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

    # --- More Robust Scoring Logic ---
    best_match = None
    best_score = -1000  # Start low to ensure any character gets picked

    for char in Character.objects.filter(id__in=candidate_ids):
        score = 0
        features = char.features or {}
        for q_id_str, user_answer in answers.items():
            char_answer = features.get(q_id_str)
            if char_answer:
                if user_answer == char_answer:
                    score += 2  # Strong agreement
                elif user_answer in ["yes", "no"] and user_answer != char_answer:
                    score -= 2  # Strong disagreement
                elif user_answer == 'dont_know':
                    score -= 1  # User is unsure about a known feature
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

