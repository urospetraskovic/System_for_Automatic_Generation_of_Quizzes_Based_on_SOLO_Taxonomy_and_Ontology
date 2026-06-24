"""
Tests for services.quality.misconception_mining — Sadler 1998 implementation.

The miner has two stages: (1) regex cue-window finding (pure Python),
(2) LLM extraction of misconception/correction pairs (we mock).
"""

import json

from services.quality.misconception_mining import (
    _parse_misconceptions,
    find_cue_windows,
    mine_misconceptions,
)


# -----------------------------------------------------------------------------
# Cue windows
# -----------------------------------------------------------------------------

def test_serbian_cue_detected():
    text = "Proces je program u izvršavanju. Česta greška je da studenti misle da je proces isto što i program."
    windows = find_cue_windows(text)
    assert len(windows) >= 1
    assert any('greška' in w['cue'].lower() for w in windows)


def test_english_cue_detected():
    text = "A process is a program in execution. A common error is to confuse processes with programs."
    windows = find_cue_windows(text)
    assert len(windows) >= 1


def test_no_cues_returns_empty():
    text = "Lorem ipsum dolor sit amet."
    assert find_cue_windows(text) == []


def test_cue_window_includes_context():
    text = "X is true. Studenti često misle da je Y, ali zapravo je X."
    windows = find_cue_windows(text)
    assert len(windows) == 1
    assert 'Studenti često misle' in windows[0]['context']
    assert 'zapravo je X' in windows[0]['context']


def test_overlapping_cues_are_merged():
    text = "A je tačno. Česta greška, najčešća greška, je da B."
    windows = find_cue_windows(text)
    # Multiple cues but overlapping → merged into one window.
    assert len(windows) == 1


def test_max_windows_caps_output():
    snippet = "X je tačno. Česta greška je da Y. "
    text = snippet * 30
    windows = find_cue_windows(text, max_windows=5)
    assert len(windows) <= 5


# -----------------------------------------------------------------------------
# LLM parser
# -----------------------------------------------------------------------------

def test_parse_extracts_pairs():
    raw = json.dumps({
        'misconceptions': [
            {'misconception': 'A == B', 'correction': 'A != B'},
            {'misconception': 'C == D', 'correction': 'C != D'},
        ]
    })
    out = _parse_misconceptions(raw)
    assert len(out) == 2
    assert out[0]['misconception'] == 'A == B'


def test_parse_drops_incomplete_pairs():
    raw = json.dumps({
        'misconceptions': [
            {'misconception': 'A'},
            {'correction': 'B'},
            {'misconception': 'C', 'correction': 'D'},
        ]
    })
    out = _parse_misconceptions(raw)
    assert len(out) == 1


def test_parse_returns_empty_on_garbage():
    assert _parse_misconceptions('not json') == []
    assert _parse_misconceptions('') == []


# -----------------------------------------------------------------------------
# Full mining pipeline
# -----------------------------------------------------------------------------

def test_mine_handles_empty_source():
    r = mine_misconceptions('')
    assert r['cue_windows_found'] == 0
    assert r['misconceptions'] == []


def test_mine_runs_llm_per_window():
    """One LLM call per cue window (after merging overlapping windows)."""
    # Long text with two cues that are far enough apart NOT to merge into one window.
    text = (
        "Lekcija o procesima u operativnim sistemima. "
        + "Pozadinski tekst koji popunjava prostor. " * 50
        + "Česta greška je da studenti misle da je proces isto što i program. "
        + "Više teksta koji odvaja dve cue tačke. " * 50
        + "Za razliku od procesa, nit deli memorijski prostor sa drugima."
    )
    calls = []

    def fake_llm(prompt):
        calls.append(1)
        return json.dumps({
            'misconceptions': [{'misconception': 'fake', 'correction': 'real'}]
        })

    r = mine_misconceptions(text, llm_caller=fake_llm)
    # At least one window — could be 1 or 2 depending on how widely the
    # filler text spaces the cues.
    assert r['cue_windows_found'] >= 1
    # One LLM call per window (the core invariant of the miner).
    assert len(calls) == r['cue_windows_found']
    assert r['misconception_count'] == r['cue_windows_found']


def test_mine_each_pair_carries_source_cue_and_offset():
    text = "Lekcija. Česta greška je da X = Y. Druga rečenica."
    r = mine_misconceptions(
        text,
        llm_caller=lambda p: json.dumps({
            'misconceptions': [{'misconception': 'X=Y', 'correction': 'X!=Y'}]
        }),
    )
    assert r['misconceptions'][0]['source_cue']
    assert isinstance(r['misconceptions'][0]['source_offset'], int)
