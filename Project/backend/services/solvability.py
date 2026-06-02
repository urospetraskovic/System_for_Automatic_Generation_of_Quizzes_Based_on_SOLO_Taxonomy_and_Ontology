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
    from core.llm_provider import call_llm
    return call_llm(
        prompt, role="solver",
        temperature=SOLVER_TEMPERATURE, json_mode=True,
        use_cache=use_cache, timeout=timeout,
    )


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


# --------------------------------------------------------------------------
# Stem-Only Solvability — Haladyna H4 ("place the central idea in the stem")
# --------------------------------------------------------------------------
#
# Haladyna, Downing & Rodriguez (2002), rule 4:
#   "The stem should be meaningful by itself and present a definite problem.
#    A test-taker should be able to answer the question without reading the
#    options."
#
# This check measures whether the stem is self-contained: we show the LLM
# ONLY the stem (no options), ask for a free-text answer, and compare it to
# the actual correct answer via embedding cosine similarity. High similarity
# → the stem alone carries the central idea (H4 satisfied). Low similarity
# → the options carry too much of the question's meaning.

STEM_ONLY_TEMPERATURE = 0.3


def build_stem_only_prompt(question_text: str) -> str:
    return f"""You will see a question with NO multiple-choice options. Answer it briefly using only the question text. If you cannot answer from the question alone, write "UNABLE TO ANSWER".

QUESTION:
{question_text}

OUTPUT — strict JSON, no other text:
{{"answer": "<short free-text answer or 'UNABLE TO ANSWER'>"}}"""


def _parse_free_answer(raw: str) -> Optional[str]:
    if not raw:
        return None
    m = re.search(r'\{[\s\S]*\}', raw)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    ans = (data.get('answer') or '').strip()
    if not ans or ans.upper() == 'UNABLE TO ANSWER':
        return None
    return ans


def _call_stem_only_llm(prompt: str, *, use_cache: bool = True, timeout: int = 60) -> Optional[str]:
    from core.llm_provider import call_llm
    return call_llm(
        prompt, role="solver",
        temperature=STEM_ONLY_TEMPERATURE, json_mode=True,
        use_cache=use_cache, timeout=timeout,
    )


# Cosine thresholds for the verdict label. Calibrated for the default
# Ollama nomic-embed-text embeddings (same as mcq_lint plausibility).
_H4_PASS_THRESHOLD = 0.55  # ≥ this → stem-self-contained
_H4_PARTIAL_THRESHOLD = 0.35  # ≥ this but below pass → partial


# ---------------------------------------------------------------------------
# LLM-judge fallback for stem-only equivalence
# ---------------------------------------------------------------------------
# The original H4 implementation embedded both the LLM's free-text guess and
# the real correct answer, then took cosine similarity. That requires an
# embedding model. If the user has no embedding model installed (typical for
# Serbian-language users — the only one we ship hooks for is the English-
# centric nomic-embed-text via Ollama), every question gets "unavail" and the
# H4 pass rate drops to 0% — not because the items fail H4 but because we
# can't measure them at all.
#
# This LLM-judge fallback uses the active LLM provider (Haiku in the user's
# current setup) to make a binary equivalence call. The result is also
# stronger on Serbian than embedding cosine because:
#   * Haiku handles synonyms and paraphrases natively
#   * It correctly resolves negation ("ne dozvoljava" ≠ "dozvoljava")
#   * It tolerates Serbian's free word order
#   * It is the same model already used by SOLO Judge, IOC, Ambiguity, etc.,
#     so the H4 metric becomes methodologically consistent with the rest.

JUDGE_TEMPERATURE = 0.0  # near-deterministic for reproducible judging


def build_stem_only_judge_prompt(stem: str, free_answer: str, correct: str) -> str:
    """Ask the active LLM whether two candidate answers are semantically
    equivalent for a given stem. Returns a strict-JSON yes/no with reasoning."""
    return f"""You will judge whether two short answers to the same question mean the same thing.

If the two answers convey the same idea (even with different wording, synonyms, paraphrasing, or word order) → equivalent: true.
If they describe genuinely different things, contradict each other, or one is much more specific than the other → equivalent: false.

QUESTION:
{stem}

ANSWER A (LLM's guess from stem alone):
{free_answer}

ANSWER B (the actual correct answer):
{correct}

OUTPUT — strict JSON, no other text:
{{"equivalent": true|false, "reasoning": "<one short sentence>"}}"""


def _parse_judge_verdict(raw: str) -> Optional[Dict[str, Any]]:
    """Parse {'equivalent': bool, 'reasoning': str}. Returns None on bad JSON."""
    if not raw:
        return None
    m = re.search(r'\{[\s\S]*\}', raw)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or 'equivalent' not in data:
        return None
    return {
        'equivalent': bool(data.get('equivalent')),
        'reasoning': str(data.get('reasoning') or '').strip(),
    }


def _call_h4_judge_llm(prompt: str, *, use_cache: bool = True, timeout: int = 60) -> Optional[str]:
    from core.llm_provider import call_llm
    return call_llm(
        prompt, role="judge",
        temperature=JUDGE_TEMPERATURE, json_mode=True,
        use_cache=use_cache, timeout=timeout,
    )


