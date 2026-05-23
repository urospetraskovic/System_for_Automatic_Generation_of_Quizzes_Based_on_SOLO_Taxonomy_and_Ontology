"""
Chain-of-Verification (CoVe) for MCQ correctness.

Dhuliawala et al. (2023), Chain-of-Verification Reduces Hallucination in Large
Language Models. ACL Findings 2024. https://arxiv.org/abs/2309.11495

The CoVe pipeline has four steps in the original paper:
  1. Generate baseline response.
  2. Plan verification questions to fact-check the response.
  3. Answer each verification question INDEPENDENTLY (separate call) so the
     answers are not biased by the baseline response.
  4. Generate a final verified response.

We adapt it to MCQ post-hoc verification: the question + correct answer +
source_line already exist (from the generator). The judge:
  - Plans 2-3 verification questions about the correct answer.
  - Answers each one given ONLY the source material (not the original
    question / answer).
  - Decides whether the original `correct_answer` is uniquely defensible.

If the verifier flags the answer as "not uniquely defensible", the question
is flagged for human review. This is an a-priori validity check —
no student responses needed.
"""

import json
import os
import re
from typing import Any, Callable, Dict, List, Optional

import requests

from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from core import llm_cache

COVE_MODEL = os.getenv("OLLAMA_COVE_MODEL") or OLLAMA_MODEL
COVE_TEMPERATURE = 0.1


# --------------------------------------------------------------------------
# Step 2: planner — what verification questions should we ask?
# --------------------------------------------------------------------------

def build_plan_prompt(question_text: str, correct_answer: str) -> str:
    return f"""You are a fact-checker. You will be given a multiple-choice QUESTION and a candidate CORRECT ANSWER. Your job in this step is to plan 2-3 short verification questions that, if answered from the source material, would confirm or refute the candidate answer.

QUESTION:
{question_text}

CANDIDATE CORRECT ANSWER:
{correct_answer}

Write verification questions that are SPECIFIC and SHORT. Avoid yes/no questions when a substantive answer is possible. Do NOT include the candidate answer in the verification questions.

OUTPUT — strict JSON, no other text:
{{"verification_questions": ["...", "...", "..."]}}"""


# --------------------------------------------------------------------------
# Step 3: verifier — answer each verification question from the source ONLY
# --------------------------------------------------------------------------

def build_verify_prompt(verification_question: str, source_text: str) -> str:
    return f"""You will be given a SOURCE excerpt and ONE verification question. Answer the question using ONLY the source. If the source does not contain enough information, say so explicitly.

SOURCE:
{source_text or "(no source excerpt available)"}

VERIFICATION QUESTION:
{verification_question}

OUTPUT — strict JSON, no other text:
{{"answer": "<short answer or 'NOT IN SOURCE'>",
 "supported_by_source": <true | false>}}"""


# --------------------------------------------------------------------------
# Step 4: judge — does the verifier evidence support the candidate answer?
# --------------------------------------------------------------------------

def build_judge_prompt(
    question_text: str,
    correct_answer: str,
    verification_qa: List[Dict[str, Any]],
) -> str:
    qa_lines = []
    for i, qa in enumerate(verification_qa, 1):
        qa_lines.append(
            f"  Q{i}: {qa.get('question', '')}\n"
            f"  A{i}: {qa.get('answer', '')} "
            f"(supported_by_source={qa.get('supported_by_source')})"
        )
    qa_block = "\n".join(qa_lines) if qa_lines else "(no verification Q/A pairs)"

    return f"""You will judge whether the CANDIDATE CORRECT ANSWER to a multiple-choice question is uniquely defensible given the verification evidence. Be strict — if the evidence is ambiguous, incomplete, or contradicts the candidate, flag it.

QUESTION:
{question_text}

CANDIDATE CORRECT ANSWER:
{correct_answer}

VERIFICATION EVIDENCE:
{qa_block}

OUTPUT — strict JSON, no other text:
{{"verdict": "<one of: SUPPORTED | UNDERDETERMINED | CONTRADICTED>",
 "confidence": <float 0..1>,
 "reasoning": "<one short sentence>"}}"""


# --------------------------------------------------------------------------
# LLM caller (mockable in tests)
# --------------------------------------------------------------------------

