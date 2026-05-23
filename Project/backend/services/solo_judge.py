"""
SOLO LLM-judge.

A second LLM classifies an already-generated question into one of the four
SOLO levels (unistructural / multistructural / relational / extended_abstract).
Agreement with the *intended* level (the level the generator was asked to
produce) is reported as Cohen's kappa plus a per-level confusion matrix.

This is the a-priori SOLO validity check from professor's point 4: it does
not require student responses, so we can use it before the June exam.

Design notes:

* Independence from generator. The judge uses a classification-only prompt
  with different framing (analyze, not generate) and temperature 0.1
  (near-deterministic). If the user provides OLLAMA_JUDGE_MODEL in .env,
  a different model is used for full independence; otherwise we fall back
  to OLLAMA_MODEL.
* Caching via existing llm_cache. First call per question is slow (~5-15s),
  every subsequent call is instant. Re-judging is automatic if the
  question text changes (cache key includes the prompt).
* Cohen's kappa is computed in-process (no scikit-learn dep).
"""

import json
import os
import re
from typing import Any, Dict, List, Optional

import requests

from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from core import llm_cache
from core.prompt_lib import SOLO_DEFINITIONS

SOLO_LEVELS: List[str] = ["unistructural", "multistructural", "relational", "extended_abstract"]

# Independent model if user configured one; otherwise fall back so the feature
# still works on single-model installs.
JUDGE_MODEL = os.getenv("OLLAMA_JUDGE_MODEL") or OLLAMA_MODEL
JUDGE_TEMPERATURE = 0.1


# --------------------------------------------------------------------------
# Prompt
# --------------------------------------------------------------------------

def build_judge_prompt(question_text: str, options: List[Any], correct_answer: Optional[str]) -> str:
    """Build the classification prompt. Distinct framing from the generator."""
    opt_lines = []
    for i, opt in enumerate(options or []):
        if isinstance(opt, dict):
            opt = opt.get("text") or opt.get("value") or ""
        opt_lines.append(f"  {chr(ord('A') + i)}. {opt}")
    opts_block = "\n".join(opt_lines) if opt_lines else "(no options provided)"
    correct_block = correct_answer if correct_answer else "(no key provided)"

    defs_block = "\n".join(
        f"  - {lvl.upper()}: {SOLO_DEFINITIONS[lvl]}" for lvl in SOLO_LEVELS
    )

    return f"""You are an educational measurement expert. Your task is to CLASSIFY a multiple-choice question into one SOLO-taxonomy level. You are NOT generating questions — you are analysing an existing item.

SOLO LEVELS:
{defs_block}

QUESTION TO CLASSIFY:
{question_text}

OPTIONS:
{opts_block}

CORRECT ANSWER:
{correct_block}

CLASSIFICATION CRITERIA — decide based on the cognitive demand placed on the student:
  - UNISTRUCTURAL: recall of one fact/term/definition.
  - MULTISTRUCTURAL: recall or identification of several independent facts/components, no integration.
  - RELATIONAL: explain how concepts connect — cause/effect, dependency, structural relationship.
  - EXTENDED_ABSTRACT: apply a principle to a new situation or generalize beyond the stated material.

Be strict: if a question only asks for a definition, it is UNISTRUCTURAL even if the concept is advanced.

OUTPUT — strict JSON, no other text:
{{"level": "<one of: unistructural | multistructural | relational | extended_abstract>",
 "confidence": <float 0..1>,
 "reasoning": "<one short sentence in English>"}}"""


# --------------------------------------------------------------------------
# LLM call (mockable in tests via dependency injection)
# --------------------------------------------------------------------------

def _call_judge_llm(prompt: str, *, use_cache: bool = True, timeout: int = 60) -> Optional[str]:
    """POST to Ollama; cache hits skip the network entirely."""
    if use_cache:
        cached = llm_cache.get(JUDGE_MODEL, prompt, JUDGE_TEMPERATURE, json_mode=True)
        if cached is not None:
            return cached
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": JUDGE_MODEL,
                "prompt": prompt,
                "stream": False,
                "temperature": JUDGE_TEMPERATURE,
                "format": "json",
            },
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None
        result = resp.json().get("response", "")
        if result and use_cache:
            llm_cache.put(JUDGE_MODEL, prompt, JUDGE_TEMPERATURE, True, result)
        return result
    except Exception:
        return None


