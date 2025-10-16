from django.db import models
import uuid

ANSWER_CHOICES = ["yes", "no", "dont_know", "probably", "probably_not"]

class Question(models.Model):
    text = models.CharField(max_length=255, unique=True)
    # These fields are for future use in a more advanced knowledge_base
    popularity = models.FloatField(default=0.0)
    information_value = models.FloatField(default=0.0)
    # --- NEW LOGIC FIELDS ---
    # This question should only be asked if the answers to the prerequisite questions were 'yes'.
    prerequisite_questions = models.ManyToManyField('self', symmetrical=False, blank=True, related_name='unlocks')
    # This question should NOT be asked if the answer to a contradictory question was 'yes'.
    contradictory_questions = models.ManyToManyField('self', symmetrical=False, blank=True)
    def __str__(self):
        return self.text


class Character(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    # The features dictionary now uses the question's ID as the key.
    features = models.JSONField(default=dict)  # {question_id: answer}
    added_by = models.CharField(max_length=50, default='system')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class GameSession(models.Model):
    session_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    current_question = models.ForeignKey(Question, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Stores answers with question ID as the key.
    answers = models.JSONField(default=dict)  # {question_id: answer}
    
    # List of character IDs that are still potential candidates.
    possible_character_ids = models.JSONField(default=list)
    
    # List of question IDs that have already been asked in this session.
    asked_question_ids = models.JSONField(default=list)

    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Session {self.session_id}"