def assess_stem_only_solvability(
    question: Dict[str, Any],
    *,
    llm_caller=None,
    embedder=None,
    cosine=None,
    judge_caller=None,
) -> Dict[str, Any]:
    """Show LLM only the stem; compare its answer to the real key.

    Comparison strategy (in order):
      1. Embedding cosine similarity, if the embedder is available.
      2. LLM-judge binary equivalence as a fallback, so installs without
         an embedding model still produce a usable H4 pass rate instead
         of "unavail" on every question.
    """
    call = llm_caller or _call_stem_only_llm
    if embedder is None or cosine is None:
        from .embedding_service import embed_text, cosine_similarity
        embedder = embedder or embed_text
        cosine = cosine or cosine_similarity

    stem = question.get('question_text') or ''
    correct = question.get('correct_answer') or ''
    if not stem or not correct:
        return {
            'question_id': question.get('id'),
            'available': False,
            'reason': 'Missing stem or correct answer.',
        }

    raw = call(build_stem_only_prompt(stem))
    free_answer = _parse_free_answer(raw or '')
    if free_answer is None:
        return {
            'question_id': question.get('id'),
            'available': True,
            'free_answer': None,
            'similarity': None,
            'verdict': 'unable',
            'h4_passes': False,
            'reasoning': 'LLM could not answer the stem alone — options likely carry critical context.',
        }

    v1 = embedder(free_answer)
    v2 = embedder(correct)
    sim = cosine(v1, v2) if (v1 is not None and v2 is not None) else None
    if sim is not None:
        if sim >= _H4_PASS_THRESHOLD:
            verdict = 'passes'
        elif sim >= _H4_PARTIAL_THRESHOLD:
            verdict = 'partial'
        else:
            verdict = 'fails'
        return {
            'question_id': question.get('id'),
            'available': True,
            'free_answer': free_answer,
            'similarity': round(sim, 3),
            'verdict': verdict,
            'h4_passes': verdict == 'passes',
            'judge': 'cosine',
        }

    # Fallback: ask the active LLM whether the two answers are equivalent.
    judge = judge_caller or _call_h4_judge_llm
    raw_judge = judge(build_stem_only_judge_prompt(stem, free_answer, correct))
    parsed = _parse_judge_verdict(raw_judge or '')
    if parsed is None:
        return {
            'question_id': question.get('id'),
            'available': False,
            'reason': 'No embedder available and LLM-judge returned an unparseable verdict.',
        }
    verdict = 'passes' if parsed['equivalent'] else 'fails'
    return {
        'question_id': question.get('id'),
        'available': True,
        'free_answer': free_answer,
        'similarity': None,
        'verdict': verdict,
        'h4_passes': parsed['equivalent'],
        'reasoning': parsed['reasoning'],
        'judge': 'llm',
    }


def stem_only_solvability_report(
    questions: List[Dict[str, Any]],
    *,
    llm_caller=None,
    embedder=None,
    cosine=None,
) -> Dict[str, Any]:
    """Batch stem-only solvability report (H4 conformance across a lesson)."""
    total = len(questions)
    from core.llm_provider import describe_active_model
    print(f'[StemOnly] Starting Haladyna H4 stem-only check on {total} question(s) — model={describe_active_model("solver")}', flush=True)
    reports = []
    for i, q in enumerate(questions, start=1):
        r = assess_stem_only_solvability(q, llm_caller=llm_caller, embedder=embedder, cosine=cosine)
        reports.append(r)
        if i == 1 or i == total or i % 5 == 0:
            verdict = r.get('verdict') if r.get('available') else 'unavail'
            print(f'[StemOnly] {i}/{total} — Q#{q.get("id")} → {verdict}', flush=True)
    available = [r for r in reports if r.get('available')]
    n = len(available)
    distribution = {'passes': 0, 'partial': 0, 'fails': 0, 'unable': 0}
    for r in available:
        v = r.get('verdict')
        if v in distribution:
            distribution[v] += 1
    pass_rate = (distribution['passes'] / n * 100) if n else None
    sims = [r['similarity'] for r in available if r.get('similarity') is not None]
    mean_sim = (sum(sims) / len(sims)) if sims else None

    return {
        'total_questions': len(reports),
        'evaluated_questions': n,
        'h4_pass_rate': round(pass_rate, 1) if pass_rate is not None else None,
        'mean_similarity': round(mean_sim, 3) if mean_sim is not None else None,
        'verdict_distribution': distribution,
        'reports': reports,
    }


