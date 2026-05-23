"""
Item-Objective Congruence (IOC) — Rovinelli & Hambleton (1977).

The classical content-validity instrument for criterion-referenced tests.
For each question, an expert rates how well it measures the *specific*
learning objective it was anchored to:
  +1  positive  — clearly measures this objective
   0  neutral   — unclear whether this objective is what's being tested
  -1  negative  — does NOT measure this objective (measures something else,
                  or measures it badly)

The mean of those ratings across experts (or, here, across questions for one
expert / LLM judge) is the IOC index. Conventionally values ≥ 0.5 indicate
acceptable congruence; ≥ 0.75 is strong.

We use an LLM as the expert rater. The same independence rules as solo_judge
apply: a different prompt framing, low temperature, and (optionally) a
different model via OLLAMA_IOC_MODEL. This is a-priori content validity:
no student responses required.

Reference:
  Rovinelli, R. J., & Hambleton, R. K. (1977). On the use of content
  specialists in the assessment of criterion-referenced test item validity.
  Dutch Journal of Educational Research, 2, 49-60.

  See also: Crocker, L. & Algina, J. (1986). Introduction to Classical and
  Modern Test Theory, Ch. 9 (Content Validation).
"""

import json
import os
import re
from typing import Any, Dict, List, Optional

import requests

from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from core import llm_cache
from repository import db

IOC_MODEL = os.getenv("OLLAMA_IOC_MODEL") or OLLAMA_MODEL
IOC_TEMPERATURE = 0.1

VALID_RATINGS = {-1, 0, 1}


def build_ioc_prompt(question_text: str, options: List[Any],
                     correct_answer: Optional[str],
                     objective_title: str,
                     objective_content: str) -> str:
    """The IOC rating prompt. Asks for one of {-1, 0, +1} plus a one-sentence rationale."""
    opt_lines = []
    for i, opt in enumerate(options or []):
        if isinstance(opt, dict):
            opt = opt.get('text') or opt.get('value') or ''
        opt_lines.append(f"  {chr(ord('A') + i)}. {opt}")
    opts_block = "\n".join(opt_lines) if opt_lines else "(no options)"
    correct_block = correct_answer or "(no key)"

    return f"""You are a subject-matter expert performing Item-Objective Congruence rating (Rovinelli & Hambleton, 1977). You will judge whether a multiple-choice question measures one specific learning objective.

LEARNING OBJECTIVE:
  Title:   {objective_title}
  Content: {objective_content or "(no content excerpt)"}

QUESTION:
{question_text}

OPTIONS:
{opts_block}

CORRECT ANSWER:
{correct_block}

RATING SCALE:
  +1  The question clearly and primarily measures THIS objective.
   0  Ambiguous — the question may measure this objective, but it could also
      be measuring something else, or the connection is unclear.
  -1  The question does NOT measure this objective. It either measures a
      different concept, or it tests this concept so poorly that it does
      not work as an item for it.

Be strict. A question that touches the objective but really tests something
else (e.g. asks about a tangential fact) rates 0 or -1, not +1.

OUTPUT — strict JSON, no other text:
{{"rating": -1 | 0 | 1,
 "reasoning": "<one short sentence>"}}"""


def _call_ioc_llm(prompt: str, *, use_cache: bool = True, timeout: int = 60) -> Optional[str]:
    if use_cache:
        cached = llm_cache.get(IOC_MODEL, prompt, IOC_TEMPERATURE, json_mode=True)
        if cached is not None:
            return cached
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": IOC_MODEL,
                "prompt": prompt,
                "stream": False,
                "temperature": IOC_TEMPERATURE,
                "format": "json",
            },
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None
        result = resp.json().get("response", "")
        if result and use_cache:
            llm_cache.put(IOC_MODEL, prompt, IOC_TEMPERATURE, True, result)
        return result
    except Exception:
        return None


