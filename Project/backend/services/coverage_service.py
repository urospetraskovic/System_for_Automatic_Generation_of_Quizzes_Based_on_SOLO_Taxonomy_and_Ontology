"""
PDF Coverage Service

Computes how much of an uploaded lesson PDF is actually exercised by the
generated questions. "Coverage" is measured both as raw pages-touched and as
char-weighted coverage (longer pages count for more), so a 50-page PDF where
questions only hit 10 short pages reports honestly.
"""

import re
from typing import Any, Dict, List, Optional

from models import Lesson, Section, LearningObject, Question, engine
from sqlalchemy.orm import sessionmaker

_Session = sessionmaker(bind=engine)

_PAGE_MARKER_RE = re.compile(r'\n--- Page (\d+) ---\n')


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
            }
        finally:
            session.close()
