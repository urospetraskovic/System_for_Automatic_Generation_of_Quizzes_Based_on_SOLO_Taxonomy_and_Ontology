"""
Tests for Fix L's deterministic helpers — slide-heading detection and
consecutive-run grouping. The injection orchestration itself runs inside
parse_lesson_structure and is exercised by the full pipeline, but these
two helpers are pure-Python and we can unit-test them directly.
"""

from core.content_parser import ContentParser


def test_extract_slide_heading_typical_slide():
    page = "Pipes\nPipes je poseban tip međuprocesne komunikacije."
    assert ContentParser._extract_slide_heading(page) == "Pipes"


def test_extract_slide_heading_multiword_title():
    page = "Tipovi pipes\nDa li je komunikacija jednosmerna ili dvosmerna"
    assert ContentParser._extract_slide_heading(page) == "Tipovi pipes"


def test_extract_slide_heading_skips_empty_lines():
    page = "\n\n  \nKomutiranje procesa\nDetails follow here."
    assert ContentParser._extract_slide_heading(page) == "Komutiranje procesa"


def test_extract_slide_heading_rejects_long_first_line():
    """First line is a paragraph, not a heading."""
    page = "This is a long sentence that is way more than 80 characters long and is therefore not a slide heading."
    assert ContentParser._extract_slide_heading(page) is None


def test_extract_slide_heading_rejects_period_ending():
    """Headings on slides don't end with a period."""
    page = "This ends with a period."
    assert ContentParser._extract_slide_heading(page) is None


def test_extract_slide_heading_rejects_too_many_words():
    page = "one two three four five six seven eight nine ten eleven twelve thirteen"
    assert ContentParser._extract_slide_heading(page) is None


def test_extract_slide_heading_on_empty_input():
    assert ContentParser._extract_slide_heading("") is None
    assert ContentParser._extract_slide_heading(None) is None


def test_consecutive_runs_groups_correctly():
    assert ContentParser._consecutive_runs([]) == []
    assert ContentParser._consecutive_runs([5]) == [(5, 5)]
    assert ContentParser._consecutive_runs([1, 2, 3]) == [(1, 3)]
    assert ContentParser._consecutive_runs([1, 2, 5, 6, 7, 10]) == [(1, 2), (5, 7), (10, 10)]
    assert ContentParser._consecutive_runs([13, 14, 15, 16, 17, 18, 19]) == [(13, 19)]


def test_consecutive_runs_handles_single_gap():
    """One missing page in the middle creates two runs."""
    assert ContentParser._consecutive_runs([1, 2, 4, 5]) == [(1, 2), (4, 5)]
