"""
Tests for services.self_consistency — best-of-N MCQ selection.

The selector is a pure function of (candidates, lint score), so tests run
without Ollama. We feed in synthetic candidates with known quality.
"""

from services.self_consistency import (
    generate_with_self_consistency,
    pick_best_question,
    score_candidate,
)


def _clean_q(id_=1):
    return {
        'id': id_,
        'question_text': 'Šta je proces?',
        'options': [
            'Program u izvršavanju.',
            'Datoteka u memoriji.',
            'Korisnik prijavljen.',
            'Hardverski resurs.',
        ],
        'correct_option_index': 0,
        'correct_answer': 'Program u izvršavanju.',
    }


def _messy_q(id_=2):
    """Candidate with multiple Haladyna violations → low score."""
    return {
        'id': id_,
        'question_text': '',  # H14_NO_STEM (error)
        'options': ['', 'b', 'c'],  # H_BLANK (error) + H_OPTION_COUNT
        'correct_option_index': 0,
        'correct_answer': '',
    }


# -----------------------------------------------------------------------------
# score_candidate
# -----------------------------------------------------------------------------

def test_score_higher_for_clean_than_messy():
    s_clean = score_candidate(_clean_q(), use_embeddings=False)
    s_messy = score_candidate(_messy_q(), use_embeddings=False)
    assert s_clean['score'] > s_messy['score']


def test_score_returns_lint_report_for_audit():
    s = score_candidate(_clean_q(), use_embeddings=False)
    assert 'lint_report' in s
    assert 'lint_score' in s
    assert 'bonus' in s


def test_score_penalises_bad_plausibility():
    """A candidate where every distractor is identical to the key (mean_plausibility = 1.0)
    is OUT of the [0.4, 0.92] range → -10 bonus."""
    q = _clean_q()
    same_vec = [1.0, 0.0]
    embedder = lambda t: same_vec  # every text → same vector → cos = 1.0
    from services.embedding_service import cosine_similarity
    s_with_embed = score_candidate(
        q, embedder=embedder, cosine=cosine_similarity, use_embeddings=True,
    )
    s_no_embed = score_candidate(q, use_embeddings=False)
    assert s_with_embed['bonus'] < s_no_embed['bonus']


# -----------------------------------------------------------------------------
# pick_best_question
# -----------------------------------------------------------------------------

def test_pick_best_chooses_clean_over_messy():
    best, scored = pick_best_question(
        [_messy_q(1), _clean_q(2), _messy_q(3)],
        use_embeddings=False,
    )
    assert best['id'] == 2
    assert len(scored) == 3


def test_pick_best_handles_empty_list():
    best, scored = pick_best_question([], use_embeddings=False)
    assert best is None
    assert scored == []


def test_pick_best_breaks_ties_deterministically():
    """Two identical candidates → first one wins (no flakiness)."""
    a = _clean_q(1)
    b = _clean_q(2)
    best, _ = pick_best_question([a, b], use_embeddings=False)
    # `max` keeps the first occurrence of the max; assert that semantics.
    assert best['id'] == 1


# -----------------------------------------------------------------------------
# generate_with_self_consistency
# -----------------------------------------------------------------------------

def test_self_consistency_calls_generator_n_times():
    calls = []

    def gen():
        calls.append(1)
        return _clean_q(id_=len(calls))

    result = generate_with_self_consistency(gen, n=3, use_embeddings=False)
    assert len(calls) == 3
    assert result['attempted'] == 3
    assert result['requested'] == 3


def test_self_consistency_skips_none_generations():
    """If the generator returns None on some attempts, only successful candidates count."""
    yields = iter([None, _clean_q(1), None, _clean_q(2)])
    result = generate_with_self_consistency(
        lambda: next(yields), n=4, use_embeddings=False,
    )
    assert result['attempted'] == 2
    assert result['requested'] == 4
    assert result['best'] is not None


