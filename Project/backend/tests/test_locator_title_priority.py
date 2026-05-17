"""
Tests for Fix G — the locator now prefers clusters that contain title hits.

Motivating bug: a section like "Komutiranje procesa" has 3 title hits on
pages 43-45 (where the section actually lives) and 30 generic keyword hits
on pages 1-28 (where words like "proces" appear densely). Old weight-only
scoring picked the keyword cluster (30 > 9). New rule: if title appears
anywhere, the cluster with the most title hits wins.
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


def test_title_cluster_beats_heavier_keyword_cluster():
    """
    A real-section title cluster (3 hits, weight 9) should beat a cluster
    of generic key_topic hits (10 hits, weight 10) — because title presence
    matters more than weight count for anchoring.

    Pages 4 and 5 are large padding to force a cluster gap between the
    keyword-dense early pages and the title-bearing later pages.
    """
    pages = [
        "Govorimo o procesu i procesoru. Proces i proces i proces."  + ("." * 200),
        "Proces, proces, proces — sve o procesu i procesoru." + ("." * 200),
        "Više proces sadržaja sa procesom i procesorom." + ("." * 200),
        ("." * 2000),
        ("." * 2000),
        "Komutiranje procesa je promena aktivnog procesa.",
        "Komutiranje procesa nastavlja. Komutiranje procesa završava.",
    ]
    content, meta = _build(pages)
    section = {"title": "Komutiranje procesa", "key_topics": ["proces"]}

    result = ContentParser()._locate_section_in_content(content, section, meta)
    # Without Fix G, the heavy keyword cluster on pages 1-3 wins.
    # With Fix G, the title cluster on pages 6-7 wins.
    assert result["start_page"] == 6
    assert result["end_page"] == 7


def test_keyword_only_fallback_when_title_absent():
    """When the title doesn't appear anywhere, the keyword cluster wins."""
    pages = [
        # Title never appears verbatim; keyword "proces" only on pages 4-5
        "intro " + ("." * 300),
        "more intro " + ("." * 300),
        "still intro " + ("." * 300),
        "ovaj proces je važan",
        "drugi proces je takođe važan",
    ]
    content, meta = _build(pages)
    section = {"title": "Paraphrased Title That Never Appears", "key_topics": ["proces"]}

    result = ContentParser()._locate_section_in_content(content, section, meta)
    # Falls back to keyword-only ranking — picks the keyword cluster.
    assert result["start_page"] in (4, 5)


def test_when_multiple_clusters_have_title_hits_pick_more_title_hits():
    """If two clusters both have title hits, the one with MORE title hits wins."""
    pages = [
        # Page 1: one title hit
        "Komutiranje procesa briefly mentioned." + ("." * 1500),
        # padding to force a cluster gap
        ("." * 2000),
        # Pages 3-4: three title hits (the real section)
        "Komutiranje procesa starts here. Komutiranje procesa is detailed.",
        "Komutiranje procesa concludes the topic.",
    ]
    content, meta = _build(pages)
    section = {"title": "Komutiranje procesa", "key_topics": []}
    result = ContentParser()._locate_section_in_content(content, section, meta)
    # Cluster on pages 3-4 has 3 title hits; cluster on page 1 has 1.
    assert result["start_page"] == 3
