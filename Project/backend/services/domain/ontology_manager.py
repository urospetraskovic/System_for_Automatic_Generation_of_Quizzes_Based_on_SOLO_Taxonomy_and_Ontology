"""
Ontology Manager Service

This service manages the evolving educational ontology using the following architecture:

ARCHITECTURE:
┌─────────────────────────────────────────────────────────────────┐
│  seed_ontology_base.owl (IMMUTABLE)                             │
│  - TBox: Classes, Properties, SOLO/Bloom levels                 │
│  - Never modified by the system                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓ imported by
┌─────────────────────────────────────────────────────────────────┐
│  SQLite Database (SOURCE OF TRUTH)                              │
│  - Courses, Lessons, Sections, Learning Objects                 │
│  - ConceptRelationships (discovered relationships)              │
│  - Questions, Quizzes                                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓ exported to
┌─────────────────────────────────────────────────────────────────┐
│  knowledge_base.owl (GENERATED ON EXPORT)                       │
│  - Imports seed_ontology_base.owl                               │
│  - Contains all individuals from database                       │
│  - Full populated ontology for Protégé                          │
└─────────────────────────────────────────────────────────────────┘

USAGE:
    from services.domain.ontology_manager import OntologyManager
    
    manager = OntologyManager()
    
    # Export full populated ontology
    owl_content = manager.export_full_ontology(course_id=1)
    
    # Export just for a lesson
    owl_content = manager.export_lesson_ontology(lesson_id=5)
    
    # Get statistics
    stats = manager.get_ontology_stats()
"""

import os
import html
import re
from datetime import datetime
from typing import Optional, List, Dict, Any

from rdflib import Graph

# Database imports
from repository import db
from models import (
    Course, Lesson, Section, LearningObject, 
    ConceptRelationship, Question, Quiz
)

# Paths
ONTOLOGY_DIR = os.path.join(os.path.dirname(__file__), '..', 'ontology')
SEED_BASE_PATH = os.path.join(ONTOLOGY_DIR, 'seed_ontology_base.owl')
KNOWLEDGE_BASE_PATH = os.path.join(ONTOLOGY_DIR, 'knowledge_base.owl')

# Ontology IRIs
SEED_IRI = "http://example.org/solo-education-ontology"
KNOWLEDGE_IRI = "http://example.org/solo-education-ontology/knowledge"


