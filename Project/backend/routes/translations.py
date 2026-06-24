"""Translation routes for questions, lessons, sections, learning objects, ontology and courses."""

import traceback

from flask import Blueprint, request, jsonify

from repository import db
from models import (
    Course,
    Lesson,
    Section,
    LearningObject,
    Question,
    ConceptRelationship,
)
from models.models import Quiz, QuizQuestion, QuestionTranslation
from services import get_translation_service
from services.domain.translation_service import SUPPORTED_LANGUAGES

translations_bp = Blueprint('translations', __name__, url_prefix='/api')

translation_service = get_translation_service()


# ---------- Language listings ----------

@translations_bp.route('/translations/languages', methods=['GET'])
def get_supported_languages():
    """Get list of supported languages for translation (legacy endpoint)."""
    try:
        service = get_translation_service()
        return jsonify({
            'languages': [
                {'code': code, 'name': name}
                for code, name in service.supported_languages.items()
            ]
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@translations_bp.route('/translate/languages', methods=['GET'])
def get_languages():
    """Get list of supported languages for translation."""
    try:
        languages = translation_service.get_supported_languages()
        return jsonify({'success': True, 'languages': languages}), 200
    except Exception as e:
        print(f'[ERROR] get_languages: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500


# ---------- Per-question translations (legacy endpoints under /questions) ----------

@translations_bp.route('/questions/<int:question_id>/translate', methods=['POST'])
def translate_question(question_id):
    """Translate a question to target language."""
    session = db.Session()
    try:
        data = request.get_json()
        if not data or 'language_code' not in data:
            return jsonify({'error': 'language_code is required'}), 400

        question = session.query(Question).filter(Question.id == question_id).first()
        if not question:
            return jsonify({'error': 'Question not found'}), 404

        service = get_translation_service()
        translation = service.translate_question(question, data['language_code'], session)

        if not translation:
            return jsonify({'error': 'Translation failed'}), 500

        return jsonify({
            'message': 'Question translated successfully',
            'translation': translation.to_dict()
        }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@translations_bp.route('/questions/<int:question_id>/translations', methods=['GET'])
def get_question_translations(question_id):
    """Get all available translations for a question."""
    session = db.Session()
    try:
        question = session.query(Question).filter(Question.id == question_id).first()
        if not question:
            return jsonify({'error': 'Question not found'}), 404

        service = get_translation_service()
        translations = service.get_translations(question_id, session)

        return jsonify({
            'question_id': question_id,
            'original_language': 'English',
            'available_translations': [t.to_dict() for t in translations]
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@translations_bp.route('/questions/<int:question_id>/translations/<language_code>', methods=['GET'])
def get_translated_question(question_id, language_code):
    """Get translated version of a question."""
    session = db.Session()
    try:
        service = get_translation_service()
        translated = service.get_translated_question(question_id, language_code, session)

        if not translated:
            return jsonify({'error': 'Translation not found'}), 404

        return jsonify(translated), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@translations_bp.route('/questions/batch/translate', methods=['POST'])
def batch_translate_questions():
    """Translate multiple questions to multiple languages."""
    session = db.Session()
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        question_ids = data.get('question_ids', [])
        target_languages = data.get('target_languages', [])

        if not question_ids or not target_languages:
            return jsonify({'error': 'question_ids and target_languages are required'}), 400

        service = get_translation_service()
        results = service.translate_batch(question_ids, target_languages, session)

        return jsonify({
            'message': 'Batch translation completed',
            'results': results
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


# ---------- Modern /translate/* endpoints ----------

def _translate_entity(model_cls, entity_id, target_language, translate_method_name):
    """Shared helper: load entity by id, run named translate method, return JSON response."""
    if not target_language:
        return jsonify({'error': 'target_language is required'}), 400

    session = db.Session()
    try:
        entity = session.get(model_cls, entity_id)
        if not entity:
            return jsonify({'error': f'{model_cls.__name__} not found'}), 404

        method = getattr(translation_service, translate_method_name)
        translation = method(entity, target_language, session)

        if not translation:
            return jsonify({'success': False, 'error': 'Translation failed'}), 500

        return jsonify({'success': True, 'translation': translation.to_dict()}), 200
    finally:
        session.close()


@translations_bp.route('/translate/question', methods=['POST'])
def translate_question_api():
    """Translate a single question to target language."""
    try:
        data = request.get_json()
        if not data or 'question_id' not in data or 'target_language' not in data:
            return jsonify({'error': 'question_id and target_language are required'}), 400

        return _translate_entity(
            Question, data['question_id'], data['target_language'], 'translate_question'
        )
    except Exception as e:
        print(f'[ERROR] translate_question_api: {str(e)}')
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@translations_bp.route('/translate/lesson', methods=['POST'])
def translate_lesson_api():
    """Translate a lesson to target language."""
    try:
        data = request.get_json()
        if not data or 'lesson_id' not in data or 'target_language' not in data:
            return jsonify({'error': 'lesson_id and target_language are required'}), 400

        return _translate_entity(
            Lesson, data['lesson_id'], data['target_language'], 'translate_lesson'
        )
    except Exception as e:
        print(f'[ERROR] translate_lesson_api: {str(e)}')
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@translations_bp.route('/translate/section', methods=['POST'])
def translate_section_api():
    """Translate a section to target language."""
    try:
        data = request.get_json()
        if not data or 'section_id' not in data or 'target_language' not in data:
            return jsonify({'error': 'section_id and target_language are required'}), 400

        return _translate_entity(
            Section, data['section_id'], data['target_language'], 'translate_section'
        )
    except Exception as e:
        print(f'[ERROR] translate_section_api: {str(e)}')
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@translations_bp.route('/translate/learning-object', methods=['POST'])
def translate_learning_object_api():
    """Translate a learning object to target language."""
    try:
        data = request.get_json()
        if not data or 'learning_object_id' not in data or 'target_language' not in data:
            return jsonify({'error': 'learning_object_id and target_language are required'}), 400

        return _translate_entity(
            LearningObject,
            data['learning_object_id'],
            data['target_language'],
            'translate_learning_object',
        )
    except Exception as e:
        print(f'[ERROR] translate_learning_object_api: {str(e)}')
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@translations_bp.route('/translate/ontology', methods=['POST'])
def translate_ontology_api():
    """Translate an ontology relationship to target language."""
    try:
        data = request.get_json()
        if not data or 'relationship_id' not in data or 'target_language' not in data:
            return jsonify({'error': 'relationship_id and target_language are required'}), 400

        return _translate_entity(
            ConceptRelationship,
            data['relationship_id'],
            data['target_language'],
            'translate_ontology_relationship',
        )
    except Exception as e:
        print(f'[ERROR] translate_ontology_api: {str(e)}')
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@translations_bp.route('/translate/quiz/<int:quiz_id>', methods=['POST'])
def translate_quiz_api(quiz_id):
    """Translate all questions in a quiz to target language."""
    session = db.Session()
    try:
        data = request.get_json()
        if not data or 'target_language' not in data:
            return jsonify({'error': 'target_language is required'}), 400

        target_language = data['target_language']

        quiz = session.get(Quiz, quiz_id)
        if not quiz:
            return jsonify({'error': 'Quiz not found'}), 404

        quiz_questions = session.query(QuizQuestion).filter_by(quiz_id=quiz_id).all()
        question_ids = [qq.question_id for qq in quiz_questions]
        questions = session.query(Question).filter(Question.id.in_(question_ids)).all()

        translated_count = 0
        for question in questions:
            if translation_service.translate_question(question, target_language, session):
                translated_count += 1

        return jsonify({
            'success': True,
            'quiz_id': quiz_id,
            'quiz_title': quiz.title,
            'questions_translated': translated_count,
            'total_questions': len(questions),
            'target_language': target_language
        }), 200
    except Exception as e:
        print(f'[ERROR] translate_quiz_api: {str(e)}')
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        session.close()


@translations_bp.route('/translate/quiz/<int:quiz_id>/status', methods=['GET'])
def get_quiz_translation_status(quiz_id):
    """Detailed translation status for a quiz - which questions are translated for each language."""
    session = db.Session()
    try:
        quiz = session.get(Quiz, quiz_id)
        if not quiz:
            return jsonify({'error': 'Quiz not found'}), 404

        quiz_questions = session.query(QuizQuestion).filter_by(quiz_id=quiz_id).all()
        question_ids = [qq.question_id for qq in quiz_questions]
        questions = session.query(Question).filter(Question.id.in_(question_ids)).all()

        translations = session.query(QuestionTranslation).filter(
            QuestionTranslation.question_id.in_(question_ids)
        ).all()

        translation_map = {}
        for t in translations:
            translation_map.setdefault(t.question_id, set()).add(t.language_code)

        language_status = {}
        for lang_code, lang_name in SUPPORTED_LANGUAGES.items():
            translated_count = 0
            missing_questions = []

            for q in questions:
                if q.id in translation_map and lang_code in translation_map[q.id]:
                    translated_count += 1
                else:
                    text = q.question_text
                    missing_questions.append({
                        'id': q.id,
                        'question_text': text[:80] + '...' if len(text) > 80 else text,
                        'solo_level': q.solo_level
                    })

            language_status[lang_code] = {
                'language_name': lang_name,
                'total_questions': len(questions),
                'translated_count': translated_count,
                'missing_count': len(missing_questions),
                'is_complete': len(missing_questions) == 0,
                'missing_questions': missing_questions
            }

        return jsonify({
            'success': True,
            'quiz_id': quiz_id,
            'quiz_title': quiz.title,
            'total_questions': len(questions),
            'language_status': language_status
        }), 200

    except Exception as e:
        print(f'[ERROR] get_quiz_translation_status: {str(e)}')
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        session.close()


@translations_bp.route('/translate/quiz/<int:quiz_id>/fix', methods=['POST'])
def fix_quiz_translations(quiz_id):
    """Delete bad translations (identical to original) for a quiz so they can be re-translated."""
    session = db.Session()
    try:
        data = request.get_json() or {}
        target_language = data.get('target_language')

        quiz_questions = session.query(QuizQuestion).filter_by(quiz_id=quiz_id).all()
        question_ids = [qq.question_id for qq in quiz_questions]
        questions = session.query(Question).filter(Question.id.in_(question_ids)).all()

        question_map = {q.id: q.question_text.strip().lower() for q in questions}

        query = session.query(QuestionTranslation).filter(
            QuestionTranslation.question_id.in_(question_ids)
        )
        if target_language:
            query = query.filter(QuestionTranslation.language_code == target_language)

        deleted_count = 0
        for t in query.all():
            original = question_map.get(t.question_id, '')
            translated = t.translated_question_text.strip().lower() if t.translated_question_text else ''

            if translated == original or (original and translated.startswith(original[:50])):
                session.delete(t)
                deleted_count += 1
                print(f"[FIX] Deleted bad translation for question {t.question_id} ({t.language_code})")

        session.commit()

        return jsonify({
            'success': True,
            'deleted_count': deleted_count,
            'message': f'Deleted {deleted_count} bad translations. You can now re-translate.'
        }), 200

    except Exception as e:
        print(f'[ERROR] fix_quiz_translations: {str(e)}')
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        session.close()


@translations_bp.route('/translate/question/<int:question_id>/retranslate', methods=['POST'])
def retranslate_question(question_id):
    """Delete existing translation for a question and retranslate it."""
    session = db.Session()
    try:
        data = request.get_json() or {}
        target_language = data.get('target_language')

        if not target_language:
            return jsonify({'error': 'target_language is required'}), 400

        question = session.get(Question, question_id)
        if not question:
            return jsonify({'error': 'Question not found'}), 404

        existing = session.query(QuestionTranslation).filter(
            QuestionTranslation.question_id == question_id,
            QuestionTranslation.language_code == target_language
        ).first()

        if existing:
            session.delete(existing)
            session.commit()
            print(f"[RETRANSLATE] Deleted old {target_language} translation for question {question_id}")

        result = translation_service.translate_question(question, target_language, session)

        if not result:
            return jsonify({
                'success': False,
                'error': 'Translation failed after multiple attempts'
            }), 500

        return jsonify({
            'success': True,
            'message': f'Question {question_id} retranslated to {target_language}',
            'translated_text': result.translated_question_text
        }), 200

    except Exception as e:
        print(f'[ERROR] retranslate_question: {str(e)}')
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        session.close()


@translations_bp.route('/translate/course/<int:course_id>', methods=['POST'])
def translate_course_api(course_id):
    """Translate all content in a course to target language."""
    session = db.Session()
    try:
        data = request.get_json()
        if not data or 'target_language' not in data:
            return jsonify({'error': 'target_language is required'}), 400

        target_language = data['target_language']

        course = session.get(Course, course_id)
        if not course:
            return jsonify({'error': 'Course not found'}), 404

        lesson_ids = [lesson.id for lesson in course.lessons]
        stats = translation_service.translate_course_content(lesson_ids, target_language, session)

        return jsonify({'success': True, 'stats': stats}), 200
    except Exception as e:
        print(f'[ERROR] translate_course_api: {str(e)}')
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        session.close()
