"""
Tests for services.quality.solo_judge.

The judge calls an LLM, so we inject a fake `llm_caller` instead of hitting
Ollama. This keeps tests fast, deterministic, and offline.
"""

import json

from services.quality.solo_judge import (
    SOLO_LEVELS,
    _cohen_kappa,
    _confusion_matrix,
    _parse_judge_response,
    build_judge_prompt,
    classify_question,
    judge_questions,
)


def _q(id_, intended, text="Šta je proces?", correct="Program u izvršavanju.",
       options=None):
    return {
        "id": id_,
        "solo_level": intended,
        "question_text": text,
        "options": options or [correct, "Datoteka.", "Korisnik.", "Resurs."],
        "correct_answer": correct,
    }


def _fake_llm(level, *, confidence=0.9, reasoning="Mock reasoning."):
    """Return an llm_caller stub that always replies with the given level."""
    payload = json.dumps({"level": level, "confidence": confidence, "reasoning": reasoning})
    return lambda prompt: payload


# -----------------------------------------------------------------------------
# Prompt
# -----------------------------------------------------------------------------

def test_prompt_contains_all_solo_definitions():
    prompt = build_judge_prompt("Šta je proces?", ["A", "B", "C", "D"], "A")
    for lvl in SOLO_LEVELS:
        assert lvl.upper() in prompt


def test_prompt_lists_options_with_letters():
    prompt = build_judge_prompt("Pitanje?", ["alfa", "beta", "gama"], "alfa")
    assert "A. alfa" in prompt
    assert "B. beta" in prompt
    assert "C. gama" in prompt


def test_prompt_handles_dict_options():
    prompt = build_judge_prompt("Pitanje?", [{"text": "alfa"}, {"text": "beta"}], "alfa")
    assert "A. alfa" in prompt
    assert "B. beta" in prompt


# -----------------------------------------------------------------------------
# Parsing
# -----------------------------------------------------------------------------

def test_parse_valid_response():
    raw = '{"level": "relational", "confidence": 0.8, "reasoning": "Connects cause and effect."}'
    p = _parse_judge_response(raw)
    assert p["level"] == "relational"
    assert p["confidence"] == 0.8
    assert p["reasoning"] == "Connects cause and effect."


def test_parse_tolerates_extra_text_around_json():
    raw = 'Sure, here is my classification:\n{"level":"unistructural","confidence":0.9,"reasoning":"x"}\nDone.'
    p = _parse_judge_response(raw)
    assert p["level"] == "unistructural"


def test_parse_rejects_unknown_level():
    raw = '{"level": "memorization", "confidence": 0.9, "reasoning": "x"}'
    assert _parse_judge_response(raw) is None


def test_parse_returns_none_on_garbage():
    assert _parse_judge_response("") is None
    assert _parse_judge_response("not json at all") is None


# -----------------------------------------------------------------------------
# classify_question
# -----------------------------------------------------------------------------

def test_classify_returns_agreement_when_levels_match():
    r = classify_question(_q(1, "unistructural"), llm_caller=_fake_llm("unistructural"))
    assert r["classified_level"] == "unistructural"
    assert r["intended_level"] == "unistructural"
    assert r["agrees"] is True
    assert r["parse_ok"] is True


def test_classify_marks_disagreement():
    r = classify_question(_q(1, "unistructural"), llm_caller=_fake_llm("relational"))
    assert r["agrees"] is False


def test_classify_handles_llm_failure_gracefully():
    r = classify_question(_q(1, "relational"), llm_caller=lambda prompt: None)
    assert r["classified_level"] is None
    assert r["parse_ok"] is False
    assert r["agrees"] is False


def test_classify_handles_invalid_intended_level():
    q = _q(1, "garbage_level")
    r = classify_question(q, llm_caller=_fake_llm("relational"))
    assert r["intended_level"] is None
    assert r["agrees"] is False


# -----------------------------------------------------------------------------
# Cohen's kappa
# -----------------------------------------------------------------------------

def test_kappa_perfect_agreement():
    pairs = [
        {"intended_level": "unistructural", "classified_level": "unistructural"},
        {"intended_level": "relational", "classified_level": "relational"},
        {"intended_level": "multistructural", "classified_level": "multistructural"},
    ]
    assert _cohen_kappa(pairs) == 1.0


def test_kappa_total_disagreement_is_negative_or_zero():
    pairs = [
        {"intended_level": "unistructural", "classified_level": "relational"},
        {"intended_level": "relational", "classified_level": "unistructural"},
    ]
    k = _cohen_kappa(pairs)
    # Random / disagreement → κ should be ≤ 0.
    assert k is not None and k <= 0


def test_kappa_none_when_no_usable_pairs():
    assert _cohen_kappa([]) is None
    pairs = [{"intended_level": None, "classified_level": "unistructural"}]
    assert _cohen_kappa(pairs) is None


# -----------------------------------------------------------------------------
# Confusion matrix + batch
# -----------------------------------------------------------------------------

def test_confusion_matrix_shape_and_counts():
    pairs = [
        {"intended_level": "unistructural", "classified_level": "unistructural"},
        {"intended_level": "unistructural", "classified_level": "relational"},
        {"intended_level": "relational", "classified_level": "relational"},
    ]
    cm = _confusion_matrix(pairs)
    assert set(cm.keys()) == set(SOLO_LEVELS)
    assert cm["unistructural"]["unistructural"] == 1
    assert cm["unistructural"]["relational"] == 1
    assert cm["relational"]["relational"] == 1
    assert cm["multistructural"]["multistructural"] == 0


def test_judge_questions_aggregates_and_reports_kappa():
    qs = [
        _q(1, "unistructural"),
        _q(2, "relational"),
        _q(3, "multistructural"),
    ]
    # Build a caller that returns a different answer per question to exercise
    # both agreement and disagreement.
    answers = iter([
        '{"level": "unistructural", "confidence": 0.9, "reasoning": "x"}',
        '{"level": "unistructural", "confidence": 0.9, "reasoning": "y"}',   # disagree
        '{"level": "multistructural", "confidence": 0.9, "reasoning": "z"}',
    ])
    report = judge_questions(qs, llm_caller=lambda prompt: next(answers))
    assert report["total_questions"] == 3
    assert report["judged_questions"] == 3
    assert report["agreement_count"] == 2
    assert report["accuracy"] is not None
    assert report["cohen_kappa"] is not None
    assert report["confusion_matrix"]["relational"]["unistructural"] == 1


def test_judge_questions_counts_parse_failures():
    qs = [_q(1, "unistructural"), _q(2, "relational")]
    answers = iter([
        '{"level": "unistructural", "confidence": 0.9, "reasoning": "x"}',
        'garbage from the model',
    ])
    report = judge_questions(qs, llm_caller=lambda prompt: next(answers))
    assert report["parse_failures"] == 1
    assert report["judged_questions"] == 1
