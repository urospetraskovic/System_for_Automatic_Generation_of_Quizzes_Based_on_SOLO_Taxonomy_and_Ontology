"""
Tests for services.quality.readability — Flesch / Flesch-Kincaid.

Pure-Python module, no LLM dependency.
"""

from services.quality.readability import (
    SOLO_GRADE_TARGETS,
    _bucket,
    _count_sentences,
    _count_syllables,
    _count_syllables_word,
    _count_words,
    assess_question_readability,
    compute_readability,
    readability_report,
)


# -----------------------------------------------------------------------------
# Counters
# -----------------------------------------------------------------------------

def test_sentence_count_with_terminal_punctuation():
    assert _count_sentences('A sentence. Another one!') == 2


def test_sentence_count_without_terminal_punctuation():
    """A stem without a final '?' still counts as one sentence."""
    assert _count_sentences('Šta je proces') == 1


def test_sentence_count_empty():
    assert _count_sentences('') == 0


def test_word_count_basic():
    assert _count_words('Šta je proces u operativnom sistemu?') == 6


def test_syllable_count_minimum_one():
    """A word with no vowels (rare in Latin scripts) still counts as one syllable."""
    assert _count_syllables_word('xyz') == 1


def test_syllable_count_serbian_word():
    """'proces' has 'o' and 'e' as separate vowel groups → 2 syllables."""
    assert _count_syllables_word('proces') == 2


def test_syllable_count_cyrillic_word():
    """Cyrillic 'процес' should also yield 2 vowel groups."""
    assert _count_syllables_word('процес') == 2


# -----------------------------------------------------------------------------
# Formulas
# -----------------------------------------------------------------------------

def test_empty_text_yields_none_scores():
    r = compute_readability('')
    assert r['flesch_reading_ease'] is None
    assert r['flesch_kincaid_grade'] is None


def test_short_simple_sentence_is_easy():
    r = compute_readability('Šta je proces?')
    # The grade should be low (easy) — well below college level.
    assert r['flesch_kincaid_grade'] is not None
    assert r['flesch_kincaid_grade'] < 12


def test_long_complex_sentence_is_harder():
    simple = compute_readability('Šta je proces?')
    complex_ = compute_readability(
        'U kontekstu sinhronizacije izvršavanja niti unutar višekorisničkog '
        'višeprogramskog operativnog sistema, na koji način implementacija '
        'semafora obezbeđuje koherentnost deljenih resursa između konkurentnih '
        'procesa?'
    )
    assert complex_['flesch_kincaid_grade'] > simple['flesch_kincaid_grade']


# -----------------------------------------------------------------------------
# Bucket + fit
# -----------------------------------------------------------------------------

def test_bucket_easy_medium_hard():
    assert _bucket(4.0) == 'easy'
    assert _bucket(8.0) == 'medium'
    assert _bucket(16.0) == 'hard'
    assert _bucket(None) is None


def test_assess_in_range_for_unistructural():
    q = {'id': 1, 'solo_level': 'unistructural', 'question_text': 'Šta je proces?'}
    r = assess_question_readability(q)
    # Short Serbian unistructural stem should land in the U target window.
    assert r['fit'] in ('in_range', 'too_easy')


def test_assess_unknown_when_solo_missing():
    q = {'id': 1, 'solo_level': '', 'question_text': 'Šta je proces?'}
    r = assess_question_readability(q)
    assert r['fit'] == 'unknown'


def test_assess_too_hard_for_unistructural():
    long_text = (
        'U kontekstu sinhronizacije izvršavanja niti unutar višekorisničkog '
        'višeprogramskog operativnog sistema, na koji način implementacija '
        'semafora obezbeđuje koherentnost deljenih resursa između konkurentnih '
        'procesa u sistemu sa višestrukim jezgrima?'
    )
    q = {'id': 1, 'solo_level': 'unistructural', 'question_text': long_text}
    r = assess_question_readability(q)
    # Should clearly exceed the 10-grade upper bound for unistructural.
    assert r['fit'] == 'too_hard'


# -----------------------------------------------------------------------------
# Batch report
# -----------------------------------------------------------------------------

def test_report_aggregates_distribution():
    qs = [
        {'id': 1, 'solo_level': 'unistructural', 'question_text': 'Šta je proces?'},
        {'id': 2, 'solo_level': 'unistructural', 'question_text': 'Definiši nit.'},
        {'id': 3, 'solo_level': '', 'question_text': 'Bez nivoa.'},
    ]
    r = readability_report(qs)
    assert r['total_questions'] == 3
    assert r['computable_questions'] == 3
    assert r['mean_flesch_kincaid_grade'] is not None
    assert r['fit_distribution']['unknown'] == 1


def test_solo_grade_targets_cover_all_levels():
    for lvl in ('unistructural', 'multistructural', 'relational', 'extended_abstract'):
        assert lvl in SOLO_GRADE_TARGETS
        lo, hi = SOLO_GRADE_TARGETS[lvl]
        assert lo < hi