class OntologyManager:
    """
    Manages the educational ontology with seed + knowledge base architecture.
    
    The seed ontology provides the TBox (schema):
    - Classes: Course, Lesson, Section, LearningObject, Question, etc.
    - Properties: isPrerequisiteFor, buildsUpon, hasSOLOLevel, etc.
    - Individuals: SOLO levels, Bloom levels
    
    The knowledge base provides the ABox (instances):
    - Actual courses, lessons, sections from the database
    - Learning objects extracted from PDFs
    - Discovered relationships between concepts
    - Generated questions and quizzes
    """
    
    def __init__(self):
        self.seed_iri = SEED_IRI
        self.knowledge_iri = KNOWLEDGE_IRI
        
    # ==================== HELPERS ====================
    
    @staticmethod
    def escape_xml(text: str) -> str:
        """Escape special XML characters"""
        if not text:
            return ""
        return html.escape(str(text), quote=True)
    
    @staticmethod
    def make_id(text: str, prefix: str = "") -> str:
        """Create valid OWL identifier from text"""
        if not text:
            return f"{prefix}Unknown"
        cleaned = re.sub(r'[^a-zA-Z0-9_-]', '_', str(text))
        # Remove consecutive underscores
        cleaned = re.sub(r'_+', '_', cleaned)
        # Remove leading/trailing underscores
        cleaned = cleaned.strip('_')
        if cleaned and cleaned[0].isdigit():
            cleaned = 'N_' + cleaned
        return f"{prefix}{cleaned}" if prefix else cleaned or "Unknown"
    
    @staticmethod
    def normalize_relationship_type(rel_type: str) -> str:
        """Normalize relationship type to match seed ontology properties"""
        if not rel_type:
            return 'relatedTo'
        
        # Map to seed ontology property names
        mappings = {
            'builds_upon': 'buildsUpon',
            'buildsupon': 'buildsUpon',
            'part_of': 'isPartOf',
            'partof': 'isPartOf',
            'is_part_of': 'isPartOf',
            'related_to': 'relatedTo',
            'relatedto': 'relatedTo',
            'related': 'relatedTo',
            'contrasts_with': 'contrastsWith',
            'contrastswith': 'contrastsWith',
            'contrasts': 'contrastsWith',
            'is_example_of': 'isExampleOf',
            'isexampleof': 'isExampleOf',
            'example_of': 'isExampleOf',
            'example': 'isExampleOf',
            'is_type_of': 'isTypeOf',
            'istypeof': 'isTypeOf',
            'type_of': 'isTypeOf',
            'type': 'isTypeOf',
            'prerequisite': 'isPrerequisiteFor',
            'prerequisite_for': 'isPrerequisiteFor',
            'is_prerequisite_for': 'isPrerequisiteFor',
            'has_prerequisite': 'hasPrerequisite',
            'enables': 'enables',
            'uses': 'uses',
            'has_part': 'hasPart',
            'haspart': 'hasPart',
            'has_example': 'hasExample',
            'hasexample': 'hasExample',
        }
        
        normalized = rel_type.lower().strip().replace(' ', '_')
        return mappings.get(normalized, 'relatedTo')
    
    @staticmethod
    def map_object_type_to_class(object_type: str) -> str:
        """Map learning object type to ontology class"""
        if not object_type:
            return 'LearningObject'
        
        mappings = {
            'concept': 'Concept',
            'definition': 'Definition',
            'procedure': 'Procedure',
            'principle': 'Principle',
            'example': 'Example',
            'fact': 'Fact',
            'algorithm': 'Procedure',  # Subtype
            'theory': 'Principle',
            'law': 'Principle',
            'rule': 'Principle',
        }
        
        return mappings.get(object_type.lower().strip(), 'LearningObject')
    
    @staticmethod
    def map_question_type_to_class(question_type: str) -> str:
        """Map question type to ontology class"""
        if not question_type:
            return 'Question'
        
        mappings = {
            'multiple_choice': 'MultipleChoiceQuestion',
            'multiplechoice': 'MultipleChoiceQuestion',
            'mcq': 'MultipleChoiceQuestion',
            'true_false': 'TrueFalseQuestion',
            'truefalse': 'TrueFalseQuestion',
            'tf': 'TrueFalseQuestion',
            'short_answer': 'ShortAnswerQuestion',
            'shortanswer': 'ShortAnswerQuestion',
            'essay': 'EssayQuestion',
            'open': 'EssayQuestion',
        }
        
        return mappings.get(question_type.lower().strip(), 'Question')
    
    @staticmethod
    def map_solo_level(solo_level: str) -> str:
        """Map SOLO level string to ontology individual"""
        if not solo_level:
            return 'Unistructural'
        
        mappings = {
            'prestructural': 'Prestructural',
            'unistructural': 'Unistructural',
            'multistructural': 'Multistructural',
            'relational': 'Relational',
            'extended_abstract': 'ExtendedAbstract',
            'extendedabstract': 'ExtendedAbstract',
        }
        
        return mappings.get(solo_level.lower().strip().replace(' ', '_'), 'Unistructural')
    
    @staticmethod
    def map_bloom_level(bloom_level: str) -> str:
        """Map Bloom level string to ontology individual"""
        if not bloom_level:
            return None
        
        mappings = {
            'remember': 'Remember',
            'understand': 'Understand',
            'apply': 'Apply',
            'analyze': 'Analyze',
            'analyse': 'Analyze',
            'evaluate': 'Evaluate',
            'create': 'Create',
        }
        
        return mappings.get(bloom_level.lower().strip(), None)
    
    # ==================== EXPORT METHODS ====================

    @staticmethod
    def _to_rdf_xml(turtle_content: str) -> str:
        """
        Convert a Turtle document to RDF/XML using rdflib.

        Falls back to returning the raw Turtle if parsing fails, so callers
        always get some serialisation rather than a 500.
        """
        try:
            from rdflib import Graph
            g = Graph()
            g.parse(data=turtle_content, format='turtle')
            return g.serialize(format='pretty-xml')
        except Exception as e:
            print(f"[OntologyManager] RDF/XML conversion failed, returning Turtle: {e}")
            return turtle_content

    def export_full_ontology(self, course_id: Optional[int] = None, fmt: str = 'turtle') -> str:
        """
        Export complete ontology with seed + all knowledge from database.
        
        Args:
            course_id: If provided, only export content from this course.
                      If None, export everything.
            fmt: 'turtle' (default) or 'xml' for RDF/XML.

        Returns:
            Serialised ontology string in the requested format.
        """
        session = db.get_session()
        try:
            # Query data based on scope
            if course_id:
                courses = session.query(Course).filter_by(id=course_id).all()
            else:
                courses = session.query(Course).all()
            
            # Force load all related data BEFORE session closes
            # This prevents lazy loading issues later
            
            # Collect all entities
            all_lessons = []
            all_sections = []
            all_learning_objects = []
            all_relationships = []
            all_questions = []
            all_quizzes = []
            
            for course in courses:
                # Force load lessons
                lessons = list(course.lessons) if course.lessons else []
                all_lessons.extend(lessons)
                
                for lesson in lessons:
                    # Force load sections
                    sections = list(lesson.sections) if lesson.sections else []
                    all_sections.extend(sections)
                    
                    for section in sections:
                        # Force load learning objects
                        los = list(section.learning_objects) if section.learning_objects else []
                        all_learning_objects.extend(los)
                
                # Force load quizzes
                quizzes = list(course.quizzes) if course.quizzes else []
                all_quizzes.extend(quizzes)
            
            # Get all learning object IDs for relationship query
            lo_ids = [lo.id for lo in all_learning_objects]
            
            if lo_ids:
                all_relationships = session.query(ConceptRelationship).filter(
                    (ConceptRelationship.source_id.in_(lo_ids)) |
                    (ConceptRelationship.target_id.in_(lo_ids))
                ).all()
                
                # Make sure related objects are fully loaded before session closes
                for rel in all_relationships:
                    _ = rel.source
                    _ = rel.target
            
            # Get questions linked to these lessons
            lesson_ids = [l.id for l in all_lessons]
            if lesson_ids:
                all_questions = session.query(Question).filter(
                    Question.primary_lesson_id.in_(lesson_ids)
                ).all()
            
            # Prepare data dictionaries to retain after session closes
            courses_dict = [{
                'id': c.id,
                'name': c.name,
                'code': c.code,
                'description': c.description,
            } for c in courses]
            
            lessons_dict = [{
                'id': l.id,
                'course_id': l.course_id,
                'title': l.title,
                'filename': l.filename,
                'summary': l.summary,
                'order_index': l.order_index,
            } for l in all_lessons]
            
            sections_dict = [{
                'id': s.id,
                'lesson_id': s.lesson_id,
                'title': s.title,
                'content': s.content,
                'summary': s.summary,
                'order_index': s.order_index,
                'start_page': s.start_page,
                'end_page': s.end_page,
            } for s in all_sections]
            
            los_dict = [{
                'id': lo.id,
                'section_id': lo.section_id,
                'title': lo.title,
                'content': lo.content,
                'description': lo.description,
                'key_points': lo.key_points,
                'object_type': lo.object_type,
                'keywords': lo.keywords,
                'order_index': lo.order_index,
            } for lo in all_learning_objects]
            
            relationships_dict = [{
                'id': r.id,
                'source_id': r.source_id,
                'target_id': r.target_id,
                'source_title': r.source.title if r.source else None,
                'target_title': r.target.title if r.target else None,
                'relationship_type': r.relationship_type,
                'description': r.description,
            } for r in all_relationships]
            
            questions_dict = [{
                'id': q.id,
                'primary_lesson_id': q.primary_lesson_id,
                'secondary_lesson_id': q.secondary_lesson_id,
                'section_id': q.section_id,
                'learning_object_id': q.learning_object_id,
                'solo_level': q.solo_level,
                'question_text': q.question_text,
                'question_type': q.question_type,
                'options': q.options,
                'correct_answer': q.correct_answer,
                'correct_option_index': q.correct_option_index,
                'explanation': q.explanation,
                'difficulty': q.difficulty,
                'bloom_level': q.bloom_level,
                'tags': q.tags,
            } for q in all_questions]
            
            quizzes_dict = [{
                'id': quiz.id,
                'course_id': quiz.course_id,
                'title': quiz.title,
                'description': quiz.description,
                'time_limit_minutes': quiz.time_limit_minutes,
                'passing_score': quiz.passing_score,
                'shuffle_questions': quiz.shuffle_questions,
                'shuffle_options': quiz.shuffle_options,
                'quiz_questions': [(qq.question_id, qq.order_index) for qq in quiz.quiz_questions],
            } for quiz in all_quizzes]
            
            # Generate OWL with dictionaries (no session dependency)
            turtle = self._generate_knowledge_base_owl(
                courses=courses_dict,
                lessons=lessons_dict,
                sections=sections_dict,
                learning_objects=los_dict,
                relationships=relationships_dict,
                questions=questions_dict,
                quizzes=quizzes_dict
            )
            return self._to_rdf_xml(turtle) if fmt == 'xml' else turtle

        finally:
            session.close()

    def export_lesson_ontology(self, lesson_id: int, fmt: str = 'turtle') -> str:
        """Export ontology for a specific lesson only. fmt: 'turtle' or 'xml'."""
        session = db.get_session()
        try:
            lesson = session.query(Lesson).filter_by(id=lesson_id).first()
            if not lesson:
                raise ValueError(f"Lesson {lesson_id} not found")
            
            course = lesson.course
            sections = list(lesson.sections) if lesson.sections else []
            
            learning_objects = []
            for section in sections:
                learning_objects.extend(section.learning_objects)
            
            # Get relationships
            lo_ids = [lo.id for lo in learning_objects]
            relationships = []
            if lo_ids:
                relationships = session.query(ConceptRelationship).filter(
                    (ConceptRelationship.source_id.in_(lo_ids)) |
                    (ConceptRelationship.target_id.in_(lo_ids))
                ).all()
            
            # Get questions
            questions = session.query(Question).filter_by(
                primary_lesson_id=lesson_id
            ).all()
            
            # Convert to dictionaries before session closes
            course_dict = {
                'id': course.id,
                'name': course.name,
                'code': course.code,
                'description': course.description,
            } if course else None
            
            lesson_dict = {
                'id': lesson.id,
                'course_id': lesson.course_id,
                'title': lesson.title,
                'filename': lesson.filename,
                'summary': lesson.summary,
                'order_index': lesson.order_index,
            }
            
            sections_dict = [{
                'id': s.id,
                'lesson_id': s.lesson_id,
                'title': s.title,
                'content': s.content,
                'summary': s.summary,
                'order_index': s.order_index,
                'start_page': s.start_page,
                'end_page': s.end_page,
            } for s in sections]
            
            los_dict = [{
                'id': lo.id,
                'section_id': lo.section_id,
                'title': lo.title,
                'content': lo.content,
                'description': lo.description,
                'key_points': lo.key_points,
                'object_type': lo.object_type,
                'keywords': lo.keywords,
                'order_index': lo.order_index,
            } for lo in learning_objects]
            
            relationships_dict = [{
                'id': r.id,
                'source_id': r.source_id,
                'target_id': r.target_id,
                'source_title': r.source.title if r.source else None,
                'target_title': r.target.title if r.target else None,
                'relationship_type': r.relationship_type,
                'description': r.description,
            } for r in relationships]
            
            questions_dict = [{
                'id': q.id,
                'primary_lesson_id': q.primary_lesson_id,
                'secondary_lesson_id': q.secondary_lesson_id,
                'section_id': q.section_id,
                'learning_object_id': q.learning_object_id,
                'solo_level': q.solo_level,
                'question_text': q.question_text,
                'question_type': q.question_type,
                'options': q.options,
                'correct_answer': q.correct_answer,
                'correct_option_index': q.correct_option_index,
                'explanation': q.explanation,
                'difficulty': q.difficulty,
                'bloom_level': q.bloom_level,
                'tags': q.tags,
            } for q in questions]
            
            turtle = self._generate_knowledge_base_owl(
                courses=[course_dict] if course_dict else [],
                lessons=[lesson_dict],
                sections=sections_dict,
                learning_objects=los_dict,
                relationships=relationships_dict,
                questions=questions_dict,
                quizzes=[]
            )
            return self._to_rdf_xml(turtle) if fmt == 'xml' else turtle

        finally:
            session.close()
    
    def _safe_str(self, value: Any, default: str = '') -> str:
        """Escape a value for safe embedding inside a Turtle "..." literal.

        Handles backslash, quote, newline, carriage return, and tab — the
        characters that would otherwise produce malformed Turtle that
        rdflib refuses to parse.
        """
        if value is None:
            return default
        return (
            str(value)
            .replace('\\', '\\\\')
            .replace('"', '\\"')
            .replace('\n', '\\n')
            .replace('\r', '\\r')
            .replace('\t', '\\t')
        )
    
    def _generate_knowledge_base_owl(
        self,
        courses: List[dict],
        lessons: List[dict],
        sections: List[dict],
        learning_objects: List[dict],
        relationships: List[dict],
        questions: List[dict],
        quizzes: List[dict]
    ) -> str:
        """Generate the knowledge base in RDF/Turtle format"""
        
        timestamp = datetime.utcnow().isoformat()
        
        # URL-encode IRIs to avoid spaces
        safe_knowledge_iri = self.knowledge_iri.replace(" ", "%20")
        safe_seed_iri = self.seed_iri.replace(" ", "%20")
        
        # Build lookup dictionaries
        courses_by_id = {course['id']: course for course in courses}
        lessons_by_id = {lesson['id']: lesson for lesson in lessons}
        sections_by_id = {section['id']: section for section in sections}
        learning_objects_by_id = {lo['id']: lo for lo in learning_objects}
        
        # Start with Turtle format header and prefixes
        owl = f'''# SOLO Education Knowledge Base - RDF/Turtle Format
# Generated: {timestamp}
# This ontology imports the seed ontology and adds populated knowledge base instances

@prefix : <{safe_knowledge_iri}#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix dc: <http://purl.org/dc/elements/1.1/> .
@prefix solo: <{safe_seed_iri}#> .

# ================================================================
# ONTOLOGY METADATA
# ================================================================

<{safe_knowledge_iri}> a owl:Ontology ;
    owl:imports <{safe_seed_iri}> ;
    dc:title "SOLO Education Knowledge Base" ;
    dc:description "Populated educational ontology containing courses, lessons, learning objects, and questions from the SOLO Quiz Generator system." ;
    dc:date "{timestamp}"^^xsd:dateTime ;
    rdfs:comment """
Statistics:
- Courses: {len(courses)}
- Lessons: {len(lessons)}
- Sections: {len(sections)}
- Learning Objects: {len(learning_objects)}
- Relationships: {len(relationships)}
- Questions: {len(questions)}
- Quizzes: {len(quizzes)}
""" .

# ================================================================
# COURSES
# ================================================================

'''
        
        for course in courses:
            course_id_safe = self.make_id(course['name'], 'Course_')
            course_name = self._safe_str(course.get('name'))
            course_desc = self._safe_str(course.get('description'))
            course_code = self._safe_str(course.get('code'))
            
            owl += f':Course_{course_id_safe}\n'
            owl += f'    a solo:Course ;\n'
            owl += f'    rdfs:label "{course_name}" ;\n'
            if course_code:
                owl += f'    solo:courseCode "{course_code}" ;\n'
            if course_desc:
                owl += f'    rdfs:comment "{course_desc}" ;\n'
            owl += f'    dc:date "{timestamp}"^^xsd:dateTime .\n\n'
        
        # ================================================================
        # LESSONS
        # ================================================================
        
        owl += '# ================================================================\n'
        owl += '# LESSONS\n'
        owl += '# ================================================================\n\n'
        
        for lesson in lessons:
            lesson_id_safe = self.make_id(lesson['title'], 'Lesson_')
            lesson_title = self._safe_str(lesson.get('title'))
            lesson_summary = self._safe_str(lesson.get('summary'))
            
            owl += f':Lesson_{lesson_id_safe}\n'
            owl += f'    a solo:Lesson ;\n'
            owl += f'    rdfs:label "{lesson_title}" ;\n'
            
            # Link to course (inverse: Course hasLesson Lesson)
            course_id = lesson.get('course_id')
            if course_id and course_id in courses_by_id:
                course = courses_by_id[course_id]
                course_id_safe = self.make_id(course['name'], 'Course_')
                # This will be added in course iteration as: Course hasLesson Lesson
            
            if lesson_summary:
                owl += f'    rdfs:comment "{lesson_summary}" ;\n'
            
            filename = lesson.get('filename')
            if filename:
                filename_safe = self._safe_str(filename)
                owl += f'    solo:filename "{filename_safe}" ;\n'
            
            order = lesson.get('order_index')
            if order is not None:
                owl += f'    solo:orderIndex {order} ;\n'
            
            owl += f'    dc:date "{timestamp}"^^xsd:dateTime .\n\n'
        
        # ================================================================
        # SECTIONS
        # ================================================================
        
        owl += '# ================================================================\n'
        owl += '# SECTIONS\n'
        owl += '# ================================================================\n\n'
        
        for section in sections:
            section_id_safe = self.make_id(section['title'], 'Section_')
            section_title = self._safe_str(section.get('title'))
            section_content = self._safe_str(section.get('content'))
            section_summary = self._safe_str(section.get('summary'))
            
            owl += f':Section_{section_id_safe}\n'
            owl += f'    a solo:Section ;\n'
            owl += f'    rdfs:label "{section_title}" ;\n'
            
            # Link to lesson (inverse: Lesson hasSection Section)
            lesson_id = section.get('lesson_id')
            if lesson_id and lesson_id in lessons_by_id:
                lesson = lessons_by_id[lesson_id]
                lesson_id_safe = self.make_id(lesson['title'], 'Lesson_')
                # This will be added in lesson iteration as: Lesson hasSection Section
            
            if section_content:
                # Truncate for content property
                content_truncated = section_content[:500]
                owl += f'    solo:hasContent "{content_truncated.replace('"', '\\"')}" ;\n'
            
            if section_summary:
                owl += f'    rdfs:comment "{section_summary}" ;\n'
            
            start_page = section.get('start_page')
            end_page = section.get('end_page')
            if start_page is not None:
                owl += f'    solo:startPage {start_page} ;\n'
            if end_page is not None:
                owl += f'    solo:endPage {end_page} ;\n'
            
            order = section.get('order_index')
            if order is not None:
                owl += f'    solo:orderIndex {order} ;\n'
            
            owl += f'    dc:date "{timestamp}"^^xsd:dateTime .\n\n'
        
        # ================================================================
        # LEARNING OBJECTS
        # ================================================================
        
        owl += '# ================================================================\n'
        owl += '# LEARNING OBJECTS\n'
        owl += '# ================================================================\n\n'
        
        for lo in learning_objects:
            lo_id_safe = self.make_id(lo['title'], 'LO_')
            lo_title = self._safe_str(lo.get('title'))
            lo_desc = self._safe_str(lo.get('description'))
            lo_content = self._safe_str(lo.get('content'))
            
            # Map object type to class
            lo_class = self.map_object_type_to_class(lo.get('object_type', 'Definition'))
            
            owl += f':LO_{lo_id_safe}\n'
            owl += f'    a solo:{lo_class} ;\n'
            owl += f'    rdfs:label "{lo_title}" ;\n'
            
            # Link to section (inverse: Section containsLearningObject LearningObject)
            section_id = lo.get('section_id')
            if section_id and section_id in sections_by_id:
                section = sections_by_id[section_id]
                section_id_safe = self.make_id(section['title'], 'Section_')
                # This will be added in section iteration as: Section containsLearningObject LO
            
            if lo_desc:
                owl += f'    rdfs:comment "{lo_desc}" ;\n'
            
            if lo_content:
                content_truncated = lo_content[:500]
                owl += f'    solo:hasContent "{content_truncated.replace('"', '\\"')}" ;\n'
            
            key_points = lo.get('key_points')
            if key_points:
                if isinstance(key_points, list):
                    for point in key_points:
                        owl += f'    solo:hasKeyPoint "{point.replace('"', '\\"')}" ;\n'
                else:
                    owl += f'    solo:hasKeyPoints "{key_points.replace('"', '\\"')}" ;\n'
            
            keywords = lo.get('keywords')
            if keywords:
                if isinstance(keywords, list):
                    for kw in keywords:
                        owl += f'    solo:hasKeyword "{kw.replace('"', '\\"')}" ;\n'
                else:
                    kw_list = keywords.split(',')
                    for kw in kw_list:
                        owl += f'    solo:hasKeyword "{kw.strip().replace('"', '\\"')}" ;\n'
            
            order = lo.get('order_index')
            if order is not None:
                owl += f'    solo:orderIndex {order} ;\n'
            
            owl += f'    dc:date "{timestamp}"^^xsd:dateTime .\n\n'
        
        # ================================================================
        # STRUCTURAL RELATIONSHIPS
        # ================================================================
        
        owl += '# ================================================================\n'
        owl += '# STRUCTURAL RELATIONSHIPS (Course->Lesson->Section->LearningObject)\n'
        owl += '# ================================================================\n\n'
        
        # Course -> Lesson (hasLesson)
        for course in courses:
            course_id_safe = self.make_id(course['name'], 'Course_')
            has_lessons = False
            lessons_to_add = []
            
            for lesson in lessons:
                if lesson.get('course_id') == course['id']:
                    lesson_id_safe = self.make_id(lesson['title'], 'Lesson_')
                    lessons_to_add.append(f':Lesson_{lesson_id_safe}')
                    has_lessons = True
            
            if has_lessons:
                owl += f':Course_{course_id_safe}\n'
                for i, lesson_iri in enumerate(lessons_to_add):
                    if i < len(lessons_to_add) - 1:
                        owl += f'    solo:hasLesson {lesson_iri} ;\n'
                    else:
                        owl += f'    solo:hasLesson {lesson_iri} .\n'
                owl += '\n'
        
        # Lesson -> Section (hasSection)
        for lesson in lessons:
            lesson_id_safe = self.make_id(lesson['title'], 'Lesson_')
            has_sections = False
            sections_to_add = []
            
            for section in sections:
                if section.get('lesson_id') == lesson['id']:
                    section_id_safe = self.make_id(section['title'], 'Section_')
                    sections_to_add.append(f':Section_{section_id_safe}')
                    has_sections = True
            
            if has_sections:
                owl += f':Lesson_{lesson_id_safe}\n'
                for i, section_iri in enumerate(sections_to_add):
                    if i < len(sections_to_add) - 1:
                        owl += f'    solo:hasSection {section_iri} ;\n'
                    else:
                        owl += f'    solo:hasSection {section_iri} .\n'
                owl += '\n'
        
        # Section -> LearningObject (containsLearningObject)
        for section in sections:
            section_id_safe = self.make_id(section['title'], 'Section_')
            has_los = False
            los_to_add = []
            
            for lo in learning_objects:
                if lo.get('section_id') == section['id']:
                    lo_id_safe = self.make_id(lo['title'], 'LO_')
                    los_to_add.append(f':LO_{lo_id_safe}')
                    has_los = True
            
            if has_los:
                owl += f':Section_{section_id_safe}\n'
                for i, lo_iri in enumerate(los_to_add):
                    if i < len(los_to_add) - 1:
                        owl += f'    solo:containsLearningObject {lo_iri} ;\n'
                    else:
                        owl += f'    solo:containsLearningObject {lo_iri} .\n'
                owl += '\n'
        
        # ================================================================
        # CONCEPT RELATIONSHIPS
        # ================================================================
        
        owl += '# ================================================================\n'
        owl += '# CONCEPT RELATIONSHIPS\n'
        owl += f'# Total: {len(relationships)} relationships\n'
        owl += '# ================================================================\n\n'
        
        for rel in relationships:
            source_id = rel.get('source_id')
            target_id = rel.get('target_id')
            rel_type = rel.get('relationship_type', 'relatedTo')
            
            if source_id in learning_objects_by_id and target_id in learning_objects_by_id:
                source_lo = learning_objects_by_id[source_id]
                target_lo = learning_objects_by_id[target_id]
                
                source_id_safe = self.make_id(source_lo['title'], 'LO_')
                target_id_safe = self.make_id(target_lo['title'], 'LO_')
                
                prop = self.normalize_relationship_type(rel_type)
                
                owl += f':LO_{source_id_safe}\n'
                owl += f'    solo:{prop} :LO_{target_id_safe} ;\n'
                
                if rel.get('description'):
                    rel_desc = rel['description'].replace('"', '\\"')
                    owl += f'    rdfs:comment "{rel_desc}" .\n\n'
                else:
                    owl += f'    rdfs:comment "Relationship: {rel_type}" .\n\n'
        
        # ================================================================
        # QUESTIONS
        # ================================================================
        
        owl += '# ================================================================\n'
        owl += '# QUESTIONS\n'
        owl += '# ================================================================\n\n'
        
        for q in questions:
            q_id = f'Question_{q["id"]}'
            q_text = self._safe_str(q.get('question_text'))
            q_type = self._safe_str(q.get('question_type'), 'ShortAnswer')
            
            # Map question type to class
            q_class = self.map_question_type_to_class(q_type)
            
            owl += f':{q_id}\n'
            owl += f'    a solo:{q_class} ;\n'
            
            # Truncate label for long questions
            q_label = q_text[:100] + '...' if len(q_text) > 100 else q_text
            owl += f'    rdfs:label "{q_label.replace('"', '\\"')}" ;\n'
            
            if q_text:
                owl += f'    solo:questionText "{q_text}" ;\n'
            
            # SOLO Level
            solo_level = q.get('solo_level')
            if solo_level:
                solo_level_mapped = self.map_solo_level(solo_level)
                owl += f'    solo:hasSOLOLevel solo:{solo_level_mapped} ;\n'
            
            # Bloom Level
            bloom_level = q.get('bloom_level')
            if bloom_level:
                bloom_level_mapped = self.map_bloom_level(bloom_level)
                if bloom_level_mapped:
                    owl += f'    solo:hasBloomLevel solo:{bloom_level_mapped} ;\n'
            
            # Difficulty
            difficulty = q.get('difficulty')
            if difficulty:
                owl += f'    solo:difficulty "{difficulty.replace('"', '\\"')}" ;\n'
            
            # Link to learning object if available
            learning_object_id = q.get('learning_object_id')
            if learning_object_id and learning_object_id in learning_objects_by_id:
                lo = learning_objects_by_id[learning_object_id]
                lo_id_safe = self.make_id(lo['title'], 'LO_')
                owl += f'    solo:assessesLearningObject :LO_{lo_id_safe} ;\n'
            
            owl += f'    dc:date "{timestamp}"^^xsd:dateTime .\n\n'
        
        # ================================================================
        # QUIZZES
        # ================================================================
        
        owl += '# ================================================================\n'
        owl += '# QUIZZES\n'
        owl += '# ================================================================\n\n'
        
        for quiz in quizzes:
            quiz_id_safe = self.make_id(quiz['title'], 'Quiz_')
            quiz_title = self._safe_str(quiz.get('title'))
            quiz_desc = self._safe_str(quiz.get('description'))
            
            owl += f':Quiz_{quiz_id_safe}\n'
            owl += f'    a solo:Quiz ;\n'
            owl += f'    rdfs:label "{quiz_title}" ;\n'
            
            if quiz_desc:
                owl += f'    rdfs:comment "{quiz_desc}" ;\n'
            
            # Link to course if available
            course_id = quiz.get('course_id')
            if course_id and course_id in courses_by_id:
                course = courses_by_id[course_id]
                course_id_safe = self.make_id(course['name'], 'Course_')
                owl += f'    solo:assessesCourse :Course_{course_id_safe} ;\n'
            
            owl += f'    dc:date "{timestamp}"^^xsd:dateTime .\n\n'
        
        return owl
    
    def save_knowledge_base(self, course_id: Optional[int] = None) -> str:
        """
        Generate and save the knowledge base to file.
        
        Returns:
            Path to the saved file
        """
        owl_content = self.export_full_ontology(course_id)
        
        with open(KNOWLEDGE_BASE_PATH, 'w', encoding='utf-8') as f:
            f.write(owl_content)
        
        return KNOWLEDGE_BASE_PATH
    
    def get_ontology_stats(self) -> Dict[str, Any]:
        """Get statistics about the current ontology knowledge base"""
        session = db.get_session()
        try:
            return {
                'courses': session.query(Course).count(),
                'lessons': session.query(Lesson).count(),
                'sections': session.query(Section).count(),
                'learning_objects': session.query(LearningObject).count(),
                'relationships': session.query(ConceptRelationship).count(),
                'questions': session.query(Question).count(),
                'quizzes': session.query(Quiz).count(),
                'seed_ontology': os.path.exists(SEED_BASE_PATH),
                'knowledge_base_exists': os.path.exists(KNOWLEDGE_BASE_PATH),
            }
        finally:
            session.close()


# Singleton instance
ontology_manager = OntologyManager()

