"""Chatbot routes."""

import traceback

from flask import Blueprint, request, jsonify

from repository import db
from models import Course, Lesson, Section
from services.domain.chatbot_service import chatbot_service

chat_bp = Blueprint('chat', __name__, url_prefix='/api/chat')


def _build_course_context(course_id):
    if not course_id:
        return None
    try:
        course = db.session.query(Course).filter_by(id=course_id).first()
        if course:
            return f"{course.name}: {course.description}"
    except Exception:
        return None
    return None


def _build_lesson_context(lesson_id):
    if not lesson_id:
        return None
    try:
        lesson = db.session.query(Lesson).filter_by(id=lesson_id).first()
        if not lesson:
            return None

        context = f"Lesson: {lesson.title}\n{lesson.description}"
        sections = db.session.query(Section).filter_by(lesson_id=lesson_id).all()
        for section in sections[:3]:
            context += f"\n\nSection: {section.title}"
            if section.content:
                context += f"\n{section.content[:500]}"
        return context
    except Exception:
        return None


@chat_bp.route('', methods=['POST'])
def chat():
    """Learning Assistant chatbot endpoint."""
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'No message provided'}), 400

        user_message = data.get('message', '').strip()
        if not user_message:
            return jsonify({'error': 'Empty message'}), 400

        course_id = data.get('course_id')
        lesson_id = data.get('lesson_id')

        result = chatbot_service.generate_response(
            user_message=user_message,
            course_context=_build_course_context(course_id),
            lesson_context=_build_lesson_context(lesson_id),
            conversation_history=data.get('conversation_history'),
            course_id=course_id,
        )

        return jsonify(result), 200
    except Exception as e:
        print(f"[Chat Error] {str(e)}")
        print(traceback.format_exc())
        return jsonify({'error': f'Chat error: {str(e)}'}), 500


@chat_bp.route('/explain-answer', methods=['POST'])
def chat_explain_answer():
    """Generate explanation for quiz answer."""
    try:
        data = request.get_json()
        if not data or 'question' not in data or 'correct_answer' not in data:
            return jsonify({'error': 'Missing required fields'}), 400

        result = chatbot_service.generate_quiz_explanation(
            question=data.get('question'),
            correct_answer=data.get('correct_answer'),
            user_answer=data.get('user_answer'),
        )

        return jsonify(result), 200
    except Exception as e:
        print(f"[Explain Answer Error] {str(e)}")
        return jsonify({'error': f'Error: {str(e)}'}), 500
