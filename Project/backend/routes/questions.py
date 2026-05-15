"""Question generation and bank routes."""

import traceback

from flask import Blueprint, request, jsonify
from pydantic import ValidationError

from repository import db
from models import Question
from services import QuestionService
from schemas import GenerateQuestionsRequest

questions_bp = Blueprint('questions', __name__, url_prefix='/api')


@questions_bp.route('/generate-questions', methods=['POST'])
def generate_questions():
    """Generate questions from lessons based on SOLO taxonomy levels."""
    try:
        try:
            req = GenerateQuestionsRequest.model_validate(request.get_json(silent=True) or {})
        except ValidationError as ve:
            return jsonify({'error': 'Invalid request body', 'details': ve.errors()}), 422

        result = QuestionService.generate_questions(
            lesson_ids=req.lesson_ids,
            solo_levels=req.solo_levels,
            questions_per_level=req.questions_per_level,
            section_ids=req.section_ids,
            save_to_db=req.save_to_db,
        )

        status = result.pop('status', 200)
        return jsonify(result), status

    except Exception as e:
        print(f"[API] Question generation error: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/questions', methods=['GET'])
def get_questions():
    """Get all questions, optionally filtered by course or lesson."""
    try:
        course_id = request.args.get('course_id', type=int)
        lesson_id = request.args.get('lesson_id', type=int)
        solo_level = request.args.get('solo_level')

        if lesson_id:
            questions = db.get_questions_by_lesson(lesson_id)
        elif solo_level:
            questions = db.get_questions_by_solo_level(solo_level, lesson_id)
        else:
            questions = db.get_all_questions(course_id)

        return jsonify({'questions': questions, 'count': len(questions)}), 200
    except Exception as e:
        print(f'[ERROR] get_questions: {str(e)}')
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/questions', methods=['POST'])
def create_manual_question():
    """Create a manual question (human-generated, not AI)."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        if 'question_text' not in data or 'solo_level' not in data:
            return jsonify({'error': 'question_text and solo_level are required'}), 400

        question = db.create_question(
            solo_level=data['solo_level'],
            question_text=data['question_text'],
            question_type=data.get('question_type', 'multiple_choice'),
            primary_lesson_id=data.get('primary_lesson_id'),
            secondary_lesson_id=data.get('secondary_lesson_id'),
            section_id=data.get('section_id'),
            learning_object_id=data.get('learning_object_id'),
            options=data.get('options'),
            correct_answer=data.get('correct_answer'),
            correct_option_index=data.get('correct_option_index'),
            explanation=data.get('explanation'),
            difficulty=data.get('difficulty'),
            bloom_level=data.get('bloom_level'),
            tags=data.get('tags'),
            is_ai_generated=False,
        )

        return jsonify({'question': question}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/questions/<int:question_id>', methods=['GET'])
def get_question(question_id):
    """Get a specific question."""
    try:
        session = db.get_session()
        try:
            q = session.query(Question).filter(Question.id == question_id).first()
            if not q:
                return jsonify({'error': 'Question not found'}), 404
            return jsonify({'question': q.to_dict()}), 200
        finally:
            session.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/questions/<int:question_id>', methods=['PUT'])
def update_question(question_id):
    """Update a question."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        update_data = {k: v for k, v in data.items() if v is not None}
        update_data['mark_human_modified'] = True

        updated_q = db.update_question(question_id, **update_data)

        if not updated_q:
            return jsonify({'error': 'Question not found'}), 404

        return jsonify({'question': updated_q}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/questions/<int:question_id>', methods=['DELETE'])
def delete_question(question_id):
    """Delete a question."""
    try:
        success = db.delete_question(question_id)
        if success:
            return jsonify({'message': 'Question deleted'}), 200
        return jsonify({'error': 'Question not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500
