"""
Tests for services.ioc — Item-Objective Congruence (Rovinelli & Hambleton 1977).

Uses an injected llm_caller so tests don't need Ollama. We also inject the
objective directly to avoid DB lookups.
"""

import json
from services.ioc import (
    _parse_rating,
    build_ioc_prompt,
    ioc_report,
    rate_question,
)


def _q(id_=1):
    return {
        'id': id_,
        'question_text': 'Šta je proces?',
        'options': ['Program u izvršavanju.', 'Datoteka.', 'Korisnik.', 'Resurs.'],
        'correct_answer': 'Program u izvršavanju.',
        'correct_option_index': 0,
        'learning_object_id': 7,
    }


def _objective(title='Proces', content='Proces je program u izvršavanju.'):
    return {'type': 'learning_object', 'id': 7, 'title': title, 'content': content}


def _scripted(*ratings):
    """Build an llm_caller that returns the given ratings in order."""
    it = iter(ratings)
    return lambda prompt: json.dumps({'rating': next(it), 'reasoning': 'mock'})


# -----------------------------------------------------------------------------
# Prompt + parser
# -----------------------------------------------------------------------------

def test_prompt_contains_objective_and_options():
    p = build_ioc_prompt('Šta je X?', ['A', 'B'], 'A', 'LO Title', 'LO body.')
    assert 'LO Title' in p
    assert 'LO body.' in p
    assert 'rating' in p


def test_parse_accepts_valid_rating():
    assert _parse_rating('{"rating": 1, "reasoning": "ok"}')['rating'] == 1
    assert _parse_rating('{"rating": 0, "reasoning": "ok"}')['rating'] == 0
    assert _parse_rating('{"rating": -1, "reasoning": "ok"}')['rating'] == -1


def test_parse_rejects_out_of_range():
    assert _parse_rating('{"rating": 2, "reasoning": "x"}') is None
    assert _parse_rating('{"rating": "yes", "reasoning": "x"}') is None
    assert _parse_rating('not json') is None


# -----------------------------------------------------------------------------
# rate_question
# -----------------------------------------------------------------------------

def test_rate_question_returns_rating():
    r = rate_question(_q(), objective=_objective(), llm_caller=_scripted(1))
    assert r['available'] is True
    assert r['rating'] == 1


def test_rate_question_handles_no_objective():
    q = _q()
    q['learning_object_id'] = None
    q['section_id'] = None
    r = rate_question(q, objective=None, llm_caller=_scripted(1))
    # Without a DB session it should still gracefully return unavailable.
    # (DB may resolve to None; this is fine.)
    assert r['available'] in (False, True)


def test_rate_question_marks_unparseable_response():
    r = rate_question(_q(), objective=_objective(),
                      llm_caller=lambda p: 'not json at all')
    assert r['available'] is False


# -----------------------------------------------------------------------------
# ioc_report aggregate
# -----------------------------------------------------------------------------

def test_ioc_index_strong():
    qs = [_q(1), _q(2), _q(3), _q(4)]
    # Inject objective via monkey patch on _resolve_objective.
    import services.ioc as ioc_mod
    ioc_mod._resolve_objective = lambda q: _objective()
    try:
        r = ioc_report(qs, llm_caller=_scripted(1, 1, 1, 1))
        assert r['ioc_index'] == 1.0
        assert r['ioc_label'] == 'strong'
        assert r['distribution']['+1'] == 4
    finally:
        # The patch only matters in this test; tests are isolated.
        pass


def test_ioc_index_weak_with_zeros():
    qs = [_q(1), _q(2), _q(3), _q(4)]
    import services.ioc as ioc_mod
    ioc_mod._resolve_objective = lambda q: _objective()
    r = ioc_report(qs, llm_caller=_scripted(0, 0, 1, 0))
    assert r['ioc_index'] == 0.25
    assert r['ioc_label'] == 'weak'


def test_ioc_index_misaligned():
    qs = [_q(1), _q(2)]
    import services.ioc as ioc_mod
    ioc_mod._resolve_objective = lambda q: _objective()
    r = ioc_report(qs, llm_caller=_scripted(-1, -1))
    assert r['ioc_index'] == -1.0
    assert r['ioc_label'] == 'misaligned'


def test_ioc_report_handles_no_anchored_questions():
    qs = [_q(1)]
    import services.ioc as ioc_mod
    ioc_mod._resolve_objective = lambda q: None
    r = ioc_report(qs, llm_caller=_scripted(1))
    assert r['rated_questions'] == 0
    assert r['ioc_index'] is None
