"""
Source-grounded misconception mining for distractor generation.

Sadler (1998) — *Psychometric Models of Student Conceptions in Science* —
showed empirically that the most discriminating MCQ distractors are those
that reflect *real* student misconceptions, not hypothetical ones invented
by the test writer. Our prior `COMMON_MISCONCEPTION` distractor strategy
asks the LLM to invent a misconception; this module instead *extracts*
them from the source text itself, so the distractors are grounded in
material the lesson author explicitly chose to address.

The miner looks for source-text cues like:
  Serbian: "česta greška", "izgleda kao... ali je", "studenti često misle",
           "za razliku od X, Y je", "ne treba mešati", "nije isto što i",
           "umesto X, neki misle Y", "pogrešno je shvatanje".
  English: "a common error", "students often think", "unlike X, Y is",
           "not to be confused with", "it is a misconception that",
           "contrary to popular belief".

For each cue match, the miner asks the LLM to extract the *misconception
itself* (what the student wrongly believes) and the *correction* (what is
actually true). These pairs are returned as seed material for distractor
generation.

When fed into the generator (via `Question.tags.misconception_seeds`), the
LLM is told: "Use these REAL misconceptions from the source as distractor
content where applicable, marking each as COMMON_MISCONCEPTION."

References:
  Sadler, P. M. (1998). Psychometric Models of Student Conceptions in
  Science: Reconciling Qualitative Studies and Distractor-Driven Assessment
  Instruments. Journal of Research in Science Teaching 35(3), 265-296.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional

import requests

from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from core import llm_cache

MINER_MODEL = os.getenv("OLLAMA_MINER_MODEL") or OLLAMA_MODEL
MINER_TEMPERATURE = 0.2

# Regex cues for misconception language in the source text. We use the cue
# to slice out a +/- 200-char window of context, then hand that window to
# the LLM for structured extraction. Cues are case-insensitive.
_CUE_PATTERNS_SR = [
    r"\bčesta\s+greška\b",
    r"izgleda\s+kao.{0,40}ali\s+je",
    r"studenti\s+često\s+misle",
    r"za\s+razliku\s+od\s+",
    r"ne\s+treba\s+mešati",
    r"nije\s+isto\s+što\s+i",
    r"umesto\s+\w+,\s+neki\s+misle",
    r"pogrešn[oi]\s+shvatanje",
    r"najčeš[ćc]a\s+greška",
]
_CUE_PATTERNS_EN = [
    r"\ba\s+common\s+(error|misconception|mistake|confusion)\b",
    r"students\s+often\s+(think|believe|assume|confuse)",
    r"unlike\s+\w+,\s+\w+\s+is",
    r"not\s+to\s+be\s+confused\s+with",
    r"it\s+is\s+a\s+misconception\s+that",
    r"contrary\s+to\s+(popular\s+belief|intuition)",
    r"some\s+(students?|people)\s+(mistakenly|incorrectly)",
]
_CUE_RE = re.compile(
    "|".join(_CUE_PATTERNS_SR + _CUE_PATTERNS_EN),
    flags=re.IGNORECASE,
)

_WINDOW_BEFORE = 150
_WINDOW_AFTER = 250


def find_cue_windows(source_text: str, *, max_windows: int = 20) -> List[Dict[str, Any]]:
    """Return up to N text windows around cue matches in the source.

    Windows are deduplicated by overlap: if two cues fire within a couple
    hundred chars of each other we keep the longer window so the LLM sees
    enough context.
    """
    if not source_text:
        return []
    matches = list(_CUE_RE.finditer(source_text))
    if not matches:
        return []

    windows: List[Dict[str, Any]] = []
    for m in matches:
        start = max(0, m.start() - _WINDOW_BEFORE)
        end = min(len(source_text), m.end() + _WINDOW_AFTER)
        windows.append({
            'cue': m.group(0),
            'start': start,
            'end': end,
            'context': source_text[start:end].strip(),
        })

    # Merge overlapping windows.
    windows.sort(key=lambda w: w['start'])
    merged: List[Dict[str, Any]] = []
    for w in windows:
        if merged and w['start'] <= merged[-1]['end']:
            merged[-1]['end'] = max(merged[-1]['end'], w['end'])
            merged[-1]['context'] = source_text[merged[-1]['start']:merged[-1]['end']].strip()
            merged[-1]['cue'] = f"{merged[-1]['cue']} | {w['cue']}"
        else:
            merged.append(dict(w))
    return merged[:max_windows]


# --------------------------------------------------------------------------
# LLM extraction over a single cue window
# --------------------------------------------------------------------------

def build_extract_prompt(window_text: str) -> str:
    return f"""You are an educational researcher reading a passage of teaching material that mentions a student misconception. Extract the misconception itself and the correction, as a structured pair. If the passage does NOT actually contain a misconception (the cue phrase was a false positive), return an empty list.

