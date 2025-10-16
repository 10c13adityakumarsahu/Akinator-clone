from django.shortcuts import render
from .models import Question,GameSession,Character
from django.http import JsonResponse
import random,json
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .serializers import QuestionSerializer,CharacterSerializer,GameSessionSerializer
from .ai_data_collector import get_character_info
from .questions import QUESTIONS
from .knowledge_base import best_question
# Create your views here.
@api_view(['GET'])
def start_game(request):
    questions = list(Question.objects.all())
    if not questions:
        return Response({"error":"No questions in database!"},status=status.HTTP_400_BAD_REQUEST)
    first_question = random.choice(questions)
    session = GameSession.objects.create(current_question=first_question)
    return Response({
        "session_id": str(session.session_id),
        "question": QuestionSerializer(first_question).data
    })

@api_view(["POST"])
def add_character(request):
    """
    Adds a new character to the database using AI-powered data collection.
    Expected body: {"name": "Elon Musk"}
    """
    name = request.data.get("name")
    if not name:
        return Response({"error": "Character name required"}, status=400)

    # Check if already exists
    if Character.objects.filter(name__iexact=name).exists():
        return Response({"message": f"{name} already exists."})

    # Fetch info
    data = get_character_info(name)
    char = Character.objects.create(
        name=data["name"],
        description=data.get("summary") or "",
        features={},  # can be filled later with answers
        added_by="AI Collector"
    )
    return Response({
        "message": "Character added successfully!",
        "character": {
            "name": char.name,
            "description": char.description,
            "details": data.get("details", {})
        }
    })


@api_view(['POST'])
def get_character_info_api(request):
    name = request.data.get('name')
    if not name:
        return Response({"error": "Name is required"}, status=400)

    info = get_character_info(name)
    return Response(info)

@api_view(['POST'])
def answer_question(request):
    session_id = request.data.get("session_id")
    answer = request.data.get("answer")
    
    try:
        session = GameSession.objects.get(session_id=session_id)
    except GameSession.DoesNotExist:
        return Response({"error": "Invalid session ID"}, status=400)

    # Save the answer
    question = session.current_question
    if not question:
        return Response({"error": "No current question"}, status=400)

    answers = dict(session.answers or {})
    answers[question.text] = answer
    session.answers = answers
    session.save()

    # Pick the next best question dynamically
    next_q = best_question(session.answers)

    if not next_q:
        # AI has run out of informative questions → make a guess
        characters = Character.objects.all()
        best_match = None
        best_score = -1
        for char in characters:
            score = sum(1 for q, a in answers.items() if q in char.features and char.features[q] == a)
            if score > best_score:
                best_match = char
                best_score = score

        session.is_completed = True
        session.save()
        return Response({
            "guessed_character": CharacterSerializer(best_match).data,
            "match_score": best_score
        })

    # Ask next question
    session.current_question = next_q
    session.save()
    return Response({
        "session_id": session_id,
        "next_question": QuestionSerializer(next_q).data
    })


@api_view(['GET'])
def get_result(request):
    session_id = request.query_params.get("session_id")
    try:
        session = GameSession.objects.get(session_id=session_id)
    except GameSession.DoesNotExist:
        return Response({"error": "Invalid session ID"}, status=status.HTTP_400_BAD_REQUEST)

    answers = session.answers or {}
    characters = Character.objects.all()

    if not characters:
        return Response({"error": "No characters in database yet!"})

    best_match = None
    best_score = -1

    for char in characters:
        score = 0
        for q, a in answers.items():
            if q in char.features and char.features[q] == a:
                score += 1
        if score > best_score:
            best_match = char
            best_score = score

    # ✅ Learning step — merge new answers into the best-matched character’s knowledge
    if best_match:
        features = dict(best_match.features or {})
        for q, a in answers.items():
            # update only if not present or if we got a new answer
            if q not in features:
                features[q] = a
        best_match.features = features
        best_match.save()

    session.is_completed = True
    session.save()

    return Response({
        "guessed_character": CharacterSerializer(best_match).data,
        "match_score": best_score
    })
