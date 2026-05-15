"""
SQLAlchemy ORM Models for SOLO Quiz Generator
All database table definitions and relationships
"""

import os
import enum
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, JSON, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

# Database path
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'quiz_database.db')
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Create engine and base
engine = create_engine(DATABASE_URL, echo=False)
Base = declarative_base()
Session = sessionmaker(bind=engine)


class SoloLevel(enum.Enum):
    """SOLO Taxonomy levels for questions"""
    UNISTRUCTURAL = "unistructural"
    MULTISTRUCTURAL = "multistructural"
    RELATIONAL = "relational"
    EXTENDED_ABSTRACT = "extended_abstract"


class Course(Base):
    """Course model - top level container (e.g., "Operating Systems")"""
    __tablename__ = 'courses'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    code = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    lessons = relationship("Lesson", back_populates="course", cascade="all, delete-orphan")
    quizzes = relationship("Quiz", back_populates="course", cascade="all, delete-orphan")
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'lesson_count': len(self.lessons) if self.lessons else 0
        }


class Lesson(Base):
    """Lesson model - represents a PDF file/lesson"""
    __tablename__ = 'lessons'
    
    id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey('courses.id'), nullable=False)
    title = Column(String(255), nullable=False)
    filename = Column(String(255), nullable=True)
    file_path = Column(String(512), nullable=True)
    raw_content = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    order_index = Column(Integer, default=0)
    # Per-page metadata: [{"page": 1, "char_count": 1234, "start_offset": 0, "end_offset": 1250}, ...]
    pages_meta = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    course = relationship("Course", back_populates="lessons")
    sections = relationship("Section", back_populates="lesson", cascade="all, delete-orphan")
    
    def to_dict(self, include_content=False):
        result = {
            'id': self.id,
            'course_id': self.course_id,
            'title': self.title,
            'filename': self.filename,
            'summary': self.summary,
            'order_index': self.order_index,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'section_count': len(self.sections) if self.sections else 0,
            'translations': [t.to_dict() for t in self.lesson_translations] if hasattr(self, 'lesson_translations') else []
        }
        if include_content:
            result['raw_content'] = self.raw_content
            result['pages_meta'] = self.pages_meta
        return result


class Section(Base):
    """Section model - major divisions within a lesson"""
    __tablename__ = 'sections'
    
    id = Column(Integer, primary_key=True)
    lesson_id = Column(Integer, ForeignKey('lessons.id'), nullable=False)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    order_index = Column(Integer, default=0)
    start_page = Column(Integer, nullable=True)
    end_page = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    lesson = relationship("Lesson", back_populates="sections")
    learning_objects = relationship("LearningObject", back_populates="section", cascade="all, delete-orphan")
    
    def to_dict(self, include_content=False):
        result = {
            'id': self.id,
            'lesson_id': self.lesson_id,
            'title': self.title,
            'summary': self.summary,
            'order_index': self.order_index,
            'start_page': self.start_page,
            'end_page': self.end_page,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'learning_object_count': 0,
            'translations': [t.to_dict() for t in self.section_translations] if hasattr(self, 'section_translations') else []
        }
        try:
            result['learning_object_count'] = len(self.learning_objects) if self.learning_objects else 0
        except Exception:
            result['learning_object_count'] = 0
        if include_content:
            result['content'] = self.content
        return result


class LearningObject(Base):
    """Learning Object model - smallest unit of knowledge"""
    __tablename__ = 'learning_objects'
    
    id = Column(Integer, primary_key=True)
    section_id = Column(Integer, ForeignKey('sections.id'), nullable=False)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    key_points = Column(JSON, nullable=True)
    object_type = Column(String(50), nullable=True)
    keywords = Column(JSON, nullable=True)
    # Pages in the source PDF where this LO's title/keywords appear (e.g. [3, 4]).
    source_pages = Column(JSON, nullable=True)
    order_index = Column(Integer, default=0)
    is_ai_generated = Column(Integer, default=1)
    human_modified = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    section = relationship("Section", back_populates="learning_objects")

    def to_dict(self):
        return {
            'id': self.id,
            'section_id': self.section_id,
            'title': self.title,
            'content': self.content,
            'description': self.description,
            'key_points': self.key_points,
            'object_type': self.object_type,
            'keywords': self.keywords,
            'source_pages': self.source_pages or [],
            'order_index': self.order_index,
            'is_ai_generated': bool(getattr(self, 'is_ai_generated', 1)),
            'human_modified': bool(getattr(self, 'human_modified', 0)),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'translations': [t.to_dict() for t in self.learning_object_translations] if hasattr(self, 'learning_object_translations') else []
        }


