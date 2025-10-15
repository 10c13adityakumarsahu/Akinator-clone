from django.shortcuts import render
from .models import Question,GameSession
from django.http import JsonResponse
import random,json
# Create your views here.

def start_game(request):
    question = random.choice(Question.objects.all())
    session = GameSession.objects.create(current_question=question)
    return JsonResponse({
        "message": "New game started!",
        "session_id": str(session.session_id),
        "question_id": question.id,
        "question_text": question.text
    })

def submit_answer(request):
    if request.method!="POST":
        return JsonResponse({"error":"Use POST method"}, status=400)
    data = json.loads(request.body)
    session_id = data.get("session_id")
    question_id = data.get("question_id")
    answer = data.get("answer")

    try:
        session = GameSession.objects.get(session_id=session_id)
        question = Question.objects.get(id=question_id)
    except:
        return JsonResponse({"error":"Invalid session/question"},status=404)   
    
    answers = session.answers
    answers[str(question.id)] = answer
    session.answers = answers

    # 2️⃣ Pick next question (for now random among those not yet asked)
    all_questions = list(Question.objects.exclude(id__in=session.answers.keys()))
    if not all_questions:
        session.is_completed = True
        session.save()
        return JsonResponse({
            "message": "Game over! (no more questions)",
            "answers": session.answers
        })

    next_question = random.choice(all_questions)
    session.current_question = next_question
    session.save()

    # 3️⃣ Send next question
    return JsonResponse({
        "message": "Answer recorded",
        "next_question_id": next_question.id,
        "next_question_text": next_question.text,
        "answers_so_far": session.answers
    })