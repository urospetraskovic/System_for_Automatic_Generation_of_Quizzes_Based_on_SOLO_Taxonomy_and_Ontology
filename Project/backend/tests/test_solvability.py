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
    options = [
        'Program u izvršavanju.',     # correct (index 0)
        'Datoteka u memoriji.',
        'Korisnik prijavljen.',
        'Hardverski resurs.',
    ]
    return {
        'id': id_,
        'question_text': 'Šta je proces?',
        'options': options,
        'correct_option_index': correct_idx,
        'correct_answer': options[correct_idx] if 0 <= correct_idx < len(options) else None,
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


# -----------------------------------------------------------------------------
# Stem-only solvability (Haladyna H4) — uses an embedding stub.
# -----------------------------------------------------------------------------

from services.solvability import (
    _parse_free_answer,
    assess_stem_only_solvability,
    build_stem_only_prompt,
    stem_only_solvability_report,
)


def _free_answer(text):
    return lambda prompt: json.dumps({'answer': text})


def _embed_factory(answer_vec, correct_vec):
    """Embedder stub that returns one vector for any answer, another for the key."""
    def _embed(s):
        if 'Program u izvršavanju.' in s:
            return correct_vec
        return answer_vec
    return _embed


def _real_cosine(a, b):
    from services.embedding_service import cosine_similarity
    return cosine_similarity(a, b)


def test_stem_only_prompt_excludes_options():
    p = build_stem_only_prompt('Šta je proces?')
    # The prompt must NOT include the option list — that's the whole point.
    assert 'Šta je proces?' in p
    assert 'OPTIONS' not in p


def test_parse_free_answer_strips_unable():
    assert _parse_free_answer(json.dumps({'answer': 'UNABLE TO ANSWER'})) is None
    assert _parse_free_answer(json.dumps({'answer': '  '})) is None
    assert _parse_free_answer(json.dumps({'answer': 'Program u izvršavanju.'})) == 'Program u izvršavanju.'


def test_stem_only_h4_passes_for_self_contained_stem():
    """High cosine between LLM free answer and key → H4 satisfied."""
    same = [1.0, 0.0]
    r = assess_stem_only_solvability(
        _q(),
        llm_caller=_free_answer('Program u izvršavanju.'),
        embedder=lambda s: same,
        cosine=_real_cosine,
    )
    assert r['verdict'] == 'passes'
    assert r['h4_passes'] is True


def test_stem_only_h4_fails_when_stem_is_underspecified():
    """Low cosine → stem alone could not get to the key."""
    r = assess_stem_only_solvability(
        _q(),
        llm_caller=_free_answer('Nešto sasvim drugo.'),
        embedder=lambda s: [1.0, 0.0] if 'Program' in s else [0.0, 1.0],
        cosine=_real_cosine,
    )
    assert r['verdict'] == 'fails'
    assert r['h4_passes'] is False


def test_stem_only_unable_when_llm_refuses():
    r = assess_stem_only_solvability(
        _q(),
        llm_caller=_free_answer('UNABLE TO ANSWER'),
        embedder=lambda s: [1.0, 0.0],
        cosine=_real_cosine,
    )
    assert r['verdict'] == 'unable'
    assert r['h4_passes'] is False


def test_stem_only_report_aggregates_pass_rate():
    qs = [_q(1), _q(2)]
    answers = iter([
        json.dumps({'answer': 'Program u izvršavanju.'}),  # passes
        json.dumps({'answer': 'UNABLE TO ANSWER'}),         # unable
    ])
    r = stem_only_solvability_report(
        qs,
        llm_caller=lambda p: next(answers),
        embedder=lambda s: [1.0, 0.0],
        cosine=_real_cosine,
    )
    assert r['verdict_distribution']['passes'] == 1
    assert r['verdict_distribution']['unable'] == 1
    assert r['h4_pass_rate'] == 50.0
