"""
Tests for the density-based section/LO page locator.

The motivating bug: a section whose key_topics include common words ("proces",
"UBP") used to span 30+ pages because the locator did min(offsets) → max(offsets).
The new locator clusters hits and picks the densest cluster.
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


def _parser():
    return ContentParser()


def test_locator_picks_dense_cluster_over_scattered_hits():
    """
    A section title appears densely on pages 4-5, with stray keyword mentions
    on pages 1 and 12. Min/max would span pages 1-12; clustering picks 4-5.
    """
    pages = [
        "Brief mention of process here." + ("." * 1500),
        ("." * 1500),
        ("." * 1500),
        "Process Control Block " * 5,  # dense cluster
        "Process Control Block continued " * 5,
        ("." * 1500),
        ("." * 1500),
        ("." * 1500),
        ("." * 1500),
        ("." * 1500),
        ("." * 1500),
        "Another mention of process." + ("." * 1500),  # stray hit
    ]
    content, meta = _build(pages)
    section = {
        "title": "Process Control Block",
        "key_topics": ["process"],
    }
    result = _parser()._locate_section_in_content(content, section, meta)
    assert result["start_page"] == 4
    # End page should NOT extend to page 12 — that was a stray "process" hit.
    assert result["end_page"] <= 5


def test_locator_returns_none_pages_when_no_match():
    pages = ["page one", "page two", "page three"]
    content, meta = _build(pages)
    section = {"title": "Totally Unrelated Topic", "key_topics": ["xyzzy"]}
    result = _parser()._locate_section_in_content(content, section, meta)
    assert result["start_page"] is None
    assert result["end_page"] is None
    assert result["content_snippet"] == ""


def test_title_match_outweighs_scattered_keyword_hits():
    """
    Two separate clusters: one with a stray keyword hit, one with a real
    title match. Title weight (3.0) beats keyword weight (1.0), so the
    title cluster wins. Pages are padded so the two clusters land more
    than CLUSTER_GAP (3000 chars) apart.
    """
    pages = [
        "the word common appears here " + ("." * 4000),  # 1 keyword hit
        ("." * 4000),  # padding to separate clusters
        "Process Control Block is defined here. " + ("." * 1500),  # title match
        ("." * 1500),
    ]
    content, meta = _build(pages)
    section = {"title": "Process Control Block", "key_topics": ["common"]}
    result = _parser()._locate_section_in_content(content, section, meta)
    # Title match cluster on page 3 wins over the keyword cluster on page 1.
    assert result["start_page"] == 3


def test_snippet_drawn_from_chosen_cluster():
    """The returned snippet should come from the chosen cluster, not the whole document."""
    pages = [
        "stray process mention here.",
        ("." * 2000),
        ("." * 2000),
        "Scheduler is the OS component that picks next process.",
        ("." * 500),
    ]
    content, meta = _build(pages)
    section = {"title": "Scheduler", "key_topics": ["process"]}
    result = _parser()._locate_section_in_content(content, section, meta)
    assert "Scheduler" in result["content_snippet"]
