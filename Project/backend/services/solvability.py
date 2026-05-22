"""
Solvability test — a-priori item difficulty calibration via LLM-blind solving.

Method:
  Hide the `correct_option_index` from the question and ask an LLM to pick
  the best option. Repeat N times (default 5). Count how often the LLM
  picks the *actual* correct answer. The resulting "LLM p-value" is a
  pre-deployment proxy for the classical item difficulty index.

Literature:
  * Lan, A. S., Vats, D., Lalor, J. P., & Brunskill, E. (2015) and follow-up
    work on item difficulty prediction.
  * Item Response Theory (IRT) p-values are the empirical analogue computed
    from student responses (Crocker & Algina, 1986). The LLM-solver acts as
    a synthetic student with stable ability.
  * Recent work on using LLMs to estimate item difficulty includes
    Kurdi et al. (2020) review of automatic question generation evaluation
    and ongoing research on LLM-based test item analysis.

Interpretation:
  LLM p ≈ 1.0  → trivially easy; the question may be too simple OR has a
                 length/grammar clue.
  0.6 ≤ p < 1  → expected for a well-formed item that the model already
                 knows the material for.
  p ≈ 0.5      → near chance (4 options ⇒ chance is 0.25, so this is still
                 informative); the question may be ambiguous.
  p < 0.5      → either the question is misframed, the key is wrong, or
                 it tests material beyond what the source contains.
"""

import json
import os
import random
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from core import llm_cache

SOLVER_MODEL = os.getenv("OLLAMA_SOLVER_MODEL") or OLLAMA_MODEL
SOLVER_TEMPERATURE = 0.7  # higher than judge — we want variance to estimate p.
DEFAULT_TRIALS = 5


# --------------------------------------------------------------------------
# Prompt
# --------------------------------------------------------------------------

def build_solver_prompt(question_text: str, options: List[str]) -> str:
    opt_lines = "\n".join(f"  {chr(ord('A') + i)}. {opt}" for i, opt in enumerate(options))
    return f"""You are a student taking a multiple-choice exam. Pick the single best option. You do NOT have the answer key. Use only your own knowledge and the question text.

QUESTION:
{question_text}

OPTIONS:
{opt_lines}

OUTPUT — strict JSON, no other text:
{{"choice": "<A | B | C | D | ...>",
 "reasoning": "<one short sentence>"}}"""


# --------------------------------------------------------------------------
# LLM caller (mockable in tests)
# --------------------------------------------------------------------------

def _call_solver_llm(prompt: str, *, use_cache: bool = False, timeout: int = 60) -> Optional[str]:
    """Note: caching is OFF by default for the solver. We need variance across
    trials, and a cached single response would collapse all N trials into
    one. If you want deterministic runs (e.g. for the research write-up),
    set use_cache=True.
    """
    if use_cache:
        cached = llm_cache.get(SOLVER_MODEL, prompt, SOLVER_TEMPERATURE, json_mode=True)
        if cached is not None:
            return cached
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": SOLVER_MODEL,
                "prompt": prompt,
                "stream": False,
                "temperature": SOLVER_TEMPERATURE,
                "format": "json",
            },
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None
        result = resp.json().get("response", "")
        if result and use_cache:
            llm_cache.put(SOLVER_MODEL, prompt, SOLVER_TEMPERATURE, True, result)
        return result
    except Exception:
        return None


def _parse_choice(raw: str, num_options: int) -> Optional[int]:
    """Parse the LLM's choice into a 0-based option index, or None on failure."""
    if not raw:
        return None
    m = re.search(r'\{[\s\S]*\}', raw)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    choice = str(data.get('choice', '')).strip().upper()
    if not choice:
        return None
    # Accept "A", "B", "(A)", "Option A", "1", etc.
    letter_match = re.search(r'[A-Z]', choice)
    if letter_match:
        idx = ord(letter_match.group(0)) - ord('A')
        if 0 <= idx < num_options:
            return idx
    digit_match = re.search(r'\d+', choice)
    if digit_match:
        idx = int(digit_match.group(0)) - 1  # 1-indexed → 0-indexed
        if 0 <= idx < num_options:
            return idx
    return None


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def _option_text(opt):
    if isinstance(opt, str):
        return opt.strip()
    if isinstance(opt, dict):
        return str(opt.get('text') or opt.get('value') or '').strip()
    return ''


