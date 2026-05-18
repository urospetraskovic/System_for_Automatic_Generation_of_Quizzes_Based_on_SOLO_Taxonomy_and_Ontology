"""
Lesson Service
Handles all lesson-related business logic
"""

from repository import db
from models import Lesson
from core import content_parser


class LessonService:
    """Handle lesson-related business logic"""
    
    @staticmethod
    def parse_lesson(lesson_id):
        """Parse a lesson to extract sections and learning objects using AI"""
        # Check if lesson exists
        lesson = db.get_lesson(lesson_id, include_content=True)
        if not lesson:
            return {'error': 'Lesson not found', 'status': 404}
        
        if not lesson.get('raw_content'):
            return {'error': 'Lesson has no content to parse', 'status': 400}
        
        # Check if already parsed
        existing_sections = db.get_sections_for_lesson(lesson_id)
        if existing_sections:
            return {
                'message': 'Lesson already parsed',
                'sections': existing_sections,
                'status': 200
            }
        
        try:
            # Parse the lesson content
            print(f"[SERVICE] Parsing lesson: {lesson['title']}")
            parsed_sections = content_parser.parse_lesson_structure(
                lesson['raw_content'],
                lesson['title'],
                pages_meta=lesson.get('pages_meta'),
            )
            
            # Save to database
            db.bulk_create_sections_and_learning_objects(lesson_id, parsed_sections)
            
            # Extract and save domain ontology
            all_sections = db.get_sections_for_lesson(lesson_id)
            all_los = []
            lo_title_to_id = {}
            for s in all_sections:
                section_los = db.get_learning_objects_for_section(s['id'])
                all_los.extend(section_los)
                for lo in section_los:
                    lo_title_to_id[lo['title']] = lo['id']
            
            ontology_rels = content_parser.extract_ontology_relationships(
                lesson['raw_content'],
                all_los,
                lesson['title'],
                sections=all_sections,
            )
            
            db_rels = []
            for rel in ontology_rels:
                source_id = lo_title_to_id.get(rel['source'])
                target_id = lo_title_to_id.get(rel['target'])
                if source_id and target_id:
                    db_rels.append({
                        'source_id': source_id,
                        'target_id': target_id,
                        'relationship_type': rel['type'],
                        'description': rel.get('description')
                    })
            
            if db_rels:
                db.bulk_create_relationships(db_rels)
            
            # Generate and save lesson summary
            summary = content_parser.generate_lesson_summary(
                lesson['raw_content'],
                lesson['title']
            )
            if summary:
                session = db.get_session()
                try:
                    lesson_obj = session.query(Lesson).filter(
                        Lesson.id == lesson_id
                    ).first()
                    if lesson_obj:
                        lesson_obj.summary = summary
                        session.commit()
                finally:
                    session.close()
            
            # Return parsed sections
            final_sections = db.get_sections_for_lesson(lesson_id)
            return {
                'message': 'Lesson parsed successfully',
                'sections': final_sections,
                'status': 200
            }
        
        except Exception as e:
            print(f"[SERVICE] Error parsing lesson: {str(e)}")
            raise