def _parse_rating(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    m = re.search(r'\{[\s\S]*\}', raw)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    try:
        rating = int(data.get('rating'))
    except (TypeError, ValueError):
        return None
    if rating not in VALID_RATINGS:
        return None
    return {'rating': rating, 'reasoning': (data.get('reasoning') or '').strip()}


def _resolve_objective(question: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Pull the LO (or section) that this question was anchored to from the DB.

    The project's repository.DatabaseManager does not currently expose direct
    `get_learning_object(id)` or `get_section(id)` accessors, so we go through
    the SQLAlchemy session it owns.
    """
    from models import LearningObject, Section

    session = db.get_session() if hasattr(db, 'get_session') else None
    if session is None:
        return None
    try:
        lo_id = question.get('learning_object_id')
        if lo_id:
            lo = session.query(LearningObject).filter(LearningObject.id == lo_id).first()
            if lo:
                return {
                    'title': lo.title or 'Unknown LO',
                    'content': lo.content or lo.description or '',
                    'type': 'learning_object',
                    'id': lo_id,
                }
        section_id = question.get('section_id')
        if section_id:
            section = session.query(Section).filter(Section.id == section_id).first()
            if section:
                return {
                    'title': section.title or 'Unknown section',
                    'content': section.content or section.summary or '',
                    'type': 'section',
                    'id': section_id,
                }
        return None
    finally:
        session.close()


def rate_question(question: Dict[str, Any], *, objective: Optional[Dict[str, str]] = None,
                  llm_caller=None) -> Dict[str, Any]:
    """Rate ONE question's congruence with its anchored objective."""
    call = llm_caller or _call_ioc_llm
    obj = objective or _resolve_objective(question)
    if obj is None:
        return {
            'question_id': question.get('id'),
            'available': False,
            'reason': 'Question has no learning_object_id or section_id anchor.',
        }

    prompt = build_ioc_prompt(
        question.get('question_text') or '',
        question.get('options') or [],
        question.get('correct_answer'),
        obj['title'],
        obj['content'],
    )
    raw = call(prompt)
    parsed = _parse_rating(raw or '')
    if parsed is None:
        return {
            'question_id': question.get('id'),
            'available': False,
            'reason': 'IOC LLM response could not be parsed.',
        }

    return {
        'question_id': question.get('id'),
        'available': True,
        'rating': parsed['rating'],
        'reasoning': parsed['reasoning'],
        'objective_type': obj['type'],
        'objective_id': obj['id'],
        'objective_title': obj['title'],
    }


def ioc_report(questions: List[Dict[str, Any]], *, llm_caller=None) -> Dict[str, Any]:
    """Batch IOC report. Returns per-question ratings and the aggregate IOC index."""
    total = len(questions)
    print(f'[IOC] Starting Item-Objective Congruence rating on {total} question(s) — model={IOC_MODEL}', flush=True)
    reports = []
    for i, q in enumerate(questions, start=1):
        r = rate_question(q, llm_caller=llm_caller)
        reports.append(r)
        if i == 1 or i == total or i % 5 == 0:
            verdict = r.get('rating') if r.get('available') else 'unavail'
            print(f'[IOC] {i}/{total} — Q#{q.get("id")} → {verdict}', flush=True)
    rated = [r for r in reports if r.get('available')]
    print(f'[IOC] Done. {len(rated)}/{total} rated.', flush=True)
    n = len(rated)
    if n == 0:
        return {
            'total_questions': len(reports),
            'rated_questions': 0,
            'ioc_index': None,
            'distribution': {'+1': 0, '0': 0, '-1': 0},
            'reports': reports,
            'ioc_model': IOC_MODEL,
        }

    distribution = {
        '+1': sum(1 for r in rated if r['rating'] == 1),
        '0': sum(1 for r in rated if r['rating'] == 0),
        '-1': sum(1 for r in rated if r['rating'] == -1),
    }
    ioc_index = sum(r['rating'] for r in rated) / n  # in [-1, +1]

    if ioc_index >= 0.75:
        label = 'strong'
    elif ioc_index >= 0.5:
        label = 'acceptable'
    elif ioc_index >= 0.0:
        label = 'weak'
    else:
        label = 'misaligned'

    return {
        'total_questions': len(reports),
        'rated_questions': n,
        'ioc_index': round(ioc_index, 3),
        'ioc_label': label,
        'distribution': distribution,
        'reports': reports,
        'ioc_model': IOC_MODEL,
    }