def _call_llm(prompt: str, *, use_cache: bool = True, timeout: int = 60) -> Optional[str]:
    if use_cache:
        cached = llm_cache.get(COVE_MODEL, prompt, COVE_TEMPERATURE, json_mode=True)
        if cached is not None:
            return cached
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": COVE_MODEL,
                "prompt": prompt,
                "stream": False,
                "temperature": COVE_TEMPERATURE,
                "format": "json",
            },
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None
        result = resp.json().get("response", "")
        if result and use_cache:
            llm_cache.put(COVE_MODEL, prompt, COVE_TEMPERATURE, True, result)
        return result
    except Exception:
        return None


def _parse_json(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    m = re.search(r'\{[\s\S]*\}', raw)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def verify_question(
    question: Dict[str, Any],
    *,
    llm_caller=None,
) -> Dict[str, Any]:
    """Run CoVe over one question. Returns verdict, verification trace,
    and a flag indicating whether the question needs human review."""
    call = llm_caller or _call_llm

    q_text = question.get('question_text') or ''
    correct = question.get('correct_answer') or ''
    source = question.get('source_line') or ''

    if not q_text or not correct:
        return {
            'question_id': question.get('id'),
            'verdict': None,
            'needs_review': True,
            'reason': 'Missing question text or correct answer.',
        }

    # Step 2: plan verification questions.
    plan_raw = call(build_plan_prompt(q_text, correct))
    plan = _parse_json(plan_raw or '') or {}
    vqs = plan.get('verification_questions') or []
    if not isinstance(vqs, list) or not vqs:
        return {
            'question_id': question.get('id'),
            'verdict': None,
            'needs_review': True,
            'reason': 'Verifier could not plan verification questions.',
        }

    # Step 3: answer each verification question independently.
    verification_trace: List[Dict[str, Any]] = []
    for vq in vqs[:3]:  # Cap at 3 per the original paper.
        if not isinstance(vq, str) or not vq.strip():
            continue
        verify_raw = call(build_verify_prompt(vq, source))
        verify = _parse_json(verify_raw or '') or {}
        verification_trace.append({
            'question': vq,
            'answer': verify.get('answer'),
            'supported_by_source': verify.get('supported_by_source'),
        })

    # Step 4: judge.
    judge_raw = call(build_judge_prompt(q_text, correct, verification_trace))
    judge = _parse_json(judge_raw or '') or {}
    verdict = str(judge.get('verdict', '')).strip().upper()
    if verdict not in {'SUPPORTED', 'UNDERDETERMINED', 'CONTRADICTED'}:
        verdict = None

    needs_review = verdict != 'SUPPORTED'

    confidence = judge.get('confidence')
    try:
        confidence = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence = None

    return {
        'question_id': question.get('id'),
        'verdict': verdict,
        'confidence': confidence,
        'reasoning': (judge.get('reasoning') or '').strip(),
        'verification_trace': verification_trace,
        'needs_review': needs_review,
        'cove_model': COVE_MODEL,
    }


def verify_questions(
    questions: List[Dict[str, Any]],
    *,
    llm_caller=None,
) -> Dict[str, Any]:
    """Batch CoVe. Returns aggregate stats + per-question reports."""
    total = len(questions)
    print(f'[CoVe] Starting Chain-of-Verification on {total} question(s) — model={COVE_MODEL} (4 LLM calls per question)', flush=True)
    reports = []
    for i, q in enumerate(questions, start=1):
        r = verify_question(q, llm_caller=llm_caller)
        reports.append(r)
        verdict = r.get('verdict') or 'unparseable'
        # CoVe is the slowest — log every question, not every 5.
        print(f'[CoVe] {i}/{total} — Q#{q.get("id")} → {verdict}', flush=True)
    total = len(reports)
    supported = sum(1 for r in reports if r['verdict'] == 'SUPPORTED')
    underdetermined = sum(1 for r in reports if r['verdict'] == 'UNDERDETERMINED')
    contradicted = sum(1 for r in reports if r['verdict'] == 'CONTRADICTED')
    needs_review = sum(1 for r in reports if r['needs_review'])

    return {
        'total_questions': total,
        'supported': supported,
        'underdetermined': underdetermined,
        'contradicted': contradicted,
        'needs_review': needs_review,
        'support_rate': round(100.0 * supported / total, 1) if total else 0.0,
        'reports': reports,
        'cove_model': COVE_MODEL,
    }
