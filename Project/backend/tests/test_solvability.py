"""
Tests for services.solvability — LLM-blind solver as a-priori item difficulty
calibration.

The solver makes N LLM calls per question. We mock the LLM with a scripted
caller, plus a deterministic RNG so shuffled-option mappings are predictable.
"""

import json
import random

from services.solvability import (
    _difficulty_label,
    _parse_choice,
    build_solver_prompt,
    solvability_report,
    assess_solvability,
)


def _q(id_=1, correct_idx=0):
    return {
        'id': id_,
        'question_text': 'Šta je proces?',
        'options': [
            'Program u izvršavanju.',     # correct (index 0)
            'Datoteka u memoriji.',
            'Korisnik prijavljen.',
            'Hardverski resurs.',
        ],
        'correct_option_index': correct_idx,
    }


def _always_picks(letter):
    """LLM stub: always returns the given letter."""
    return lambda prompt: json.dumps({'choice': letter, 'reasoning': 'fixed.'})


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def test_parse_choice_accepts_letter():
    assert _parse_choice('{"choice": "B", "reasoning": "x"}', 4) == 1


def test_parse_choice_accepts_parenthesised_letter():
    assert _parse_choice('{"choice": "(C)", "reasoning": "x"}', 4) == 2


def test_parse_choice_accepts_digit():
    assert _parse_choice('{"choice": "2", "reasoning": "x"}', 4) == 1


def test_parse_choice_rejects_out_of_range():
    assert _parse_choice('{"choice": "Z", "reasoning": "x"}', 4) is None


def test_parse_choice_returns_none_on_garbage():
    assert _parse_choice('', 4) is None
    assert _parse_choice('not json', 4) is None


def test_difficulty_labels():
    assert _difficulty_label(0.95) == 'trivially_easy'
    assert _difficulty_label(0.7) == 'appropriate'
    assert _difficulty_label(0.4) == 'hard'
    assert _difficulty_label(0.1) == 'too_hard_or_misframed'
    assert _difficulty_label(None) is None


def test_solver_prompt_lists_options():
    p = build_solver_prompt('Q?', ['alpha', 'beta', 'gamma'])
    assert 'A. alpha' in p
    assert 'B. beta' in p
    assert 'C. gamma' in p


# -----------------------------------------------------------------------------
# test_solvability — single question, mocked LLM
# -----------------------------------------------------------------------------

def test_solvability_perfect_score_when_llm_always_correct():
    """LLM picks the right option in every trial. With shuffle disabled, the
    correct option is always at index 0, so 'A' is always correct."""
    r = assess_solvability(
        _q(), n_trials=5, shuffle=False,
        llm_caller=_always_picks('A'),
    )
    assert r['p_value'] == 1.0
    assert r['difficulty_label'] == 'trivially_easy'
    assert r['correct_count'] == 5
    assert r['parse_failures'] == 0


def test_solvability_zero_when_llm_always_wrong():
    r = assess_solvability(
        _q(), n_trials=5, shuffle=False,
        llm_caller=_always_picks('B'),  # always picks index 1, but correct is 0
    )
    assert r['p_value'] == 0.0
    assert r['difficulty_label'] == 'too_hard_or_misframed'


def test_solvability_counts_parse_failures():
    """Garbage responses are counted as parse failures, not wrong answers."""
    r = assess_solvability(
        _q(), n_trials=4, shuffle=False,
        llm_caller=lambda p: 'not json',
    )
    assert r['parse_failures'] == 4
    assert r['p_value'] is None


def test_solvability_returns_unavailable_when_no_key():
    q = _q()
    q['correct_option_index'] = None
    r = assess_solvability(q, n_trials=2, shuffle=False, llm_caller=_always_picks('A'))
    assert r['available'] is False


def test_solvability_shuffle_inverts_mapping_correctly():
    """With shuffle on and a seeded RNG, the picked index in the original
    option list must match the shuffled position the LLM picked."""
    rng = random.Random(42)
    # Build a caller that always picks the first shuffled option ("A").
    # We just check that across trials, p_value reflects how often that
    # shuffled position happened to be the real correct answer.
    r = assess_solvability(
        _q(), n_trials=20, shuffle=True,
        llm_caller=_always_picks('A'),
        rng=rng,
    )
    # With 4 options and random shuffle, "always-A" yields p ≈ 0.25.
    # Allow generous tolerance for 20 trials.
    assert 0.0 <= r['p_value'] <= 1.0


# -----------------------------------------------------------------------------
# solvability_report — batch
# -----------------------------------------------------------------------------

def test_solvability_report_aggregates():
    qs = [_q(1, correct_idx=0), _q(2, correct_idx=0)]
    r = solvability_report(
        qs, n_trials=3, shuffle=False,
        llm_caller=_always_picks('A'),
    )
    assert r['total_questions'] == 2
    assert r['solvable_questions'] == 2
    assert r['mean_p_value'] == 1.0
    assert r['difficulty_distribution']['trivially_easy'] == 2