class ConceptRelationship(Base):
    """Ontology relationship between learning objects"""
    __tablename__ = 'concept_relationships'
    
    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey('learning_objects.id'), nullable=False)
    target_id = Column(Integer, ForeignKey('learning_objects.id'), nullable=False)
    relationship_type = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    source = relationship("LearningObject", foreign_keys=[source_id])
    target = relationship("LearningObject", foreign_keys=[target_id])
    
    def to_dict(self):
        return {
            'id': self.id,
            'source_id': self.source_id,
            'target_id': self.target_id,
            'relationship_type': self.relationship_type,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'source_title': self.source.title if self.source else None,
            'target_title': self.target.title if self.target else None
        }


class Question(Base):
    """Question model - stores generated questions"""
    __tablename__ = 'questions'
    
    id = Column(Integer, primary_key=True)
    primary_lesson_id = Column(Integer, ForeignKey('lessons.id'), nullable=True)
    secondary_lesson_id = Column(Integer, ForeignKey('lessons.id'), nullable=True)
    section_id = Column(Integer, ForeignKey('sections.id'), nullable=True)
    learning_object_id = Column(Integer, ForeignKey('learning_objects.id'), nullable=True)
    
    solo_level = Column(String(50), nullable=False)
    question_text = Column(Text, nullable=False)
    question_type = Column(String(50), default='multiple_choice')
    
    options = Column(JSON, nullable=True)
    correct_answer = Column(Text, nullable=True)
    correct_option_index = Column(Integer, nullable=True)
    
    explanation = Column(Text, nullable=True)
    # Verbatim quote from the source text that justifies the correct answer
    # (captured from the LLM to detect hallucinations and enable "show source" UX).
    source_line = Column(Text, nullable=True)
    difficulty = Column(Float, nullable=True)
    bloom_level = Column(String(50), nullable=True)
    tags = Column(JSON, nullable=True)
    
    is_ai_generated = Column(Integer, default=1)
    human_modified = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    used_count = Column(Integer, default=0)
    
    # Relationships
    primary_lesson = relationship("Lesson", foreign_keys=[primary_lesson_id])
    secondary_lesson = relationship("Lesson", foreign_keys=[secondary_lesson_id])
    quiz_questions = relationship("QuizQuestion", back_populates="question", cascade="all, delete-orphan")
    # Note: 'translations' relationship is created via backref from QuestionTranslation
    
    def to_dict(self):
        # Get translations - handle both lazy-loaded and eager-loaded cases
        translations_list = []
        try:
            if hasattr(self, 'translations') and self.translations is not None:
                translations_list = [t.to_dict() for t in self.translations]
        except Exception:
            pass  # If translations can't be loaded, return empty list
        
        result = {
            'id': self.id,
            'primary_lesson_id': self.primary_lesson_id,
            'secondary_lesson_id': self.secondary_lesson_id,
            'section_id': self.section_id,
            'learning_object_id': self.learning_object_id,
            'solo_level': self.solo_level,
            'question_text': self.question_text,
            'question_type': self.question_type,
            'options': self.options,
            'correct_answer': self.correct_answer,
            'correct_option_index': self.correct_option_index,
            'explanation': self.explanation,
            'source_line': self.source_line,
            'difficulty': self.difficulty,
            'bloom_level': self.bloom_level,
            'tags': self.tags,
            'is_ai_generated': bool(getattr(self, 'is_ai_generated', 1)),
            'human_modified': bool(getattr(self, 'human_modified', 0)),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'used_count': self.used_count,
            'translations': translations_list
        }
        if self.primary_lesson:
            result['primary_lesson_title'] = self.primary_lesson.title
        if self.secondary_lesson:
            result['secondary_lesson_title'] = self.secondary_lesson.title
        return result


class Quiz(Base):
    """Quiz model - a collection of questions"""
    __tablename__ = 'quizzes'
    
    id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey('courses.id'), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    time_limit_minutes = Column(Integer, nullable=True)
    passing_score = Column(Float, nullable=True)
    shuffle_questions = Column(Integer, default=0)
    shuffle_options = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    course = relationship("Course", back_populates="quizzes")
    quiz_questions = relationship("QuizQuestion", back_populates="quiz", cascade="all, delete-orphan")
    
    def to_dict(self, include_questions=False):
        result = {
            'id': self.id,
            'course_id': self.course_id,
            'title': self.title,
            'description': self.description,
            'time_limit_minutes': self.time_limit_minutes,
            'passing_score': self.passing_score,
            'shuffle_questions': bool(self.shuffle_questions),
            'shuffle_options': bool(self.shuffle_options),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'question_count': len(self.quiz_questions) if self.quiz_questions else 0
        }
        if include_questions:
            result['questions'] = [qq.question.to_dict() for qq in self.quiz_questions]
        return result


class QuizQuestion(Base):
    """Association table between Quiz and Question with ordering"""
    __tablename__ = 'quiz_questions'
    
    id = Column(Integer, primary_key=True)
    quiz_id = Column(Integer, ForeignKey('quizzes.id', ondelete='CASCADE'), nullable=False)
    question_id = Column(Integer, ForeignKey('questions.id', ondelete='CASCADE'), nullable=False)
    order_index = Column(Integer, default=0)
    points = Column(Float, default=1.0)
    
    # Relationships
    quiz = relationship("Quiz", back_populates="quiz_questions")
    question = relationship("Question", back_populates="quiz_questions")