def assess_solvability(
    question: Dict[str, Any],
    *,
    n_trials: int = DEFAULT_TRIALS,
    shuffle: bool = True,
    llm_caller=None,
    rng=None,
) -> Dict[str, Any]:
    """Run the LLM solver N times and compute an empirical p-value.

    `shuffle`: if True, options are shuffled per trial so the LLM cannot
    exploit a position bias (always picking "A"). Shuffle mapping is
    inverted before checking correctness.
    """
    call = llm_caller or _call_solver_llm
    rng = rng or random.Random()

    options = question.get('options') or []
    texts = [_option_text(o) for o in options]
    correct_idx = question.get('correct_option_index')

    if not texts or correct_idx is None or not (0 <= correct_idx < len(texts)):
        return {
            'question_id': question.get('id'),
            'available': False,
            'reason': 'Question is missing options or a designated correct index.',
        }

    trials: List[Dict[str, Any]] = []
    correct_count = 0
    parse_failures = 0

    for trial_idx in range(max(1, n_trials)):
        order = list(range(len(texts)))
        if shuffle:
            rng.shuffle(order)
        shuffled = [texts[i] for i in order]
        prompt = build_solver_prompt(question.get('question_text') or '', shuffled)
        raw = call(prompt)
        picked_shuffled_idx = _parse_choice(raw or '', len(shuffled))

        picked_original_idx: Optional[int]
        if picked_shuffled_idx is None:
            parse_failures += 1
            picked_original_idx = None
            is_correct = False
        else:
            picked_original_idx = order[picked_shuffled_idx]
            is_correct = picked_original_idx == correct_idx
            if is_correct:
                correct_count += 1

        trials.append({
            'trial': trial_idx,
            'picked_index': picked_original_idx,
            'correct': is_correct,
        })

    n_usable = n_trials - parse_failures
    p_value = (correct_count / n_usable) if n_usable > 0 else None

    label = _difficulty_label(p_value)

    return {
        'question_id': question.get('id'),
        'available': True,
        'n_trials': n_trials,
        'parse_failures': parse_failures,
        'correct_count': correct_count,
        'p_value': round(p_value, 3) if p_value is not None else None,
        'difficulty_label': label,
        'trials': trials,
        'solver_model': SOLVER_MODEL,
    }


def _difficulty_label(p: Optional[float]) -> Optional[str]:
    if p is None:
        return None
    if p >= 0.9:
        return 'trivially_easy'
    if p >= 0.6:
        return 'appropriate'
    if p >= 0.3:
        return 'hard'
    return 'too_hard_or_misframed'


def solvability_report(
    questions: List[Dict[str, Any]],
    *,
    n_trials: int = DEFAULT_TRIALS,
    shuffle: bool = True,
    llm_caller=None,
) -> Dict[str, Any]:
    """Batch solvability report for a list of questions."""
    reports = [
        assess_solvability(q, n_trials=n_trials, shuffle=shuffle, llm_caller=llm_caller)
        for q in questions
    ]
    usable = [r for r in reports if r.get('available') and r.get('p_value') is not None]

    distribution = {'trivially_easy': 0, 'appropriate': 0, 'hard': 0, 'too_hard_or_misframed': 0}
    for r in usable:
        lbl = r.get('difficulty_label')
        if lbl in distribution:
            distribution[lbl] += 1

    return {
        'total_questions': len(reports),
        'solvable_questions': len(usable),
        'mean_p_value': (
            round(sum(r['p_value'] for r in usable) / len(usable), 3) if usable else None
        ),
        'difficulty_distribution': distribution,
        'reports': reports,
        'solver_model': SOLVER_MODEL,
    }
