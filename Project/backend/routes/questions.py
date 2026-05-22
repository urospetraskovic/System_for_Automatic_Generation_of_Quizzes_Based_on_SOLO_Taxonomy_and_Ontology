"""Question generation and bank routes."""

import traceback

from flask import Blueprint, request, jsonify
from pydantic import ValidationError

from repository import db
from models import Question
from services import (
    QuestionService,
    lint_question, lint_questions,
    classify_question, judge_questions,
    verify_question, verify_questions,
    assess_solvability, solvability_report,
    assess_stem_only_solvability, stem_only_solvability_report,
    ioc_rate_question, ioc_report,
    assess_question_readability, readability_report,
    assess_ambiguity, ambiguity_report,
    mine_lesson_misconceptions,
    check_homogeneity, homogeneity_report,
    assess_face_validity, face_validity_report,
)
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


@questions_bp.route('/questions/<int:question_id>/lint', methods=['GET'])
def lint_single_question(question_id):
    """Run Haladyna-rule MCQ quality checks against a single question."""
    try:
        session = db.get_session()
        try:
            q = session.query(Question).filter(Question.id == question_id).first()
            if not q:
                return jsonify({'error': 'Question not found'}), 404
            return jsonify(lint_question(q.to_dict())), 200
        finally:
            session.close()
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/lessons/<int:lesson_id>/lint', methods=['GET'])
def lint_lesson_questions(lesson_id):
    """Run lint over all questions for a lesson; returns aggregate + per-item reports."""
    try:
        questions = db.get_questions_by_lesson(lesson_id)
        return jsonify(lint_questions(questions)), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/questions/<int:question_id>/solo-judge', methods=['GET'])
def solo_judge_single(question_id):
    """Classify one question's SOLO level via a second LLM (independent of the generator)."""
    try:
        session = db.get_session()
        try:
            q = session.query(Question).filter(Question.id == question_id).first()
            if not q:
                return jsonify({'error': 'Question not found'}), 404
            return jsonify(classify_question(q.to_dict())), 200
        finally:
            session.close()
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/lessons/<int:lesson_id>/solo-judge', methods=['GET'])
def solo_judge_lesson(lesson_id):
    """Run SOLO LLM-judge over a lesson; returns agreement, Cohen's kappa, confusion matrix."""
    try:
        questions = db.get_questions_by_lesson(lesson_id)
        return jsonify(judge_questions(questions)), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/questions/<int:question_id>/cove', methods=['GET'])
def cove_single(question_id):
    """Chain-of-Verification (Dhuliawala 2023) for one question's correctness."""
    try:
        session = db.get_session()
        try:
            q = session.query(Question).filter(Question.id == question_id).first()
            if not q:
                return jsonify({'error': 'Question not found'}), 404
            return jsonify(verify_question(q.to_dict())), 200
        finally:
            session.close()
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/lessons/<int:lesson_id>/cove', methods=['GET'])
def cove_lesson(lesson_id):
    """Chain-of-Verification across a lesson's questions; flags ones needing review."""
    try:
        questions = db.get_questions_by_lesson(lesson_id)
        return jsonify(verify_questions(questions)), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/questions/<int:question_id>/solvability', methods=['GET'])
def solvability_single(question_id):
    """LLM-blind solver as a-priori item difficulty calibration."""
    try:
        session = db.get_session()
        try:
            q = session.query(Question).filter(Question.id == question_id).first()
            if not q:
                return jsonify({'error': 'Question not found'}), 404
            n_trials = int(request.args.get('n_trials', 5))
            return jsonify(assess_solvability(q.to_dict(), n_trials=n_trials)), 200
        finally:
            session.close()
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/lessons/<int:lesson_id>/solvability', methods=['GET'])
def solvability_lesson(lesson_id):
    """LLM-blind solver across a lesson's questions; gives synthetic p-values."""
    try:
        questions = db.get_questions_by_lesson(lesson_id)
        n_trials = int(request.args.get('n_trials', 5))
        return jsonify(solvability_report(questions, n_trials=n_trials)), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# --------------------------------------------------------------------------
# Extended validity layer (A–H from the best-practices document)
# --------------------------------------------------------------------------

