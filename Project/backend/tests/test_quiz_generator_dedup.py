"""
Tests for the question-deduplication logic in SoloQuizGeneratorLocal.

Two questions are functional duplicates if they share an anchor (LO or section)
AND their normalised correct answer matches — even if the wording differs.
That's the property `_is_question_unique` guards.
"""

from core.quiz_generator import SoloQuizGeneratorLocal


def _make_question(text, correct, lo_id=None, section_id=None):
    return {
        "question_text": text,
        "correct_answer": correct,
        "learning_object_id": lo_id,
        "section_id": section_id,
    }


def test_first_question_is_unique():
    gen = SoloQuizGeneratorLocal()
    q = _make_question("What is a process?", "A) An instance of a program.", lo_id=1)
    assert gen._is_question_unique(q) is True


def test_exact_text_duplicate_is_rejected():
    gen = SoloQuizGeneratorLocal()
    q1 = _make_question("What is a process?", "A) An instance.", lo_id=1)
    assert gen._is_question_unique(q1) is True
    gen._register_question(q1)

    q2 = _make_question("What is a process?", "B) Different answer.", lo_id=99)
    assert gen._is_question_unique(q2) is False


def test_same_anchor_plus_same_answer_is_rejected_even_when_wording_differs():
    """The big win: a rephrased question testing the same fact is caught."""
    gen = SoloQuizGeneratorLocal()
    q1 = _make_question(
        "What is a process?",
        "A) An instance of a program.",
        lo_id=42,
    )
    assert gen._is_question_unique(q1) is True
    gen._register_question(q1)

    # Same LO, same correct answer, different stem — still a duplicate.
    q2 = _make_question(
        "Define the term 'process' as used in operating systems.",
        "B) An instance of a program",  # note: different letter prefix, no period
        lo_id=42,
    )
    assert gen._is_question_unique(q2) is False


def test_different_anchor_with_same_answer_is_allowed():
    """Two questions about different LOs can share answer text."""
    gen = SoloQuizGeneratorLocal()
    q1 = _make_question("Q about LO 1", "A) Common phrase", lo_id=1)
    gen._register_question(q1)

    q2 = _make_question("Q about LO 2", "A) Common phrase", lo_id=2)
    assert gen._is_question_unique(q2) is True


def test_questions_without_anchor_fall_back_to_text_only_dedup():
    """No anchor → only the text-hash check matters."""
    gen = SoloQuizGeneratorLocal()
    q1 = _make_question("Floating question", "A) X", lo_id=None, section_id=None)
    gen._register_question(q1)

    # Same text, no anchor — caught by hash.
    q2 = _make_question("Floating question", "B) Y", lo_id=None, section_id=None)
    assert gen._is_question_unique(q2) is False

    # Different text, no anchor — allowed.
    q3 = _make_question("Different question entirely", "A) X", lo_id=None, section_id=None)
    assert gen._is_question_unique(q3) is True


def test_empty_question_text_is_rejected():
    gen = SoloQuizGeneratorLocal()
    assert gen._is_question_unique({"question_text": "", "correct_answer": "X"}) is False
    assert gen._is_question_unique({"correct_answer": "X"}) is False  # missing key
