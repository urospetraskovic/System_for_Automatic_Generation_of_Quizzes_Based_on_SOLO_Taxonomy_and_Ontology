"""
MCQ Lint — automatic quality checks for multiple-choice questions.

Implements the automatable subset of the Haladyna, Downing & Rodriguez (2002)
31-rule taxonomy for multiple-choice item writing. Each check emits a flag
with a stable code (e.g. H17_NEGATIVE_STEM), a severity (info/warn/error),
and a human-readable message in Serbian + English.

Rules covered (rule numbers reference Haladyna 2002):

  H14  stem must end with a clear directive (question mark or imperative)
  H16  stem must not contain excessive "window dressing"
  H17  negatives in the stem (NE/NIJE/OSIM/NOT/EXCEPT) must be emphasized
  H19  exactly one correct option must be designated
  H21  numeric options must be in ascending or descending order
  H22  options must not overlap (no near-duplicate distractors)
  H24  option lengths must be roughly equal (no length clue)
  H25  avoid "all of the above" / "none of the above"
  H27  the correct answer must not be the longest option (length clue)
  H_BLANK  no option may be empty
  H_OPTION_COUNT  unusual number of options (must be 3-5)

Rules requiring domain expertise (H2 trivial content, H5 over-specific,
H6 opinion-based) are out of scope for automated linting and are flagged
to a separate LLM-judge service.
"""

import re
from typing import Any, Callable, Dict, List, Optional, Tuple

SEVERITY_ERROR = 'error'
SEVERITY_WARN = 'warn'
SEVERITY_INFO = 'info'

# Cosine similarity thresholds for embedding-based distractor checks.
# These follow Bitew et al. 2023 + BERTScore practice and are calibrated for
# Ollama nomic-embed-text. Tunable via env if needed.
_PLAUSIBILITY_MIN = 0.40   # below = trivially-wrong distractor
_PLAUSIBILITY_MAX = 0.92   # above = paraphrase of correct → ambiguous
_DIVERSITY_MAX = 0.92      # pairs of distractors above this are near-duplicates

# Negation tokens that, if present in the stem without bold/underline emphasis,
# trigger H17. Covers Serbian (sr) and English (en).
_NEGATION_TOKENS_SR = {'ne', 'nije', 'nisu', 'osim', 'izuzev', 'netačno'}
_NEGATION_TOKENS_EN = {'not', 'except', 'never', 'incorrect'}
_NEGATION_TOKENS = _NEGATION_TOKENS_SR | _NEGATION_TOKENS_EN

# "All / none of the above" phrases (sr + en).
_AOTA_NOTA_PATTERNS = [
    re.compile(r'\ball of the above\b', re.IGNORECASE),
    re.compile(r'\bnone of the above\b', re.IGNORECASE),
    re.compile(r'\bsvi (od )?navedeni[hm]?\b', re.IGNORECASE),
    re.compile(r'\bnijedan (od )?navedeni[hm]?\b', re.IGNORECASE),
    re.compile(r'\bsve (od )?navedeno\b', re.IGNORECASE),
    re.compile(r'\bništa (od )?navedeno\b', re.IGNORECASE),
]

# Emphasis markers: any of these around a negation suppresses H17.
_EMPHASIS_RE = re.compile(r'(<b>|<strong>|\*\*|__|<u>)')

# Window-dressing threshold: stems beyond this length earn an H16 warning.
_STEM_LONG_CHARS = 250
# Option length disparity threshold (longest / shortest ratio).
_LENGTH_RATIO_WARN = 2.0
# Distractor near-duplicate threshold (Jaccard token similarity).
_DISTRACTOR_OVERLAP_THRESHOLD = 0.7


def _flag(code: str, severity: str, message: str, **extra) -> Dict[str, Any]:
    out = {'code': code, 'severity': severity, 'message': message}
    out.update(extra)
    return out


def _option_text(opt: Any) -> str:
    """Coerce an option (str or dict) into its text content."""
    if isinstance(opt, str):
        return opt.strip()
    if isinstance(opt, dict):
        return str(opt.get('text') or opt.get('value') or '').strip()
    return ''


def _tokens(text: str) -> List[str]:
    return re.findall(r'\w+', (text or '').lower())


