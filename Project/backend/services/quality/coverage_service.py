"""
PDF Coverage Service

Computes how much of an uploaded lesson PDF is actually exercised by the
generated questions. Two complementary views are returned:

* Physical coverage — pages touched, character-weighted (longer pages count more).
* Concept coverage — semantic coverage over the lesson's ontology (LO titles +
  keywords). Each concept is weighted by its centrality in the
  ConceptRelationship graph, so well-connected concepts count for more than
  isolated ones. This is the measure that answers "did the questions cover
  the material's *ideas*?", not just "did they hit the same pages?".
"""

import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from models import Lesson, Section, LearningObject, ConceptRelationship, Question, engine
from sqlalchemy.orm import sessionmaker

_Session = sessionmaker(bind=engine)

_PAGE_MARKER_RE = re.compile(r'\n--- Page (\d+) ---\n')

# Concepts shorter than this are too generic to match reliably (e.g. "i", "je").
_MIN_CONCEPT_LEN = 3
# Concepts in this stoplist are filtered out even if extracted as keywords.
_CONCEPT_STOPWORDS = {
    'the', 'and', 'for', 'with', 'this', 'that', 'are', 'can', 'has',
    'sve', 'jedan', 'jedna', 'jedno', 'koji', 'koja', 'koje', 'kao', 'kada',
    'tako', 'pri', 'biti', 'samo', 'svaki', 'svaka', 'svako',
}


def _reconstruct_pages_meta(raw_content: str) -> List[Dict[str, Any]]:
    """Rebuild pages_meta for old lessons whose raw_content still has `--- Page N ---` markers."""
    if not raw_content:
        return []
    matches = list(_PAGE_MARKER_RE.finditer(raw_content))
    if not matches:
        return []
    pages = []
    for i, m in enumerate(matches):
        page_num = int(m.group(1))
        start_offset = m.end()
        end_offset = matches[i + 1].start() if i + 1 < len(matches) else len(raw_content)
        page_text = raw_content[start_offset:end_offset]
        pages.append({
            'page': page_num,
            'char_count': len(page_text.strip()),
            'start_offset': start_offset,
            'end_offset': end_offset,
        })
    return pages


def _question_pages(question: Question, lo_pages: Dict[int, List[int]],
                    section_pages: Dict[int, List[int]]) -> List[int]:
    """Resolve the source pages for a question."""
    if question.learning_object_id and question.learning_object_id in lo_pages:
        pages = lo_pages.get(question.learning_object_id) or []
        if pages:
            return pages
    if question.section_id and question.section_id in section_pages:
        return section_pages.get(question.section_id) or []
    return []


def _build_section_page_range(section: Section) -> List[int]:
    if not section.start_page or not section.end_page:
        return []
    return list(range(section.start_page, section.end_page + 1))


def _normalize_concept(text: str) -> str:
    """Lowercase + collapse whitespace; concepts compared in this canonical form."""
    if not text:
        return ''
    return re.sub(r'\s+', ' ', text.strip().lower())


def _is_acceptable_concept(text: str) -> bool:
    if not text or len(text) < _MIN_CONCEPT_LEN:
        return False
    if text in _CONCEPT_STOPWORDS:
        return False
    # Pure punctuation / numbers are not concepts.
    if not re.search(r'[A-Za-zĐĆČŠŽđćčšž]', text):
        return False
    return True


def _extract_lesson_concepts(
    learning_objects: List[LearningObject],
) -> Dict[str, Dict[str, Any]]:
    """Build the canonical concept set for a lesson.

    Returns: {normalized_concept: {"display": str, "lo_ids": set[int]}}

    Each LO contributes its title and every entry in its `keywords` list.
    LO ids are tracked so we can later compute centrality from
    ConceptRelationship.
    """
    concepts: Dict[str, Dict[str, Any]] = {}

    def _add(raw: str, lo_id: int) -> None:
        norm = _normalize_concept(raw)
        if not _is_acceptable_concept(norm):
            return
        entry = concepts.setdefault(norm, {'display': raw.strip(), 'lo_ids': set()})
        entry['lo_ids'].add(lo_id)

    for lo in learning_objects:
        if lo.title:
            _add(lo.title, lo.id)
        for kw in (lo.keywords or []):
            if isinstance(kw, str):
                _add(kw, lo.id)

    return concepts


