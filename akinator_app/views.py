from django.shortcuts import render
from .models import Question,GameSession,Character
from django.http import JsonResponse
import random,json
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .serializers import QuestionSerializer,CharacterSerializer,GameSessionSerializer
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

@api_view(['POST'])
def answer_question(request):
    data = request.data
    session_id = data.get("session_id")
    answer = data.get("answer")
    try:
        session = GameSession.objects.get(session_id=session_id)
    except GameSession.DoesNotExist:
        return Response({"error": "Invalid session ID"}, status=status.HTTP_400_BAD_REQUEST)
    question = session.current_question
    session.answers[str(question.text)]=answer
    session.save()

    remaining_questions = list(Question.objects.exclude(id=question.id))
    if not remaining_questions:
        session.is_completed=True
        session.save()
        return Response({"message":"No more questions!","session_id":session_id})
    
    next_q = random.choice(remaining_questions)
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

    answers = session.answers
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

    session.is_completed = True
    session.save()

    return Response({
        "guessed_character": CharacterSerializer(best_match).data,
        "match_score": best_score
    })