"""
Linguistic ambiguity detection for MCQ stems.

A question is ambiguous when it admits more than one plausible interpretation
and a careful test-taker could legitimately answer differently depending on
which reading they apply. Downing (2005) lists ambiguity among the top
item-writing flaws in actual high-stakes exams; it is the single most
common cause of items that look fine to the writer but split student
performance for no defensible reason.

We use an LLM as the expert reader. The prompt asks specifically for
*alternative interpretations* — not for "is this question unclear?", which
would conflate ambiguity with difficulty. If the model can articulate two
or more distinct readings whose answers differ, the question is flagged.

References:
  Downing, S. M. (2005). The effects of violating standard item writing
  principles on tests and students. Advances in Health Sciences Education,
  10(2), 133-143.
  Haladyna, T. M., Downing, S. M., & Rodriguez, M. C. (2002), rules on
  clarity and avoiding "tricky" items.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional

import requests

from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from core import llm_cache

AMBIGUITY_MODEL = os.getenv("OLLAMA_AMBIGUITY_MODEL") or OLLAMA_MODEL
AMBIGUITY_TEMPERATURE = 0.2


def build_ambiguity_prompt(question_text: str, options: List[Any]) -> str:
    opt_lines = []
    for i, opt in enumerate(options or []):
        if isinstance(opt, dict):
            opt = opt.get('text') or opt.get('value') or ''
        opt_lines.append(f"  {chr(ord('A') + i)}. {opt}")
    opts_block = "\n".join(opt_lines) if opt_lines else "(no options)"

    return f"""You are a careful test reviewer. Determine whether the multiple-choice question below is LINGUISTICALLY AMBIGUOUS — that is, whether it admits two or more distinct, defensible interpretations that could lead a careful test-taker to different answers.

Do NOT flag a question just because it is HARD. A question is hard when the answer is difficult to find; a question is AMBIGUOUS when the *meaning of the question itself* is unclear (e.g. a pronoun has two possible referents, a key term has two domain meanings, the syntax allows two parses, or a quantifier is unclear in scope).

QUESTION:
{question_text}

OPTIONS:
{opts_block}

OUTPUT — strict JSON, no other text:
{{"ambiguous": true | false,
 "interpretations": ["<reading 1, one sentence>", "<reading 2, one sentence>"],
 "ambiguity_type": "lexical | referential | syntactic | scope | none",
 "reasoning": "<one short sentence>"}}

If ambiguous is false, return `interpretations: []` and `ambiguity_type: "none"`."""


def _call_llm(prompt: str, *, use_cache: bool = True, timeout: int = 60) -> Optional[str]:
    if use_cache:
        cached = llm_cache.get(AMBIGUITY_MODEL, prompt, AMBIGUITY_TEMPERATURE, json_mode=True)
        if cached is not None:
            return cached
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": AMBIGUITY_MODEL,
                "prompt": prompt,
                "stream": False,
                "temperature": AMBIGUITY_TEMPERATURE,
                "format": "json",
            },
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None
        result = resp.json().get("response", "")
        if result and use_cache:
            llm_cache.put(AMBIGUITY_MODEL, prompt, AMBIGUITY_TEMPERATURE, True, result)
        return result
    except Exception:
        return None


VALID_AMBIGUITY_TYPES = {'lexical', 'referential', 'syntactic', 'scope', 'none'}


def _parse(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    m = re.search(r'\{[\s\S]*\}', raw)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data.get('ambiguous'), bool):
        return None
    interps = data.get('interpretations') or []
    if not isinstance(interps, list):
        interps = []
    interps = [str(s).strip() for s in interps if isinstance(s, str) and s.strip()]
    atype = str(data.get('ambiguity_type', 'none')).strip().lower()
    if atype not in VALID_AMBIGUITY_TYPES:
        atype = 'none'
    return {
        'ambiguous': bool(data['ambiguous']),
        'interpretations': interps[:5],
        'ambiguity_type': atype,
        'reasoning': (data.get('reasoning') or '').strip(),
    }


def assess_ambiguity(question: Dict[str, Any], *, llm_caller=None) -> Dict[str, Any]:
    call = llm_caller or _call_llm
    stem = question.get('question_text') or ''
    options = question.get('options') or []
    if not stem:
        return {
            'question_id': question.get('id'),
            'available': False,
            'reason': 'No question text.',
        }
    raw = call(build_ambiguity_prompt(stem, options))
    parsed = _parse(raw or '')
    if parsed is None:
        return {
            'question_id': question.get('id'),
            'available': False,
            'reason': 'Ambiguity LLM response could not be parsed.',
        }
    # A valid response with one or zero interpretations should not be marked
    # ambiguous regardless of the boolean — the model is inconsistent.
    if parsed['ambiguous'] and len(parsed['interpretations']) < 2:
        parsed['ambiguous'] = False
        parsed['ambiguity_type'] = 'none'

    return {
        'question_id': question.get('id'),
        'available': True,
        **parsed,
    }


def ambiguity_report(questions: List[Dict[str, Any]], *, llm_caller=None) -> Dict[str, Any]:
    reports = [assess_ambiguity(q, llm_caller=llm_caller) for q in questions]
    available = [r for r in reports if r.get('available')]
    n = len(available)
    ambiguous_count = sum(1 for r in available if r.get('ambiguous'))
    type_distribution = {t: 0 for t in VALID_AMBIGUITY_TYPES}
    for r in available:
        t = r.get('ambiguity_type', 'none')
        if t in type_distribution:
            type_distribution[t] += 1
    return {
        'total_questions': len(reports),
        'evaluated_questions': n,
        'ambiguous_count': ambiguous_count,
        'ambiguity_rate': round(100.0 * ambiguous_count / n, 1) if n else None,
        'type_distribution': type_distribution,
        'reports': reports,
        'ambiguity_model': AMBIGUITY_MODEL,
    }
