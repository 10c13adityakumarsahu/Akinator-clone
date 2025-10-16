import math
from .models import Character, Question

# five answer keys we use everywhere
ALL_ANSWERS = ["yes", "no", "dont_know", "probably", "probably_not"]

def load_kb():
    """
    Load knowledge base as dict: { char_name: features_dict }
    where features_dict maps question_text -> one of the 5 answers.
    """
    kb = {}
    for c in Character.objects.all():
        # ensure we have a plain dict for features
        kb[c.name] = dict(c.features or {})
    return kb

def entropy_distribution(probs):
    """Shannon entropy for a discrete distribution probs (list of p_i)."""
    ent = 0.0
    for p in probs:
        if p > 0:
            ent -= p * math.log2(p)
    return ent

def question_answer_distribution(question_text, remaining_chars):
    """
    For a given question_text and remaining_chars (list of (name, features)),
    return distribution over ALL_ANSWERS in the same order.
    """
    counts = {a: 0 for a in ALL_ANSWERS}
    total = 0
    for name, feats in remaining_chars:
        val = feats.get(question_text, None)
        if val in ALL_ANSWERS:
            counts[val] += 1
        else:
            # treat missing info as 'dont_know'
            counts["dont_know"] += 1
        total += 1
    if total == 0:
        return [0 for _ in ALL_ANSWERS]
    return [counts[a] / total for a in ALL_ANSWERS]

def best_question(answers_so_far):
    """
    Choose the question (Question object) that maximizes entropy
    over the distribution of answers among the remaining candidate characters.

    answers_so_far: dict mapping question_text -> answer (one of ALL_ANSWERS)
    """
    knowledge_base = load_kb()

    # 1) Compute remaining candidate characters given answers_so_far
    remaining = []
    for name, feats in knowledge_base.items():
        ok = True
        for q_text, user_ans in answers_so_far.items():
            # if char has the question and it conflicts strongly with user's answer,
            # we treat it as mismatch. For simplicity, require exact match here.
            if q_text in feats:
                if feats[q_text] != user_ans:
                    ok = False
                    break
            # if char doesn't have that question, we don't immediately discard it
        if ok:
            remaining.append((name, feats))

    # If no candidates remain, return None (nothing to ask)
    if not remaining:
        return None

    # 2) Build a set of candidate questions to evaluate:
    #    union of all feature keys among remaining chars + all Questions in DB (fallback)
    feature_questions = set()
    for _, feats in remaining:
        feature_questions.update(feats.keys())

    # Convert to Question objects: prefer DB Question by exact text, else create a pseudo wrapper
    # We'll check DB for matching text
    possible_questions = []
    for q_text in feature_questions:
        q_obj = Question.objects.filter(text=q_text).first()
        if q_obj:
            possible_questions.append(q_obj)
        else:
            # If there's no DB question with that text, we create a lightweight object-like dict
            # with a .text attribute so calling code can use it similarly.
            class PseudoQ:
                def __init__(self, text): self.text = text
            possible_questions.append(PseudoQ(q_text))

    # Also include any Questions from DB that might not be in feature_questions
    # (This ensures the system can ask questions even if one character lacks that feature)
    for q in Question.objects.all():
        if q.text not in feature_questions:
            possible_questions.append(q)

    # 3) Exclude already-asked questions
    asked_texts = set(answers_so_far.keys())
    candidate_qs = [q for q in possible_questions if q.text not in asked_texts]

    if not candidate_qs:
        return None

    # 4) Evaluate entropy for each candidate question and pick highest
    best_q = None
    best_entropy = -1.0
    for q in candidate_qs:
        dist = question_answer_distribution(q.text, remaining)
        ent = entropy_distribution(dist)
        # We can also weight by how many chars would be affected (optional).
        if ent > best_entropy:
            best_entropy = ent
            best_q = q

    # best_q may be a PseudoQ or a real Question. If it's pseudo, try to find/create DB Question
    if best_q is None:
        return None

    if isinstance(best_q, Question):
        return best_q
    else:
        # try to find DB Question; if none, create a new Question entry
        qdb = Question.objects.filter(text=best_q.text).first()
        if qdb:
            return qdb
        else:
            # create a lightweight DB question (so future runs will use it)
            qdb = Question.objects.create(text=best_q.text)
            return qdb
