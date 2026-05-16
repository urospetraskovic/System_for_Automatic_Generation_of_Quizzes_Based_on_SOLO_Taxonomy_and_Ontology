"""
Tests for the TOC-page detection and locator exclusion.

The motivating bug: a slide deck repeats its TOC slide on pages 2, 20, 29,
38, 50, 61. A section title that's listed in the TOC ("Stanja procesa")
appears as a bullet on every TOC slide, so the locator used to span the
whole document. _find_toc_pages identifies those repeated pages; the
locator then skips offsets inside them.
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


def test_find_toc_pages_returns_all_repeats():
    """The TOC slide repeats on multiple pages — all should be detected."""
    toc_text = "Sadržaj\nPojam procesa\nStanja procesa\nUpravljačke strukture\nUpravljanje procesom\nKomunikacija"
    pages = [
        "Title slide",
        toc_text,                           # first TOC
        "Pojam procesa\nDefinicija...",
        "Pojam procesa\nElementi...",
        toc_text,                           # repeated TOC
        "Stanja procesa\nIzvršavanje...",
        "Stanja procesa\nSpreman...",
        toc_text,                           # repeated TOC
        "Upravljačke strukture\nUBP...",
    ]
    content, meta = _build(pages)
    outline_items = ['Pojam procesa', 'Stanja procesa', 'Upravljačke strukture', 'Upravljanje procesom', 'Komunikacija']
    toc_pages = ContentParser._find_toc_pages(content, meta, outline_items)
    detected_page_numbers = [p['page'] for p in toc_pages]
    # All three TOC slides should be flagged (pages 2, 5, 8).
    assert 2 in detected_page_numbers
    assert 5 in detected_page_numbers
    assert 8 in detected_page_numbers


def test_find_toc_pages_ignores_content_pages():
    """A content page that mentions ONE outline item is not a TOC page."""
    pages = [
        "Title",
        "Sadržaj\nIntro\nCore\nApplications\nSummary\nReferences",  # TOC
        "Intro\nThis is the intro chapter and we explain things in detail here.",  # 1 item only
        "Core\nThe core chapter discusses the main concepts.",                      # 1 item only
    ]
    content, meta = _build(pages)
    outline_items = ['Intro', 'Core', 'Applications', 'Summary', 'References']
    toc_pages = ContentParser._find_toc_pages(content, meta, outline_items)
    detected = [p['page'] for p in toc_pages]
    assert 2 in detected
    assert 3 not in detected
    assert 4 not in detected


def test_locator_excludes_toc_page_offsets():
    """
    The real bug: a TOC slide repeats on multiple pages in a slide deck.
    Each TOC instance contains the section title as a bullet, so the title
    hits cluster across the whole deck. With excluded_ranges, only the real
    content page remains.
    """
    toc_text = "Sadržaj\nStanja procesa\nUBP\nKomunikacija"
    pages = [
        "Title slide",
        toc_text,                                              # page 2 — TOC
        ("." * 300),                                           # short slide
        ("." * 300),
        toc_text,                                              # page 5 — TOC repeat
        ("." * 300),
        toc_text,                                              # page 7 — TOC repeat
        "Stanja procesa\nIzvršavanje, Spreman, Blokiran",      # page 8 — real section
    ]
    content, meta = _build(pages)
    section = {"title": "Stanja procesa", "key_topics": []}

    # Without exclusion: TOC hits cluster and pull start_page earlier
    # than the real content page.
    no_excl = ContentParser()._locate_section_in_content(content, section, meta)
    assert no_excl["start_page"] < 8

    # With exclusion of all three TOC pages: only the page-8 hit survives.
    toc_pages_meta = [meta[1], meta[4], meta[6]]
    excluded = [(p['start_offset'], p['end_offset']) for p in toc_pages_meta]
    excl = ContentParser()._locate_section_in_content(
        content, section, meta, excluded_ranges=excluded
    )
    assert excl["start_page"] == 8


def test_offset_in_excluded_helper():
    assert ContentParser._offset_in_excluded(50, [(0, 100)]) is True
    assert ContentParser._offset_in_excluded(100, [(0, 100)]) is False  # half-open
    assert ContentParser._offset_in_excluded(150, [(0, 100), (200, 300)]) is False
    assert ContentParser._offset_in_excluded(250, [(0, 100), (200, 300)]) is True
    assert ContentParser._offset_in_excluded(50, None) is False
    assert ContentParser._offset_in_excluded(50, []) is False


def test_find_toc_pages_handles_missing_inputs():
    assert ContentParser._find_toc_pages("any", [], ['a', 'b']) == []
    assert ContentParser._find_toc_pages("any", [{'page': 1, 'char_count': 5, 'start_offset': 0, 'end_offset': 5}], []) == []
