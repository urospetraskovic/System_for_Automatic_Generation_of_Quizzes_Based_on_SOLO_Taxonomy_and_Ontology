"""
Tests for QuestionService.generate_for_lessons — auto-quota generation
restricted to a user-selected subset of lessons.

We mock the database and the underlying `generate_questions` call so the test
covers only the orchestration logic: input validation, plan-building (skip
unparsed lessons), quota wiring, and EA pairing across consecutive selected
lessons. The expensive LLM generator path is exercised separately.
"""

from unittest.mock import patch

import pytest

from services.domain.question_service import QuestionService


def _lesson(id_, title, n_sections=4, n_los=20):
    sections = [
        {
            'id': s,
            'title': f'S{s}',
            'learning_objects': [
                {'id': s * 100 + j, 'title': f'LO{s}-{j}'}
                for j in range(n_los // max(n_sections, 1))
            ],
        }
        for s in range(1, n_sections + 1)
    ]
    return {'id': id_, 'title': title, 'sections': sections}


def _ok_result(level, count):
    """Stand-in for generate_questions' return shape."""
    return {
        'questions': [
            {'id': i, 'solo_level': level, 'question_text': f'Q{i}'}
            for i in range(count)
        ],
        'count': count,
        'status': 200,
    }


def test_rejects_empty_lesson_ids():
    r = QuestionService.generate_for_lessons(lesson_ids=[])
    assert r['status'] == 400


def test_rejects_only_invalid_lesson_ids():
    r = QuestionService.generate_for_lessons(lesson_ids=['x', None])
    assert r['status'] == 400


def test_deduplicates_lesson_ids_preserving_order():
    """Same ID listed twice → only one plan, kept in first-seen order."""
    with patch('services.domain.question_service.db') as mock_db:
        mock_db.get_lesson_with_sections.side_effect = lambda lid: _lesson(lid, f'L{lid}')
        with patch.object(QuestionService, 'generate_questions',
                          side_effect=lambda **kw: _ok_result(kw['solo_levels'][0], kw['questions_per_level'])):
            r = QuestionService.generate_for_lessons(lesson_ids=[7, 7, 9, 7])
    # The call site is mocked so we can't trivially read `plans`, but the
    # report still tells us how many distinct lessons were processed.
    assert r['lessons_processed'] == 2  # 7 and 9


def test_skips_unparsed_lessons():
    """Unparsed lesson (no sections) must NOT show up in the plan."""
    def _fake_lookup(lid):
        if lid == 1:
            return _lesson(1, 'Parsed')
        if lid == 2:
            return {'id': 2, 'title': 'Unparsed', 'sections': []}
        return None

    with patch('services.domain.question_service.db') as mock_db:
        mock_db.get_lesson_with_sections.side_effect = _fake_lookup
        with patch.object(QuestionService, 'generate_questions',
                          side_effect=lambda **kw: _ok_result(kw['solo_levels'][0], kw['questions_per_level'])):
            r = QuestionService.generate_for_lessons(lesson_ids=[1, 2])
    assert r['lessons_processed'] == 1


def test_returns_error_when_no_parseable_lessons():
    with patch('services.domain.question_service.db') as mock_db:
        mock_db.get_lesson_with_sections.return_value = None
        r = QuestionService.generate_for_lessons(lesson_ids=[42])
    assert r['status'] == 400


def test_single_lesson_skips_extended_abstract():
    """One lesson selected → EA is not attempted (matches manual-mode UI)."""
    calls = []

    def _capture(**kw):
        calls.append(kw['solo_levels'][0])
        return _ok_result(kw['solo_levels'][0], 1)

    with patch('services.domain.question_service.db') as mock_db:
        mock_db.get_lesson_with_sections.side_effect = lambda lid: _lesson(lid, f'L{lid}')
        with patch.object(QuestionService, 'generate_questions', side_effect=_capture):
            QuestionService.generate_for_lessons(lesson_ids=[1])
    assert 'extended_abstract' not in calls


def test_two_lessons_attempt_ea_pair():
    """Two lessons → EA must be requested once across the pair."""
    calls = []

    def _capture(**kw):
        calls.append((tuple(kw['lesson_ids']), kw['solo_levels'][0]))
        return _ok_result(kw['solo_levels'][0], 1)

    with patch('services.domain.question_service.db') as mock_db:
        mock_db.get_lesson_with_sections.side_effect = lambda lid: _lesson(lid, f'L{lid}')
        with patch.object(QuestionService, 'generate_questions', side_effect=_capture):
            QuestionService.generate_for_lessons(lesson_ids=[10, 11])
    ea_calls = [c for c in calls if c[1] == 'extended_abstract']
    assert len(ea_calls) == 1
    assert set(ea_calls[0][0]) == {10, 11}


def test_progress_callback_receives_messages():
    received = []

    def cb(message, current=None, total=None):
        received.append({'message': message, 'current': current, 'total': total})

    with patch('services.domain.question_service.db') as mock_db:
        mock_db.get_lesson_with_sections.side_effect = lambda lid: _lesson(lid, f'L{lid}')
        with patch.object(QuestionService, 'generate_questions',
                          side_effect=lambda **kw: _ok_result(kw['solo_levels'][0], 1)):
            QuestionService.generate_for_lessons(lesson_ids=[1], progress_cb=cb)
    assert received  # at least one progress emit
