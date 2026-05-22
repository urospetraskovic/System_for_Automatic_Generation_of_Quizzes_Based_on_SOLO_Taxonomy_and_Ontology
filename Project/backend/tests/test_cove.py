"""
Tests for services.cove — Chain-of-Verification for MCQ correctness.

CoVe orchestrates 3 LLM calls per question (plan → verify ×N → judge).
We mock the LLM caller so tests are fast and deterministic.
"""

import json

from services.cove import (
    _parse_json,
    build_judge_prompt,
    build_plan_prompt,
    build_verify_prompt,
    verify_question,
    verify_questions,
)


def _q(id_=1, text='Šta je proces?', correct='Program u izvršavanju.', source='Proces je program u izvršavanju.'):
    return {
        'id': id_,
        'question_text': text,
        'correct_answer': correct,
        'source_line': source,
    }


def _scripted_llm(responses):
    """Return a caller that yields the given responses in order.
    Each response is a dict; it gets JSON-encoded before being returned."""
    it = iter(responses)
    return lambda prompt: json.dumps(next(it))


# -----------------------------------------------------------------------------
# Prompt builders
# -----------------------------------------------------------------------------

def test_plan_prompt_contains_question_and_answer():
    p = build_plan_prompt('Šta je X?', 'A')
    assert 'Šta je X?' in p
    assert 'A' in p
    assert 'verification_questions' in p


def test_verify_prompt_carries_source_and_question():
    p = build_verify_prompt('What does X do?', 'Source about X.')
    assert 'What does X do?' in p
    assert 'Source about X.' in p
    assert 'supported_by_source' in p


def test_judge_prompt_lists_verification_qa():
    qa = [
        {'question': 'Q1?', 'answer': 'A1', 'supported_by_source': True},
        {'question': 'Q2?', 'answer': 'A2', 'supported_by_source': False},
    ]
    p = build_judge_prompt('Stem?', 'Key', qa)
    assert 'Q1?' in p
    assert 'A1' in p
    assert 'supported_by_source=True' in p
    assert 'supported_by_source=False' in p


# -----------------------------------------------------------------------------
# Parser
# -----------------------------------------------------------------------------

def test_parse_extracts_json_from_messy_output():
    raw = 'Here is my answer: {"verdict": "SUPPORTED", "confidence": 0.9, "reasoning": "x"} done.'
    p = _parse_json(raw)
    assert p['verdict'] == 'SUPPORTED'


def test_parse_returns_none_on_garbage():
    assert _parse_json('') is None
    assert _parse_json('no json here') is None


# -----------------------------------------------------------------------------
# verify_question — full pipeline with mocked LLM
# -----------------------------------------------------------------------------

def test_verify_question_supported_path():
    """All verification answers supported → SUPPORTED verdict, no review needed."""
    caller = _scripted_llm([
        {'verification_questions': ['Q1?', 'Q2?']},
        {'answer': 'A1', 'supported_by_source': True},
        {'answer': 'A2', 'supported_by_source': True},
        {'verdict': 'SUPPORTED', 'confidence': 0.95, 'reasoning': 'All checks passed.'},
    ])
    r = verify_question(_q(), llm_caller=caller)
    assert r['verdict'] == 'SUPPORTED'
    assert r['needs_review'] is False
    assert len(r['verification_trace']) == 2


def test_verify_question_underdetermined_triggers_review():
    caller = _scripted_llm([
        {'verification_questions': ['Q1?']},
        {'answer': 'NOT IN SOURCE', 'supported_by_source': False},
        {'verdict': 'UNDERDETERMINED', 'confidence': 0.6, 'reasoning': 'Source ambiguous.'},
    ])
    r = verify_question(_q(), llm_caller=caller)
    assert r['verdict'] == 'UNDERDETERMINED'
    assert r['needs_review'] is True


def test_verify_question_contradicted_triggers_review():
    caller = _scripted_llm([
        {'verification_questions': ['Q1?']},
        {'answer': 'Different answer.', 'supported_by_source': True},
        {'verdict': 'CONTRADICTED', 'confidence': 0.85, 'reasoning': 'Source says otherwise.'},
    ])
    r = verify_question(_q(), llm_caller=caller)
    assert r['verdict'] == 'CONTRADICTED'
    assert r['needs_review'] is True


def test_verify_question_handles_missing_fields():
    r = verify_question({'id': 1, 'question_text': '', 'correct_answer': ''}, llm_caller=lambda p: '{}')
    assert r['needs_review'] is True
    assert r['verdict'] is None
    assert 'Missing' in r['reason']


def test_verify_question_handles_planner_failure():
    """Planner returns no verification questions → review needed, no further calls."""
    caller = _scripted_llm([{'verification_questions': []}])
    r = verify_question(_q(), llm_caller=caller)
    assert r['needs_review'] is True
    assert r['verdict'] is None


def test_verify_question_caps_verification_at_three():
    caller = _scripted_llm([
        {'verification_questions': ['Q1', 'Q2', 'Q3', 'Q4', 'Q5']},
        {'answer': 'a', 'supported_by_source': True},
        {'answer': 'b', 'supported_by_source': True},
        {'answer': 'c', 'supported_by_source': True},
        {'verdict': 'SUPPORTED', 'confidence': 0.9, 'reasoning': 'ok'},
    ])
    r = verify_question(_q(), llm_caller=caller)
    assert len(r['verification_trace']) == 3


# -----------------------------------------------------------------------------
# Batch
# -----------------------------------------------------------------------------

def test_verify_questions_aggregates_verdicts():
    # Two questions: one SUPPORTED, one CONTRADICTED.
    responses = [
        # Q1
        {'verification_questions': ['v1']},
        {'answer': 'a', 'supported_by_source': True},
        {'verdict': 'SUPPORTED', 'confidence': 0.9, 'reasoning': 'x'},
        # Q2
        {'verification_questions': ['v2']},
        {'answer': 'b', 'supported_by_source': False},
        {'verdict': 'CONTRADICTED', 'confidence': 0.8, 'reasoning': 'y'},
    ]
    caller = _scripted_llm(responses)
    report = verify_questions([_q(1), _q(2)], llm_caller=caller)
    assert report['total_questions'] == 2
    assert report['supported'] == 1
    assert report['contradicted'] == 1
    assert report['needs_review'] == 1
    assert report['support_rate'] == 50.0
