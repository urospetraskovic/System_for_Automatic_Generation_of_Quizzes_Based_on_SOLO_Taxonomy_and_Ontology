"""
Tests for Fix J — when a title-bearing cluster wins, the section's
boundaries are trimmed to just the title hits inside that cluster.

Motivating bug: a section like "Zahtevi OS pri upravljanju procesima" had
1 title hit on page 5 plus many keyword hits scattered on later pages
(within the same cluster). The cluster's full extent reached page 65, so
the section was tagged as spanning the whole document. With trimming, the
range collapses to just the title hits — page 5 only.
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


def test_trim_to_title_when_keywords_extend_cluster():
    """
    Title appears once on page 1; keyword "x" appears on pages 1, 3, 5
    (all within cluster_gap). Without trim, range = page 1 to page 5.
    With trim (Fix J), range = page 1 only.
    """
    pages = [
        "Zahtevi OS pri upravljanju procesima x x x" + ("." * 300),
        ("." * 800),
        "another x mention" + ("." * 800),
        ("." * 800),
        "yet another x mention" + ("." * 800),
    ]
    content, meta = _build(pages)
    section = {"title": "Zahtevi OS pri upravljanju procesima", "key_topics": ["x"]}
    result = ContentParser()._locate_section_in_content(content, section, meta)
    # Title appears only on page 1; trim collapses end_page back to page 1.
    assert result["start_page"] == 1
    assert result["end_page"] == 1


def test_trim_uses_full_title_range_when_multiple_title_hits():
    """If title appears on pages 1 AND 3, range spans 1-3 (title hits define endpoints)."""
    pages = [
        "Komutiranje procesa start.",
        ("." * 800),
        "Komutiranje procesa continues here.",
        ("." * 800),
        "stray keyword proces here." + ("." * 800),
    ]
    content, meta = _build(pages)
    section = {"title": "Komutiranje procesa", "key_topics": ["proces"]}
    result = ContentParser()._locate_section_in_content(content, section, meta)
    # Title hits on pages 1 and 3 anchor the range; keyword on page 5 is dropped.
    assert result["start_page"] == 1
    assert result["end_page"] == 3


def test_no_trim_when_title_never_appears():
    """Title absent → falls back to weight-based cluster; keyword span used."""
    pages = [
        "proces here is mentioned " + ("." * 800),
        "proces also here " + ("." * 800),
        "proces appears here too " + ("." * 800),
    ]
    content, meta = _build(pages)
    section = {"title": "TitleThatNeverAppearsLiterally", "key_topics": ["proces"]}
    result = ContentParser()._locate_section_in_content(content, section, meta)
    # No title hit → use keyword cluster bounds: pages 1 through 3.
    assert result["start_page"] == 1
    assert result["end_page"] == 3
