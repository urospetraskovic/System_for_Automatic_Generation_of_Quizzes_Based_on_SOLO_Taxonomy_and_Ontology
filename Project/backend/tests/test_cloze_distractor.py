"""
Tests for services.cloze_distractor — Aldabe 2009 sibling-concept extraction.

Pure-Python module; no LLM dependency.
"""

from services.cloze_distractor import (
    _is_near_duplicate,
    _normalise,
    format_pool_for_prompt,
    gather_sibling_concepts,
    suggest_cloze_distractors,
)


def _lo(id_, title, keywords=None):
    return {'id': id_, 'title': title, 'keywords': keywords or []}


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def test_normalise_collapses_whitespace_and_lowercases():
    assert _normalise('  Proces  Sa Više  Niti ') == 'proces sa više niti'


def test_near_duplicate_substring():
    assert _is_near_duplicate('Proces', 'procesi') is True


def test_near_duplicate_token_jaccard():
    """High token overlap should count as near-duplicate."""
    assert _is_near_duplicate('atributi procesa', 'atributi procesa.') is True


def test_not_near_duplicate_for_distinct_concepts():
    assert _is_near_duplicate('Proces', 'Nit') is False


# -----------------------------------------------------------------------------
# gather_sibling_concepts
# -----------------------------------------------------------------------------

def test_section_keywords_rank_first():
    section = [_lo(1, 'Proces', keywords=['PCB', 'stanje procesa'])]
    lesson = [
        _lo(1, 'Proces', keywords=['PCB', 'stanje procesa']),
        _lo(2, 'Mutex', keywords=['mutex']),
    ]
    pool = gather_sibling_concepts(section, lesson, correct_answer='Proces')
    # Section-tier should come before lesson-tier.
    section_first = [c for c in pool if c['proximity'] == 'section']
    lesson_after = [c for c in pool if c['proximity'] == 'lesson']
    # All section entries before all lesson entries.
    assert pool == section_first + lesson_after


def test_correct_answer_is_excluded():
    section = [_lo(1, 'Proces', keywords=['Proces', 'PCB'])]
    pool = gather_sibling_concepts(section, [], correct_answer='Proces')
    assert all(c['concept'].lower() != 'proces' for c in pool)


def test_near_duplicate_keywords_collapsed():
    section = [_lo(1, 'Proces', keywords=['proces', 'procesi', 'PCB'])]
    pool = gather_sibling_concepts(section, [], correct_answer='Proces')
    # Only one of {proces, procesi} should survive; PCB should remain.
    assert len(pool) == 1
    assert pool[0]['concept'].lower() == 'pcb'


def test_falls_back_to_lesson_when_section_thin():
    """If section has too few siblings, lesson keywords fill in."""
    section = [_lo(1, 'Proces', keywords=['PCB'])]
    lesson = [
        _lo(1, 'Proces', keywords=['PCB']),
        _lo(2, 'Nit', keywords=['nit', 'TCB']),
        _lo(3, 'Mutex', keywords=['mutex']),
    ]
    pool = gather_sibling_concepts(section, lesson, correct_answer='Proces',
                                   max_candidates=10)
    # PCB from section, plus lesson-tier entries.
    proximities = [c['proximity'] for c in pool]
    assert 'section' in proximities
    assert 'lesson' in proximities


def test_max_candidates_caps_output():
    section = [_lo(1, 'X', keywords=[f'kw{i}' for i in range(50)])]
    pool = gather_sibling_concepts(section, [], correct_answer='target',
                                   max_candidates=5)
    assert len(pool) == 5


# -----------------------------------------------------------------------------
# suggest_cloze_distractors
# -----------------------------------------------------------------------------

def test_suggest_top_n():
    section = [_lo(1, 'Proces', keywords=['PCB', 'stanje procesa', 'atribut'])]
    lesson = section
    q = {'id': 1, 'correct_answer': 'Proces'}
    out = suggest_cloze_distractors(q, section, lesson, n=2)
    assert out['requested'] == 2
    assert len(out['distractors']) == 2


def test_suggest_when_pool_smaller_than_n():
    section = [_lo(1, 'Proces', keywords=['PCB'])]
    q = {'id': 1, 'correct_answer': 'Proces'}
    out = suggest_cloze_distractors(q, section, section, n=5)
    # Only one sibling available (PCB).
    assert len(out['distractors']) == 1
    assert out['available_pool_size'] == 1


# -----------------------------------------------------------------------------
# Prompt formatter
# -----------------------------------------------------------------------------

def test_format_pool_includes_proximity_tag():
    pool = [
        {'concept': 'PCB', 'lo_title': 'Proces', 'proximity': 'section'},
        {'concept': 'mutex', 'lo_title': 'Sinhronizacija', 'proximity': 'lesson'},
    ]
    block = format_pool_for_prompt(pool)
    assert 'PCB' in block
    assert 'mutex' in block
    assert 'proximity=section' in block
    assert 'Aldabe' in block


def test_format_empty_pool_yields_empty_string():
    assert format_pool_for_prompt([]) == ''
