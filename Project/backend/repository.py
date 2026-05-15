"""
Database Repository
All CRUD operations for the SOLO Quiz Generator database
"""

from datetime import datetime
from sqlalchemy import text
from sqlalchemy.orm import joinedload
from models import (
    Base, engine, Session,
    Course, Lesson, Section, LearningObject,
    ConceptRelationship, Question, Quiz, QuizQuestion,
    QuestionTranslation, LessonTranslation, SectionTranslation,
    LearningObjectTranslation, OntologyTranslation
)


def _add_missing_columns():
    """Idempotently add nullable columns introduced after the initial schema."""
    expected = {
        'lessons': [('pages_meta', 'JSON')],
        'learning_objects': [('source_pages', 'JSON')],
        'questions': [('source_line', 'TEXT')],
    }
    with engine.connect() as conn:
        for table, columns in expected.items():
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()}
            for col_name, col_type in columns:
                if col_name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"))
                    print(f"[DATABASE] Added column {table}.{col_name}")
        conn.commit()


def init_database():
    """Initialize the database, creating all tables"""
    from models.models import DB_PATH
    Base.metadata.create_all(engine)
    _add_missing_columns()
    print(f"[DATABASE] Initialized at {DB_PATH}")


class DatabaseManager:
    """Manager class for all database operations"""
    
    # Re-export models for backward compatibility
    Lesson = Lesson
    Question = Question
    
    def __init__(self):
        self.Session = Session
    
    def get_session(self):
        return self.Session()
    
    # ==================== COURSE OPERATIONS ====================
    
    def create_course(self, name, code=None, description=None):
        session = self.get_session()
        try:
            course = Course(name=name, code=code, description=description)
            session.add(course)
            session.commit()
            return course.to_dict()
        finally:
            session.close()
    
    def get_all_courses(self):
        session = self.get_session()
        try:
            courses = session.query(Course).all()
            return [c.to_dict() for c in courses]
        finally:
            session.close()
    
    def get_course(self, course_id):
        session = self.get_session()
        try:
            course = session.query(Course).filter(Course.id == course_id).first()
            return course.to_dict() if course else None
        finally:
            session.close()
    
    def delete_course(self, course_id):
        session = self.get_session()
        try:
            course = session.query(Course).filter(Course.id == course_id).first()
            if course:
                session.delete(course)
                session.commit()
                return True
            return False
        finally:
            session.close()
    
    # ==================== LESSON OPERATIONS ====================
    
    def create_lesson(self, course_id, title, filename=None, file_path=None, raw_content=None):
        session = self.get_session()
        try:
            max_order = session.query(Lesson).filter(Lesson.course_id == course_id).count()
            lesson = Lesson(
                course_id=course_id,
                title=title,
                filename=filename,
                file_path=file_path,
                raw_content=raw_content,
                order_index=max_order
            )
            session.add(lesson)
            session.commit()
            return lesson.to_dict()
        finally:
            session.close()
    
    def get_lessons_for_course(self, course_id):
        session = self.get_session()
        try:
            lessons = session.query(Lesson).filter(Lesson.course_id == course_id).order_by(Lesson.order_index).all()
            return [l.to_dict() for l in lessons]
        finally:
            session.close()
    
    def get_lesson(self, lesson_id, include_content=False):
        session = self.get_session()
        try:
            lesson = session.query(Lesson).filter(Lesson.id == lesson_id).first()
            return lesson.to_dict(include_content=include_content) if lesson else None
        finally:
            session.close()
    
    def get_lesson_with_sections(self, lesson_id):
        session = self.get_session()
        try:
            lesson = session.query(Lesson).filter(Lesson.id == lesson_id).first()
            if not lesson:
                return None
            
            result = lesson.to_dict(include_content=True)
            sections_list = []
            
            for s in lesson.sections:
                section_dict = s.to_dict(include_content=True)
                try:
                    learning_objects = session.query(LearningObject).filter(
                        LearningObject.section_id == s.id
                    ).all()
                    section_dict['learning_objects'] = [lo.to_dict() for lo in learning_objects]
                except Exception as e:
                    print(f"[WARNING] Could not load learning objects for section {s.id}: {str(e)}")
                    section_dict['learning_objects'] = []
                sections_list.append(section_dict)
            
            result['sections'] = sections_list
            return result
        finally:
            session.close()
    
    def update_lesson_pages_meta(self, lesson_id, pages_meta):
        session = self.get_session()
        try:
            lesson = session.query(Lesson).filter(Lesson.id == lesson_id).first()
            if not lesson:
                return False
            lesson.pages_meta = pages_meta
            session.commit()
            return True
        finally:
            session.close()

    def delete_lesson(self, lesson_id):
        session = self.get_session()
        try:
            lesson = session.query(Lesson).filter(Lesson.id == lesson_id).first()
            if lesson:
                session.delete(lesson)
                session.commit()
                return True
            return False
        finally:
            session.close()
    
    # ==================== SECTION OPERATIONS ====================
    
    def create_section(self, lesson_id, title, content=None, start_page=None, end_page=None):
        session = self.get_session()
        try:
            max_order = session.query(Section).filter(Section.lesson_id == lesson_id).count()
            section = Section(
                lesson_id=lesson_id,
                title=title,
                content=content,
                start_page=start_page,
                end_page=end_page,
                order_index=max_order
            )
            session.add(section)
            session.commit()
            return section.to_dict()
        finally:
            session.close()
    
    def get_sections_for_lesson(self, lesson_id):
        session = self.get_session()
        try:
            sections = session.query(Section).filter(Section.lesson_id == lesson_id).order_by(Section.order_index).all()
            return [s.to_dict() for s in sections]
        finally:
            session.close()
    
    def get_section_with_learning_objects(self, section_id):
        session = self.get_session()
        try:
            section = session.query(Section).filter(Section.id == section_id).first()
            if not section:
                return None
            result = section.to_dict(include_content=True)
            result['learning_objects'] = [lo.to_dict() for lo in section.learning_objects]
            return result
        finally:
            session.close()
    
    # ==================== LEARNING OBJECT OPERATIONS ====================
    
    def create_learning_object(self, section_id, title, content=None, object_type=None, keywords=None, is_ai_generated=True):
        session = self.get_session()
        try:
            max_order = session.query(LearningObject).filter(LearningObject.section_id == section_id).count()
            lo = LearningObject(
                section_id=section_id,
                title=title,
                content=content,
                object_type=object_type,
                keywords=keywords,
                order_index=max_order,
                is_ai_generated=int(is_ai_generated)
            )
            session.add(lo)
            session.commit()
            return lo.to_dict()
        finally:
            session.close()
    
    def update_learning_object(self, lo_id, title=None, content=None, object_type=None, keywords=None, mark_as_human_modified=False):
        session = self.get_session()
        try:
            lo = session.query(LearningObject).filter(LearningObject.id == lo_id).first()
            if not lo:
                return None
            
            if title is not None:
                lo.title = title
            if content is not None:
                lo.content = content
            if object_type is not None:
                lo.object_type = object_type
            if keywords is not None:
                lo.keywords = keywords
            if mark_as_human_modified:
                lo.human_modified = 1
            lo.updated_at = datetime.utcnow()
            
            session.commit()
            return lo.to_dict()
        finally:
            session.close()
    
    def delete_learning_object(self, lo_id):
        session = self.get_session()
        try:
            lo = session.query(LearningObject).filter(LearningObject.id == lo_id).first()
            if lo:
                session.delete(lo)
                session.commit()
                return True
            return False
        finally:
            session.close()
    
    def get_learning_objects_for_section(self, section_id):
        session = self.get_session()
        try:
            los = session.query(LearningObject).filter(LearningObject.section_id == section_id).order_by(LearningObject.order_index).all()
            return [lo.to_dict() for lo in los]
        finally:
            session.close()
    
    # ==================== RELATIONSHIP OPERATIONS ====================
    
    def create_relationship(self, source_id, target_id, relationship_type, description=None):
        session = self.get_session()
        try:
            rel = ConceptRelationship(
                source_id=source_id,
                target_id=target_id,
                relationship_type=relationship_type,
                description=description
            )
            session.add(rel)
            session.commit()
            return rel.to_dict()
        finally:
            session.close()

    def get_relationships_for_lesson(self, lesson_id):
        session = self.get_session()
        try:
            sections = session.query(Section).filter(Section.lesson_id == lesson_id).all()
            section_ids = [s.id for s in sections]
            los = session.query(LearningObject).filter(LearningObject.section_id.in_(section_ids)).all()
            lo_ids = [lo.id for lo in los]
            
            rels = session.query(ConceptRelationship).filter(
                ConceptRelationship.source_id.in_(lo_ids) | 
                ConceptRelationship.target_id.in_(lo_ids)
            ).all()
            return [r.to_dict() for r in rels]
        finally:
            session.close()

    def delete_relationship(self, rel_id):
        session = self.get_session()
        try:
            rel = session.query(ConceptRelationship).filter(ConceptRelationship.id == rel_id).first()
            if not rel:
                raise ValueError(f"Relationship with ID {rel_id} not found")
            session.delete(rel)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def bulk_create_relationships(self, relationships_data):
        session = self.get_session()
        try:
            for r_data in relationships_data:
                rel = ConceptRelationship(
                    source_id=r_data['source_id'],
                    target_id=r_data['target_id'],
                    relationship_type=r_data['relationship_type'],
                    description=r_data.get('description')
                )
                session.add(rel)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    
    # ==================== QUESTION OPERATIONS ====================
    
    def create_question(self, solo_level, question_text, question_type='multiple_choice',
                       primary_lesson_id=None, secondary_lesson_id=None, section_id=None,
                       learning_object_id=None, options=None, correct_answer=None,
                       correct_option_index=None, explanation=None, difficulty=None,
                       bloom_level=None, tags=None, is_ai_generated=True):
        session = self.get_session()
        try:
            question = Question(
                solo_level=solo_level,
                question_text=question_text,
                question_type=question_type,
                primary_lesson_id=primary_lesson_id,
                secondary_lesson_id=secondary_lesson_id,
                section_id=section_id,
                learning_object_id=learning_object_id,
                options=options,
                correct_answer=correct_answer,
                correct_option_index=correct_option_index,
                explanation=explanation,
                difficulty=difficulty,
                bloom_level=bloom_level,
                tags=tags,
                is_ai_generated=int(is_ai_generated)
            )
            session.add(question)
            session.commit()
            return question.to_dict()
        finally:
            session.close()
    
    def update_question(self, question_id, **kwargs):
        session = self.get_session()
        try:
            question = session.query(Question).filter(Question.id == question_id).first()
            if not question:
                return None
            
            mark_human_modified = kwargs.pop('mark_human_modified', False)
            
            for key, value in kwargs.items():
                if hasattr(question, key) and value is not None:
                    setattr(question, key, value)
            
            if mark_human_modified:
                question.human_modified = 1
            question.updated_at = datetime.utcnow()
            
            session.commit()
            return question.to_dict()
        finally:
            session.close()
    
    def get_questions_by_lesson(self, lesson_id):
        session = self.get_session()
        try:
            questions = session.query(Question).filter(
                (Question.primary_lesson_id == lesson_id) | 
                (Question.secondary_lesson_id == lesson_id)
            ).all()
            return [q.to_dict() for q in questions]
        finally:
            session.close()
    
    def get_questions_by_solo_level(self, solo_level, lesson_id=None):
        session = self.get_session()
        try:
            query = session.query(Question).filter(Question.solo_level == solo_level)
            if lesson_id:
                query = query.filter(
                    (Question.primary_lesson_id == lesson_id) | 
                    (Question.secondary_lesson_id == lesson_id)
                )
            questions = query.all()
            return [q.to_dict() for q in questions]
        finally:
            session.close()
    
    def get_all_questions(self, course_id=None):
        session = self.get_session()
        try:
            if course_id:
                lessons = session.query(Lesson).filter(Lesson.course_id == course_id).all()
                lesson_ids = [l.id for l in lessons]
                questions = session.query(Question).filter(
                    (Question.primary_lesson_id.in_(lesson_ids)) | 
                    (Question.secondary_lesson_id.in_(lesson_ids))
                ).all()
            else:
                questions = session.query(Question).all()
            return [q.to_dict() for q in questions]
        finally:
            session.close()
    
    def delete_question(self, question_id):
        session = self.get_session()
        try:
            question = session.query(Question).filter(Question.id == question_id).first()
            if question:
                # Import all translation models that might reference this question
                from models.models import QuizQuestion, QuestionTranslation
                
                # Delete related quiz questions first
                session.query(QuizQuestion).filter(QuizQuestion.question_id == question_id).delete()
                
                # Delete question translations
                session.query(QuestionTranslation).filter(QuestionTranslation.question_id == question_id).delete()
                
                # Now delete the question itself
                session.delete(question)
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    
    # ==================== QUIZ OPERATIONS ====================
    
    def create_quiz(self, title, course_id=None, description=None, time_limit_minutes=None,
                   passing_score=None, shuffle_questions=False, shuffle_options=False):
        session = self.get_session()
        try:
            quiz = Quiz(
                title=title,
                course_id=course_id,
                description=description,
                time_limit_minutes=time_limit_minutes,
                passing_score=passing_score,
                shuffle_questions=int(shuffle_questions),
                shuffle_options=int(shuffle_options)
            )
            session.add(quiz)
            session.commit()
            return quiz.to_dict()
        finally:
            session.close()
    
    def add_question_to_quiz(self, quiz_id, question_id, points=1.0):
        session = self.get_session()
        try:
            max_order = session.query(QuizQuestion).filter(QuizQuestion.quiz_id == quiz_id).count()
            qq = QuizQuestion(
                quiz_id=quiz_id,
                question_id=question_id,
                order_index=max_order,
                points=points
            )
            session.add(qq)
            session.commit()
            return True
        finally:
            session.close()
    
    def get_quiz(self, quiz_id, include_questions=False):
        session = self.get_session()
        try:
            if include_questions:
                # Eagerly load questions and their translations
                quiz = session.query(Quiz).options(
                    joinedload(Quiz.quiz_questions)
                    .joinedload(QuizQuestion.question)
                    .joinedload(Question.translations)
                ).filter(Quiz.id == quiz_id).first()
            else:
                quiz = session.query(Quiz).filter(Quiz.id == quiz_id).first()
            return quiz.to_dict(include_questions=include_questions) if quiz else None
        finally:
            session.close()
    
    def get_quizzes_for_course(self, course_id):
        session = self.get_session()
        try:
            quizzes = session.query(Quiz).filter(Quiz.course_id == course_id).all()
            return [q.to_dict() for q in quizzes]
        finally:
            session.close()
    
    def delete_quiz(self, quiz_id):
        session = self.get_session()
        try:
            quiz = session.query(Quiz).filter(Quiz.id == quiz_id).first()
            if quiz:
                session.delete(quiz)
                session.commit()
                return True
            return False
        finally:
            session.close()
    
    # ==================== BULK OPERATIONS ====================
    
    def bulk_create_sections_and_learning_objects(self, lesson_id, parsed_data):
        """Create multiple sections and learning objects from parsed PDF data"""
        session = self.get_session()
        try:
            for idx, section_data in enumerate(parsed_data):
                section = Section(
                    lesson_id=lesson_id,
                    title=section_data['title'],
                    content=section_data.get('content'),
                    start_page=section_data.get('start_page'),
                    end_page=section_data.get('end_page'),
                    order_index=idx
                )
                session.add(section)
                session.flush()
                
                for lo_idx, lo_data in enumerate(section_data.get('learning_objects', [])):
                    lo = LearningObject(
                        section_id=section.id,
                        title=lo_data['title'],
                        content=lo_data.get('content'),
                        description=lo_data.get('description'),
                        key_points=lo_data.get('key_points'),
                        object_type=lo_data.get('object_type', lo_data.get('type')),
                        keywords=lo_data.get('keywords'),
                        source_pages=lo_data.get('source_pages'),
                        order_index=lo_idx
                    )
                    session.add(lo)
            
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    
    def bulk_create_questions(self, questions_data):
        """Create multiple questions at once"""
        session = self.get_session()
        try:
            created_ids = []
            for q_data in questions_data:
                question = Question(
                    solo_level=q_data['solo_level'],
                    question_text=q_data['question_text'],
                    question_type=q_data.get('question_type', 'multiple_choice'),
                    primary_lesson_id=q_data.get('primary_lesson_id'),
                    secondary_lesson_id=q_data.get('secondary_lesson_id'),
                    section_id=q_data.get('section_id'),
                    learning_object_id=q_data.get('learning_object_id'),
                    options=q_data.get('options'),
                    correct_answer=q_data.get('correct_answer'),
                    correct_option_index=q_data.get('correct_option_index'),
                    explanation=q_data.get('explanation'),
                    source_line=q_data.get('source_line'),
                    difficulty=q_data.get('difficulty'),
                    bloom_level=q_data.get('bloom_level'),
                    tags=q_data.get('tags')
                )
                session.add(question)
                session.flush()
                created_ids.append(question.id)
            
            session.commit()
            return created_ids
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()


# Initialize on import
init_database()

# Create global database manager instance
db = DatabaseManager()
