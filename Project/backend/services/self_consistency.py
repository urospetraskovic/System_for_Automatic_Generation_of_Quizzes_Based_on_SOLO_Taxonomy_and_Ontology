"""
Self-consistency sampling for MCQ generation (Wang et al. 2022, ICLR 2023).

The original Wang paper used self-consistency for arithmetic reasoning: sample
multiple chain-of-thought paths, then majority-vote the final answer. For our
domain — multiple-choice question writing — there is no single "answer" to
vote on, so we adapt the idea:

  1. Generate N candidate questions for the same target (lesson + SOLO level).
  2. Score each candidate with the Haladyna lint + embedding-based plausibility
     and diversity (Bitew 2023, Falchikov 2008).
  3. Return the candidate with the highest composite score.

Citation:
  Wang, X., Wei, J., Schuurmans, D., Le, Q., Chi, E., Narang, S., Chowdhery, A.,
  Zhou, D. (2023). Self-Consistency Improves Chain of Thought Reasoning in
  Language Models. ICLR 2023.
  https://arxiv.org/abs/2203.11171

Composite score:
  Base = lint score (0-100, Haladyna lint).
  Plausibility bonus: +0 if mean_plausibility is in [0.40, 0.92], -10 otherwise.
  Diversity bonus: +0 if no D_DIVERSITY_LOW flags, -5 otherwise.
  The lint already deducts for each flag, so we just nudge by embedding signal
  where it exists. Candidates without embeddings fall back to pure lint.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple

from .mcq_lint import lint_question


# Penal for ambiguity flag in composite scoring (option D from the validity
# layer). Set deliberately mild (-5) because ambiguity detection is a softer
# LLM-judge call than the deterministic Haladyna rules — we do not want one
# false-positive ambiguity flag to demote an otherwise clean candidate by too
# much. The selector still uses the lint base score as the dominant signal.
_AMBIGUITY_PENALTY = 5


def score_candidate(
    candidate: Dict[str, Any],
    *,
    embedder: Optional[Callable[[str], Optional[List[float]]]] = None,
    cosine: Optional[Callable[[List[float], List[float]], Optional[float]]] = None,
    use_embeddings: bool = True,
    check_ambiguity: bool = False,
    ambiguity_caller: Optional[Callable[[str], Optional[str]]] = None,
) -> Dict[str, Any]:
    """Return {'score': composite, 'lint_score': base, 'lint_report': ...} for
    one candidate question dict.

    `check_ambiguity` is opt-in because it adds one LLM call per candidate.
    When True, the candidate is also scored against `services.ambiguity` —
    an `ambiguous=true` verdict subtracts 5 from the composite score.
    `ambiguity_caller` is injectable for tests; production code can leave it
    None to use the real Ollama-backed judge.
    """
    report = lint_question(
        candidate,
        embedder=embedder,
        cosine=cosine,
        use_embeddings=use_embeddings,
    )
    base = report['score']
    bonus = 0

    embed = report.get('embeddings') or {}
    mp = embed.get('mean_plausibility')
    if mp is not None and not (0.40 <= mp <= 0.92):
        bonus -= 10

    has_diversity_flag = any(f['code'] == 'D_DIVERSITY_LOW' for f in report['flags'])
    if has_diversity_flag:
        bonus -= 5

    ambiguity_report: Optional[Dict[str, Any]] = None
    if check_ambiguity:
        from .ambiguity import assess_ambiguity
        ambiguity_report = assess_ambiguity(candidate, llm_caller=ambiguity_caller)
        if ambiguity_report.get('available') and ambiguity_report.get('ambiguous'):
            bonus -= _AMBIGUITY_PENALTY

    result: Dict[str, Any] = {
        'score': max(0, base + bonus),
        'lint_score': base,
        'bonus': bonus,
        'lint_report': report,
    }
    if ambiguity_report is not None:
        result['ambiguity_report'] = ambiguity_report
    return result


def pick_best_question(
    candidates: List[Dict[str, Any]],
    *,
    embedder: Optional[Callable[[str], Optional[List[float]]]] = None,
    cosine: Optional[Callable[[List[float], List[float]], Optional[float]]] = None,
    use_embeddings: bool = True,
    check_ambiguity: bool = False,
    ambiguity_caller: Optional[Callable[[str], Optional[str]]] = None,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """Pick the best of N candidate questions.

    Returns (best_candidate, all_scored). `all_scored[i]` mirrors the order
    of `candidates` and carries the score breakdown so the caller can log /
    audit the decision (good for the research write-up).
    """
    if not candidates:
        return None, []

    scored = []
    for c in candidates:
        s = score_candidate(
            c,
            embedder=embedder,
            cosine=cosine,
            use_embeddings=use_embeddings,
            check_ambiguity=check_ambiguity,
            ambiguity_caller=ambiguity_caller,
        )
        s['candidate'] = c
        scored.append(s)

    best = max(scored, key=lambda s: s['score'])
    return best['candidate'], scored


def generate_with_self_consistency(
    generator_fn: Callable[[], Optional[Dict[str, Any]]],
    *,
    n: int = 3,
    embedder: Optional[Callable[[str], Optional[List[float]]]] = None,
    cosine: Optional[Callable[[List[float], List[float]], Optional[float]]] = None,
    use_embeddings: bool = True,
    check_ambiguity: bool = False,
    ambiguity_caller: Optional[Callable[[str], Optional[str]]] = None,
) -> Dict[str, Any]:
    """Run `generator_fn` N times and keep the best candidate.

    `generator_fn` is a zero-argument closure that produces one question dict
    (or None on failure). The caller is responsible for constructing it
    (e.g., binding the SOLO level, lesson, source text). This keeps the
    selector pure and trivially testable.

    When `check_ambiguity=True`, each candidate also runs through the
    ambiguity LLM-judge (Downing 2005); an `ambiguous=true` verdict
    subtracts 5 from the composite score so non-ambiguous candidates are
    preferred. This adds one LLM call per candidate — opt-in for that
    reason.
    """
    candidates: List[Dict[str, Any]] = []
    for _ in range(max(1, n)):
        c = generator_fn()
        if c is not None:
            candidates.append(c)

    best, scored = pick_best_question(
        candidates,
        embedder=embedder,
        cosine=cosine,
        use_embeddings=use_embeddings,
        check_ambiguity=check_ambiguity,
        ambiguity_caller=ambiguity_caller,
    )

    # Strip the inner candidate dict from `scored` to avoid duplicating data
    # in the API response — caller already has `best`.
    audit = [
        {k: v for k, v in s.items() if k != 'candidate'}
        for s in scored
    ]
    return {
        'best': best,
        'attempted': len(candidates),
        'requested': max(1, n),
        'scores': [s['score'] for s in scored],
        'audit': audit,
    }