@questions_bp.route('/lessons/<int:lesson_id>/stem-only-solvability', methods=['GET'])
def stem_only_solvability_lesson(lesson_id):
    """Haladyna H4: stem must be answerable without options."""
    try:
        questions = db.get_questions_by_lesson(lesson_id)
        return jsonify(stem_only_solvability_report(questions)), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/questions/<int:question_id>/ioc', methods=['GET'])
def ioc_single(question_id):
    """Item-Objective Congruence rating for one question (Rovinelli & Hambleton 1977)."""
    try:
        session = db.get_session()
        try:
            q = session.query(Question).filter(Question.id == question_id).first()
            if not q:
                return jsonify({'error': 'Question not found'}), 404
            return jsonify(ioc_rate_question(q.to_dict())), 200
        finally:
            session.close()
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/lessons/<int:lesson_id>/ioc', methods=['GET'])
def ioc_lesson(lesson_id):
    """Lesson-wide IOC index + per-question ratings."""
    try:
        questions = db.get_questions_by_lesson(lesson_id)
        return jsonify(ioc_report(questions)), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/questions/<int:question_id>/readability', methods=['GET'])
def readability_single(question_id):
    """Flesch / Flesch-Kincaid metrics + fit to SOLO level."""
    try:
        session = db.get_session()
        try:
            q = session.query(Question).filter(Question.id == question_id).first()
            if not q:
                return jsonify({'error': 'Question not found'}), 404
            return jsonify(assess_question_readability(q.to_dict())), 200
        finally:
            session.close()
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/lessons/<int:lesson_id>/readability', methods=['GET'])
def readability_lesson(lesson_id):
    """Batch readability report across a lesson's questions."""
    try:
        questions = db.get_questions_by_lesson(lesson_id)
        return jsonify(readability_report(questions)), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/questions/<int:question_id>/ambiguity', methods=['GET'])
def ambiguity_single(question_id):
    """Linguistic-ambiguity check for one question."""
    try:
        session = db.get_session()
        try:
            q = session.query(Question).filter(Question.id == question_id).first()
            if not q:
                return jsonify({'error': 'Question not found'}), 404
            return jsonify(assess_ambiguity(q.to_dict())), 200
        finally:
            session.close()
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/lessons/<int:lesson_id>/ambiguity', methods=['GET'])
def ambiguity_lesson(lesson_id):
    """Lesson-wide ambiguity rate + per-question reports."""
    try:
        questions = db.get_questions_by_lesson(lesson_id)
        return jsonify(ambiguity_report(questions)), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/lessons/<int:lesson_id>/misconception-mining', methods=['GET'])
def misconception_mining_lesson(lesson_id):
    """Sadler 1998: extract real misconceptions from a lesson's source PDF."""
    try:
        return jsonify(mine_lesson_misconceptions(lesson_id)), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/questions/<int:question_id>/grammar-homogeneity', methods=['GET'])
def grammar_homogeneity_single(question_id):
    """Haladyna O7: are the four options grammatically parallel?"""
    try:
        session = db.get_session()
        try:
            q = session.query(Question).filter(Question.id == question_id).first()
            if not q:
                return jsonify({'error': 'Question not found'}), 404
            return jsonify(check_homogeneity(q.to_dict())), 200
        finally:
            session.close()
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/lessons/<int:lesson_id>/grammar-homogeneity', methods=['GET'])
def grammar_homogeneity_lesson(lesson_id):
    """Lesson-wide grammatical homogeneity check across all options."""
    try:
        questions = db.get_questions_by_lesson(lesson_id)
        return jsonify(homogeneity_report(questions)), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/questions/<int:question_id>/face-validity', methods=['GET'])
def face_validity_single(question_id):
    """Considine 2005 distractor face-validity rubric."""
    try:
        session = db.get_session()
        try:
            q = session.query(Question).filter(Question.id == question_id).first()
            if not q:
                return jsonify({'error': 'Question not found'}), 404
            return jsonify(assess_face_validity(q.to_dict())), 200
        finally:
            session.close()
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/lessons/<int:lesson_id>/face-validity', methods=['GET'])
def face_validity_lesson(lesson_id):
    """Lesson-wide face-validity score + per-criterion means."""
    try:
        questions = db.get_questions_by_lesson(lesson_id)
        return jsonify(face_validity_report(questions)), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
