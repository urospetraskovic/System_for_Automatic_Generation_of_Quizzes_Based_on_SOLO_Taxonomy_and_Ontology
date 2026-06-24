"""
Services Layer
Centralized business logic for all domain operations
"""

from .domain.lesson_service import LessonService
from .domain.question_service import QuestionService
from .domain.quiz_service import QuizService
from .domain.ontology_manager import OntologyManager, ontology_manager
from .domain.translation_service import TranslationService, get_translation_service
from .domain.chatbot_service import ChatbotService, chatbot_service
from .quality.coverage_service import CoverageService
from .quality.mcq_lint import lint_question, lint_questions
from .quality.solo_judge import classify_question, judge_questions
from .quality.cove import verify_question, verify_questions
from .quality.solvability import (
    assess_solvability, solvability_report,
    assess_stem_only_solvability, stem_only_solvability_report,
)
from .quality.ioc import rate_question as ioc_rate_question, ioc_report
from .quality.readability import (
    compute_readability,
    assess_question_readability,
    readability_report,
)
from .quality.ambiguity import assess_ambiguity, ambiguity_report
from .quality.misconception_mining import (
    mine_misconceptions,
    mine_lesson_misconceptions,
)
from .quality.grammar_homogeneity import check_homogeneity, homogeneity_report
from .quality.face_validity import assess_face_validity, face_validity_report
from .quality import validation_cache

__all__ = [
    'LessonService',
    'QuestionService',
    'QuizService',
    'OntologyManager',
    'ontology_manager',
    'TranslationService',
    'get_translation_service',
    'ChatbotService',
    'chatbot_service',
    'CoverageService',
    'lint_question',
    'lint_questions',
    'classify_question',
    'judge_questions',
    'verify_question',
    'verify_questions',
    'assess_solvability',
    'solvability_report',
]
