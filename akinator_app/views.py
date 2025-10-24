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
    """
    Adds a new character to the database by scraping its info.
    Features are stored using question text as the key.
    """
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
                    
                    # --- MODIFIED: Get question text from ID ---
                    q_id = mapping["question_id"]
                    if q_id != -1:
                        try:
                            # We fetch the question text to use it as the key
                            question = Question.objects.get(id=q_id)
                            initial_features[question.text] = mapping["answer"]
                        except Question.DoesNotExist:
                            print(f"Error in add_character: Question ID {q_id} not found in WIKIDATA_TO_QUESTION_MAP.")
                    # --- END MODIFIED ---

        char = Character.objects.create(
            name=data["name"],
            description=data.get("summary", ""),
            features=initial_features, # This is now {'Is your character male?': 'yes'}
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
    """
    Starts a new game session and returns the first question.
    """
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
    """
    Processes a user's answer to a question, filters candidates,
    and returns the next best question.
    
    This view contains the SQLITE WORKAROUND and uses
    question TEXT for feature lookups.
    """
    session_id = request.data.get("session_id")
    answer = request.data.get("answer")
    question_id = request.data.get("question_id")

    try:
        session = GameSession.objects.get(session_id=session_id)
    except GameSession.DoesNotExist:
        return Response({"error": "Invalid session ID"}, status=status.HTTP_404_NOT_FOUND)

    # --- NEW: We must get the question text to do the lookup ---
    try:
        question = Question.objects.get(id=question_id)
    except Question.DoesNotExist:
        return Response({"error": "Invalid question ID"}, status=status.HTTP_404_NOT_FOUND)
    # --- END NEW ---

    current_candidates_ids = session.possible_character_ids
    question_id_str = str(question_id) # We still use this for the session.answers
    
    # --- SQLITE WORKAROUND START ---
    # We must filter in Python because SQLite does not support __contains on JSON fields.
    if current_candidates_ids:
        # This map defines which character answers to exclude based on the user's answer.
        exclusion_map = {
            "yes": ["no", "probably_not"],
            "no": ["yes", "probably"],
            "probably": ["no"],
            "probably_not": ["yes"]
        }
        
        # We only filter if the answer provides clear information.
        # "dont_know" does not filter anyone.
        if answer in exclusion_map:
            new_possible_ids = []
            
            # Get the list of values we need to exclude
            values_to_exclude = exclusion_map[answer]
            
            # Fetch all candidate objects from the DB to check them in Python
            candidate_chars = Character.objects.filter(id__in=current_candidates_ids)

            for char in candidate_chars:
                # --- MODIFIED: Use question.text as the key ---
                # Get this character's answer for the current question (if any)
                char_answer = char.features.get(question.text) 
                # --- END MODIFIED ---
                
                # Keep the character ONLY if their answer is NOT in the exclusion list
                if char_answer not in values_to_exclude:
                    new_possible_ids.append(char.id)
            
            # Update the session with the new, filtered list of IDs
            session.possible_character_ids = new_possible_ids
        
        # If the answer was "dont_know", we do nothing and keep all candidates.
        
    # --- SQLITE WORKAROUND END ---
    
    # Save the current answer to the session.
    # NOTE: session.answers will STILL use the ID as the key (e.g., {'5': 'yes'}).
    # We will convert this to text in the "learn_from_feedback" step.
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
    """
    Calculates and returns the best-matching character at the end of a game.
    This view has been MODIFIED to read features using question TEXT.
    """
    session_id = request.query_params.get("session_id")
    try:
        session = GameSession.objects.get(session_id=session_id)
    except GameSession.DoesNotExist:
        return Response({"error": "Invalid session ID"}, status=status.HTTP_404_NOT_FOUND)

    candidate_ids = session.possible_character_ids or []
    # answers is {'5': 'yes', '12': 'no'}
    answers = session.answers or {}
    
    if not candidate_ids:
        return Response({"guessed_character": None, "match_score": 0, "message": "No characters matched your answers."})

    if len(candidate_ids) == 1:
        best_match = Character.objects.get(id=candidate_ids[0])
        return Response({
            "guessed_character": CharacterSerializer(best_match).data,
            "match_score": 100
        })

    # --- MODIFIED: Convert answer IDs to question text for lookup ---
    # Get all questions from the session in one efficient query
    question_ids = [int(q_id) for q_id in answers.keys()]
    # questions becomes a dict like {5: <Question object>, 12: <Question object>}
    questions = Question.objects.in_bulk(question_ids) 
    # --- END MODIFIED ---

    best_match = None
    best_score = -1000 
    for char in Character.objects.filter(id__in=candidate_ids):
        score = 0
        features = char.features or {}
        
        for q_id_str, user_answer in answers.items():
            # Get the <Question> object corresponding to the ID
            question = questions.get(int(q_id_str))
            
            if question:
                # --- MODIFIED: Use question.text as the key ---
                char_answer = features.get(question.text)
                # --- END MODIFIED ---
                
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
    """
    Learns from user feedback after a game.
    Converts session answers (by ID) to features (by text) before saving.
    """
    session_id = request.data.get("session_id")
    was_correct = request.data.get("was_correct")
    guessed_character_id = request.data.get("guessed_character_id")
    
    try:
        session = GameSession.objects.get(session_id=session_id)
        # session.answers is {'5': 'yes', '12': 'no'}
        answers_from_session = session.answers or {}
    except GameSession.DoesNotExist:
        return Response({"error": "Invalid session ID"}, status=status.HTTP_404_NOT_FOUND)

    # --- NEW: Convert session answers (by ID) to features (by text) ---
    features_to_learn = {}
    
    # Efficiently get all questions in one query
    question_ids = [int(q_id) for q_id in answers_from_session.keys()]
    questions = Question.objects.in_bulk(question_ids) # {5: <Question>, 12: <Question>}

    for q_id_str, answer in answers_from_session.items():
        question = questions.get(int(q_id_str))
        if question:
            # Use the question's text as the key
            features_to_learn[question.text] = answer
        else:
            print(f"Warning in learn_from_feedback: Question ID {q_id_str} not found. Skipping feature.")
    
    # features_to_learn is now {'Is your character male?': 'yes', ...}
    # --- END NEW ---

    if was_correct:
        try:
            character = Character.objects.get(id=guessed_character_id)
            # --- MODIFIED: Merge the new text-based features ---
            character.features = (character.features or {}) | features_to_learn
            # --- END MODIFIED ---
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
        
        # --- MODIFIED: Merge the new text-based features ---
        character.features = (character.features or {}) | features_to_learn
        # --- END MODIFIED ---
        character.save()
        
        message = f"Thanks for teaching me about {character.name}!"
        if created:
            message += " They are new to my knowledge base."
            
        return Response({"message": message})
