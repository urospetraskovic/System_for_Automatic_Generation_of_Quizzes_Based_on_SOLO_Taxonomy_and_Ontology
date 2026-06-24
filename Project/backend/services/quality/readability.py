"""
Readability metrics for MCQ stems.

Implements the classical Flesch Reading Ease and Flesch-Kincaid Grade Level
formulas (Flesch 1948; Kincaid et al. 1975). The Grade Level estimates which
US school grade can comfortably read the text. For a SOLO-aligned test,
the stem's reading grade should match the cognitive level being tested —
otherwise the question is partly measuring reading ability instead of the
target concept (Wood et al. 2007 on test fairness).

Two important caveats:

1. The original formulas are calibrated for English. For Serbian, the
   syllable counter falls back to vowel-group counting (the standard
   language-agnostic approximation used in most readability libraries
   for non-English text). The relative comparison between two stems
   in the SAME language remains valid; absolute grade levels for Serbian
   should be read as a rough proxy.

2. Stems are short (10-30 words), which means single-sentence scoring is
   noisier than paragraph-level scoring. We surface that uncertainty by
   reporting both raw scores AND a coarse 3-level bucket (easy / medium /
   hard) rather than putting absolute weight on the exact number.

References:
  Flesch, R. (1948). A new readability yardstick. Journal of Applied
  Psychology, 32(3), 221-233.
  Kincaid, J. P., Fishburne, R. P., Rogers, R. L., & Chissom, B. S.
  (1975). Derivation of new readability formulas for navy enlisted
  personnel. Naval Technical Training Research Branch Report 8-75.
  Wood, S. et al. (2007). Effects of Test Time Limits on Score Accuracy.
"""

import re
from typing import Any, Dict, List, Optional

# Recommended grade-level ranges per SOLO level. Calibrated so a U-level
# stem should be readable at high-school level; EA may legitimately require
# college-level reading because the concepts are themselves more abstract.
SOLO_GRADE_TARGETS = {
    'unistructural':     (4, 10),
    'multistructural':   (6, 12),
    'relational':        (8, 14),
    'extended_abstract': (10, 16),
}

# Vowel groups for syllable counting. Serbian Latin + Cyrillic vowels plus
# English. The "group" definition (consecutive vowels = one syllable) is
# the standard portable heuristic.
_VOWEL_RE = re.compile(r'[aeiouAEIOUyYаеиоуАЕИОУ]+')


def _count_sentences(text: str) -> int:
    # End-of-sentence punctuation plus the implicit final sentence.
    if not text or not text.strip():
        return 0
    end_punct = re.findall(r'[.!?]+', text)
    # A stem without terminal punctuation still counts as one sentence.
    return max(1, len(end_punct))


def _count_words(text: str) -> int:
    if not text:
        return 0
    return len(re.findall(r'\b\w+\b', text, flags=re.UNICODE))


def _count_syllables_word(word: str) -> int:
    """Approximate syllable count by counting vowel groups, minimum 1."""
    if not word:
        return 0
    groups = _VOWEL_RE.findall(word)
    return max(1, len(groups))


def _count_syllables(text: str) -> int:
    words = re.findall(r'\b\w+\b', text or '', flags=re.UNICODE)
    return sum(_count_syllables_word(w) for w in words)


def compute_readability(text: str) -> Dict[str, Any]:
    """Compute Flesch Reading Ease and Flesch-Kincaid Grade Level.

    Returns counters too so callers can audit the numbers. If the text is
    empty or has zero sentences/words, the formulas are undefined and we
    return them as None.
    """
    sentences = _count_sentences(text)
    words = _count_words(text)
    syllables = _count_syllables(text)

    if sentences == 0 or words == 0:
        return {
            'sentences': sentences,
            'words': words,
            'syllables': syllables,
            'flesch_reading_ease': None,
            'flesch_kincaid_grade': None,
        }

    asl = words / sentences          # average sentence length (words/sentence)
    asw = syllables / words          # average syllables per word

    # Flesch (1948): higher = easier. 60-70 ≈ plain English.
    flesch = 206.835 - 1.015 * asl - 84.6 * asw
    # Kincaid (1975): grade level. 8 ≈ US 8th grade, 12 ≈ high-school senior.
    fk_grade = 0.39 * asl + 11.8 * asw - 15.59

    return {
        'sentences': sentences,
        'words': words,
        'syllables': syllables,
        'avg_sentence_length': round(asl, 2),
        'avg_syllables_per_word': round(asw, 2),
        'flesch_reading_ease': round(flesch, 1),
        'flesch_kincaid_grade': round(fk_grade, 1),
    }


def _bucket(grade: Optional[float]) -> Optional[str]:
    if grade is None:
        return None
    if grade < 6:
        return 'easy'
    if grade < 12:
        return 'medium'
    return 'hard'


def assess_question_readability(question: Dict[str, Any]) -> Dict[str, Any]:
    """Compute readability for a question's stem and assess fit to its SOLO level.

    `fit` values:
      'in_range'  — grade is inside the target range for this SOLO level.
      'too_easy'  — below the target (rare; usually fine, but flagged for EA).
      'too_hard'  — above the target (likely measures reading, not the concept).
      'unknown'   — could not compute (empty stem, undefined SOLO level).
    """
    stem = question.get('question_text') or ''
    metrics = compute_readability(stem)
    grade = metrics.get('flesch_kincaid_grade')

    solo_level = (question.get('solo_level') or '').strip().lower()
    target = SOLO_GRADE_TARGETS.get(solo_level)

    if grade is None or target is None:
        fit = 'unknown'
    else:
        lo, hi = target
        if grade < lo:
            fit = 'too_easy'
        elif grade > hi:
            fit = 'too_hard'
        else:
            fit = 'in_range'

    return {
        'question_id': question.get('id'),
        'solo_level': solo_level or None,
        'metrics': metrics,
        'bucket': _bucket(grade),
        'target_range': list(target) if target else None,
        'fit': fit,
    }


def readability_report(questions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Batch readability across a lesson's questions."""
    reports = [assess_question_readability(q) for q in questions]
    computable = [r for r in reports if r['metrics'].get('flesch_kincaid_grade') is not None]
    n = len(computable)
    fit_distribution = {'in_range': 0, 'too_easy': 0, 'too_hard': 0, 'unknown': 0}
    bucket_distribution = {'easy': 0, 'medium': 0, 'hard': 0}
    for r in reports:
        fit_distribution[r['fit']] = fit_distribution.get(r['fit'], 0) + 1
        b = r.get('bucket')
        if b in bucket_distribution:
            bucket_distribution[b] += 1

    grades = [r['metrics']['flesch_kincaid_grade'] for r in computable]
    mean_grade = (sum(grades) / n) if n else None
    eases = [r['metrics']['flesch_reading_ease'] for r in computable
             if r['metrics'].get('flesch_reading_ease') is not None]
    mean_ease = (sum(eases) / len(eases)) if eases else None

    return {
        'total_questions': len(reports),
        'computable_questions': n,
        'mean_flesch_kincaid_grade': round(mean_grade, 2) if mean_grade is not None else None,
        'mean_flesch_reading_ease': round(mean_ease, 2) if mean_ease is not None else None,
        'fit_distribution': fit_distribution,
        'bucket_distribution': bucket_distribution,
        'reports': reports,
    }
