"""
Tests for Fix N — dropping near-duplicate sections by page-range +
LO-content overlap.
"""

from core.content_parser import ContentParser


def _section(title, start_page, end_page, lo_titles):
    return {
        'title': title,
        'start_page': start_page,
        'end_page': end_page,
        'learning_objects': [{'title': t} for t in lo_titles],
    }


def test_no_dedup_when_no_overlap():
    """Different pages, different LOs — nothing should merge."""
    sections = [
        _section("A", 1, 3, ['x', 'y']),
        _section("B", 10, 12, ['p', 'q']),
    ]
    out = ContentParser._dedup_sections_by_lo_overlap(sections)
    assert len(out) == 2


def test_dedup_same_pages_same_los():
    """Same page range, same LOs → one section absorbed by the other."""
    sections = [
        _section("Deljena memorija - varijanta A", 53, 56, ['Deljena memorija', 'Razmena poruka', 'Pipes']),
        _section("Razmena poruka", 53, 56, ['Deljena memorija', 'Razmena poruka', 'Pipes']),
    ]
    out = ContentParser._dedup_sections_by_lo_overlap(sections)
    assert len(out) == 1
    # The shorter-title section "Razmena poruka" wins on the tiebreaker.
    assert out[0]['title'] == "Razmena poruka"


def test_no_dedup_when_pages_overlap_but_los_differ():
    """Same pages but distinct concepts → keep both (legitimate split)."""
    sections = [
        _section("Blokiran", 22, 22, ['blokiran u čekanju', 'završetak U/I']),
        _section("Spreman", 22, 22, ['spreman za izvršavanje', 'red spremnih']),
    ]
    out = ContentParser._dedup_sections_by_lo_overlap(sections)
    # LO overlap = 0 — both kept.
    assert len(out) == 2


def test_winner_absorbs_uniques_from_loser():
    """When merging, the loser's unique LOs are added to the winner."""
    sections = [
        _section("Loser title (long)", 1, 1, ['a', 'b', 'c']),
        _section("Winner", 1, 1, ['a', 'b', 'd', 'e']),  # 4 LOs > 3, wins on count
    ]
    out = ContentParser._dedup_sections_by_lo_overlap(sections)
    assert len(out) == 1
    assert out[0]['title'] == 'Winner'
    titles = {lo['title'] for lo in out[0]['learning_objects']}
    # Winner's LOs + loser's unique LO 'c' should all be present.
    assert titles == {'a', 'b', 'c', 'd', 'e'}


def test_section_with_no_pages_is_left_alone():
    """Phantoms / page-less sections shouldn't be merged blindly."""
    sections = [
        {'title': 'No pages', 'start_page': None, 'end_page': None, 'learning_objects': []},
        _section("Other", 1, 2, ['x']),
    ]
    out = ContentParser._dedup_sections_by_lo_overlap(sections)
    assert len(out) == 2
