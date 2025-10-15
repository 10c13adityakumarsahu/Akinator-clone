from django.db import models
import uuid

ANSWER_CHOICES = ["yes", "no", "dont_know", "probably", "probably_not"]

class Question(models.Model):
    question_id = models.CharField(max_length=20, default='', blank=True)
    text = models.CharField(max_length=255)
    popularity = models.FloatField(default=0.0)
    information_value = models.FloatField(default=0.0)

    def __str__(self):
        return self.text

class Character(models.Model):
    character_id = models.CharField(max_length=20, default='', blank=True)
    name = models.CharField(max_length=100)
    image_url = models.URLField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    # Each feature maps question text → one of the 5 possible answers
    # e.g. {"Can your character fly?": "yes", "Is your character real?": "no"}
    features = models.JSONField(default=dict)
    added_by = models.CharField(max_length=50, default='system')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Relation(models.Model):
    ANSWER_CHOICES = [
        ("yes", "Yes"),
        ("no", "No"),
        ("probably", "Probably"),
        ("probably_not", "Probably Not"),
        ("dont_know", "Don't Know"),
    ]

    character = models.ForeignKey(Character, on_delete=models.CASCADE)
    question = models.ForeignKey('Question', on_delete=models.CASCADE)
    answer = models.CharField(max_length=20, choices=ANSWER_CHOICES)

    def __str__(self):
        return f"{self.character.name} → {self.question.text} = {self.answer}"

class GameSession(models.Model):
    session_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    current_question = models.ForeignKey(Question, on_delete=models.SET_NULL, null=True, blank=True)
    answers = models.JSONField(default=dict)
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Session {self.session_id}"