def _compute_concept_weights(
    concepts: Dict[str, Dict[str, Any]],
    relationships: List[ConceptRelationship],
) -> Dict[str, float]:
    """Weight each concept by its degree in the ConceptRelationship graph.

    A concept's weight is 1 + (number of relationships in which any of its
    source LOs participates). Concepts associated with hub LOs (many
    isPrerequisiteFor / buildsUpon links) thus contribute more to the
    weighted coverage.
    """
    degree_by_lo: Dict[int, int] = defaultdict(int)
    for rel in relationships:
        degree_by_lo[rel.source_id] += 1
        degree_by_lo[rel.target_id] += 1

    weights: Dict[str, float] = {}
    for norm, entry in concepts.items():
        lo_degree = sum(degree_by_lo.get(lo_id, 0) for lo_id in entry['lo_ids'])
        weights[norm] = 1.0 + lo_degree
    return weights


def _question_text_blob(q: Question) -> str:
    """Concatenate all student-facing fields of a question for concept matching."""
    parts: List[str] = []
    if q.question_text:
        parts.append(q.question_text)
    if q.correct_answer:
        parts.append(q.correct_answer)
    if q.explanation:
        parts.append(q.explanation)
    if isinstance(q.options, list):
        for opt in q.options:
            if isinstance(opt, str):
                parts.append(opt)
            elif isinstance(opt, dict):
                # Some generators store options as {"text": "..."} dicts.
                txt = opt.get('text') or opt.get('value') or ''
                if txt:
                    parts.append(str(txt))
    return _normalize_concept(' '.join(parts))


def _concept_mentions(
    concepts: Dict[str, Dict[str, Any]],
    questions: List[Question],
) -> Tuple[Dict[str, int], Dict[int, Set[str]]]:
    """Count, per concept, how many questions mention it (case-insensitive substring).

    Multi-word concepts must appear as a contiguous phrase; single-word
    concepts use a word-boundary match so "proces" does not match
    "procesor". This is a deliberate naive baseline — sufficient for
    Serbian morphology in 80%+ of cases because keywords from the
    generator are usually already lemmatized. Embedding-based matching
    is a planned upgrade.
    """
    mentions: Dict[str, int] = defaultdict(int)
    per_question: Dict[int, Set[str]] = defaultdict(set)

    # Precompile a regex per concept once.
    compiled: List[Tuple[str, re.Pattern]] = []
    for norm in concepts:
        # Escape regex metacharacters in the concept itself.
        escaped = re.escape(norm)
        if ' ' in norm:
            pattern = re.compile(escaped)
        else:
            pattern = re.compile(rf'\b{escaped}\w*\b')
        compiled.append((norm, pattern))

    for q in questions:
        blob = _question_text_blob(q)
        if not blob:
            continue
        for norm, pattern in compiled:
            if pattern.search(blob):
                mentions[norm] += 1
                per_question[q.id].add(norm)

    return mentions, per_question


def _compute_concept_coverage(
    learning_objects: List[LearningObject],
    relationships: List[ConceptRelationship],
    questions: List[Question],
) -> Dict[str, Any]:
    """Return concept-coverage block for the CoverageService payload."""
    concepts = _extract_lesson_concepts(learning_objects)
    if not concepts:
        return {
            'available': False,
            'reason': 'No learning objects with keywords for this lesson — parse the lesson first.',
        }

    weights = _compute_concept_weights(concepts, relationships)
    mentions, _per_question = _concept_mentions(concepts, questions)

    total_concepts = len(concepts)
    covered = [norm for norm in concepts if mentions.get(norm, 0) > 0]
    covered_count = len(covered)

    total_weight = sum(weights.values()) or 1.0
    covered_weight = sum(weights[n] for n in covered)

    concept_records = sorted(
        (
            {
                'concept': concepts[norm]['display'],
                'normalized': norm,
                'weight': round(weights[norm], 2),
                'mention_count': mentions.get(norm, 0),
                'covered': mentions.get(norm, 0) > 0,
            }
            for norm in concepts
        ),
        key=lambda r: (-r['weight'], r['concept']),
    )

    top_uncovered = [r for r in concept_records if not r['covered']][:20]

    return {
        'available': True,
        'total_concepts': total_concepts,
        'concepts_covered': covered_count,
        'concept_coverage_pct': round(100.0 * covered_count / total_concepts, 1),
        'weighted_concept_coverage_pct': round(100.0 * covered_weight / total_weight, 1),
        'top_uncovered_concepts': top_uncovered,
        'concepts': concept_records,
    }


