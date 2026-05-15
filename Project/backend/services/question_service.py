"""
Question Service
Handles question generation and management logic
"""

from repository import db
from core import SoloQuizGeneratorLocal as SoloQuizGenerator


class QuestionService:
    """Handle question generation and management"""
    
    @staticmethod
    def generate_questions(lesson_ids, solo_levels, questions_per_level,
                          section_ids=None, save_to_db=True, progress_cb=None):
        """Generate SOLO taxonomy questions from lessons"""
        
        # Validate input
        if not lesson_ids:
            return {'error': 'At least one lesson_id is required', 'status': 400}
        
        # Ensure lesson_ids are integers
        lesson_ids = [int(lid) for lid in lesson_ids]
        
        # Check for extended_abstract - requires 2 lessons
        if 'extended_abstract' in solo_levels and len(lesson_ids) < 2:
            return {
                'error': 'Extended abstract questions require at least 2 lessons',
                'status': 400
            }
        
        try:
            # Get lesson content
            lessons_data = []
            lesson_titles = {}
            ontology_relationships = []
            
            for lid in lesson_ids:
                lesson = db.get_lesson_with_sections(lid)
                if not lesson:
                    return {'error': f'Lesson {lid} not found', 'status': 404}
                lessons_data.append(lesson)
                lesson_titles[lid] = db.get_lesson(lid).get('title')
                
                # Get ontology relationships for this lesson to enhance question generation
                rels = db.get_relationships_for_lesson(lid)
                if rels:
                    ontology_relationships.extend(rels)
            
            print(f"[QuestionService] Found {len(ontology_relationships)} ontology relationships for enhanced question generation")
            
            # Generate questions using AI with ontology support
            generator = SoloQuizGenerator()
            generated_questions = generator.generate_solo_questions(
                lessons_data=lessons_data,
                solo_levels=solo_levels,
                questions_per_level=questions_per_level,
                section_ids=section_ids,
                ontology_relationships=ontology_relationships,
                progress_cb=progress_cb,
            )
            
            # Save to database if requested
            if save_to_db and generated_questions:
                # Add lesson IDs and titles to questions
                for q in generated_questions:
                    if q.get('solo_level') == 'extended_abstract':
                        if not q.get('primary_lesson_id'):
                            q['primary_lesson_id'] = lesson_ids[0]
                        if not q.get('secondary_lesson_id') and len(lesson_ids) > 1:
                            q['secondary_lesson_id'] = lesson_ids[1]
                    else:
                        q['primary_lesson_id'] = lesson_ids[0]
                    
                    # Add titles for frontend
                    if q.get('primary_lesson_id'):
                        q['primary_lesson_title'] = lesson_titles.get(q['primary_lesson_id'])
                    if q.get('secondary_lesson_id'):
                        q['secondary_lesson_title'] = lesson_titles.get(q['secondary_lesson_id'])
                
                question_ids = db.bulk_create_questions(generated_questions)
                for i, q in enumerate(generated_questions):
                    q['id'] = question_ids[i]
            
            return {
                'questions': generated_questions,
                'count': len(generated_questions),
                'solo_distribution': {
                    level: len([q for q in generated_questions if q.get('solo_level') == level])
                    for level in solo_levels
                },
                'status': 200
            }
        
        except Exception as e:
            print(f"[SERVICE] Question generation error: {str(e)}")
            raise
