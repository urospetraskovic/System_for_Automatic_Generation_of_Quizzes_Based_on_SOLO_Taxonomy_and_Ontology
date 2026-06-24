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
from services import validation_cache
from schemas import GenerateQuestionsRequest


def _wants_fresh() -> bool:
    """Treat ?fresh=true as a cache bypass."""
    return request.args.get('fresh', '').lower() in ('1', 'true', 'yes')


def _cached_or_compute(lesson_id: int, metric_key: str, compute_fn):
    """Read the cached lesson-level report; if missing or ?fresh=true,
    compute it now, write it back, and return."""
    if not _wants_fresh():
        cached = validation_cache.get(metric_key, lesson_id)
        if cached is not None:
            return cached
    payload = compute_fn()
    try:
        validation_cache.put(metric_key, lesson_id, payload)
    except Exception:
        # Cache write failure should never break the response.
        traceback.print_exc()
    return payload

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

        # Editing a question invalidates any lesson-scoped cached metrics.
        try:
            validation_cache.invalidate_question(question_id)
        except Exception:
            traceback.print_exc()

        return jsonify({'question': updated_q}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/questions/<int:question_id>', methods=['DELETE'])
def delete_question(question_id):
    """Delete a question."""
    try:
        # Capture affected lessons BEFORE deletion (after deletion the FK lookup fails).
        try:
            validation_cache.invalidate_question(question_id)
        except Exception:
            traceback.print_exc()
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
        payload = _cached_or_compute(
            lesson_id, 'lint',
            lambda: lint_questions(db.get_questions_by_lesson(lesson_id)),
        )
        return jsonify(payload), 200
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
        payload = _cached_or_compute(
            lesson_id, 'solo_judge',
            lambda: judge_questions(db.get_questions_by_lesson(lesson_id)),
        )
        return jsonify(payload), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


def _with_cove_context(q_dict):
    """Attach the question's section / learning-object text as `context` so
    CoVe verifies against the wider passage, not just the one-line quote.
    See EduQG calibration: this cuts CoVe's false-positive rate (42% -> 36%)."""
    from services.quality.ioc import _resolve_objective
    obj = _resolve_objective(q_dict)
    if obj and obj.get('content'):
        q_dict = dict(q_dict)
        q_dict['context'] = obj['content']
    return q_dict


@questions_bp.route('/questions/<int:question_id>/cove', methods=['GET'])
def cove_single(question_id):
    """Chain-of-Verification (Dhuliawala 2023) for one question's correctness."""
    try:
        session = db.get_session()
        try:
            q = session.query(Question).filter(Question.id == question_id).first()
            if not q:
                return jsonify({'error': 'Question not found'}), 404
            return jsonify(verify_question(_with_cove_context(q.to_dict()))), 200
        finally:
            session.close()
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/lessons/<int:lesson_id>/cove', methods=['GET'])
def cove_lesson(lesson_id):
    """Chain-of-Verification across a lesson's questions; flags ones needing review."""
    try:
        payload = _cached_or_compute(
            lesson_id, 'cove',
            lambda: verify_questions(
                [_with_cove_context(q) for q in db.get_questions_by_lesson(lesson_id)]),
        )
        return jsonify(payload), 200
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
    """LLM-blind solver across a lesson's questions; gives synthetic p-values.

    Solvability is the slowest check in the suite (n_trials × question_count
    LLM calls). To stop interrupted runs from wiping all completed work, we
    bypass the standard _cached_or_compute helper here and instead:
      1. Return a FULL cached payload as-is (no recompute).
      2. Return a PARTIAL cached payload only when the client explicitly
         opts in via ?accept_partial=true (the UI can use this to show
         progress without forcing a recompute).
      3. Otherwise recompute, and ask solvability_report to checkpoint
         partial aggregates into validation_cache every few questions so
         that an abort mid-run still leaves a usable partial snapshot.
    """
    try:
        n_trials = int(request.args.get('n_trials', 5))
        accept_partial = request.args.get('accept_partial', '').lower() in ('1', 'true', 'yes')

        if not _wants_fresh():
            cached = validation_cache.get('solvability', lesson_id)
            if cached is not None and (accept_partial or not cached.get('partial')):
                return jsonify(cached), 200

        def _checkpoint(partial_payload):
            try:
                validation_cache.put('solvability', lesson_id, partial_payload)
            except Exception:
                traceback.print_exc()

        payload = solvability_report(
            db.get_questions_by_lesson(lesson_id),
            n_trials=n_trials,
            progress_cache_fn=_checkpoint,
        )
        try:
            validation_cache.put('solvability', lesson_id, payload)
        except Exception:
            traceback.print_exc()
        return jsonify(payload), 200
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
        payload = _cached_or_compute(
            lesson_id, 'stem_only',
            lambda: stem_only_solvability_report(
                db.get_questions_by_lesson(lesson_id)),
        )
        return jsonify(payload), 200
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
        payload = _cached_or_compute(
            lesson_id, 'ioc',
            lambda: ioc_report(db.get_questions_by_lesson(lesson_id)),
        )
        return jsonify(payload), 200
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
        payload = _cached_or_compute(
            lesson_id, 'readability',
            lambda: readability_report(db.get_questions_by_lesson(lesson_id)),
        )
        return jsonify(payload), 200
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
        payload = _cached_or_compute(
            lesson_id, 'ambiguity',
            lambda: ambiguity_report(db.get_questions_by_lesson(lesson_id)),
        )
        return jsonify(payload), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/lessons/<int:lesson_id>/misconception-mining', methods=['GET'])
def misconception_mining_lesson(lesson_id):
    """Sadler 1998: extract real misconceptions from a lesson's source PDF."""
    try:
        payload = _cached_or_compute(
            lesson_id, 'misconception_mining',
            lambda: mine_lesson_misconceptions(lesson_id),
        )
        return jsonify(payload), 200
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
        payload = _cached_or_compute(
            lesson_id, 'grammar_homogeneity',
            lambda: homogeneity_report(db.get_questions_by_lesson(lesson_id)),
        )
        return jsonify(payload), 200
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
        payload = _cached_or_compute(
            lesson_id, 'face_validity',
            lambda: face_validity_report(db.get_questions_by_lesson(lesson_id)),
        )
        return jsonify(payload), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# --------------------------------------------------------------------------
# Bulk quality cache — used by ContentViewer to hydrate every sub-panel in
# one shot on mount. Returns whatever lesson-scoped validation reports are
# already cached, plus _cached_at timestamps. Sub-panels that have no cache
# entry yet simply receive nothing and fall back to their "Run" button.
# --------------------------------------------------------------------------

@questions_bp.route('/lessons/<int:lesson_id>/quality-cache', methods=['GET'])
def quality_cache_for_lesson(lesson_id):
    """Return every cached validation report for this lesson, keyed by metric.
    Empty object if nothing has been cached yet — the panels then render their
    'Run' buttons. Used to rehydrate the Quality Overview after a page reload."""
    try:
        return jsonify(validation_cache.get_all_for_lesson(lesson_id)), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@questions_bp.route('/lessons/<int:lesson_id>/quality-cache', methods=['DELETE'])
def clear_quality_cache_for_lesson(lesson_id):
    """Drop every cached validation report for a lesson. The next GET on any
    metric will recompute (slow LLM calls). Useful after manual question edits
    or before a model swap."""
    try:
        n = validation_cache.invalidate_lesson(lesson_id)
        return jsonify({'cleared': n}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