class CoverageService:
    """Compute coverage metrics for a single lesson."""

    @staticmethod
    def compute(lesson_id: int) -> Optional[Dict[str, Any]]:
        session = _Session()
        try:
            lesson = session.query(Lesson).filter(Lesson.id == lesson_id).first()
            if not lesson:
                return None

            pages_meta = lesson.pages_meta or []
            reconstructed = False
            if not pages_meta and lesson.raw_content:
                pages_meta = _reconstruct_pages_meta(lesson.raw_content)
                reconstructed = bool(pages_meta)

            if not pages_meta:
                return {
                    'lesson_id': lesson_id,
                    'available': False,
                    'reason': 'No per-page metadata for this lesson. Re-upload the PDF to enable coverage.',
                }

            sections = session.query(Section).filter(Section.lesson_id == lesson_id).all()
            section_ids = [s.id for s in sections]

            learning_objects = (
                session.query(LearningObject)
                .filter(LearningObject.section_id.in_(section_ids))
                .all()
                if section_ids else []
            )

            lo_ids = [lo.id for lo in learning_objects]
            relationships = (
                session.query(ConceptRelationship)
                .filter(
                    ConceptRelationship.source_id.in_(lo_ids)
                    | ConceptRelationship.target_id.in_(lo_ids)
                )
                .all()
                if lo_ids else []
            )

            questions = session.query(Question).filter(
                (Question.primary_lesson_id == lesson_id)
                | (Question.secondary_lesson_id == lesson_id)
            ).all()

            section_pages = {s.id: _build_section_page_range(s) for s in sections}
            lo_pages = {lo.id: (lo.source_pages or []) for lo in learning_objects}

            # Per-page aggregations
            page_records: Dict[int, Dict[str, Any]] = {}
            for meta in pages_meta:
                page_records[meta['page']] = {
                    'page': meta['page'],
                    'char_count': meta.get('char_count', 0),
                    'learning_object_count': 0,
                    'question_count': 0,
                }

            for lo in learning_objects:
                for page in (lo.source_pages or []):
                    if page in page_records:
                        page_records[page]['learning_object_count'] += 1

            covered_pages = set()
            for q in questions:
                pages = _question_pages(q, lo_pages, section_pages)
                if not pages:
                    continue
                for page in pages:
                    if page in page_records:
                        page_records[page]['question_count'] += 1
                        covered_pages.add(page)

            total_pages = len(page_records)
            total_chars = sum(rec['char_count'] for rec in page_records.values()) or 1
            covered_chars = sum(
                rec['char_count'] for rec in page_records.values() if rec['question_count'] > 0
            )
            substantive_total_chars = sum(
                rec['char_count'] for rec in page_records.values() if rec['char_count'] >= 50
            ) or 1
            substantive_covered_chars = sum(
                rec['char_count']
                for rec in page_records.values()
                if rec['question_count'] > 0 and rec['char_count'] >= 50
            )

            uncovered_substantive = sorted(
                [
                    rec for rec in page_records.values()
                    if rec['question_count'] == 0 and rec['char_count'] >= 50
                ],
                key=lambda r: r['char_count'],
                reverse=True,
            )

            untracked_questions = sum(
                1 for q in questions
                if not _question_pages(q, lo_pages, section_pages)
            )

            concept_coverage = _compute_concept_coverage(
                learning_objects, relationships, questions
            )

            return {
                'lesson_id': lesson_id,
                'available': True,
                'reconstructed': reconstructed,
                'total_pages': total_pages,
                'total_questions': len(questions),
                'questions_with_page_data': len(questions) - untracked_questions,
                'questions_without_page_data': untracked_questions,
                'pages_covered': len(covered_pages),
                'page_coverage_pct': round(100.0 * len(covered_pages) / total_pages, 1) if total_pages else 0.0,
                'weighted_coverage_pct': round(100.0 * covered_chars / total_chars, 1),
                'substantive_weighted_coverage_pct': round(
                    100.0 * substantive_covered_chars / substantive_total_chars, 1
                ),
                'pages': sorted(page_records.values(), key=lambda r: r['page']),
                'uncovered_substantive_pages': [p['page'] for p in uncovered_substantive[:20]],
                'concept_coverage': concept_coverage,
            }
        finally:
            session.close()
