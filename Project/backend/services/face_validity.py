"""
Distractor face validity rubric.

Quantitative metrics (Haladyna lint, embedding plausibility, diversity) miss
the *qualitative* sense in which a distractor is or is not "the kind of
thing a teacher would write". Considine et al. (2005) and Tarrant & Ware
(2008) describe a standard rubric used to review MCQ items in medical
education; the same criteria translate cleanly to any domain.

For each distractor we score four criteria 1-5 and average them into a
face-validity score. The criteria:

  1. Plausibility — could a reasonable, partially-prepared student pick
     this? (1 = trivially absurd; 5 = genuinely tempting)
  2. Representativeness — does it correspond to a real misconception or
     reasoning error a student might actually have? (1 = invented;
     5 = textbook misconception)
  3. Absence of give-aways — is the option free of absolute words
     ("uvek", "nikad", "potpuno", "samo") and grammar mismatches that
     would let a test-wise student eliminate it without subject knowledge?
     (1 = obvious give-aways; 5 = none)
  4. Clarity — is it unambiguous, properly punctuated, and free of typos?
     (1 = unparseable; 5 = clean)

The aggregate face-validity score for a question is the mean across its
distractors (the correct answer is not scored).

References:
  Considine, J., Botti, M., & Thomas, S. (2005). Design, format, validity
  and reliability of multiple choice questions for use in nursing research
  and education. Collegian 12(1), 19-24.
  Tarrant, M., & Ware, J. (2008). Impact of item-writing flaws in
  multiple-choice questions on student achievement in high-stakes nursing
  assessments. Medical Education 42(2), 198-206.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional

import requests

from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from core import llm_cache

FACE_MODEL = os.getenv("OLLAMA_FACE_MODEL") or OLLAMA_MODEL
FACE_TEMPERATURE = 0.1


def build_face_validity_prompt(question_text: str, options: List[Any],
                               correct_index: int) -> str:
    opt_lines = []
    for i, opt in enumerate(options or []):
        if isinstance(opt, dict):
            opt = opt.get('text') or opt.get('value') or ''
        marker = " ← KEY" if i == correct_index else ""
        opt_lines.append(f"  {chr(ord('A') + i)}. {opt}{marker}")
    opts_block = "\n".join(opt_lines)

    return f"""You are reviewing the DISTRACTORS (the wrong options) of a multiple-choice question, applying the face-validity rubric from Considine et al. (2005). Do NOT review the KEY — only the distractors.

QUESTION:
{question_text}

OPTIONS (the one marked KEY is correct; rate the others):
{opts_block}

For each DISTRACTOR, give four 1-5 ratings:
  - plausibility: 1 = obviously wrong, 5 = genuinely tempting
  - representativeness: 1 = invented, 5 = textbook misconception
  - no_giveaways: 1 = absolute words / grammar mismatch / silly phrasing, 5 = clean
  - clarity: 1 = unparseable, 5 = clean

