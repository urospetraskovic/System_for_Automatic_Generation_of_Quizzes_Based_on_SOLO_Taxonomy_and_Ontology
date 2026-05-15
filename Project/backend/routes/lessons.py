"""Lesson upload, retrieval, and parsing routes."""

import os
import traceback

from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename

from repository import db
from core import content_parser
from services import LessonService, CoverageService

lessons_bp = Blueprint('lessons', __name__, url_prefix='/api')

ALLOWED_EXTENSIONS = {'pdf'}


def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@lessons_bp.route('/courses/<int:course_id>/lessons', methods=['GET'])
def get_lessons(course_id):
    """Get all lessons for a course."""
    try:
        lessons = db.get_lessons_for_course(course_id)
        return jsonify({'lessons': lessons}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@lessons_bp.route('/courses/<int:course_id>/lessons', methods=['POST'])
def upload_lesson(course_id):
    """Upload a new lesson (PDF file) to a course."""
    try:
        course = db.get_course(course_id)
        if not course:
            return jsonify({'error': 'Course not found'}), 404

        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if not _allowed_file(file.filename):
            return jsonify({'error': 'Only PDF files are allowed'}), 400

        title = request.form.get('title') or file.filename.rsplit('.', 1)[0]
        filename = secure_filename(file.filename)

        try:
            pdf_data = content_parser.extract_pdf_text_from_stream(file.stream)
            raw_content = pdf_data['full_text']
            pages_meta = pdf_data.get('pages_meta')
        except Exception as e:
            return jsonify({'error': f'Failed to extract PDF text: {str(e)}'}), 500

        lesson = db.create_lesson(
            course_id=course_id,
            title=title,
            filename=filename,
            file_path=None,
            raw_content=raw_content
        )

        if pages_meta:
            db.update_lesson_pages_meta(lesson['id'], pages_meta)

        return jsonify({
            'lesson': lesson,
            'message': 'Lesson uploaded successfully. Use /parse endpoint to extract sections and learning objects.'
        }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@lessons_bp.route('/lessons/<int:lesson_id>', methods=['GET'])
def get_lesson(lesson_id):
    """Get a specific lesson with its sections."""
    try:
        lesson = db.get_lesson_with_sections(lesson_id)
        if not lesson:
            return jsonify({'error': 'Lesson not found'}), 404
        return jsonify({'lesson': lesson}), 200
    except Exception as e:
        print(f"[ERROR] get_lesson({lesson_id}): {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@lessons_bp.route('/lessons/<int:lesson_id>', methods=['DELETE'])
def delete_lesson(lesson_id):
    """Delete a lesson."""
    try:
        lesson = db.get_lesson(lesson_id)
        if lesson and lesson.get('file_path') and os.path.exists(lesson['file_path']):
            os.remove(lesson['file_path'])

        success = db.delete_lesson(lesson_id)
        if success:
            return jsonify({'message': 'Lesson deleted successfully'}), 200
        return jsonify({'error': 'Lesson not found'}), 404
    except Exception as e:
        print(f'[ERROR] delete_lesson: {str(e)}')
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@lessons_bp.route('/lessons/<int:lesson_id>/parse', methods=['POST'])
def parse_lesson(lesson_id):
    """Parse a lesson to extract sections and learning objects using AI."""
    try:
        lesson = db.get_lesson(lesson_id, include_content=True)
        if not lesson:
            return jsonify({'error': 'Lesson not found'}), 404

        if not lesson.get('raw_content'):
            return jsonify({'error': 'Lesson has no content to parse'}), 400

        existing_sections = db.get_sections_for_lesson(lesson_id)
        if existing_sections:
            return jsonify({
                'message': 'Lesson already parsed',
                'sections': existing_sections
            }), 200

        print(f"[API] Parsing lesson: {lesson['title']}")
        full_lesson = db.get_lesson(lesson_id, include_content=True)
        pages_meta = full_lesson.get('pages_meta') if full_lesson else None
        parsed_sections = content_parser.parse_lesson_structure(
            lesson['raw_content'],
            lesson['title'],
            pages_meta=pages_meta,
        )

        db.bulk_create_sections_and_learning_objects(lesson_id, parsed_sections)

        sections = db.get_sections_for_lesson(lesson_id)
        for section in sections:
            section['learning_objects'] = db.get_learning_objects_for_section(section['id'])

        return jsonify({
            'message': 'Lesson parsed successfully. Sections and learning objects extracted. Use ontology/generate endpoint to create ontologies.',
            'sections': sections,
            'section_count': len(sections),
            'learning_object_count': sum(len(s.get('learning_objects', [])) for s in sections)
        }), 200

    except Exception as e:
        print(f"[API] Parse error: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@lessons_bp.route('/lessons/<int:lesson_id>/coverage', methods=['GET'])
def get_lesson_coverage(lesson_id):
    """Report how much of the lesson's PDF is covered by generated questions."""
    try:
        result = CoverageService.compute(lesson_id)
        if result is None:
            return jsonify({'error': 'Lesson not found'}), 404
        return jsonify(result), 200
    except Exception as e:
        print(f'[ERROR] get_lesson_coverage: {str(e)}')
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@lessons_bp.route('/lessons/<int:lesson_id>/parse-refactored', methods=['POST'])
def parse_lesson_refactored(lesson_id):
    """Refactored parse endpoint using the service layer."""
    try:
        result = LessonService.parse_lesson(lesson_id)
        status = result.pop('status', 200)

        if status != 200:
            return jsonify(result), status

        for section in result.get('sections', []):
            section['learning_objects'] = db.get_learning_objects_for_section(section['id'])

        return jsonify(result), status

    except Exception as e:
        print(f'[ERROR] parse_lesson_refactored: {str(e)}')
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
