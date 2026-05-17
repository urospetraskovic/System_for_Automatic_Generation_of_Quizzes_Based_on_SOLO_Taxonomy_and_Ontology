"""
Tests for Fix I — the two-stage planner's deterministic helpers.

We can't easily test the full _expand_chapters_into_sections without
running Ollama, so we test the chapter-boundary math and the page-range
content extractor, which are the pieces with non-trivial logic.
"""

from core.content_parser import ContentParser


def test_compute_chapter_ranges_uses_toc_as_boundaries():
    """6 chapters + 6 TOC pages → chapter i runs from toc_i+1 to toc_{i+1}-1."""
    outline = [
        "Pojam procesa",
        "Stanja procesa",
        "Upravljačke strukture procesa",
        "Upravljanje procesom",
        "Međuprocesna komunikacija",
        "Izvršavanje OS",
    ]
    toc_pages = [2, 20, 29, 38, 50, 61]
    total_pages = 65

    ranges = ContentParser._compute_chapter_ranges(outline, toc_pages, total_pages)
    assert len(ranges) == 6
    assert ranges[0] == ("Pojam procesa", 3, 19)
    assert ranges[1] == ("Stanja procesa", 21, 28)
    assert ranges[2] == ("Upravljačke strukture procesa", 30, 37)
    assert ranges[3] == ("Upravljanje procesom", 39, 49)
    assert ranges[4] == ("Međuprocesna komunikacija", 51, 60)
    # Last chapter extends to the final page.
    assert ranges[5] == ("Izvršavanje OS", 62, 65)


def test_compute_chapter_ranges_handles_more_chapters_than_tocs():
    """
    Only the first chapter has a reliable boundary when TOC-count <
    chapter-count. Later chapters can't be inferred from TOC alone, so they
    get skipped. The caller (two-stage planner) should then fall back to
    the single-stage planner for chapters beyond the first.
    """
    outline = ["A", "B", "C", "D"]
    toc_pages = [2]
    total_pages = 20
    ranges = ContentParser._compute_chapter_ranges(outline, toc_pages, total_pages)
    # First chapter spans from page 3 (TOC+1) to the end.
    assert ranges[0] == ("A", 3, 20)
    # Later chapters can't be reliably bounded from one TOC.
    assert len(ranges) == 1


def test_compute_chapter_ranges_handles_empty_inputs():
    assert ContentParser._compute_chapter_ranges([], [2, 20], 50) == []
    assert ContentParser._compute_chapter_ranges(["A"], [], 50) == []
    assert ContentParser._compute_chapter_ranges(["A"], [2], 0) == []


def test_content_for_page_range_concatenates_only_in_range():
    """Should return content only from pages [start..end], skipping excluded."""
    pages = ["page1 text", "page2 text", "page3 text", "page4 text", "page5 text"]
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
    content = "".join(parts)

    # Pages 2-4 only:
    out = ContentParser._content_for_page_range(content, meta, 2, 4)
    assert "page1 text" not in out
    assert "page2 text" in out
    assert "page3 text" in out
    assert "page4 text" in out
    assert "page5 text" not in out

    # Pages 2-4 excluding page 3:
    out = ContentParser._content_for_page_range(content, meta, 2, 4, excluded_page_nums={3})
    assert "page2 text" in out
    assert "page3 text" not in out
    assert "page4 text" in out


def test_content_for_page_range_handles_empty():
    assert ContentParser._content_for_page_range("anything", [], 1, 5) == ""