def _aggregate_solvability(reports: List[Dict[str, Any]], *, total: int,
                           partial: bool) -> Dict[str, Any]:
    """Build the aggregate report dict from a (possibly incomplete) list of
    per-question reports. Used both for the final result and for checkpoints
    written mid-run so an interruption preserves what was already computed."""
    usable = [r for r in reports if r.get('available') and r.get('p_value') is not None]
    distribution = {'trivially_easy': 0, 'appropriate': 0, 'hard': 0, 'too_hard_or_misframed': 0}
    for r in usable:
        lbl = r.get('difficulty_label')
        if lbl in distribution:
            distribution[lbl] += 1
    return {
        'total_questions': total,
        'completed_questions': len(reports),
        'solvable_questions': len(usable),
        'mean_p_value': (
            round(sum(r['p_value'] for r in usable) / len(usable), 3) if usable else None
        ),
        'difficulty_distribution': distribution,
        'reports': reports,
        'solver_model': SOLVER_MODEL,
        'partial': partial,
    }


# Checkpoint cadence for solvability's progressive cache: every N questions.
# Tuned to be frequent enough that an abort loses at most ~5 questions of
# work, but infrequent enough that the SQLite writes don't dominate.
_SOLVABILITY_CHECKPOINT_EVERY = 5

# Metric key used for per-question validation_cache entries. Keeping it
# distinct from the lesson-level "solvability" key lets both coexist:
# the lesson aggregate is the partial/full report, while each question's
# raw per-question result is keyed under this so a re-run can true-resume
# instead of recomputing already-solved questions.
_PER_QUESTION_METRIC_KEY = "solvability_q"


def _per_question_cache_get(question_id, n_trials):
    """Return the cached per-question solvability result, or None on
    miss / n_trials mismatch / DB error. n_trials must match because a
    cached p_value at n_trials=5 is not interchangeable with one at n=3."""
    if question_id is None:
        return None
    try:
        from services import validation_cache
        cached = validation_cache.get(
            _PER_QUESTION_METRIC_KEY, question_id, scope_type='question'
        )
    except Exception:
        return None
    if not cached or cached.get('n_trials_used') != n_trials:
        return None
    return cached


def _per_question_cache_put(question_id, payload):
    if question_id is None:
        return
    try:
        from services import validation_cache
        validation_cache.put(
            _PER_QUESTION_METRIC_KEY, question_id, payload, scope_type='question'
        )
    except Exception:
        pass


def solvability_report(
    questions: List[Dict[str, Any]],
    *,
    n_trials: int = DEFAULT_TRIALS,
    shuffle: bool = True,
    llm_caller=None,
    progress_cache_fn=None,
    use_question_cache: bool = True,
) -> Dict[str, Any]:
    """Batch solvability report for a list of questions.

    progress_cache_fn, if provided, receives a partial aggregate every
    _SOLVABILITY_CHECKPOINT_EVERY questions. The route uses this to write
    intermediate state to validation_cache so an interrupted run survives.

    use_question_cache (default True) makes each question's result persist
    individually under metric_key=solvability_q, scope_type=question. On a
    re-run the function checks this cache before calling the LLM, so any
    questions completed in a previous (possibly interrupted) run are
    skipped instantly. This is the real "resume" behaviour: even if the
    aggregate checkpoint missed a question, that question's per-question
    cache survives. Tests set this to False to keep them hermetic.
    """
    total = len(questions)
    expected_calls = total * n_trials
    from core.llm_provider import describe_active_model
    print(f'[Solvability] Starting LLM-blind solver on {total} question(s) — model={describe_active_model("solver")}, n_trials={n_trials}', flush=True)
    print(f'[Solvability]   This will make up to {expected_calls} LLM calls total. With local Ollama this can take HOURS.', flush=True)
    reports = []
    cache_hits = 0
    for i, q in enumerate(questions, start=1):
        q_id = q.get('id')

        # Resume path: a per-question cached result with matching n_trials
        # short-circuits the LLM call entirely. This is what makes a
        # second "Run all" finish in seconds instead of minutes.
        cached_q = _per_question_cache_get(q_id, n_trials) if use_question_cache else None
        if cached_q is not None:
            reports.append(cached_q)
            cache_hits += 1
            print(f'[Solvability] {i}/{total} — Q#{q_id} → cached (resume)', flush=True)
        else:
            r = assess_solvability(q, n_trials=n_trials, shuffle=shuffle, llm_caller=llm_caller)
            # Annotate so future cache reads can detect n_trials mismatch.
            r['n_trials_used'] = n_trials
            reports.append(r)
            if use_question_cache:
                _per_question_cache_put(q_id, r)
            p = r.get('p_value') if r.get('available') else 'unavail'
            label = r.get('difficulty_label', '')
            print(f'[Solvability] {i}/{total} — Q#{q_id} → p={p} ({label})', flush=True)

        # Progressive checkpoint: persist partial aggregate every N questions
        # so an interruption (server restart, user closes tab, network blip)
        # doesn't throw away the work we already did.
        if progress_cache_fn is not None and i < total and i % _SOLVABILITY_CHECKPOINT_EVERY == 0:
            try:
                progress_cache_fn(_aggregate_solvability(reports, total=total, partial=True))
            except Exception:
                # Checkpoint failure should never abort the actual run.
                pass

    if cache_hits:
        print(f'[Solvability] Resumed: {cache_hits}/{total} question(s) loaded from per-question cache.', flush=True)
    return _aggregate_solvability(reports, total=total, partial=False)
