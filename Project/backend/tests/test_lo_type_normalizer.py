"""
Tests for ContentParser._normalize_lo_type — coerces LLM-supplied LO types
into the allowed enum so downstream code sees a clean vocabulary.
"""

import pytest

from core.content_parser import ContentParser


ALLOWED = {'concept', 'definition', 'process', 'principle',
           'component', 'example', 'technique', 'structure'}


@pytest.mark.parametrize("t", sorted(ALLOWED))
def test_allowed_types_pass_through_unchanged(t):
    assert ContentParser._normalize_lo_type(t) == t


def test_uppercase_normalised_to_lowercase():
    assert ContentParser._normalize_lo_type("Concept") == "concept"
    assert ContentParser._normalize_lo_type("DEFINITION") == "definition"


def test_english_synonyms_mapped():
    assert ContentParser._normalize_lo_type("procedure") == "process"
    assert ContentParser._normalize_lo_type("Mechanism") == "process"
    assert ContentParser._normalize_lo_type("algorithm") == "process"
    assert ContentParser._normalize_lo_type("law") == "principle"
    assert ContentParser._normalize_lo_type("rule") == "principle"
    assert ContentParser._normalize_lo_type("theory") == "principle"
    assert ContentParser._normalize_lo_type("fact") == "concept"


def test_serbian_variants_mapped():
    assert ContentParser._normalize_lo_type("definicija") == "definition"
    assert ContentParser._normalize_lo_type("princip") == "principle"
    assert ContentParser._normalize_lo_type("primer") == "example"
    assert ContentParser._normalize_lo_type("Pojam") == "concept"


def test_freeform_garbage_falls_back_to_concept():
    """Anything outside the enum or alias table maps to 'concept'."""
    assert ContentParser._normalize_lo_type("XYZ Banana") == "concept"
    assert ContentParser._normalize_lo_type("") == "concept"
    assert ContentParser._normalize_lo_type(None) == "concept"
    assert ContentParser._normalize_lo_type(123) == "concept"  # non-string


def test_specific_observed_llm_outputs():
    """Real type values seen in the 03-Procesi DB dump — they all need to land somewhere sensible."""
    assert ContentParser._normalize_lo_type("Proces stanja") == "concept"
    assert ContentParser._normalize_lo_type("Management Information") == "concept"
    assert ContentParser._normalize_lo_type("Processor Register") == "component"