OUTPUT — strict JSON, no other text. Use the option letter (A/B/C/...) as the key, and OMIT the KEY option.
{{"distractors": {{
  "A": {{"plausibility": 1-5, "representativeness": 1-5, "no_giveaways": 1-5, "clarity": 1-5}},
  ...
}}}}"""


def _call_llm(prompt: str, *, use_cache: bool = True, timeout: int = 60) -> Optional[str]:
    from core.llm_provider import call_llm
    return call_llm(
        prompt, role="face",
        temperature=FACE_TEMPERATURE, json_mode=True,
        use_cache=use_cache, timeout=timeout,
    )


_CRITERIA = ('plausibility', 'representativeness', 'no_giveaways', 'clarity')


def _clamp_rating(v: Any) -> Optional[int]:
    try:
        r = int(v)
    except (TypeError, ValueError):
        return None
    if r < 1 or r > 5:
        return None
    return r


def _parse_face_ratings(raw: str, n_options: int, correct_index: int) -> Optional[Dict[int, Dict[str, int]]]:
    if not raw:
        return None
    m = re.search(r'\{[\s\S]*\}', raw)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    block = data.get('distractors')
    if not isinstance(block, dict):
        return None

    out: Dict[int, Dict[str, int]] = {}
    for key, ratings in block.items():
        if not isinstance(ratings, dict):
            continue
        # Convert letter (A/B/...) to index.
        letter = re.match(r'[A-Za-z]', key.strip())
        if not letter:
            continue
        idx = ord(letter.group(0).upper()) - ord('A')
        if not (0 <= idx < n_options) or idx == correct_index:
            continue
        parsed_ratings: Dict[str, int] = {}
        for c in _CRITERIA:
            r = _clamp_rating(ratings.get(c))
            if r is not None:
                parsed_ratings[c] = r
        if len(parsed_ratings) == len(_CRITERIA):
            out[idx] = parsed_ratings
    return out if out else None


def assess_face_validity(question: Dict[str, Any], *, llm_caller=None) -> Dict[str, Any]:
    call = llm_caller or _call_llm
    options = question.get('options') or []
    correct_idx = question.get('correct_option_index')
    if not options or correct_idx is None or not (0 <= correct_idx < len(options)):
        return {
            'question_id': question.get('id'),
            'available': False,
            'reason': 'Missing options or correct index.',
        }

    raw = call(build_face_validity_prompt(
        question.get('question_text') or '', options, correct_idx))
    ratings_by_idx = _parse_face_ratings(raw or '', len(options), correct_idx)
    if not ratings_by_idx:
        return {
            'question_id': question.get('id'),
            'available': False,
            'reason': 'Face-validity LLM response could not be parsed.',
        }

    per_distractor = []
    all_means = []
    for idx, ratings in ratings_by_idx.items():
        mean = sum(ratings.values()) / len(ratings)
        per_distractor.append({
            'position': idx,
            'ratings': ratings,
            'mean': round(mean, 2),
        })
        all_means.append(mean)
    question_mean = round(sum(all_means) / len(all_means), 2) if all_means else None

    return {
        'question_id': question.get('id'),
        'available': True,
        'distractor_ratings': per_distractor,
        'face_validity_score': question_mean,
    }


def face_validity_report(questions: List[Dict[str, Any]], *, llm_caller=None) -> Dict[str, Any]:
    total = len(questions)
    from core.llm_provider import describe_active_model
    print(f'[FaceValidity] Starting distractor face-validity scoring on {total} question(s) — model={describe_active_model("face")}', flush=True)
    reports = []
    for i, q in enumerate(questions, start=1):
        r = assess_face_validity(q, llm_caller=llm_caller)
        reports.append(r)
        if i == 1 or i == total or i % 5 == 0:
            score = r.get('face_validity_score') if r.get('available') else 'unavail'
            print(f'[FaceValidity] {i}/{total} — Q#{q.get("id")} → score={score}', flush=True)
    available = [r for r in reports if r.get('available')]
    n = len(available)
    scores = [r['face_validity_score'] for r in available
              if r.get('face_validity_score') is not None]
    mean_score = (sum(scores) / len(scores)) if scores else None

    # Mean per criterion across all distractors of all questions.
    criterion_totals = {c: [] for c in _CRITERIA}
    for r in available:
        for d in r.get('distractor_ratings', []):
            for c, v in d.get('ratings', {}).items():
                if c in criterion_totals:
                    criterion_totals[c].append(v)
    criterion_means = {
        c: round(sum(v) / len(v), 2) if v else None
        for c, v in criterion_totals.items()
    }

    return {
        'total_questions': len(reports),
        'evaluated_questions': n,
        'mean_face_validity_score': round(mean_score, 2) if mean_score is not None else None,
        'criterion_means': criterion_means,
        'reports': reports,
        'face_model': FACE_MODEL,
    }
