"""
Tests for services.quality.ambiguity — linguistic ambiguity detection.

Mocks the LLM via an injected llm_caller.
"""

import json

from services.quality.ambiguity import (
    VALID_AMBIGUITY_TYPES,
    _parse,
    ambiguity_report,
    assess_ambiguity,
    build_ambiguity_prompt,
)


def _q(id_=1, text='Šta je proces?'):
    return {
        'id': id_,
        'question_text': text,
        'options': ['A', 'B', 'C', 'D'],
    }


def _scripted(payload):
    return lambda prompt: json.dumps(payload)


def test_prompt_lists_options():
    p = build_ambiguity_prompt('Stem?', ['alpha', 'beta'])
    assert 'A. alpha' in p
    assert 'B. beta' in p
    assert 'ambiguous' in p


def test_parse_valid_payload():
    raw = json.dumps({
        'ambiguous': True,
        'interpretations': ['reading 1', 'reading 2'],
        'ambiguity_type': 'lexical',
        'reasoning': 'x',
    })
    p = _parse(raw)
    assert p['ambiguous'] is True
    assert len(p['interpretations']) == 2
    assert p['ambiguity_type'] == 'lexical'


def test_parse_unknown_ambiguity_type_falls_back_to_none():
    raw = json.dumps({
        'ambiguous': False,
        'interpretations': [],
        'ambiguity_type': 'pragmatic',  # not in our closed list
    })
    p = _parse(raw)
    assert p['ambiguity_type'] == 'none'


def test_parse_rejects_missing_ambiguous_flag():
    raw = json.dumps({'interpretations': []})
    assert _parse(raw) is None


def test_parse_returns_none_on_garbage():
    assert _parse('') is None
    assert _parse('not json') is None


def test_assess_marks_clear_question():
    r = assess_ambiguity(_q(), llm_caller=_scripted({
        'ambiguous': False,
        'interpretations': [],
        'ambiguity_type': 'none',
        'reasoning': 'clear',
    }))
    assert r['available'] is True
    assert r['ambiguous'] is False


def test_assess_flags_ambiguous_question():
    r = assess_ambiguity(_q(), llm_caller=_scripted({
        'ambiguous': True,
        'interpretations': ['Reading 1', 'Reading 2'],
        'ambiguity_type': 'referential',
        'reasoning': 'pronoun ambiguous',
    }))
    assert r['ambiguous'] is True
    assert r['ambiguity_type'] == 'referential'


def test_assess_corrects_inconsistent_response():
    """If the LLM says 'ambiguous=true' but gives <2 interpretations, treat as not ambiguous."""
    r = assess_ambiguity(_q(), llm_caller=_scripted({
        'ambiguous': True,
        'interpretations': ['only one reading'],
        'ambiguity_type': 'lexical',
        'reasoning': 'inconsistent',
    }))
    assert r['ambiguous'] is False
    assert r['ambiguity_type'] == 'none'


def test_report_aggregates_rate():
    qs = [_q(1), _q(2), _q(3)]
    responses = iter([
        json.dumps({'ambiguous': True, 'interpretations': ['a', 'b'],
                    'ambiguity_type': 'lexical', 'reasoning': 'x'}),
        json.dumps({'ambiguous': False, 'interpretations': [],
                    'ambiguity_type': 'none', 'reasoning': 'x'}),
        json.dumps({'ambiguous': False, 'interpretations': [],
                    'ambiguity_type': 'none', 'reasoning': 'x'}),
    ])
    r = ambiguity_report(qs, llm_caller=lambda p: next(responses))
    assert r['ambiguous_count'] == 1
    assert r['ambiguity_rate'] == round(100/3, 1)
    assert r['type_distribution']['lexical'] == 1


def test_valid_ambiguity_types_includes_none():
    assert 'none' in VALID_AMBIGUITY_TYPES
