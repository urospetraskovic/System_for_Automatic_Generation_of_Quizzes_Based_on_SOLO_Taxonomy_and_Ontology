"""
Grammatical homogeneity check for MCQ options — Haladyna O7.

The existing mcq_lint module checks option *length* parity (H24) and the
correct-as-longest length clue (H27), both of which are surface proxies for
the deeper rule Haladyna O7 states:

  "All options must be grammatically parallel: same part of speech,
   same syntactic structure, same tense, same register."

If three options start with a verb in the infinitive and one starts with a
noun phrase, the noun-phrase option is a give-away regardless of how long
it is. Tarrant et al. (2009), studying real high-stakes nursing exams,
found grammatical mismatch to be the most frequent item-writing flaw
overall.

A truly robust POS check requires a tagger that handles Serbian morphology
well (classla, stanza). Both are heavy installs. Instead, we use an LLM as
a lightweight POS classifier: it categorises each option into one of a
small closed vocabulary of structural types, and we flag the question if
the four options don't all share the same type.

References:
  Haladyna, T. M., Downing, S. M., & Rodriguez, M. C. (2002). A Review of
  Multiple-Choice Item-Writing Guidelines for Classroom Assessment.
  Applied Measurement in Education 15(3), 309-334. (Rule O7.)
  Tarrant, M., Knierim, A., Hayes, S. K., & Ware, J. (2009). The frequency
  of item writing flaws in multiple-choice questions used in high-stakes
  nursing assessments. Nurse Education in Practice 9(3), 184-191.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional

import requests

from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from core import llm_cache

GRAMMAR_MODEL = os.getenv("OLLAMA_GRAMMAR_MODEL") or OLLAMA_MODEL
GRAMMAR_TEMPERATURE = 0.1

# Closed vocabulary the LLM must use. Smaller vocabulary = more agreement
# between options. These cover the structures MCQ options normally take.
STRUCTURAL_TYPES = [
    "noun_phrase",       # "Operativni sistem"
    "verb_phrase",       # "Izvršava program"
    "full_sentence",     # "Operativni sistem izvršava programe."
    "adjective_phrase",  # "Veoma efikasan u radu sa nitima"
    "numeric",           # "42", "3.14"
    "named_entity",      # "Linux", "POSIX"
    "definition_clause", # "Program koji se izvršava"
    "other",             # everything else
]


def build_grammar_prompt(options: List[Any]) -> str:
    opt_lines = []
    for i, opt in enumerate(options or []):
        if isinstance(opt, dict):
            opt = opt.get('text') or opt.get('value') or ''
        opt_lines.append(f"  {chr(ord('A') + i)}. {opt}")
    opts_block = "\n".join(opt_lines)
    types_block = ", ".join(STRUCTURAL_TYPES)

    return f"""You are a linguistic annotator. Classify each multiple-choice OPTION into ONE structural type from this closed list:
  {types_block}

OPTIONS:
{opts_block}

Use the most specific applicable type. If an option does not fit any type above, use "other".

OUTPUT — strict JSON, no other text:
{{"types": ["<type for A>", "<type for B>", "<type for C>", "<type for D>"]}}"""


def _call_llm(prompt: str, *, use_cache: bool = True, timeout: int = 60) -> Optional[str]:
    if use_cache:
        cached = llm_cache.get(GRAMMAR_MODEL, prompt, GRAMMAR_TEMPERATURE, json_mode=True)
        if cached is not None:
            return cached
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": GRAMMAR_MODEL,
                "prompt": prompt,
                "stream": False,
                "temperature": GRAMMAR_TEMPERATURE,
                "format": "json",
            },
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None
        result = resp.json().get("response", "")
        if result and use_cache:
            llm_cache.put(GRAMMAR_MODEL, prompt, GRAMMAR_TEMPERATURE, True, result)
        return result
    except Exception:
        return None


def _parse_types(raw: str, num_options: int) -> Optional[List[str]]:
    if not raw:
        return None
    m = re.search(r'\{[\s\S]*\}', raw)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    types = data.get('types')
    if not isinstance(types, list) or len(types) < 2:
        return None
    # Pad / truncate to the option count.
    out = []
    for i in range(num_options):
        if i < len(types):
            t = str(types[i]).strip().lower()
            if t not in STRUCTURAL_TYPES:
                t = 'other'
            out.append(t)
        else:
            out.append('other')
    return out


def check_homogeneity(question: Dict[str, Any], *, llm_caller=None) -> Dict[str, Any]:
    """Classify each option's structural type and flag mismatches.

    Verdict:
      `homogeneous`  — every option has the same type.
      `single_outlier` — one option differs from the rest (give-away risk).
      `mixed`        — two or more distinct types beyond one outlier.
      `unavailable`  — the LLM classifier failed.
    """
    call = llm_caller or _call_llm
    options = question.get('options') or []
    if not options:
        return {
            'question_id': question.get('id'),
            'available': False,
            'reason': 'No options.',
        }
    raw = call(build_grammar_prompt(options))
    types = _parse_types(raw or '', len(options))
    if types is None:
        return {
            'question_id': question.get('id'),
            'available': False,
            'reason': 'Grammar LLM response could not be parsed.',
        }

    type_counts: Dict[str, int] = {}
    for t in types:
        type_counts[t] = type_counts.get(t, 0) + 1
    distinct = len(type_counts)

    if distinct == 1:
        verdict = 'homogeneous'
        outlier_indices: List[int] = []
    else:
        majority_type = max(type_counts.items(), key=lambda kv: kv[1])[0]
        minority = [i for i, t in enumerate(types) if t != majority_type]
        if len(minority) == 1:
            verdict = 'single_outlier'
            outlier_indices = minority
        else:
            verdict = 'mixed'
            outlier_indices = minority

    correct_idx = question.get('correct_option_index')
    correct_is_outlier = (
        correct_idx is not None
        and correct_idx in outlier_indices
    )

    return {
        'question_id': question.get('id'),
        'available': True,
        'option_types': types,
        'distinct_types': distinct,
        'verdict': verdict,
        'outlier_indices': outlier_indices,
        'correct_is_outlier': correct_is_outlier,
        'homogeneous': verdict == 'homogeneous',
    }


def homogeneity_report(questions: List[Dict[str, Any]], *, llm_caller=None) -> Dict[str, Any]:
    total = len(questions)
    print(f'[Grammar] Starting grammatical-homogeneity check on {total} question(s) — model={GRAMMAR_MODEL}', flush=True)
    reports = []
    for i, q in enumerate(questions, start=1):
        r = check_homogeneity(q, llm_caller=llm_caller)
        reports.append(r)
        if i == 1 or i == total or i % 5 == 0:
            verdict = r.get('verdict') if r.get('available') else 'unavail'
            print(f'[Grammar] {i}/{total} — Q#{q.get("id")} → {verdict}', flush=True)
    available = [r for r in reports if r.get('available')]
    n = len(available)
    distribution = {'homogeneous': 0, 'single_outlier': 0, 'mixed': 0}
    correct_clue = 0
    for r in available:
        v = r.get('verdict')
        if v in distribution:
            distribution[v] += 1
        if r.get('correct_is_outlier'):
            correct_clue += 1
    return {
        'total_questions': len(reports),
        'evaluated_questions': n,
        'verdict_distribution': distribution,
        'homogeneous_rate': round(100.0 * distribution['homogeneous'] / n, 1) if n else None,
        'correct_outlier_count': correct_clue,
        'reports': reports,
        'grammar_model': GRAMMAR_MODEL,
    }
