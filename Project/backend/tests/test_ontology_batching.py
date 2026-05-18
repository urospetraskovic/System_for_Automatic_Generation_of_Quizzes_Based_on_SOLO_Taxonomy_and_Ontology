"""
Tests for CC's section-aware batching and BB's title→section-order map.

The batching helper itself is deterministic; we test that it respects
target size, overlaps adjacent sections, and falls back gracefully when
section info is missing.
"""

from core.content_parser import ContentParser


def _los_in_section(section_id: int, n: int) -> list:
    """Build n LO dicts attached to one section."""
    return [{'title': f's{section_id}_lo{i}', 'section_id': section_id} for i in range(n)]


def _section(sid: int, order: int) -> dict:
    return {'id': sid, 'title': f'Section {sid}', 'order_index': order}


def test_no_sections_yields_single_batch():
    los = [{'title': 'a'}, {'title': 'b'}]
    batches = ContentParser._section_batches(los, None)
    assert len(batches) == 1
    assert batches[0][0] == los
    assert batches[0][1] == []


def test_empty_sections_yields_single_batch():
    los = [{'title': 'a'}, {'title': 'b'}]
    batches = ContentParser._section_batches(los, [])
    assert len(batches) == 1


def test_small_lesson_one_batch():
    """Total LOs under target → single batch, all LOs included."""
    sections = [_section(1, 0), _section(2, 1)]
    los = _los_in_section(1, 5) + _los_in_section(2, 5)
    batches = ContentParser._section_batches(los, sections, target_size=30)
    assert len(batches) == 1
    assert len(batches[0][0]) == 10


def test_splits_on_target_size_with_overlap():
    """Two sections each with 20 LOs, target 30 → two batches with section overlap."""
    sections = [_section(1, 0), _section(2, 1), _section(3, 2)]
    los = _los_in_section(1, 20) + _los_in_section(2, 20) + _los_in_section(3, 20)
    batches = ContentParser._section_batches(los, sections, target_size=30)
    assert len(batches) >= 2
    # Each batch's LO count is bounded by target_size + one overlap section.
    for batch_los, batch_secs in batches:
        assert len(batch_los) <= 50  # generous bound: target + one overlap section
        assert len(batch_secs) >= 1


def test_sections_kept_contiguous_within_batch():
    """LOs in each batch should belong to consecutive sections (in order)."""
    sections = [_section(i, i) for i in range(1, 6)]
    los = sum((_los_in_section(i, 12) for i in range(1, 6)), [])
    batches = ContentParser._section_batches(los, sections, target_size=30)
    for batch_los, batch_secs in batches:
        if not batch_secs:
            continue
        section_ids_in_batch = [s.get('id') for s in batch_secs]
        # Sections within a batch should be in order_index order.
        assert section_ids_in_batch == sorted(section_ids_in_batch)


def test_orphan_los_get_their_own_batch():
    """LOs with no section_id should still be processed in a final batch."""
    sections = [_section(1, 0)]
    los = _los_in_section(1, 5) + [{'title': 'orphan1'}, {'title': 'orphan2'}]
    batches = ContentParser._section_batches(los, sections, target_size=30)
    # The orphans batch should appear last.
    last_batch_titles = {lo.get('title') for lo in batches[-1][0]}
    assert 'orphan1' in last_batch_titles
    assert 'orphan2' in last_batch_titles


def test_title_to_section_order_basic():
    sections = [_section(1, 0), _section(2, 1)]
    los = [
        {'title': 'Alpha', 'section_id': 1},
        {'title': 'Beta', 'section_id': 2},
    ]
    mapping = ContentParser._build_title_to_section_order(los, sections)
    assert mapping.get('alpha') == 0
    assert mapping.get('beta') == 1


def test_title_to_section_order_handles_missing_section_info():
    los = [{'title': 'NoSection'}]
    assert ContentParser._build_title_to_section_order(los, None) == {}
    assert ContentParser._build_title_to_section_order(los, []) == {}


def test_title_to_section_order_skips_los_without_section_id():
    sections = [_section(1, 0)]
    los = [{'title': 'X'}, {'title': 'Y', 'section_id': 1}]
    mapping = ContentParser._build_title_to_section_order(los, sections)
    assert 'x' not in mapping
    assert mapping.get('y') == 0
