"""
Quiz Service
Handles quiz building and management logic
"""

from repository import db


class QuizService:
    """Handle quiz building and management"""
    
    @staticmethod
    def create_quiz(title, course_id=None, description=None, time_limit_minutes=None,
                    passing_score=None, shuffle_questions=False, shuffle_options=False):
        """Create a new quiz"""
        try:
            quiz = db.create_quiz(
                title=title,
                course_id=course_id,
                description=description,
                time_limit_minutes=time_limit_minutes,
                passing_score=passing_score,
                shuffle_questions=shuffle_questions,
                shuffle_options=shuffle_options
            )
            return {'quiz': quiz, 'status': 201}
        except Exception as e:
            print(f"[SERVICE] Error creating quiz: {str(e)}")
            raise
    
    @staticmethod
    def add_questions_to_quiz(quiz_id, question_ids):
        """Add questions to a quiz"""
        try:
            quiz = db.get_quiz(quiz_id)
            if not quiz:
                return {'error': 'Quiz not found', 'status': 404}
            
            # Add each question to the quiz
            for q_id in question_ids:
                db.add_question_to_quiz(quiz_id, q_id)
            
            # Return updated quiz
            updated_quiz = db.get_quiz_with_questions(quiz_id)
            return {'quiz': updated_quiz, 'status': 200}
        
        except Exception as e:
            print(f"[SERVICE] Error adding questions: {str(e)}")
            raise