class QuestionTranslation(Base):
    """Stores translations of questions in different languages"""
    __tablename__ = 'question_translations'
    
    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey('questions.id', ondelete='CASCADE'), nullable=False)
    language_code = Column(String(10), nullable=False)  # e.g., 'en', 'sr', 'fr', 'es', 'de'
    language_name = Column(String(50), nullable=False)  # e.g., 'English', 'Serbian', 'French'
    
    translated_question_text = Column(Text, nullable=False)
    translated_options = Column(JSON, nullable=True)  # Translated options for multiple choice
    translated_correct_answer = Column(Text, nullable=True)
    translated_explanation = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    question = relationship("Question", backref="translations")
    
    def to_dict(self):
        return {
            'id': self.id,
            'question_id': self.question_id,
            'language_code': self.language_code,
            'language_name': self.language_name,
            'translated_question_text': self.translated_question_text,
            'translated_options': self.translated_options,
            'translated_correct_answer': self.translated_correct_answer,
            'translated_explanation': self.translated_explanation,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class LessonTranslation(Base):
    """Stores translations of lessons in different languages"""
    __tablename__ = 'lesson_translations'
    
    id = Column(Integer, primary_key=True)
    lesson_id = Column(Integer, ForeignKey('lessons.id', ondelete='CASCADE'), nullable=False)
    language_code = Column(String(10), nullable=False)
    language_name = Column(String(50), nullable=False)
    
    translated_title = Column(String(255), nullable=False)
    translated_summary = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    lesson = relationship("Lesson", backref="lesson_translations")
    
    def to_dict(self):
        return {
            'id': self.id,
            'lesson_id': self.lesson_id,
            'language_code': self.language_code,
            'language_name': self.language_name,
            'translated_title': self.translated_title,
            'translated_summary': self.translated_summary,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class SectionTranslation(Base):
    """Stores translations of sections in different languages"""
    __tablename__ = 'section_translations'
    
    id = Column(Integer, primary_key=True)
    section_id = Column(Integer, ForeignKey('sections.id', ondelete='CASCADE'), nullable=False)
    language_code = Column(String(10), nullable=False)
    language_name = Column(String(50), nullable=False)
    
    translated_title = Column(String(255), nullable=False)
    translated_content = Column(Text, nullable=True)
    translated_summary = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    section = relationship("Section", backref="section_translations")
    
    def to_dict(self):
        return {
            'id': self.id,
            'section_id': self.section_id,
            'language_code': self.language_code,
            'language_name': self.language_name,
            'translated_title': self.translated_title,
            'translated_content': self.translated_content,
            'translated_summary': self.translated_summary,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class LearningObjectTranslation(Base):
    """Stores translations of learning objects in different languages"""
    __tablename__ = 'learning_object_translations'
    
    id = Column(Integer, primary_key=True)
    learning_object_id = Column(Integer, ForeignKey('learning_objects.id', ondelete='CASCADE'), nullable=False)
    language_code = Column(String(10), nullable=False)
    language_name = Column(String(50), nullable=False)
    
    translated_title = Column(String(255), nullable=False)
    translated_content = Column(Text, nullable=True)
    translated_description = Column(Text, nullable=True)
    translated_key_points = Column(JSON, nullable=True)
    translated_keywords = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    learning_object = relationship("LearningObject", backref="learning_object_translations")
    
    def to_dict(self):
        return {
            'id': self.id,
            'learning_object_id': self.learning_object_id,
            'language_code': self.language_code,
            'language_name': self.language_name,
            'translated_title': self.translated_title,
            'translated_content': self.translated_content,
            'translated_description': self.translated_description,
            'translated_key_points': self.translated_key_points,
            'translated_keywords': self.translated_keywords,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class OntologyTranslation(Base):
    """Stores translations of ontology relationships in different languages"""
    __tablename__ = 'ontology_translations'
    
    id = Column(Integer, primary_key=True)
    concept_relationship_id = Column(Integer, ForeignKey('concept_relationships.id', ondelete='CASCADE'), nullable=False)
    language_code = Column(String(10), nullable=False)
    language_name = Column(String(50), nullable=False)
    
    translated_relationship_type = Column(String(100), nullable=False)
    translated_description = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    concept_relationship = relationship("ConceptRelationship", backref="ontology_translations")
    
    def to_dict(self):
        return {
            'id': self.id,
            'concept_relationship_id': self.concept_relationship_id,
            'language_code': self.language_code,
            'language_name': self.language_name,
            'translated_relationship_type': self.translated_relationship_type,
            'translated_description': self.translated_description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
