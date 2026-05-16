"""Quiz CRUD routes."""

import traceback

from flask import Blueprint, request, jsonify
from sqlalchemy import func

from repository import db
from models.models import Quiz, QuizQuestion, QuestionTranslation

quizzes_bp = Blueprint('quizzes', __name__, url_prefix='/api')


def _quiz_dict_with_languages(quiz, session):
    """Build a quiz dict and attach the languages every question has been translated into."""
    quiz_dict = quiz.to_dict()

    quiz_questions = session.query(QuizQuestion).filter_by(quiz_id=quiz.id).all()
    question_ids = [qq.question_id for qq in quiz_questions]
    total_questions = len(question_ids)

    if not question_ids:
        quiz_dict['available_languages'] = []
        return quiz_dict

    lang_counts = session.query(
        QuestionTranslation.language_code,
        func.count(QuestionTranslation.question_id)
    ).filter(
        QuestionTranslation.question_id.in_(question_ids)
    ).group_by(QuestionTranslation.language_code).all()

    quiz_dict['available_languages'] = [
        lang for lang, count in lang_counts if count == total_questions
    ]
    return quiz_dict


@quizzes_bp.route('/quizzes', methods=['POST'])
def create_quiz():
    """Create a new quiz from selected questions."""
    try:
        data = request.get_json()
        if not data or 'title' not in data:
            return jsonify({'error': 'Quiz title is required'}), 400

        quiz = db.create_quiz(
            title=data['title'],
            course_id=data.get('course_id'),
            description=data.get('description'),
            time_limit_minutes=data.get('time_limit_minutes'),
            passing_score=data.get('passing_score'),
            shuffle_questions=data.get('shuffle_questions', False),
            shuffle_options=data.get('shuffle_options', False)
        )

        for qid in data.get('question_ids', []):
            db.add_question_to_quiz(quiz['id'], qid)

        updated_quiz = db.get_quiz(quiz['id'], include_questions=False)
        return jsonify({'quiz': updated_quiz}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@quizzes_bp.route('/quizzes/<int:quiz_id>', methods=['GET'])
def get_quiz(quiz_id):
    """Get a quiz with its questions."""
    try:
        quiz = db.get_quiz(quiz_id, include_questions=True)
        if not quiz:
            return jsonify({'error': 'Quiz not found'}), 404
        return jsonify({'quiz': quiz}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@quizzes_bp.route('/quizzes/<int:quiz_id>', methods=['DELETE'])
def delete_quiz(quiz_id):
    """Delete a quiz."""
    try:
        success = db.delete_quiz(quiz_id)
        if not success:
            return jsonify({'error': 'Quiz not found'}), 404
        return jsonify({'message': 'Quiz deleted successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@quizzes_bp.route('/quizzes/<int:quiz_id>/add-questions', methods=['POST'])
def add_questions_to_quiz(quiz_id):
    """Add questions to an existing quiz."""
    try:
        data = request.get_json()
        question_ids = data.get('question_ids', [])

        for qid in question_ids:
            db.add_question_to_quiz(quiz_id, qid)

        return jsonify({'message': f'Added {len(question_ids)} questions to quiz'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@quizzes_bp.route('/courses/<int:course_id>/quizzes', methods=['GET'])
def get_course_quizzes(course_id):
    """Get all quizzes for a course with available translation languages."""
    try:
        session = db.Session()
        try:
            quizzes = session.query(Quiz).filter(Quiz.course_id == course_id).all()
            result = [_quiz_dict_with_languages(q, session) for q in quizzes]
        finally:
            session.close()
        return jsonify({'quizzes': result}), 200
    except Exception as e:
        print(f'[ERROR] get_course_quizzes: {str(e)}')
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@quizzes_bp.route('/quizzes', methods=['GET'])
def get_all_quizzes():
    """Get all quizzes with available translation languages."""
    try:
        session = db.Session()
        try:
            quizzes = session.query(Quiz).all()
            result = [_quiz_dict_with_languages(q, session) for q in quizzes]
        finally:
            session.close()
        return jsonify({'quizzes': result}), 200
    except Exception as e:
        print(f'[ERROR] get_all_quizzes: {str(e)}')
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


