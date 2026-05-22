"""
Cloze-style distractor generation — Aldabe et al. (2009).

In the original ArikIturri system, distractors for fact-based MCQs are
selected from the source corpus itself: the model picks "sibling concepts"
— other terms that occupy similar positions in the same type of sentence
as the correct answer. This produces distractors that are anchored in real
text rather than hallucinated.

We adapt that idea using the project's existing structure: every lesson is
already parsed into LearningObjects, each with a list of `keywords`. For a
unistructural question whose correct answer corresponds to one LO/keyword,
sibling concepts are the OTHER keywords that:
  * belong to the SAME section (closest topical neighbours),
  * or the same lesson if the section has too few alternatives,
  * filtered out the correct answer itself and trivial near-duplicates.

The output is a ranked list of candidate distractors. The LLM-based
generator already produces three distractors per question; this module
provides a *fallback* / *complement*: if the LLM ones are weak (caught by
the embedding-plausibility lint), the generator can swap in cloze
distractors from the same source.

References:
  Aldabe, I., de Lacalle, M. L., Maritxalar, M., Martinez, E., & Uria, L.
  (2006). ArikIturri: An Automatic Question Generator Based on Corpora and
  NLP Techniques. AI in Education, IOS Press, 584-594.
  Aldabe, I., & Maritxalar, M. (2010). Automatic Distractor Generation for
  Domain Specific Texts. Lecture Notes in Computer Science 6233, 27-38.
"""

import re
from typing import Any, Dict, List, Optional


def _normalise(s: str) -> str:
    return re.sub(r'\s+', ' ', (s or '').strip().lower())


def _is_near_duplicate(a: str, b: str) -> bool:
    """True if two normalised concepts overlap heavily enough to count as the same."""
    na, nb = _normalise(a), _normalise(b)
    if not na or not nb:
        return True
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    # Token-level Jaccard >= 0.7 → near-duplicate (e.g. "Proces" vs "Procesi").
    ta = set(re.findall(r'\w+', na))
    tb = set(re.findall(r'\w+', nb))
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.7


def gather_sibling_concepts(
    section_los: List[Dict[str, Any]],
    lesson_los: List[Dict[str, Any]],
    correct_answer: str,
    *,
    max_candidates: int = 12,
) -> List[Dict[str, Any]]:
    """Collect sibling-concept candidates ranked by topical proximity.

    Section keywords rank highest (closest neighbours), lesson keywords
    fall back next. Each candidate is annotated with the LO it came from
    and a `proximity` field that the generator can use to pick its top-N.
    """
    seen_norm = set([_normalise(correct_answer)]) if correct_answer else set()

    candidates: List[Dict[str, Any]] = []

    def _add(text: str, lo: Dict[str, Any], proximity: str) -> None:
        if not text:
            return
        nrm = _normalise(text)
        if not nrm or nrm in seen_norm:
            return
        # Drop anything that's a near-duplicate of the correct answer too —
        # a sibling that overlaps heavily with the key is not a distractor,
        # it is the key in disguise.
        if correct_answer and _is_near_duplicate(text, correct_answer):
            return
        if any(_is_near_duplicate(text, c['concept']) for c in candidates):
            return
        seen_norm.add(nrm)
        candidates.append({
            'concept': text.strip(),
            'lo_id': lo.get('id'),
            'lo_title': lo.get('title'),
            'proximity': proximity,
        })

    # Section keywords (closest siblings).
    for lo in section_los or []:
        if lo.get('title'):
            _add(lo['title'], lo, 'section')
        for kw in (lo.get('keywords') or []):
            if isinstance(kw, str):
                _add(kw, lo, 'section')

    # Lesson keywords (broader siblings) — only if we don't already have many.
    if len(candidates) < max_candidates:
        for lo in lesson_los or []:
            if lo in (section_los or []):
                continue
            if lo.get('title'):
                _add(lo['title'], lo, 'lesson')
            for kw in (lo.get('keywords') or []):
                if isinstance(kw, str):
                    _add(kw, lo, 'lesson')
            if len(candidates) >= max_candidates:
                break

    # Stable priority: section first, then lesson; preserves insertion order
    # inside each tier (which mirrors the document order).
    return sorted(candidates, key=lambda c: 0 if c['proximity'] == 'section' else 1)[:max_candidates]


def suggest_cloze_distractors(
    question: Dict[str, Any],
    section_los: List[Dict[str, Any]],
    lesson_los: List[Dict[str, Any]],
    *,
    n: int = 3,
) -> Dict[str, Any]:
    """Return the top-N cloze-style sibling-concept distractors for a question.

    The caller decides whether to USE these or just compare against the
    existing LLM-generated distractors. The function is pure (no LLM call)
    and runs in milliseconds.
    """
    correct = question.get('correct_answer') or ''
    pool = gather_sibling_concepts(section_los, lesson_los, correct)
    distractors = pool[:n]
    return {
        'question_id': question.get('id'),
        'requested': n,
        'available_pool_size': len(pool),
        'distractors': distractors,
    }


def format_pool_for_prompt(pool: List[Dict[str, Any]]) -> str:
    """Render a sibling-concept pool as a short text block to inject into
    the question-generation prompt."""
    if not pool:
        return ''
    lines = ["CLOZE-STYLE DISTRACTOR POOL (Aldabe 2009 — pick distractors from these source-grounded sibling concepts when they fit):"]
    for c in pool:
        prox = c['proximity']
        lo = c.get('lo_title') or 'unknown'
        lines.append(f"  - {c['concept']} (from LO '{lo}', proximity={prox})")
    return "\n".join(lines)
