"""
Tests for Fix R's underlying signal — the locator now reports whether the
section was anchored by a verbatim title match or by keyword fallback.
"""

from core.content_parser import ContentParser


def _build(pages):
    parts, meta = [], []
    offset = 0
    for i, text in enumerate(pages, start=1):
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
    return "".join(parts), meta


def test_returns_matched_via_title_true_when_title_found():
    pages = [
        "intro " + ("." * 200),
        "Atributi procesa is the key topic here.",
    ]
    content, meta = _build(pages)
    section = {"title": "Atributi procesa", "key_topics": []}
    result = ContentParser()._locate_section_in_content(content, section, meta)
    assert result["matched_via_title"] is True


def test_returns_matched_via_title_false_when_falls_back_to_keywords():
    """Title doesn't exist in source — locator uses keyword cluster; flag False."""
    pages = [
        "proces here " + ("." * 200),
        "more proces " + ("." * 200),
        "another proces " + ("." * 200),
    ]
    content, meta = _build(pages)
    section = {"title": "ParaphrasedTitleThatNeverAppears", "key_topics": ["proces"]}
    result = ContentParser()._locate_section_in_content(content, section, meta)
    assert result["matched_via_title"] is False
    # And the page range should span the keyword cluster (wide).
    assert result["start_page"] == 1
    assert result["end_page"] == 3


def test_returns_matched_via_title_false_when_no_matches_at_all():
    pages = ["something", "completely", "unrelated"]
    content, meta = _build(pages)
    section = {"title": "NothingMatches", "key_topics": ["xyzzy"]}
    result = ContentParser()._locate_section_in_content(content, section, meta)
    assert result["matched_via_title"] is False
    # No hits at all → no pages
    assert result["start_page"] is None
