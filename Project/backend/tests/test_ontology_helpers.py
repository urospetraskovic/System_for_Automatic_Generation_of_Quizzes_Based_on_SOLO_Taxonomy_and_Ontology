"""
Tests for the deterministic helpers powering V/W/X/Y/Z in the ontology
extractor. The full extractor itself runs an LLM and isn't unit-tested
directly — these are the pieces we can verify in isolation.
"""

import pytest

from core.content_parser import ContentParser


# =====================================================================
# W — LO dedup
# =====================================================================

def test_dedup_keeps_unique_los():
    los = [
        {'title': 'Atributi procesa'},
        {'title': 'Praćenje izvršavanja procesa'},
        {'title': 'Komutiranje procesa'},
    ]
    out = ContentParser._dedupe_los_for_ontology(los)
    assert len(out) == 3


def test_dedup_drops_near_duplicate_titles():
    """Two LO titles with high token overlap → only the first survives."""
    los = [
        {'title': 'Deljenje i razmena informacija između procesa'},
        {'title': 'Deljenje informacija između procesa'},  # near-dup of the first
        {'title': 'Komutiranje procesa'},                   # distinct
    ]
    out = ContentParser._dedupe_los_for_ontology(los)
    titles = [lo['title'] for lo in out]
    assert 'Komutiranje procesa' in titles
    # Only ONE of the two near-duplicates should remain.
    near_dup_kept = sum(1 for t in titles if 'Deljenje' in t)
    assert near_dup_kept == 1


def test_dedup_handles_empty_input():
    assert ContentParser._dedupe_los_for_ontology([]) == []
    assert len(ContentParser._dedupe_los_for_ontology([{'title': 'Solo'}])) == 1


def test_dedup_ignores_short_token_overlap():
    """Single short tokens shouldn't cause false-positive dedup."""
    los = [
        {'title': 'A B C'},   # tokens too short (<3 chars), removed
        {'title': 'XYZ'},      # single substantive token
        {'title': 'XYZ extra'},
    ]
    out = ContentParser._dedupe_los_for_ontology(los)
    # 'A B C' has no tokens >=3 chars → filtered out entirely.
    # 'XYZ' and 'XYZ extra' share {xyz} → jaccard = 1/2 = 0.5 < 0.6 → both kept.
    titles = [lo['title'] for lo in out]
    assert 'XYZ' in titles
    assert 'XYZ extra' in titles


# =====================================================================
# X — section structure block
# =====================================================================

def test_section_structure_block_empty_when_no_sections():
    los = [{'title': 'X', 'section_id': 1}]
    assert ContentParser._build_section_structure_block(los, None) == ""
    assert ContentParser._build_section_structure_block(los, []) == ""


def test_section_structure_block_groups_los_by_section():
    sections = [
        {'id': 1, 'title': 'Section A', 'order_index': 0},
        {'id': 2, 'title': 'Section B', 'order_index': 1},
    ]
    los = [
        {'title': 'Alpha', 'section_id': 1},
        {'title': 'Beta',  'section_id': 1},
        {'title': 'Gamma', 'section_id': 2},
    ]
    block = ContentParser._build_section_structure_block(los, sections)
    assert "Section 'Section A'" in block
    assert "Section 'Section B'" in block
    assert "Alpha" in block
    assert "Beta" in block
    assert "Gamma" in block


def test_section_structure_block_respects_order_index():
    """Output should reflect document order, not insertion order."""
    sections = [
        {'id': 2, 'title': 'Second', 'order_index': 1},
        {'id': 1, 'title': 'First', 'order_index': 0},
    ]
    los = [
        {'title': 'In Second', 'section_id': 2},
        {'title': 'In First', 'section_id': 1},
    ]
    block = ContentParser._build_section_structure_block(los, sections)
    first_pos = block.index("Section 'First'")
    second_pos = block.index("Section 'Second'")
    assert first_pos < second_pos


