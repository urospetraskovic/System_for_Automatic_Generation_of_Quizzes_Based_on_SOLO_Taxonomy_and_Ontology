"""
Tests for Fix S's _extract_slide_headings helper — scans all non-TOC pages
and groups consecutive duplicate headings into a single run.
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


def test_extracts_headings_for_all_pages():
    pages = [
        "Pojam procesa\nintro stuff",
        "Stanja procesa\ndetails about states",
        "Niti u C++\nthread details",
    ]
    content, meta = _build(pages)
    result = ContentParser._extract_slide_headings(content, meta)
    headings = [r['heading'] for r in result]
    assert "Pojam procesa" in headings
    assert "Stanja procesa" in headings
    assert "Niti u C++" in headings


def test_consecutive_duplicate_headings_are_grouped():
    """A heading repeated on pp 3 and 4 should appear once with start_page=3, end_page=4."""
    pages = [
        "Pojam procesa\nintro",
        "Stanja procesa\ndetails",
        "Koristi od višenitne obrade\npart 1",
        "Koristi od višenitne obrade\npart 2",
        "Tipovi niti\nULT vs KLT",
    ]
    content, meta = _build(pages)
    result = ContentParser._extract_slide_headings(content, meta)
    coristi = [r for r in result if r['heading'] == "Koristi od višenitne obrade"]
    assert len(coristi) == 1
    assert coristi[0]['start_page'] == 3
    assert coristi[0]['end_page'] == 4


def test_toc_pages_are_excluded():
    pages = [
        "Pojam procesa\nintro",
        "Sadržaj\nPojam\nStanja\nUpravljanje",  # TOC-style
        "Stanja procesa\nstates",
    ]
    content, meta = _build(pages)
    toc_pages = [meta[1]]  # page 2 is TOC
    result = ContentParser._extract_slide_headings(content, meta, toc_pages=toc_pages)
    headings = [r['heading'] for r in result]
    assert "Sadržaj" not in headings
    assert "Pojam procesa" in headings
    assert "Stanja procesa" in headings


def test_lowercase_heading_is_rejected():
    """Lowercase-starting first lines (citations, body text) shouldn't be treated as headings."""
    pages = [
        "Real Heading\nbody",
        "izvor : www.youtube.com",  # citation slide — first line lowercase
        "Another Heading\nbody",
    ]
    content, meta = _build(pages)
    result = ContentParser._extract_slide_headings(content, meta)
    headings = [r['heading'] for r in result]
    assert "Real Heading" in headings
    assert "Another Heading" in headings
    # The "izvor" line is lowercase — should be filtered out.
    assert not any("izvor" in h.lower() for h in headings)


def test_page_range_filter():
    """start_page / end_page restrict the scan."""
    pages = ["A heading", "B heading", "C heading", "D heading", "E heading"]
    content, meta = _build(pages)
    result = ContentParser._extract_slide_headings(content, meta, start_page=2, end_page=4)
    headings = [r['heading'] for r in result]
    assert headings == ["B heading", "C heading", "D heading"]


def test_pages_with_no_heading_are_skipped():
    pages = [
        "Real Heading\nbody",
        ".",  # just a period — fails heading check
        "Another Heading",
    ]
    content, meta = _build(pages)
    result = ContentParser._extract_slide_headings(content, meta)
    headings = [r['heading'] for r in result]
    assert headings == ["Real Heading", "Another Heading"]