PASSAGE:
{window_text}

OUTPUT — strict JSON, no other text:
{{"misconceptions": [
  {{"misconception": "<what students wrongly believe, one sentence>",
    "correction": "<what is actually true, one sentence>"}},
  ...
]}}"""


def _call_llm(prompt: str, *, use_cache: bool = True, timeout: int = 60) -> Optional[str]:
    if use_cache:
        cached = llm_cache.get(MINER_MODEL, prompt, MINER_TEMPERATURE, json_mode=True)
        if cached is not None:
            return cached
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": MINER_MODEL,
                "prompt": prompt,
                "stream": False,
                "temperature": MINER_TEMPERATURE,
                "format": "json",
            },
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None
        result = resp.json().get("response", "")
        if result and use_cache:
            llm_cache.put(MINER_MODEL, prompt, MINER_TEMPERATURE, True, result)
        return result
    except Exception:
        return None


def _parse_misconceptions(raw: str) -> List[Dict[str, str]]:
    if not raw:
        return []
    m = re.search(r'\{[\s\S]*\}', raw)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    items = data.get('misconceptions') or []
    if not isinstance(items, list):
        return []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        misc = (it.get('misconception') or '').strip()
        corr = (it.get('correction') or '').strip()
        if misc and corr:
            out.append({'misconception': misc, 'correction': corr})
    return out


def mine_misconceptions(source_text: str, *, llm_caller=None,
                        max_windows: int = 20) -> Dict[str, Any]:
    """Extract Sadler-style misconception/correction pairs from a source text."""
    call = llm_caller or _call_llm
    windows = find_cue_windows(source_text, max_windows=max_windows)
    if not windows:
        return {
            'available': True,
            'cue_windows_found': 0,
            'misconceptions': [],
            'reason': 'No misconception cues found in source text.',
        }

    all_pairs: List[Dict[str, Any]] = []
    for w in windows:
        raw = call(build_extract_prompt(w['context']))
        pairs = _parse_misconceptions(raw or '')
        for p in pairs:
            p['source_cue'] = w['cue']
            p['source_offset'] = w['start']
            all_pairs.append(p)

    return {
        'available': True,
        'cue_windows_found': len(windows),
        'misconceptions': all_pairs,
        'misconception_count': len(all_pairs),
        'miner_model': MINER_MODEL,
    }


def mine_lesson_misconceptions(lesson_id: int, *, llm_caller=None,
                               max_windows: int = 20) -> Dict[str, Any]:
    """Convenience wrapper: pull raw_content from the DB and run the miner."""
    from repository import db
    lesson = db.get_lesson(lesson_id, include_content=True) if hasattr(db, 'get_lesson') else None
    if not lesson:
        return {
            'available': False,
            'reason': f'Lesson {lesson_id} not found.',
        }
    text = lesson.get('raw_content') or ''
    return mine_misconceptions(text, llm_caller=llm_caller, max_windows=max_windows)
