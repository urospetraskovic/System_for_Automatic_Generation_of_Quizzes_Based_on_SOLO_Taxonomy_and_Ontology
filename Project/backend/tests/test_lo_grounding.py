"""
Tests for ContentParser._lo_is_grounded — the anti-hallucination guard
that drops LOs whose title and keywords don't appear in the section content.
"""

from core.content_parser import ContentParser


def test_lo_with_title_in_content_is_grounded():
    section_content = "Upravljački blok procesa (UBP) sadrži atribute procesa. OS upravlja UBP."
    lo = {"title": "Upravljački blok procesa", "keywords": []}
    assert ContentParser._lo_is_grounded(lo, section_content) is True


def test_lo_with_keyword_in_content_is_grounded():
    section_content = "Procesi koriste UBP za upravljanje stanjem. UBP sadrži programski brojač."
    # Title doesn't appear verbatim but keyword does.
    lo = {"title": "Process Control Block", "keywords": ["UBP", "programski brojač"]}
    assert ContentParser._lo_is_grounded(lo, section_content) is True


def test_lo_with_neither_title_nor_keyword_in_content_is_dropped():
    """The motivating case: 'Mutex' in a lesson that doesn't mention mutexes."""
    section_content = "Niti dele isti adresni prostor. Sinhronizacija je potrebna."
    lo = {"title": "Mutex (Mutual Exclusion)", "keywords": ["mutex", "lock"]}
    assert ContentParser._lo_is_grounded(lo, section_content) is False


def test_short_title_alone_does_not_ground():
    """Titles < 4 chars are too noisy to use for grounding."""
    section_content = "abcdef ghi jkl"
    lo = {"title": "abc", "keywords": []}  # title is too short
    assert ContentParser._lo_is_grounded(lo, section_content) is False


def test_short_keyword_alone_does_not_ground():
    section_content = "ab cd ef gh"
    lo = {"title": "Made Up Title", "keywords": ["ab", "cd"]}  # all keywords too short
    assert ContentParser._lo_is_grounded(lo, section_content) is False


def test_case_insensitive_match():
    section_content = "PROCESI dele resurse."
    lo = {"title": "Procesi", "keywords": []}  # different case
    assert ContentParser._lo_is_grounded(lo, section_content) is True


def test_empty_section_content_drops_everything():
    lo = {"title": "Anything", "keywords": ["whatever"]}
    assert ContentParser._lo_is_grounded(lo, "") is False
    assert ContentParser._lo_is_grounded(lo, None) is False


def test_observed_hallucinations_get_dropped():
    """Real hallucinations from the 04-Niti dump should fail the check."""
    # The Niti lesson is in Serbian and doesn't mention mutexes or "Thread Lifecycle".
    section_content = (
        "Niti su putanje izvršavanja unutar procesa. "
        "OS podržava više konkurentnih niti istog procesa. "
        "Niti dele adresni prostor procesa."
    )
    for hallucinated in [
        {"title": "Thread Lifecycle", "keywords": []},
        {"title": "Concurrency Models Beyond Multithreading", "keywords": []},
        {"title": "Mutex (Mutual Exclusion)", "keywords": ["mutex"]},
        {"title": "Thread Management Details", "keywords": ["lifecycle"]},
    ]:
        assert ContentParser._lo_is_grounded(hallucinated, section_content) is False, \
            f"Should have dropped: {hallucinated}"

    # But a real Serbian LO from the same section passes.
    real_lo = {"title": "Niti", "keywords": ["adresni prostor", "konkurentnih"]}
    assert ContentParser._lo_is_grounded(real_lo, section_content) is True