def _parse_judge_response(raw: str) -> Optional[Dict[str, Any]]:
    """Parse LLM JSON; tolerate stray text around the JSON block."""
    if not raw:
        return None
    # Pull the first JSON object out of the response.
    m = re.search(r'\{[\s\S]*\}', raw)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    lvl = str(data.get("level", "")).strip().lower()
    if lvl not in SOLO_LEVELS:
        return None
    conf = data.get("confidence")
    try:
        conf = float(conf) if conf is not None else None
    except (TypeError, ValueError):
        conf = None
    return {
        "level": lvl,
        "confidence": conf,
        "reasoning": (data.get("reasoning") or "").strip(),
    }


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def classify_question(
    question: Dict[str, Any],
    *,
    llm_caller=None,
) -> Dict[str, Any]:
    """Classify one question. `llm_caller` is injectable for tests."""
    call = llm_caller or _call_judge_llm
    prompt = build_judge_prompt(
        question.get("question_text") or "",
        question.get("options") or [],
        question.get("correct_answer"),
    )
    raw = call(prompt)
    parsed = _parse_judge_response(raw or "")
    intended = (question.get("solo_level") or "").strip().lower()

    return {
        "question_id": question.get("id"),
        "intended_level": intended if intended in SOLO_LEVELS else None,
        "classified_level": parsed["level"] if parsed else None,
        "confidence": parsed["confidence"] if parsed else None,
        "reasoning": parsed["reasoning"] if parsed else None,
        "agrees": (
            parsed is not None
            and intended in SOLO_LEVELS
            and parsed["level"] == intended
        ),
        "parse_ok": parsed is not None,
    }


def _cohen_kappa(pairs: List[Dict[str, Any]]) -> Optional[float]:
    """Cohen's kappa between intended and classified labels."""
    usable = [p for p in pairs if p.get("intended_level") and p.get("classified_level")]
    n = len(usable)
    if n == 0:
        return None
    p_o = sum(1 for p in usable if p["intended_level"] == p["classified_level"]) / n
    # Expected agreement assuming independence.
    p_e = 0.0
    for lvl in SOLO_LEVELS:
        p_int = sum(1 for p in usable if p["intended_level"] == lvl) / n
        p_cls = sum(1 for p in usable if p["classified_level"] == lvl) / n
        p_e += p_int * p_cls
    if p_e >= 1.0:
        # Degenerate: everything in one cell → no variance to disagree on.
        return 1.0 if p_o == 1.0 else 0.0
    return (p_o - p_e) / (1.0 - p_e)


def _confusion_matrix(pairs: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    """confusion[intended][classified] = count."""
    cm: Dict[str, Dict[str, int]] = {
        lvl: {lvl2: 0 for lvl2 in SOLO_LEVELS} for lvl in SOLO_LEVELS
    }
    for p in pairs:
        i, c = p.get("intended_level"), p.get("classified_level")
        if i in cm and c in cm[i]:
            cm[i][c] += 1
    return cm


def judge_questions(
    questions: List[Dict[str, Any]],
    *,
    llm_caller=None,
) -> Dict[str, Any]:
    """Classify every question in `questions` and return aggregate stats."""
    total = len(questions)
    print(f'[SOLO-Judge] Starting SOLO classification on {total} question(s) — model={JUDGE_MODEL}', flush=True)
    reports = []
    for i, q in enumerate(questions, start=1):
        r = classify_question(q, llm_caller=llm_caller)
        reports.append(r)
        if i == 1 or i == total or i % 5 == 0:
            cl = r.get("classified_level") or 'unparseable'
            agree = '✓' if r.get("agrees") else '✗'
            print(f'[SOLO-Judge] {i}/{total} — Q#{q.get("id")} intended={r.get("intended_level")} classified={cl} {agree}', flush=True)
    parse_failures = sum(1 for r in reports if not r["parse_ok"])
    usable = [r for r in reports if r["parse_ok"] and r["intended_level"]]
    agreement_count = sum(1 for r in usable if r["agrees"])
    accuracy = agreement_count / len(usable) if usable else None
    print(f'[SOLO-Judge] Done. {agreement_count}/{len(usable)} agree ({round(100*accuracy,1) if accuracy else 0}%).', flush=True)

    return {
        "total_questions": len(reports),
        "judged_questions": len(usable),
        "parse_failures": parse_failures,
        "agreement_count": agreement_count,
        "accuracy": round(accuracy, 3) if accuracy is not None else None,
        "cohen_kappa": (round(_cohen_kappa(reports), 3)
                        if _cohen_kappa(reports) is not None else None),
        "confusion_matrix": _confusion_matrix(reports),
        "reports": reports,
        "judge_model": JUDGE_MODEL,
    }
