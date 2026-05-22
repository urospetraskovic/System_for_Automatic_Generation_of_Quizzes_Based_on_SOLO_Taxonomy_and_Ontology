"""
Services Layer
Centralized business logic for all domain operations
"""

from .lesson_service import LessonService
from .question_service import QuestionService
from .quiz_service import QuizService
from .ontology_manager import OntologyManager, ontology_manager
from .translation_service import TranslationService, get_translation_service
from .chatbot_service import ChatbotService, chatbot_service
from .coverage_service import CoverageService
from .mcq_lint import lint_question, lint_questions
from .solo_judge import classify_question, judge_questions
from .self_consistency import (
    score_candidate,
    pick_best_question,
    generate_with_self_consistency,
)
from .cove import verify_question, verify_questions
from .solvability import (
    assess_solvability, solvability_report,
    assess_stem_only_solvability, stem_only_solvability_report,
)
from .ioc import rate_question as ioc_rate_question, ioc_report
from .readability import (
    compute_readability,
    assess_question_readability,
    readability_report,
)
from .ambiguity import assess_ambiguity, ambiguity_report
from .misconception_mining import (
    mine_misconceptions,
    mine_lesson_misconceptions,
)
from .cloze_distractor import (
    suggest_cloze_distractors,
    gather_sibling_concepts,
    format_pool_for_prompt,
)
from .grammar_homogeneity import check_homogeneity, homogeneity_report
from .face_validity import assess_face_validity, face_validity_report

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
    'score_candidate',
    'pick_best_question',
    'generate_with_self_consistency',
    'verify_question',
    'verify_questions',
    'assess_solvability',
    'solvability_report',
]
