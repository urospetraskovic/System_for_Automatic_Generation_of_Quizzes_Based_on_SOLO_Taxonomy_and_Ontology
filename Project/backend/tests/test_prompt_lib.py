"""
Tests for the PS4 prompt builder in core/prompt_lib.py.

These are pure-Python tests — no network, no DB, no Ollama. They protect the
prompt structure (worked example for the right level, distractor strategies,
output language clause) since the model's behaviour depends on it being right.
"""

import pytest

from core.prompt_lib import (
    SOLO_DEFINITIONS,
    DISTRACTOR_STRATEGIES,
    WORKED_EXAMPLES,
    build_question_prompt,
    build_extended_abstract_pass1_prompt,
    build_extended_abstract_pass2_prompt,
)


SOLO_LEVELS = ["unistructural", "multistructural", "relational", "extended_abstract"]


@pytest.mark.parametrize("level", SOLO_LEVELS)
def test_build_question_prompt_includes_level_definition(level):
    """The level's SOLO definition must appear verbatim in the prompt."""
    prompt = build_question_prompt(
        level=level,
        lesson_title="Test Lesson",
        content_block="X: a thing.",
        source_text="X is a thing.",
        language="en",
    )
    assert SOLO_DEFINITIONS[level] in prompt
    assert f"{level.upper()} LEVEL" in prompt


@pytest.mark.parametrize("level", SOLO_LEVELS)
def test_build_question_prompt_includes_correct_worked_example(level):
    """Each prompt must carry ITS level's worked example, not a different one."""
    prompt = build_question_prompt(
        level=level,
        lesson_title="Test Lesson",
        content_block="X: a thing.",
        source_text="X is a thing.",
        language="en",
    )
    expected = WORKED_EXAMPLES[level]["question"]
    assert expected in prompt
    # Sanity: a *different* level's worked example must NOT leak in.
    other_levels = [lv for lv in SOLO_LEVELS if lv != level]
    for other in other_levels:
        if WORKED_EXAMPLES[other]["question"] != expected:
            assert WORKED_EXAMPLES[other]["question"] not in prompt


@pytest.mark.parametrize("level", SOLO_LEVELS)
def test_build_question_prompt_includes_distractor_strategies(level):
    """All typed distractor strategies for the level must appear in the prompt."""
    prompt = build_question_prompt(
        level=level,
        lesson_title="Test Lesson",
        content_block="X: a thing.",
        source_text="X is a thing.",
        language="en",
    )
    for strategy in DISTRACTOR_STRATEGIES[level]:
        # Strategies are full sentences; we check the leading TOKEN: portion which
        # is the stable identifier (e.g. "REVERSED_CAUSE_EFFECT:").
        token = strategy.split(":", 1)[0]
        assert token in prompt, f"Missing distractor strategy {token!r} for {level}"


def test_build_question_prompt_respects_language_serbian():
    """Serbian output clause must mention Serbian + technical-terminology rule."""
    prompt = build_question_prompt(
        level="unistructural",
        lesson_title="Test Lesson",
        content_block="X: a thing.",
        source_text="X is a thing.",
        language="sr",
    )
    assert "Serbian" in prompt
    assert "technical terminology" in prompt


def test_build_question_prompt_carries_ontology_anchor_when_provided():
    """When an ontology anchor block is supplied, it must end up in the prompt."""
    anchor_block = "\n\nONTOLOGY ANCHOR — test this relationship:\n  A --[causes]--> B"
    prompt = build_question_prompt(
        level="relational",
        lesson_title="Test Lesson",
        content_block="A causes B.",
        source_text="A is the cause of B.",
        language="en",
        ontology_anchor_block=anchor_block,
        extra_task_line="Must test the specific anchor below.",
    )
    assert anchor_block.strip() in prompt
    assert "Must test the specific anchor below." in prompt


def test_extended_abstract_pass1_with_two_lessons_names_both():
    """Pass-1 EA prompt must mention both lesson titles in the synthesis clause."""
    prompt = build_extended_abstract_pass1_prompt(
        lesson_title="Operating Systems",
        secondary_title="Computer Networks",
        primary_content="processes; scheduling",
        secondary_content="packet switching; TCP",
        primary_source="Processes are scheduled by the OS.",
        secondary_source="TCP provides reliable transport.",
        ontology_anchor_block="",
        language="en",
    )
    assert "Operating Systems" in prompt
    assert "Computer Networks" in prompt
    assert "PASS 1 of 2" in prompt
    # Pass 1 must NOT instruct distractors — those are pass 2's job.
    assert '"distractors"' not in prompt