def test_self_consistency_picks_best_across_attempts():
    yields = iter([_messy_q(1), _clean_q(2), _messy_q(3)])
    result = generate_with_self_consistency(
        lambda: next(yields), n=3, use_embeddings=False,
    )
    assert result['best']['id'] == 2
    assert len(result['scores']) == 3


def test_self_consistency_audit_does_not_duplicate_candidate():
    """Audit log should not embed the full candidate (caller already has `best`)."""
    yields = iter([_clean_q(1), _clean_q(2)])
    result = generate_with_self_consistency(
        lambda: next(yields), n=2, use_embeddings=False,
    )
    for entry in result['audit']:
        assert 'candidate' not in entry
        assert 'score' in entry
        assert 'lint_score' in entry


# -----------------------------------------------------------------------------
# Ambiguity integration (Option D — Downing 2005) — 5-point penalty.
# -----------------------------------------------------------------------------

import json


def _ambig_caller(verdict):
    """Stub llm_caller that always returns the given ambiguity verdict.

    `verdict` is a dict like {'ambiguous': True, 'interpretations': [..], ...}
    """
    return lambda prompt: json.dumps(verdict)


def test_ambiguity_penalty_off_by_default():
    """Without check_ambiguity=True, score is unchanged and no ambiguity_report."""
    s = score_candidate(_clean_q(), use_embeddings=False)
    assert 'ambiguity_report' not in s


def test_ambiguity_flag_subtracts_five_points():
    base_score = score_candidate(_clean_q(), use_embeddings=False)['score']
    flagged = score_candidate(
        _clean_q(),
        use_embeddings=False,
        check_ambiguity=True,
        ambiguity_caller=_ambig_caller({
            'ambiguous': True,
            'interpretations': ['reading 1', 'reading 2'],
            'ambiguity_type': 'lexical',
            'reasoning': 'unclear key term',
        }),
    )
    assert flagged['score'] == max(0, base_score - 5)
    assert flagged['ambiguity_report']['ambiguous'] is True


def test_non_ambiguous_candidate_keeps_score():
    base_score = score_candidate(_clean_q(), use_embeddings=False)['score']
    clean = score_candidate(
        _clean_q(),
        use_embeddings=False,
        check_ambiguity=True,
        ambiguity_caller=_ambig_caller({
            'ambiguous': False,
            'interpretations': [],
            'ambiguity_type': 'none',
            'reasoning': 'clear',
        }),
    )
    assert clean['score'] == base_score
    assert clean['ambiguity_report']['ambiguous'] is False


def test_pick_best_prefers_non_ambiguous():
    """With two equally-clean lint candidates, the non-ambiguous one wins."""
    # Build an ambiguity caller that returns different verdicts per question id.
    def caller(prompt):
        # Heuristic: candidate id 1 is ambiguous, id 2 is not. We sniff the
        # question text in the prompt — the helper happens to use the same
        # stem for both, so we differentiate via call order instead.
        caller.calls = getattr(caller, 'calls', 0) + 1
        if caller.calls == 1:
            return json.dumps({
                'ambiguous': True,
                'interpretations': ['r1', 'r2'],
                'ambiguity_type': 'referential',
                'reasoning': 'x',
            })
        return json.dumps({
            'ambiguous': False,
            'interpretations': [],
            'ambiguity_type': 'none',
            'reasoning': 'clear',
        })

    best, scored = pick_best_question(
        [_clean_q(1), _clean_q(2)],
        use_embeddings=False,
        check_ambiguity=True,
        ambiguity_caller=caller,
    )
    assert best['id'] == 2
    assert scored[0]['score'] < scored[1]['score']


def test_ambiguity_unavailable_does_not_penalise():
    """If the LLM judge fails to parse, no penalty is applied (graceful)."""
    base_score = score_candidate(_clean_q(), use_embeddings=False)['score']
    s = score_candidate(
        _clean_q(),
        use_embeddings=False,
        check_ambiguity=True,
        ambiguity_caller=lambda p: 'unparseable garbage',
    )
    assert s['score'] == base_score
    # available=False → no penalty
    assert s['ambiguity_report']['available'] is False
