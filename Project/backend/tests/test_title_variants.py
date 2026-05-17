"""
Tests for Fix M — title variant generation for fuzzy locator matching.
"""

from core.content_parser import ContentParser


def test_basic_title_produces_lowercase_variant():
    variants = ContentParser._title_variants("Definicije procesa")
    assert "definicije procesa" in variants


def test_trailing_punctuation_is_stripped():
    variants = ContentParser._title_variants("Definicije procesa.")
    assert "definicije procesa" in variants


def test_nbsp_is_normalised_to_regular_space():
    """NBSP (\\u00a0) should fold into a regular space via the whitespace-split variant."""
    title_with_nbsp = "Definicije procesa"
    variants = ContentParser._title_variants(title_with_nbsp)
    # The whitespace-normalised version should appear
    assert "definicije procesa" in variants


def test_empty_and_too_short_returns_empty():
    assert ContentParser._title_variants("") == []
    assert ContentParser._title_variants("   ") == []
    assert ContentParser._title_variants("ab") == []  # under 3 chars


def test_variants_are_deduplicated():
    """If multiple normalisation paths produce the same string, only one entry."""
    variants = ContentParser._title_variants("Hello")
    # All variants for a plain ASCII title should collapse to one entry.
    assert variants == ["hello"]


def test_first_variant_is_the_exact_lowercase():
    """The first variant should be the simple lowercase — most specific match attempt."""
    variants = ContentParser._title_variants("Process Control Block")
    assert variants[0] == "process control block"


def test_real_content_finds_section_via_variant():
    """End-to-end: a title with trailing punctuation should still locate."""
    # Build content using the same scheme the parser uses internally.
    parts, meta = [], []
    offset = 0
    for i, text in enumerate(["Intro line.", "Definicije procesa\nDetails."], start=1):
        marker = f"\n--- Page {i} ---\n"
        parts.append(marker)
        offset += len(marker)
        start = offset
        parts.append(text)
        offset += len(text)
        meta.append({
            'page': i,
            'char_count': len(text.strip()),
            'start_offset': start,
            'end_offset': offset,
        })
    content = "".join(parts)

    section = {"title": "Definicije procesa.", "key_topics": []}  # Note trailing period
    result = ContentParser()._locate_section_in_content(content, section, meta)
    # Locator finds "definicije procesa" via the stripped variant on page 2.
    assert result["start_page"] == 2
