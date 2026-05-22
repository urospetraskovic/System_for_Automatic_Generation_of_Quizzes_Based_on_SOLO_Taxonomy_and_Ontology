"""
Tests for services.grammar_homogeneity — Haladyna O7 / Tarrant 2009.

LLM classification is mocked.
"""

import json

from services.grammar_homogeneity import (
    STRUCTURAL_TYPES,
    _parse_types,
    build_grammar_prompt,
    check_homogeneity,
    homogeneity_report,
)


def _q(id_=1, options=None, correct_index=0):
    return {
        'id': id_,
        'question_text': 'Šta je proces?',
        'options': options or [
            'Program u izvršavanju.',
            'Datoteka.',
            'Korisnik.',
            'Resurs.',
        ],
        'correct_option_index': correct_index,
    }


def _scripted(types_list):
    """Return a fake llm_caller that yields the given type list once."""
    return lambda prompt: json.dumps({'types': types_list})


# -----------------------------------------------------------------------------
# Parser
# -----------------------------------------------------------------------------

def test_parse_returns_normalised_types():
    raw = json.dumps({'types': ['noun_phrase', 'verb_phrase', 'noun_phrase', 'noun_phrase']})
    out = _parse_types(raw, num_options=4)
    assert out == ['noun_phrase', 'verb_phrase', 'noun_phrase', 'noun_phrase']


def test_parse_falls_back_to_other_for_invalid_type():
    raw = json.dumps({'types': ['noun_phrase', 'unicorn_phrase', 'noun_phrase', 'noun_phrase']})
    out = _parse_types(raw, num_options=4)
    assert out[1] == 'other'


def test_parse_pads_short_response():
    raw = json.dumps({'types': ['noun_phrase', 'noun_phrase']})
    out = _parse_types(raw, num_options=4)
    assert len(out) == 4
    assert out[2] == 'other'
    assert out[3] == 'other'


def test_parse_returns_none_on_garbage():
    assert _parse_types('not json', 4) is None
    assert _parse_types('', 4) is None


# -----------------------------------------------------------------------------
# Verdicts
# -----------------------------------------------------------------------------

def test_homogeneous_when_all_same_type():
    r = check_homogeneity(_q(), llm_caller=_scripted(['noun_phrase'] * 4))
    assert r['verdict'] == 'homogeneous'
    assert r['homogeneous'] is True
    assert r['outlier_indices'] == []


def test_single_outlier_detected():
    r = check_homogeneity(_q(), llm_caller=_scripted([
        'noun_phrase', 'noun_phrase', 'verb_phrase', 'noun_phrase',
    ]))
    assert r['verdict'] == 'single_outlier'
    assert r['outlier_indices'] == [2]


def test_mixed_when_multiple_minority():
    r = check_homogeneity(_q(), llm_caller=_scripted([
        'noun_phrase', 'verb_phrase', 'noun_phrase', 'adjective_phrase',
    ]))
    assert r['verdict'] == 'mixed'
    assert len(r['outlier_indices']) >= 2


def test_flag_when_correct_is_outlier():
    """If the KEY is the structural odd one out, that is a give-away clue."""
    r = check_homogeneity(_q(correct_index=2), llm_caller=_scripted([
        'noun_phrase', 'noun_phrase', 'verb_phrase', 'noun_phrase',
    ]))
    assert r['correct_is_outlier'] is True


def test_llm_failure_marks_unavailable():
    r = check_homogeneity(_q(), llm_caller=lambda p: 'not json')
    assert r['available'] is False


def test_empty_options_unavailable():
    r = check_homogeneity({'id': 1, 'options': []}, llm_caller=_scripted([]))
    assert r['available'] is False


# -----------------------------------------------------------------------------
# Batch + sanity
# -----------------------------------------------------------------------------

def test_report_aggregates_distribution():
    qs = [_q(1), _q(2)]
    answers = iter([
        json.dumps({'types': ['noun_phrase'] * 4}),
        json.dumps({'types': ['noun_phrase', 'verb_phrase', 'noun_phrase', 'noun_phrase']}),
    ])
    r = homogeneity_report(qs, llm_caller=lambda p: next(answers))
    assert r['total_questions'] == 2
    assert r['verdict_distribution']['homogeneous'] == 1
    assert r['verdict_distribution']['single_outlier'] == 1


def test_structural_types_include_common_categories():
    assert 'noun_phrase' in STRUCTURAL_TYPES
    assert 'verb_phrase' in STRUCTURAL_TYPES
    assert 'other' in STRUCTURAL_TYPES


def test_prompt_lists_all_options_and_types():
    p = build_grammar_prompt(['alpha', 'beta'])
    assert 'A. alpha' in p
    assert 'B. beta' in p
    assert 'noun_phrase' in p
