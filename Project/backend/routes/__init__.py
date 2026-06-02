"""
Routes Package
Flask Blueprints organized by domain area.
"""

from .health import health_bp
from .sparql import sparql_bp
from .courses import courses_bp
from .lessons import lessons_bp
from .ontology import ontology_bp
from .sections import sections_bp
from .learning_objects import learning_objects_bp
from .questions import questions_bp
from .quizzes import quizzes_bp
from .translations import translations_bp
from .chat import chat_bp
from .admin import admin_bp
from .jobs import jobs_bp
from .llm import llm_bp
from .errors import register_error_handlers


ALL_BLUEPRINTS = [
    health_bp,
    sparql_bp,
    courses_bp,
    lessons_bp,
    ontology_bp,
    sections_bp,
    learning_objects_bp,
    questions_bp,
    quizzes_bp,
    translations_bp,
    chat_bp,
    admin_bp,
    jobs_bp,
    llm_bp,
]


def register_routes(app):
    """Register every blueprint and error handler on the Flask app."""
    for bp in ALL_BLUEPRINTS:
        app.register_blueprint(bp)
    register_error_handlers(app)


__all__ = ['register_routes']
