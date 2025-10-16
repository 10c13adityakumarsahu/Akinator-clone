import math
import random
from .models import Character, Question

ALL_ANSWERS = ["yes", "no", "dont_know", "probably", "probably_not"]

def calculate_entropy(probabilities):
    """Calculates the Shannon entropy for a list of probabilities."""
    return -sum(p * math.log2(p) for p in probabilities if p > 0)

def calculate_answer_distribution(question, candidate_characters):
    """
    Calculates the distribution of answers for a single question based on a list
    of candidate characters already in memory.
    """
    answer_counts = {answer: 0 for answer in ALL_ANSWERS}
    total_candidates = len(candidate_characters)

    if total_candidates == 0:
        return [0.0] * len(ALL_ANSWERS)

    # Count answers in memory
    for char in candidate_characters:
        features = char.features or {}
        answer = features.get(str(question.id))
        if answer in answer_counts:
            answer_counts[answer] += 1
        else:
            answer_counts["dont_know"] += 1

    # Return the probability distribution
    return [count / total_candidates for count in answer_counts.values()]

def best_question(candidate_ids, asked_question_ids, answers_so_far):
    """
    Finds the best question to ask next by maximizing information gain (entropy)
    while respecting logical dependencies between questions.

    Args:
        candidate_ids (list): IDs of characters that are still possible candidates.
        asked_question_ids (list): IDs of questions that have already been asked.
        answers_so_far (dict): A dictionary of {question_id: answer} for the current session.
    
    Returns:
        Question: The best Question object to ask next, or None.
    """
    if not candidate_ids:
        return None

    # --- Step 1: Efficiently fetch all candidate data in one query ---
    candidate_chars = list(Character.objects.filter(id__in=candidate_ids))
    
    # --- Step 2: Determine the pool of potential questions ---
    
    # Start with all questions that haven't been asked yet.
    potential_questions = Question.objects.exclude(id__in=asked_question_ids)

    # --- Step 3: (OPTIONAL, BUT RECOMMENDED) Filter questions based on logical rules ---
    # This is the "smart" part that prevents asking illogical questions.
    # It requires prerequisite_questions and contradictory_questions fields on the Question model.
    
    logically_valid_qs = []
    if hasattr(Question, 'prerequisite_questions'): # Check if the model has been updated
        for question in potential_questions:
            is_valid = True
            
            # Rule 1: Check if all prerequisites are met.
            # Only ask "founded a car company?" if the answer to "is real?" was "yes".
            for prereq in question.prerequisite_questions.all():
                if answers_so_far.get(str(prereq.id)) != 'yes':
                    is_valid = False
                    break
            if not is_valid:
                continue

            # Rule 2: Check for direct contradictions.
            # Don't ask about real-world things if we know the character is fictional.
            for contra in question.contradictory_questions.all():
                if answers_so_far.get(str(contra.id)) == 'yes':
                    is_valid = False
                    break
            
            if is_valid:
                logically_valid_qs.append(question)
    else:
        # If the model hasn't been updated, just use all potential questions.
        logically_valid_qs = list(potential_questions)

    if not logically_valid_qs:
        return None

    # --- Step 4: Calculate entropy for each valid question ---
    best_q = None
    max_entropy = -1

    for question in logically_valid_qs:
        probabilities = calculate_answer_distribution(question, candidate_chars)
        current_entropy = calculate_entropy(probabilities)

        if current_entropy > max_entropy:
            max_entropy = current_entropy
            best_q = question

    # --- Step 5: (Fallback) If no question provides info, pick a random one ---
    # This happens if all remaining characters have "dont_know" for all remaining questions.
    if best_q is None and logically_valid_qs:
        return random.choice(logically_valid_qs)

    return best_q

