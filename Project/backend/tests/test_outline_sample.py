"""
Tests for ContentParser._build_outline_sample — the deterministic content
sampler that feeds the planner LLM call. Pure-Python, no network.
"""

from core.content_parser import ContentParser


def _pages_meta_from_text(pages: list) -> tuple:
    """Helper: build (full_content, pages_meta) from a list of page strings."""
    text_parts = []
    pages_meta = []
    offset = 0
    for i, page_text in enumerate(pages, start=1):
        marker = f"\n--- Page {i} ---\n"
        text_parts.append(marker)
        offset += len(marker)
        start = offset
        text_parts.append(page_text)
        offset += len(page_text)
        pages_meta.append({
            "page": i,
            "char_count": len(page_text.strip()),
            "start_offset": start,
            "end_offset": offset,
        })
    return "".join(text_parts), pages_meta


def test_short_content_returned_verbatim():
    """If content fits under the budget, the sample IS the content."""
    content = "A short lesson body."
    sample = ContentParser._build_outline_sample(content, pages_meta=None, max_chars=14000)
    assert sample == content


def test_long_content_without_pages_meta_falls_back_to_head_and_tail():
    """No page metadata → head + tail slice with an omission marker."""
    content = "A" * 20000 + "B" * 20000
    sample = ContentParser._build_outline_sample(content, pages_meta=None, max_chars=10000)
    assert len(sample) <= 10000 + 100  # plus the omission marker
    assert "[... omitted middle ...]" in sample
    # Both head ('A') and tail ('B') should be present.
    assert "A" in sample
    assert "B" in sample


def test_long_content_with_pages_meta_samples_first_last_full_others_excerpt():
    """With pages_meta, first and last pages appear full; middle pages appear truncated."""
    pages = [
        "FIRST PAGE FULL TEXT " + "x" * 100,  # short
        "MIDDLE PAGE 2 START " + "y" * 5000,  # long — should be truncated
        "MIDDLE PAGE 3 START " + "z" * 5000,
        "LAST PAGE FULL TEXT " + "w" * 100,
    ]
    content, pages_meta = _pages_meta_from_text(pages)
    # Force sampling by setting max_chars below total content length (~10.5k).
    sample = ContentParser._build_outline_sample(content, pages_meta=pages_meta, max_chars=2000)

    assert "FIRST PAGE FULL TEXT" in sample
    assert "LAST PAGE FULL TEXT" in sample
    assert "MIDDLE PAGE 2 START" in sample
    assert "MIDDLE PAGE 3 START" in sample
    # Middle pages should be truncated — the 5000 'y' chars shouldn't all show.
    assert sample.count("y") < 1000


def test_sample_respects_max_chars_budget():
    """Even with many pages, the sample stays within budget (plus small overhead)."""
    pages = [f"Page {i} content " + ("p" * 2000) for i in range(1, 30)]
    content, pages_meta = _pages_meta_from_text(pages)
    sample = ContentParser._build_outline_sample(content, pages_meta=pages_meta, max_chars=8000)
    # Allow a small slack for the truncation marker.
    assert len(sample) <= 8000 + 50


def test_empty_pages_are_skipped_in_middle():
    """Blank middle pages shouldn't produce empty PAGE headers in the sample."""
    pages = [
        "FIRST WITH CONTENT",
        "   ",  # blank middle page (whitespace only)
        "LAST WITH CONTENT",
    ]
    content, pages_meta = _pages_meta_from_text(pages)
    sample = ContentParser._build_outline_sample(content, pages_meta=pages_meta, max_chars=14000)
    # The middle blank page must not appear as its own header.
    assert "=== PAGE 2 (top excerpt) ===" not in sample
    assert "FIRST WITH CONTENT" in sample
    assert "LAST WITH CONTENT" in sample