def test_section_structure_block_skips_empty_sections():
    sections = [
        {'id': 1, 'title': 'Empty', 'order_index': 0},
        {'id': 2, 'title': 'Has LO', 'order_index': 1},
    ]
    los = [{'title': 'Only One', 'section_id': 2}]
    block = ContentParser._build_section_structure_block(los, sections)
    assert "Empty" not in block
    assert "Has LO" in block


# =====================================================================
# Y — evidence validation
# =====================================================================

def test_validate_evidence_accepts_quote_in_source():
    rel = {'evidence': "Komutiranje procesa je promena aktivnog procesa"}
    content_lower = "neki tekst ... komutiranje procesa je promena aktivnog procesa ... vise teksta"
    assert ContentParser._validate_relationship_evidence(rel, content_lower) is True


def test_validate_evidence_rejects_quote_not_in_source():
    rel = {'evidence': "This is an entirely invented English sentence."}
    content_lower = "samo srpski tekst ovde, nema engleskih recenica"
    assert ContentParser._validate_relationship_evidence(rel, content_lower) is False


def test_validate_evidence_rejects_too_short():
    rel = {'evidence': "short"}
    content_lower = "short"  # even if present, too short to be meaningful
    assert ContentParser._validate_relationship_evidence(rel, content_lower) is False


def test_validate_evidence_rejects_missing_field():
    assert ContentParser._validate_relationship_evidence({}, "any content") is False
    assert ContentParser._validate_relationship_evidence({'evidence': ''}, "any content") is False
    assert ContentParser._validate_relationship_evidence({'evidence': None}, "any content") is False


def test_validate_evidence_case_insensitive():
    rel = {'evidence': "Atributi Stanja Procesa"}
    content_lower = "atributi stanja procesa su informacije..."
    assert ContentParser._validate_relationship_evidence(rel, content_lower) is True


# =====================================================================
# Z — direction check for hierarchical relationships
# =====================================================================

def test_direction_check_passes_through_non_hierarchical():
    rel = {'source': 'A', 'target': 'B', 'type': 'relates_to'}
    out, reversed_ = ContentParser._check_part_of_direction(rel)
    assert out == rel
    assert reversed_ is False


def test_direction_check_keeps_correct_direction():
    """target's title is a substring of source's → direction is correct."""
    rel = {
        'source': 'Atributi procesa - Stanje',
        'target': 'Atributi procesa',
        'type': 'part_of',
    }
    out, reversed_ = ContentParser._check_part_of_direction(rel)
    assert out['source'] == 'Atributi procesa - Stanje'
    assert out['target'] == 'Atributi procesa'
    assert reversed_ is False


def test_direction_check_swaps_reversed():
    """source's title is a substring of target's → swap."""
    rel = {
        'source': 'Atributi procesa',
        'target': 'Atributi procesa - Stanje',
        'type': 'part_of',
    }
    out, reversed_ = ContentParser._check_part_of_direction(rel)
    assert out['source'] == 'Atributi procesa - Stanje'
    assert out['target'] == 'Atributi procesa'
    assert reversed_ is True


def test_direction_check_keeps_unrelated_titles():
    """No substring relationship → keep as-is (can't tell from titles)."""
    rel = {
        'source': 'Komutiranje procesa',
        'target': 'Stanja procesa',
        'type': 'part_of',
    }
    out, reversed_ = ContentParser._check_part_of_direction(rel)
    assert out == rel
    assert reversed_ is False


def test_direction_check_handles_self_relationship():
    rel = {'source': 'X', 'target': 'X', 'type': 'part_of'}
    out, reversed_ = ContentParser._check_part_of_direction(rel)
    assert out == rel
    assert reversed_ is False


@pytest.mark.parametrize("rel_type", ['part_of', 'is_type_of', 'is_example_of', 'specialization_of'])
def test_direction_check_applies_to_all_hierarchical_types(rel_type):
    rel = {
        'source': 'General',
        'target': 'General Specific',
        'type': rel_type,
    }
    out, reversed_ = ContentParser._check_part_of_direction(rel)
    assert reversed_ is True
    assert out['source'] == 'General Specific'
    assert out['target'] == 'General'