def _jaccard(a: str, b: str) -> float:
    ta, tb = set(_tokens(a)), set(_tokens(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _check_stem(stem: str) -> List[Dict[str, Any]]:
    flags: List[Dict[str, Any]] = []
    stripped = (stem or '').strip()
    if not stripped:
        flags.append(_flag(
            'H14_NO_STEM', SEVERITY_ERROR,
            'Pitanje nema tekst (stem) / Question has no stem.'
        ))
        return flags

    # H14: clear directive — question mark, or stem looks imperative.
    if '?' not in stripped and not re.match(r'^(definiši|navedi|opiši|objasni|odredi|izračunaj|define|describe|explain|determine|calculate)\b', stripped.lower()):
        flags.append(_flag(
            'H14_UNCLEAR_DIRECTIVE', SEVERITY_WARN,
            'Stem nema jasnu direktivu (znak pitanja ili imperativ). / Stem lacks a clear directive.'
        ))

    # H16: window dressing — overlong stem.
    if len(stripped) > _STEM_LONG_CHARS:
        flags.append(_flag(
            'H16_LONG_STEM', SEVERITY_WARN,
            f'Stem je predugačak ({len(stripped)} karaktera, preporuka < {_STEM_LONG_CHARS}). / Stem too long.',
            length=len(stripped),
        ))

    # H17: negation in the stem must be emphasized.
    lowered_tokens = re.findall(r'\w+', stripped.lower())
    negations_found = [t for t in lowered_tokens if t in _NEGATION_TOKENS]
    if negations_found and not _EMPHASIS_RE.search(stripped):
        # 'ne' is a common Serbian particle — only flag if it modifies a verb
        # adjacent to it. Heuristic: require a length signal (>= 3 char negation)
        # or a strong token like "osim"/"izuzev"/"not"/"except".
        strong = [t for t in negations_found if t in {'osim', 'izuzev', 'nije', 'nisu', 'netačno', 'not', 'except', 'never', 'incorrect'}]
        if strong:
            flags.append(_flag(
                'H17_NEGATIVE_STEM', SEVERITY_WARN,
                f'Negacija u stem-u ({", ".join(strong)}) nije istaknuta. Podebljaj ili podvuci. / Negation in stem not emphasized.',
                tokens=strong,
            ))

    return flags


def _check_options(
    options: List[Any],
    correct_index: Optional[int],
    correct_answer: Optional[str],
) -> List[Dict[str, Any]]:
    flags: List[Dict[str, Any]] = []
    texts = [_option_text(o) for o in (options or [])]

    # H_OPTION_COUNT
    if len(texts) < 3 or len(texts) > 5:
        flags.append(_flag(
            'H_OPTION_COUNT', SEVERITY_WARN,
            f'Neuobičajen broj opcija ({len(texts)}). Preporuka: 3–5. / Unusual option count.',
            count=len(texts),
        ))

    # H_BLANK
    blanks = [i for i, t in enumerate(texts) if not t]
    if blanks:
        flags.append(_flag(
            'H_BLANK', SEVERITY_ERROR,
            f'Prazna(e) opcija(e) na pozicijama {blanks}. / Empty option(s).',
            positions=blanks,
        ))

    # H19: exactly one designated correct answer, in range.
    if correct_index is None:
        flags.append(_flag(
            'H19_NO_KEY', SEVERITY_ERROR,
            'Nije označen tačan odgovor. / No correct option designated.'
        ))
    elif not (0 <= correct_index < len(texts)):
        flags.append(_flag(
            'H19_KEY_OUT_OF_RANGE', SEVERITY_ERROR,
            f'Indeks tačnog odgovora ({correct_index}) van opsega opcija. / Correct index out of range.'
        ))
    elif correct_answer:
        # Soft check: correct_answer text should appear at correct_index.
        expected = _option_text(options[correct_index])
        if expected and correct_answer.strip() and expected.strip().lower() != correct_answer.strip().lower():
            flags.append(_flag(
                'H19_KEY_MISMATCH', SEVERITY_WARN,
                'Tekst tačnog odgovora ne podudara se sa opcijom na označenom indeksu. / Correct text does not match designated option.',
            ))

    # H21: numeric options must be ordered.
    nums: List[Optional[float]] = []
    for t in texts:
        m = re.fullmatch(r'\s*-?\d+(?:[.,]\d+)?\s*', t or '')
        nums.append(float(m.group(0).replace(',', '.')) if m else None)
    if texts and all(n is not None for n in nums):
        is_asc = all(nums[i] <= nums[i + 1] for i in range(len(nums) - 1))
        is_desc = all(nums[i] >= nums[i + 1] for i in range(len(nums) - 1))
        if not (is_asc or is_desc):
            flags.append(_flag(
                'H21_NUMERIC_DISORDER', SEVERITY_WARN,
                'Numeričke opcije nisu u rastućem/opadajućem redosledu. / Numeric options not ordered.',
            ))

    # H22: distractor near-duplicates.
    seen_pairs = set()
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            if not texts[i] or not texts[j]:
                continue
            if _jaccard(texts[i], texts[j]) >= _DISTRACTOR_OVERLAP_THRESHOLD:
                seen_pairs.add((i, j))
    for i, j in seen_pairs:
        flags.append(_flag(
            'H22_OPTION_OVERLAP', SEVERITY_WARN,
            f'Opcije {i} i {j} previše se preklapaju (tekst je gotovo isti). / Options overlap.',
            positions=[i, j],
        ))

    # H24, H27: length parity + correct-answer-longest length clue.
    lengths = [len(t) for t in texts if t]
    if len(lengths) >= 2:
        lo, hi = min(lengths), max(lengths)
        if lo > 0 and hi / lo > _LENGTH_RATIO_WARN:
            flags.append(_flag(
                'H24_LENGTH_DISPARITY', SEVERITY_WARN,
                f'Razlika u dužini opcija je velika (najduža {hi} vs najkraća {lo} karaktera). / Option length disparity.',
                min_length=lo, max_length=hi,
            ))
        if correct_index is not None and 0 <= correct_index < len(texts):
            correct_len = len(texts[correct_index])
            if correct_len == hi and correct_len > lo:
                flags.append(_flag(
                    'H27_CORRECT_LONGEST', SEVERITY_WARN,
                    'Tačan odgovor je najduži — klasičan length-clue. Izjednači dužine. / Correct answer is longest (length clue).',
                ))

    # H25: avoid "all/none of the above".
    for i, t in enumerate(texts):
        for pat in _AOTA_NOTA_PATTERNS:
            if pat.search(t):
                flags.append(_flag(
                    'H25_AOTA_NOTA', SEVERITY_WARN,
                    f'Opcija {i} koristi "{t}" — izbegavaj "svi/nijedan od navedenih". / "All/None of the above" discouraged.',
                    position=i,
                ))
                break

    return flags


def _check_embeddings(
    options: List[Any],
    correct_index: Optional[int],
    embedder: Callable[[str], Optional[List[float]]],
    cosine: Callable[[List[float], List[float]], Optional[float]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Embedding-based distractor plausibility (Bitew 2023) and diversity (Falchikov 2008).

    Returns (flags, similarity_summary). If embeddings are unavailable, both
    are empty — callers see no embedding flags but the rest of lint works.
    """
    flags: List[Dict[str, Any]] = []
    summary: Dict[str, Any] = {}

    if correct_index is None or not (0 <= correct_index < len(options)):
        return flags, summary

    texts = [_option_text(o) for o in options]
    if any(not t for t in texts):
        return flags, summary

    vectors: List[Optional[List[float]]] = [embedder(t) for t in texts]
    if any(v is None for v in vectors):
        # Embedding model unavailable. Skip silently.
        return flags, summary

    key_vec = vectors[correct_index]
    sims_to_key: List[Tuple[int, float]] = []
    for i, v in enumerate(vectors):
        if i == correct_index:
            continue
        s = cosine(key_vec, v)
        if s is None:
            continue
        sims_to_key.append((i, s))
        if s < _PLAUSIBILITY_MIN:
            flags.append(_flag(
                'D_PLAUS_TOO_LOW', SEVERITY_WARN,
                f'Distraktor {i} previše udaljen od tačnog odgovora '
                f'(cos={s:.2f} < {_PLAUSIBILITY_MIN}) — trivijalno netačan. '
                f'/ Distractor too dissimilar from key (Bitew 2023).',
                position=i, similarity=round(s, 3),
            ))
        elif s > _PLAUSIBILITY_MAX:
            flags.append(_flag(
                'D_PLAUS_TOO_HIGH', SEVERITY_WARN,
                f'Distraktor {i} previše sličan tačnom odgovoru '
                f'(cos={s:.2f} > {_PLAUSIBILITY_MAX}) — moguća dvosmislenost. '
                f'/ Distractor too similar to key.',
                position=i, similarity=round(s, 3),
            ))

    # Pairwise distractor diversity.
    distractor_idx = [i for i in range(len(texts)) if i != correct_index]
    pair_sims: List[Tuple[int, int, float]] = []
    for i in range(len(distractor_idx)):
        for j in range(i + 1, len(distractor_idx)):
            a, b = distractor_idx[i], distractor_idx[j]
            s = cosine(vectors[a], vectors[b])
            if s is None:
                continue
            pair_sims.append((a, b, s))
            if s > _DIVERSITY_MAX:
                flags.append(_flag(
                    'D_DIVERSITY_LOW', SEVERITY_WARN,
                    f'Distraktori {a} i {b} previše slični jedan drugom '
                    f'(cos={s:.2f}) — nedostatak diverziteta. '
                    f'/ Distractor pair too similar (Falchikov 2008).',
                    positions=[a, b], similarity=round(s, 3),
                ))

    if sims_to_key:
        summary['distractor_key_similarity'] = [
            {'position': i, 'cosine': round(s, 3)} for i, s in sims_to_key
        ]
        summary['mean_plausibility'] = round(
            sum(s for _, s in sims_to_key) / len(sims_to_key), 3
        )
    if pair_sims:
        summary['distractor_pair_similarity'] = [
            {'positions': [a, b], 'cosine': round(s, 3)} for a, b, s in pair_sims
        ]
        summary['mean_diversity'] = round(
            1.0 - sum(s for _, _, s in pair_sims) / len(pair_sims), 3
        )

    return flags, summary


def lint_question(
    question: Dict[str, Any],
    *,
    embedder: Optional[Callable[[str], Optional[List[float]]]] = None,
    cosine: Optional[Callable[[List[float], List[float]], Optional[float]]] = None,
    use_embeddings: bool = True,
) -> Dict[str, Any]:
    """Run the automatable Haladyna checks against a single question.

    `question` is a dict in the shape produced by `Question.to_dict()`.
    Returns a dict with a flat `flags` list, aggregate counters, and
    (when embeddings are available) an `embeddings` summary block.

    `embedder` / `cosine` are injectable for tests; production code passes
    `use_embeddings=True` and lazily imports the Ollama-backed service.
    """
    stem = question.get('question_text') or ''
    options = question.get('options') or []
    correct_index = question.get('correct_option_index')
    correct_answer = question.get('correct_answer')

    flags: List[Dict[str, Any]] = []
    flags.extend(_check_stem(stem))
    flags.extend(_check_options(options, correct_index, correct_answer))

    embed_summary: Dict[str, Any] = {}
    if use_embeddings and options and correct_index is not None:
        if embedder is None or cosine is None:
            from .embedding_service import embed_text, cosine_similarity
            embedder = embedder or embed_text
            cosine = cosine or cosine_similarity
        emb_flags, embed_summary = _check_embeddings(options, correct_index, embedder, cosine)
        flags.extend(emb_flags)

    counts = {SEVERITY_ERROR: 0, SEVERITY_WARN: 0, SEVERITY_INFO: 0}
    for f in flags:
        counts[f['severity']] = counts.get(f['severity'], 0) + 1

    # 0–100 score: subtract 15 per error, 5 per warn (floored at 0).
    score = max(0, 100 - 15 * counts[SEVERITY_ERROR] - 5 * counts[SEVERITY_WARN])

    result = {
        'question_id': question.get('id'),
        'flags': flags,
        'counts': counts,
        'score': score,
    }
    if embed_summary:
        result['embeddings'] = embed_summary
    return result


def lint_questions(
    questions: List[Dict[str, Any]],
    *,
    use_embeddings: bool = True,
    embedder: Optional[Callable[[str], Optional[List[float]]]] = None,
    cosine: Optional[Callable[[List[float], List[float]], Optional[float]]] = None,
) -> Dict[str, Any]:
    """Batch lint — returns per-question reports plus aggregate stats."""
    reports = [
        lint_question(q, embedder=embedder, cosine=cosine, use_embeddings=use_embeddings)
        for q in questions
    ]
    total = len(reports)
    avg_score = sum(r['score'] for r in reports) / total if total else 0.0
    aggregate_counts = {SEVERITY_ERROR: 0, SEVERITY_WARN: 0, SEVERITY_INFO: 0}
    flag_frequency: Dict[str, int] = {}
    for r in reports:
        for k in aggregate_counts:
            aggregate_counts[k] += r['counts'].get(k, 0)
        for f in r['flags']:
            flag_frequency[f['code']] = flag_frequency.get(f['code'], 0) + 1

    # Aggregate embedding metrics across questions that produced them.
    with_embeddings = [r for r in reports if r.get('embeddings')]
    aggregate_embeddings: Dict[str, Any] = {}
    if with_embeddings:
        plaus_vals = [r['embeddings'].get('mean_plausibility')
                      for r in with_embeddings if r['embeddings'].get('mean_plausibility') is not None]
        div_vals = [r['embeddings'].get('mean_diversity')
                    for r in with_embeddings if r['embeddings'].get('mean_diversity') is not None]
        if plaus_vals:
            aggregate_embeddings['mean_plausibility'] = round(sum(plaus_vals) / len(plaus_vals), 3)
        if div_vals:
            aggregate_embeddings['mean_diversity'] = round(sum(div_vals) / len(div_vals), 3)
        aggregate_embeddings['coverage'] = round(100.0 * len(with_embeddings) / total, 1) if total else 0.0

    result = {
        'total_questions': total,
        'average_score': round(avg_score, 1),
        'aggregate_counts': aggregate_counts,
        'flag_frequency': dict(sorted(flag_frequency.items(), key=lambda kv: -kv[1])),
        'reports': reports,
    }
    if aggregate_embeddings:
        result['embeddings_summary'] = aggregate_embeddings
    return result
