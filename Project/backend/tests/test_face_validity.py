"""
Tests for services.quality.face_validity — Considine 2005 / Tarrant 2008 rubric.

LLM rubric scoring is mocked.
"""

import json

from services.quality.face_validity import (
    _CRITERIA,
    _parse_face_ratings,
    assess_face_validity,
    build_face_validity_prompt,
    face_validity_report,
)


def _q(id_=1, correct_index=0):
    return {
        'id': id_,
        'question_text': 'Šta je proces?',
        'options': [
            'Program u izvršavanju.',  # 0 (key)
            'Datoteka u memoriji.',     # 1
            'Korisnik prijavljen.',     # 2
            'Hardverski resurs.',       # 3
        ],
        'correct_option_index': correct_index,
    }


def _good_ratings():
    return {'plausibility': 4, 'representativeness': 5, 'no_giveaways': 5, 'clarity': 5}


def _bad_ratings():
    return {'plausibility': 1, 'representativeness': 1, 'no_giveaways': 2, 'clarity': 3}


def _scripted_response(distractors_block):
    return lambda prompt: json.dumps({'distractors': distractors_block})


# -----------------------------------------------------------------------------
# Prompt + parser
# -----------------------------------------------------------------------------

def test_prompt_marks_key():
    p = build_face_validity_prompt('Stem?', ['a', 'b', 'c', 'd'], correct_index=2)
    assert 'KEY' in p


def test_parse_assigns_ratings_to_distractor_indices():
    raw = json.dumps({'distractors': {
        'B': _good_ratings(),
        'C': _good_ratings(),
        'D': _bad_ratings(),
    }})
    out = _parse_face_ratings(raw, n_options=4, correct_index=0)
    assert set(out.keys()) == {1, 2, 3}
    for c in _CRITERIA:
        assert c in out[1]


def test_parse_skips_the_key_index():
    raw = json.dumps({'distractors': {
        'A': _good_ratings(),  # KEY — should be ignored
        'B': _good_ratings(),
    }})
    out = _parse_face_ratings(raw, n_options=4, correct_index=0)
    assert 0 not in out
    assert 1 in out


def test_parse_clamps_invalid_ratings():
    raw = json.dumps({'distractors': {
        'B': {'plausibility': 99, 'representativeness': 0,
              'no_giveaways': 3, 'clarity': 4},
    }})
    out = _parse_face_ratings(raw, n_options=4, correct_index=0)
    # 99 and 0 are out of [1,5] → distractor B has incomplete ratings → dropped.
    assert out is None


def test_parse_returns_none_on_garbage():
    assert _parse_face_ratings('not json', 4, 0) is None
    assert _parse_face_ratings('', 4, 0) is None


# -----------------------------------------------------------------------------
# Single question
# -----------------------------------------------------------------------------

def test_assess_returns_score_and_per_distractor():
    r = assess_face_validity(
        _q(),
        llm_caller=_scripted_response({
            'B': _good_ratings(),
            'C': _good_ratings(),
            'D': _good_ratings(),
        }),
    )
    assert r['available'] is True
    assert r['face_validity_score'] > 4
    assert len(r['distractor_ratings']) == 3
    for d in r['distractor_ratings']:
        assert 'plausibility' in d['ratings']


def test_low_scoring_distractor_pulls_average_down():
    r = assess_face_validity(
        _q(),
        llm_caller=_scripted_response({
            'B': _good_ratings(),
            'C': _good_ratings(),
            'D': _bad_ratings(),
        }),
    )
    assert r['face_validity_score'] < 4.5


def test_missing_key_returns_unavailable():
    q = _q()
    q['correct_option_index'] = None
    r = assess_face_validity(q, llm_caller=_scripted_response({'B': _good_ratings()}))
    assert r['available'] is False


def test_llm_failure_marks_unavailable():
    r = assess_face_validity(_q(), llm_caller=lambda p: 'garbage')
    assert r['available'] is False


# -----------------------------------------------------------------------------
# Batch + criterion aggregation
# -----------------------------------------------------------------------------

def test_batch_aggregates_criterion_means():
    qs = [_q(1), _q(2)]
    responses = iter([
        json.dumps({'distractors': {
            'B': _good_ratings(), 'C': _good_ratings(), 'D': _good_ratings(),
        }}),
        json.dumps({'distractors': {
            'B': _bad_ratings(), 'C': _bad_ratings(), 'D': _bad_ratings(),
        }}),
    ])
    r = face_validity_report(qs, llm_caller=lambda p: next(responses))
    assert r['evaluated_questions'] == 2
    assert r['mean_face_validity_score'] is not None
    for c in _CRITERIA:
        assert r['criterion_means'][c] is not None