def test_extended_abstract_pass1_without_secondary_falls_back_to_single():
    """No secondary lesson → no synthesis clause naming a second title."""
    prompt = build_extended_abstract_pass1_prompt(
        lesson_title="Operating Systems",
        secondary_title=None,
        primary_content="processes; scheduling",
        secondary_content="",
        primary_source="Processes are scheduled by the OS.",
        secondary_source="",
        ontology_anchor_block="",
        language="en",
    )
    assert "Operating Systems" in prompt
    # The "synthesize from BOTH" clause should not appear.
    assert "synthesize concepts from BOTH" not in prompt


def test_extended_abstract_pass2_carries_question_and_answer():
    """Pass-2 EA prompt must echo the question and correct answer back to the model."""
    prompt = build_extended_abstract_pass2_prompt(
        question="How would X principle apply to Y?",
        correct_answer="By doing Z.",
        explanation="Because Z follows from X.",
        source_text="X is defined as...",
        language="en",
    )
    assert "How would X principle apply to Y?" in prompt
    assert "By doing Z." in prompt
    assert "PASS 2 of 2" in prompt
    # And pass 2's output schema must request distractors.
    assert '"distractors"' in prompt


# -----------------------------------------------------------------------------
# Haladyna item-writing rules — must be explicit in every generation prompt.
# Rule codes mirror services.quality.mcq_lint so prevention (prompt) and detection
# (lint) share a vocabulary. If a code below disappears from the prompt,
# the LLM will regress on that lint check.
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("level", SOLO_LEVELS)
def test_question_prompt_carries_stem_and_option_rules(level):
    prompt = build_question_prompt(
        level=level,
        lesson_title="Test Lesson",
        content_block="X: a thing.",
        source_text="X is a thing.",
        language="en",
    )
    # Stem rules — H14, H16, H17 plus the new S5/S6/S7 quality rules.
    assert "STEM RULES" in prompt
    for code in ("H14", "H16", "H17"):
        assert code in prompt
    assert "S5" in prompt and "S6" in prompt and "S7" in prompt
    # Option rules — H19, H22, H24, H27, H25, H21 plus the new O8 quality rule.
    assert "OPTION RULES" in prompt
    for code in ("H19", "H22", "H24", "H27", "H25", "H21"):
        assert code in prompt
    assert "O8" in prompt


@pytest.mark.parametrize("level", SOLO_LEVELS)
def test_question_prompt_carries_banned_openers_block(level):
    """Anti-formulaic openers (added May 2026 after corpus analysis) must
    appear in every generation prompt so the model avoids them."""
    prompt = build_question_prompt(
        level=level,
        lesson_title="Test Lesson",
        content_block="X: a thing.",
        source_text="X is a thing.",
        language="en",
    )
    assert "BANNED STEM OPENERS" in prompt
    # The two most-frequent problem openers from the corpus analysis.
    assert "Koji od sledećih je ključni za razumevanje" in prompt
    assert "Po čemu se" in prompt


def test_extended_abstract_pass1_carries_banned_openers():
    """Extended-abstract Pass 1 also writes a stem, so banned openers apply."""
    prompt = build_extended_abstract_pass1_prompt(
        lesson_title="Operating Systems",
        secondary_title=None,
        primary_content="processes; scheduling",
        secondary_content="",
        primary_source="Processes are scheduled by the OS.",
        secondary_source="",
        ontology_anchor_block="",
        language="en",
    )
    assert "BANNED STEM OPENERS" in prompt


def test_extended_abstract_pass1_carries_stem_rules_only():
    """Pass 1 produces only the stem + correct answer — no distractor rules yet."""
    prompt = build_extended_abstract_pass1_prompt(
        lesson_title="Operating Systems",
        secondary_title=None,
        primary_content="processes; scheduling",
        secondary_content="",
        primary_source="Processes are scheduled by the OS.",
        secondary_source="",
        ontology_anchor_block="",
        language="en",
    )
    assert "STEM RULES" in prompt
    assert "OPTION RULES" not in prompt


def test_extended_abstract_pass2_carries_option_rules():
    """Pass 2 writes distractors — option rules must be present."""
    prompt = build_extended_abstract_pass2_prompt(
        question="How would X principle apply to Y?",
        correct_answer="By doing Z.",
        explanation="Because Z follows from X.",
        source_text="X is defined as...",
        language="en",
    )
    assert "OPTION RULES" in prompt
    for code in ("H19", "H22", "H24", "H27", "H25"):
        assert code in prompt
