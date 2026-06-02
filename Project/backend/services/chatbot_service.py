"""
Chatbot Service for Learning Assistant
Uses Ollama for local processing with offline mode and database queries
"""

import requests
import json
from typing import Optional, List, Dict

# Single source of truth for Ollama URL/model lives in backend/config.py
from config import OLLAMA_BASE_URL, OLLAMA_MODEL


class ChatbotService:
    """Learning Assistant Chatbot Service"""

    def __init__(self, db_session=None):
        """Initialize chatbot with Ollama support"""
        self.ollama_url = OLLAMA_BASE_URL
        self.ollama_model = OLLAMA_MODEL
        self.max_context_length = 2000
        self.db_session = db_session
        
        # Simple offline knowledge base
        self.offline_responses = {
            "hello": "Hello! I'm your Learning Assistant. How can I help you today?",
            "hi": "Hi there! What would you like to learn about?",
            "help": "I can help you with:\n- Questions about course content\n- Explanations of concepts\n- Quiz answer discussions\n- Study tips\n- Course and lesson information\n\nJust ask me anything!",
            "what can you do": "I'm here to help you learn! I can answer questions about:\n- Your course materials\n- Difficult concepts\n- Quiz questions and answers\n- Study strategies\n- Your courses and lessons",
            "thanks": "You're welcome! Feel free to ask more questions!",
            "thank you": "Happy to help! Let me know if you need anything else.",
        }
        
        print(f"[ChatbotService] Initialized with Ollama: {self.ollama_url}/{self.ollama_model}")
        print("[ChatbotService] Offline mode available as fallback")

    def set_db_session(self, db_session):
        """Set database session for database queries"""
        self.db_session = db_session

    def _test_ollama_connection(self) -> bool:
        """Test if Ollama is running"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=2)
            return response.status_code == 200
        except:
            return False

    def _search_learning_content(self, query: str, course_id: Optional[int] = None) -> Optional[str]:
        """
        Search through lessons, sections, learning objects, and ontology 
        to find relevant content for the user's question
        """
        if not self.db_session:
            return None
        
        query_lower = query.lower().strip()
        # Extract key terms (remove common question words)
        stop_words = ["what", "is", "a", "an", "the", "whats", "what's", "how", "why", "does", "do", "can", "you", "tell", "me", "about", "explain"]
        query_terms = [w for w in query_lower.split() if w not in stop_words and len(w) > 2]
        
        if not query_terms:
            return None
        
        try:
            from models import Course, Lesson, Section, LearningObject, ConceptRelationship
            
            results = []
            
            # Search in Learning Objects (most specific content)
            learning_objects = self.db_session.query(LearningObject).all()
            for lo in learning_objects:
                lo_text = f"{lo.title or ''} {lo.description or ''} {lo.content or ''}".lower()
                match_score = sum(1 for term in query_terms if term in lo_text)
                # Boost score if the term appears in the title
                for term in query_terms:
                    if term in (lo.title or '').lower():
                        match_score += 2
                if match_score > 0:
                    results.append({
                        'type': 'learning_object',
                        'title': lo.title,
                        'content': lo.description or lo.content,
                        'score': match_score
                    })
            
            # Search in Sections
            sections = self.db_session.query(Section).all()
            for section in sections:
                section_text = f"{section.title or ''} {section.content or ''}".lower()
                match_score = sum(1 for term in query_terms if term in section_text)
                if match_score > 0:
                    results.append({
                        'type': 'section',
                        'title': section.title,
                        'content': section.content,
                        'score': match_score
                    })
            
            # Search in Lessons
            lessons = self.db_session.query(Lesson).all()
            for lesson in lessons:
                lesson_text = f"{lesson.title or ''} {lesson.summary or ''}".lower()
                match_score = sum(1 for term in query_terms if term in lesson_text)
                if match_score > 0:
                    results.append({
                        'type': 'lesson',
                        'title': lesson.title,
                        'content': lesson.summary,
                        'score': match_score
                    })
            
            # Search in Ontology/Concept Relationships
            try:
                concepts = self.db_session.query(ConceptRelationship).all()
                for concept in concepts:
                    source_title = concept.source.title if concept.source else ''
                    target_title = concept.target.title if concept.target else ''
                    concept_text = f"{source_title} {target_title} {concept.relationship_type or ''}".lower()
                    match_score = sum(1 for term in query_terms if term in concept_text)
                    if match_score > 0:
                        results.append({
                            'type': 'ontology',
                            'title': f"{source_title} → {target_title}",
                            'content': f"Relationship: {concept.relationship_type}",
                            'score': match_score
                        })
            except Exception as e:
                print(f"[ChatbotService] Ontology search error: {e}")
            
            # Sort by score and return the best match
            if results:
                results.sort(key=lambda x: x['score'], reverse=True)
                best = results[0]
                
                # Format response based on content type
                if best['type'] == 'learning_object':
                    response = f"📖 **{best['title']}** (Learning Object)\n\n{best['content'][:800] if best['content'] else 'No detailed content available.'}"
                elif best['type'] == 'section':
                    response = f"📚 **{best['title']}** (Section)\n\n{best['content'][:800] if best['content'] else 'No detailed content available.'}"
                elif best['type'] == 'lesson':
                    response = f"📘 Found in lesson **{best['title']}**\n\n{best['content'][:800] if best['content'] else 'Check this lesson for more details.'}"
                else:
                    response = f"🔗 **Ontology**: {best['title']}\n{best['content']}"
                
                # If there are more results, mention them
                if len(results) > 1:
                    other_titles = [r['title'] for r in results[1:4] if r['title'] != best['title']]
                    if other_titles:
                        response += f"\n\n💡 *Related content in: {', '.join(other_titles)}*"
                
                return response
            
            return None
            
        except Exception as e:
            print(f"[ChatbotService] Search error: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _check_database_query(self, user_message: str, course_id: Optional[int] = None) -> Optional[str]:
        """
        Check if the user is asking a database query (counts, lists, course content) and answer directly.
        Returns None if not a database query, otherwise returns the answer.
        """
        if not self.db_session:
            return None
            
        message_lower = user_message.lower().strip()
        
        try:
            from models import Course, Lesson, Question, Quiz, ConceptRelationship, LearningObject, Section, QuizQuestion
            
            # Keywords for different entity types
            relationship_keywords = ["relationship", "relationships", "ontological", "ontology"]
            quiz_keywords = ["quiz", "quizzes"]
            lesson_keywords = ["lesson", "lessons"]
            course_keywords = ["course", "courses"]
            question_keywords = ["question", "questions", "question bank", "questionbank", "generated questions"]
            learning_object_keywords = ["learning object", "learning objects"]
            section_keywords = ["section", "sections"]
            topic_keywords = ["topic", "topics", "content", "cover", "about", "in the", "teaches", "contains"]
            
            # Check what entity type user is asking about
            wants_relationships = any(kw in message_lower for kw in relationship_keywords)
            wants_quizzes = any(kw in message_lower for kw in quiz_keywords)
            wants_lessons = any(kw in message_lower for kw in lesson_keywords)
            wants_courses = any(kw in message_lower for kw in course_keywords)
            wants_questions = any(kw in message_lower for kw in question_keywords)
            wants_learning_objects = any(kw in message_lower for kw in learning_object_keywords)
            wants_sections = any(kw in message_lower for kw in section_keywords)
            wants_topics = any(kw in message_lower for kw in topic_keywords)
            
            # Check if user is asking about a SPECIFIC course by name (with abbreviation support)
            courses = self.db_session.query(Course).all()
            target_course = None
            
            # Common abbreviations mapping
            abbreviations = {
                "os": ["operativni sistemi", "operating system", "operating systems"],
                "cs": ["computer science", "racunarske nauke"],
                "db": ["database", "databases", "baze podataka"],
                "ai": ["artificial intelligence", "vestacka inteligencija"],
                "ml": ["machine learning", "masinsko ucenje"],
                "ts": ["testiranje softvera", "software testing"],
            }
            
            for course in courses:
                course_name_lower = course.name.lower()
                # Direct match - course name in message
                if course_name_lower in message_lower:
                    target_course = course
                    print(f"[ChatbotService] Matched course by name: {course.name}")
                    break
                # Partial match - any significant word from course name (3+ chars)
                # Clean the message words of punctuation for better matching
                import re
                message_words = re.findall(r'\b\w+\b', message_lower)
                course_words = [w for w in course_name_lower.split() if len(w) >= 4]
                for word in course_words:
                    if word in message_words:
                        target_course = course
                        print(f"[ChatbotService] Matched course by word '{word}': {course.name}")
                        break
                if target_course:
                    break
                # Check abbreviations
                for abbrev, full_names in abbreviations.items():
                    # If user typed the abbreviation and course name matches any full name
                    if abbrev in message_words:  # Word boundary check
                        for full_name in full_names:
                            if full_name in course_name_lower or course_name_lower in full_name:
                                target_course = course
                                print(f"[ChatbotService] Matched course by abbreviation '{abbrev}': {course.name}")
                                break
                    if target_course:
                        break
                if target_course:
                    break
            
            # Debug log
            print(f"[ChatbotService] Query analysis: questions={wants_questions}, topics={wants_topics}, target_course={target_course.name if target_course else 'None'}")
            
            # Check if user is asking about a SPECIFIC lesson by name
            all_lessons = self.db_session.query(Lesson).all()
            target_lesson = None
            import re
            message_words = re.findall(r'\b\w+\b', message_lower)
            
            # Score each lesson by how many words match - pick best match
            lesson_scores = []
            for lesson in all_lessons:
                lesson_title_lower = lesson.title.lower()
                lesson_words = re.findall(r'\b\w+\b', lesson_title_lower)
                
                # Count matching words (only significant words 3+ chars)
                significant_lesson_words = [w for w in lesson_words if len(w) >= 3]
                matching_words = [w for w in significant_lesson_words if w in message_words]
                
                if matching_words:
                    # Score = number of matches + bonus for exact phrase match
                    score = len(matching_words)
                    if lesson_title_lower in message_lower:
                        score += 10  # Big bonus for exact title match
                    lesson_scores.append((lesson, score, matching_words))
            
            # Pick lesson with highest score
            if lesson_scores:
                lesson_scores.sort(key=lambda x: x[1], reverse=True)
                best_match = lesson_scores[0]
                target_lesson = best_match[0]
                print(f"[ChatbotService] Best lesson match: {target_lesson.title} (score={best_match[1]}, words={best_match[2]})")
            
            # LESSON SUMMARY queries: "summarize lesson X", "what is in lesson X", "explain lesson X"
            summarize_keywords = ["summarize", "summary", "explain", "describe", "tell me about", "what is in", "what's in", "overview"]
            concept_keywords = ["key concepts", "concepts", "learning objects", "main ideas", "key points", "key topics"]
            wants_summary = any(kw in message_lower for kw in summarize_keywords)
            wants_concepts = any(kw in message_lower for kw in concept_keywords)
            
            # KEY CONCEPTS query: show learning objects from the lesson
            if target_lesson and wants_concepts:
                sections = self.db_session.query(Section).filter_by(lesson_id=target_lesson.id).order_by(Section.order_index).all()
                
                if sections:
                    concept_list = []
                    for s in sections:
                        los = self.db_session.query(LearningObject).filter_by(section_id=s.id).all()
                        for lo in los:
                            concept_list.append(f"• **{lo.title}**" + (f" - {lo.description[:60]}..." if lo.description and len(lo.description) > 60 else (f" - {lo.description}" if lo.description else "")))
                    
                    course = self.db_session.query(Course).get(target_lesson.course_id)
                    course_name = course.name if course else "Unknown"
                    
                    # Show first 25 concepts
                    concepts_text = "\n".join(concept_list[:25])
                    extra = f"\n\n... and {len(concept_list)-25} more concepts" if len(concept_list) > 25 else ""
                    
                    return f"""💡 **Key Concepts in: {target_lesson.title}**
📚 Course: {course_name}
📊 Total: {len(concept_list)} learning objects

{concepts_text}{extra}

These are the actual concepts extracted from your lesson materials."""
                else:
                    return f"📖 **{target_lesson.title}** - No concepts found (lesson not parsed yet)."
            
            # QUIZ PREPARATION queries: "what should I study for X quiz", "prepare for quiz"
            study_keywords = ["study for", "prepare for", "review for", "practice for", "what's on the", "what is on the"]
            wants_study = any(kw in message_lower for kw in study_keywords)
            
            if wants_study and (wants_quizzes or target_course):
                # Find quizzes for the target course
                if target_course:
                    quizzes = self.db_session.query(Quiz).filter_by(course_id=target_course.id).all()
                elif course_id:
                    quizzes = self.db_session.query(Quiz).filter_by(course_id=course_id).all()
                    target_course = self.db_session.query(Course).get(course_id)
                else:
                    quizzes = self.db_session.query(Quiz).all()
                
                if quizzes:
                    result_parts = []
                    total_questions = 0
                    lessons_to_study = set()
                    
                    for quiz in quizzes:
                        # Get questions in this quiz
                        quiz_questions = self.db_session.query(Question).join(
                            QuizQuestion, Question.id == QuizQuestion.question_id
                        ).filter(QuizQuestion.quiz_id == quiz.id).all()
                        
                        total_questions += len(quiz_questions)
                        
                        # Get lesson titles for these questions
                        for q in quiz_questions:
                            if q.primary_lesson:
                                lessons_to_study.add(q.primary_lesson.title)
                        
                        result_parts.append(f"• **{quiz.title}** ({len(quiz_questions)} questions)")
                    
                    lessons_text = "\n".join([f"  - {l}" for l in sorted(lessons_to_study)])
                    course_name = target_course.name if target_course else "your courses"
                    
                    return f"""📝 **Study Guide for {course_name}**

**Quizzes ({len(quizzes)}):**
{chr(10).join(result_parts)}

**Topics to Review ({len(lessons_to_study)} lessons):**
{lessons_text}

**Total Questions:** {total_questions}

💡 Tip: Ask me to "summarize [lesson name]" for detailed content of each topic!"""
                else:
                    return f"No quizzes found for {target_course.name if target_course else 'this course'}. Create some quizzes first!"
            
            # PRACTICE QUESTIONS query: "give me practice questions about X", "questions about threads"
            practice_keywords = ["practice question", "practice questions", "give me question", "give me questions", 
                                "show me question", "show me questions", "questions about", "questions on", 
                                "test me on", "quiz me on", "sample question"]
            wants_practice = any(kw in message_lower for kw in practice_keywords)
            
            # Also check for topic-specific keywords that map to lessons
            topic_mappings = {
                "thread": ["niti", "threads", "thread"],
                "threads": ["niti", "threads", "thread"],
                "niti": ["niti"],
                "process": ["procesi", "process"],
                "processes": ["procesi", "process"],
                "procesi": ["procesi"],
                "memory": ["memorija", "memory", "upravljanje memorijom", "virtuelna memorija"],
                "memorija": ["memorija", "upravljanje memorijom"],
                "concurrency": ["konkurentnost", "concurrency"],
                "konkurentnost": ["konkurentnost"],
                "selenium": ["selenium"],
                "angular": ["angular"],
                "java": ["java"],
                "spring": ["spring"],
                "testing": ["testiranje", "testing"],
                "testiranje": ["testiranje"],
            }
            
            # Find topic from message
            target_topic_lesson = None
            for topic_key, lesson_matches in topic_mappings.items():
                if topic_key in message_words:
                    # Find lesson that matches
                    for lesson in all_lessons:
                        lesson_lower = lesson.title.lower()
                        for match_term in lesson_matches:
                            if match_term in lesson_lower:
                                target_topic_lesson = lesson
                                break
                        if target_topic_lesson:
                            break
                    break
            
            if wants_practice and (target_lesson or target_topic_lesson):
                lesson_to_use = target_topic_lesson or target_lesson
                # Get questions from this lesson
                questions = self.db_session.query(Question).filter_by(primary_lesson_id=lesson_to_use.id).limit(5).all()
                
                if questions:
                    question_list = []
                    for idx, q in enumerate(questions, start=1):
                        q_text = q.question_text[:150] + "..." if len(q.question_text) > 150 else q.question_text
                        solo = q.solo_level.upper() if q.solo_level else "N/A"
                        question_list.append(f"**{idx}. [{solo}]** {q_text}")
                    
                    questions_text = "\n\n".join(question_list)
                    total_available = self.db_session.query(Question).filter_by(primary_lesson_id=lesson_to_use.id).count()
                    
                    return f"""❓ **Practice Questions: {lesson_to_use.title}**

{questions_text}

📊 Showing 5 of {total_available} questions available.

💡 Go to **Question Bank** to see all questions or **Build Quiz** to create a practice quiz!"""
                else:
                    return f"No questions found for **{lesson_to_use.title}**. Generate some questions first in the Question Generator!"
            
            if target_lesson and (wants_summary or wants_lessons):
                # Fetch sections and learning objects for this lesson
                sections = self.db_session.query(Section).filter_by(lesson_id=target_lesson.id).order_by(Section.order_index).all()
                
                if sections:
                    section_list = []
                    total_los = 0
                    for idx, s in enumerate(sections, start=1):
                        lo_count = self.db_session.query(LearningObject).filter_by(section_id=s.id).count()
                        total_los += lo_count
                        section_list.append(f"**{idx}. {s.title}** ({lo_count} concepts)")
                    
                    # Show all sections, no limit
                    sections_text = "\n".join([f"• {s}" for s in section_list])
                    
                    course = self.db_session.query(Course).get(target_lesson.course_id)
                    course_name = course.name if course else "Unknown"
                    
                    return f"""📖 **Lesson: {target_lesson.title}**
📚 Course: {course_name}
📑 Sections: {len(sections)} | 💡 Learning Objects: {total_los}

**Content Structure:**
{sections_text}

This is the actual content structure from your uploaded materials."""
                else:
                    return f"📖 **{target_lesson.title}** - This lesson hasn't been parsed yet (no sections found)."
            
            # COURSE CONTENT queries: "what topics are in OS course?", "what does OS cover?"
            if wants_topics and (wants_courses or target_course):
                if target_course:
                    lessons = self.db_session.query(Lesson).filter_by(course_id=target_course.id).all()
                    if lessons:
                        lesson_list = "\n".join([f"• **{l.title}**" for l in lessons])
                        return f"📚 **Topics/Lessons in {target_course.name} ({len(lessons)}):**\n{lesson_list}\n\nThese are the actual lessons from your course materials."
                    return f"The course '{target_course.name}' doesn't have any lessons yet."
                elif course_id:
                    course = self.db_session.query(Course).get(course_id)
                    lessons = self.db_session.query(Lesson).filter_by(course_id=course_id).all()
                    if lessons:
                        lesson_list = "\n".join([f"• **{l.title}**" for l in lessons])
                        course_name = course.name if course else "this course"
                        return f"📚 **Topics/Lessons in {course_name} ({len(lessons)}):**\n{lesson_list}\n\nThese are the actual lessons from your course materials."
                else:
                    # List all courses and their lessons
                    result_parts = []
                    for course in courses:
                        lessons = self.db_session.query(Lesson).filter_by(course_id=course.id).all()
                        if lessons:
                            lesson_titles = ", ".join([l.title for l in lessons[:5]])
                            extra = f"... +{len(lessons)-5} more" if len(lessons) > 5 else ""
                            result_parts.append(f"**{course.name}**: {lesson_titles}{extra}")
                    if result_parts:
                        return f"📚 **Your Course Topics:**\n" + "\n".join([f"• {r}" for r in result_parts])
            
            # COUNT queries: "how many X do I have?"
            if any(word in message_lower for word in ["how many", "total", "count", "number of"]):
                if wants_relationships:
                    count = self.db_session.query(ConceptRelationship).count()
                    return f"🔗 You have **{count}** ontological relationship(s)."
                
                if wants_quizzes:
                    if target_course:
                        count = self.db_session.query(Quiz).filter_by(course_id=target_course.id).count()
                        return f"📋 You have **{count}** quiz(zes) in {target_course.name}."
                    elif course_id:
                        count = self.db_session.query(Quiz).filter_by(course_id=course_id).count()
                        return f"📋 You have **{count}** quiz(zes) in this course."
                    else:
                        count = self.db_session.query(Quiz).count()
                        return f"📋 You have **{count}** total quiz(zes)."
                
                if wants_lessons:
                    if target_course:
                        count = self.db_session.query(Lesson).filter_by(course_id=target_course.id).count()
                        return f"📚 You have **{count}** lesson(s) in {target_course.name}."
                    elif course_id:
                        count = self.db_session.query(Lesson).filter_by(course_id=course_id).count()
                        return f"📚 You have **{count}** lesson(s) in this course."
                    else:
                        count = self.db_session.query(Lesson).count()
                        return f"📚 You have **{count}** total lesson(s)."
                
                if wants_courses:
                    count = self.db_session.query(Course).count()
                    return f"📚 You have **{count}** course(s)."
                
                if wants_questions:
                    if target_course:
                        # Questions don't have course_id directly - join through Lesson
                        count = self.db_session.query(Question).join(
                            Lesson, Question.primary_lesson_id == Lesson.id
                        ).filter(Lesson.course_id == target_course.id).count()
                        return f"❓ You have **{count}** question(s) in the question bank for {target_course.name}."
                    elif course_id:
                        count = self.db_session.query(Question).join(
                            Lesson, Question.primary_lesson_id == Lesson.id
                        ).filter(Lesson.course_id == course_id).count()
                        return f"❓ You have **{count}** question(s) in the question bank for this course."
                    else:
                        count = self.db_session.query(Question).count()
                        return f"❓ You have **{count}** total question(s) in the question bank."
                
                if wants_learning_objects:
                    count = self.db_session.query(LearningObject).count()
                    return f"📖 You have **{count}** learning object(s)."
                
                if wants_sections:
                    count = self.db_session.query(Section).count()
                    return f"📑 You have **{count}** section(s)."
            
            # LIST queries: "list my X", "show me my X"
            wants_list = any(word in message_lower for word in ["list", "show", "what are my", "tell me my", "give me", "what are the"])
            
            if wants_list:
                if wants_courses:
                    if courses:
                        course_list = "\n".join([f"• **{c.name}**" + (f" - {c.description[:50]}..." if c.description else "") for c in courses])
                        return f"📚 **Your Courses ({len(courses)}):**\n{course_list}"
                    return "You don't have any courses yet. Create one to get started!"
                
                if wants_lessons:
                    if target_course:
                        lessons = self.db_session.query(Lesson).filter_by(course_id=target_course.id).all()
                        if lessons:
                            lesson_list = "\n".join([f"• **{l.title}**" for l in lessons])
                            return f"📖 **Lessons in {target_course.name} ({len(lessons)}):**\n{lesson_list}"
                        return f"No lessons in {target_course.name}."
                    else:
                        # Show ALL lessons grouped by course
                        result_parts = []
                        total_count = 0
                        for course in courses:
                            lessons = self.db_session.query(Lesson).filter_by(course_id=course.id).all()
                            if lessons:
                                total_count += len(lessons)
                                lesson_titles = "\n".join([f"  - {l.title}" for l in lessons[:8]])
                                extra = f"\n  - ... +{len(lessons)-8} more" if len(lessons) > 8 else ""
                                result_parts.append(f"**{course.name}** ({len(lessons)}):\n{lesson_titles}{extra}")
                        if result_parts:
                            return f"📖 **All Lessons ({total_count}):**\n\n" + "\n\n".join(result_parts)
                        return "No lessons found."
                
                if wants_quizzes:
                    if target_course:
                        quizzes = self.db_session.query(Quiz).filter_by(course_id=target_course.id).all()
                        if quizzes:
                            quiz_list = "\n".join([f"• **{q.title}**" for q in quizzes])
                            return f"📋 **Quizzes in {target_course.name} ({len(quizzes)}):**\n{quiz_list}"
                        return f"No quizzes in {target_course.name}."
                    else:
                        # Show ALL quizzes grouped by course
                        result_parts = []
                        total_count = 0
                        for course in courses:
                            quizzes = self.db_session.query(Quiz).filter_by(course_id=course.id).all()
                            if quizzes:
                                total_count += len(quizzes)
                                quiz_titles = "\n".join([f"  - {q.title}" for q in quizzes])
                                result_parts.append(f"**{course.name}** ({len(quizzes)}):\n{quiz_titles}")
                        if result_parts:
                            return f"📋 **All Quizzes ({total_count}):**\n\n" + "\n\n".join(result_parts)
                        return "No quizzes found."
            
            return None
            
        except Exception as e:
            print(f"[ChatbotService] Database query error: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _get_offline_response(self, user_message: str, course_id: Optional[int] = None) -> Optional[str]:
        """Generate response from simple offline knowledge base and database queries"""
        message_lower = user_message.lower().strip()
        
        # Check for exact word matches first (not substring)
        for key, response in self.offline_responses.items():
            if f" {key} " in f" {message_lower} " or message_lower == key or message_lower.startswith(key + " ") or message_lower.endswith(" " + key):
                return response
        
        # Database queries for course/lesson information - CHECK THESE FIRST
        if self.db_session:
            try:
                from models import Course, Lesson, Question, Quiz, ConceptRelationship
                
                # Flexible keyword matching
                lesson_keywords = ["lesson", "lesion", "lession", "les"]
                course_keywords = ["course"]
                quiz_keywords = ["quiz", "quizzes"]
                question_keywords = ["question"]
                relationship_keywords = ["relationship", "relationships", "ontological", "concept", "ontology"]
                
                wants_lessons = any(kw in message_lower for kw in lesson_keywords)
                wants_courses = any(kw in message_lower for kw in course_keywords) and not wants_lessons
                wants_quizzes = any(kw in message_lower for kw in quiz_keywords)
                wants_questions = any(kw in message_lower for kw in question_keywords)
                wants_relationships = any(kw in message_lower for kw in relationship_keywords)
                wants_list = any(word in message_lower for word in ["list", "show", "what do i have", "tell me my", "give me", "them"])
                
                # Check for count/list questions first (BEFORE learning content search)
                if any(word in message_lower for word in ["how many", "total", "count", "number of"]):
                    if wants_relationships:
                        relationships = self.db_session.query(ConceptRelationship).all()
                        return f"🔗 You have **{len(relationships)}** ontological relationship(s)."
                    
                    if wants_quizzes:
                        if course_id:
                            quizzes = self.db_session.query(Quiz).filter_by(course_id=course_id).all()
                            return f"📋 You have **{len(quizzes)}** quiz(zes) in this course."
                        else:
                            quizzes = self.db_session.query(Quiz).all()
                            return f"📋 You have **{len(quizzes)}** total quiz(zes)."
                    
                    if wants_lessons:
                        if course_id:
                            lessons = self.db_session.query(Lesson).filter_by(course_id=course_id).all()
                            return f"📚 You have **{len(lessons)}** lesson(s) in this course."
                        else:
                            lessons = self.db_session.query(Lesson).all()
                            return f"📚 You have **{len(lessons)}** total lesson(s)."
                    
                    if wants_courses:
                        courses = self.db_session.query(Course).all()
                        return f"📚 You have **{len(courses)}** course(s)."
                    
                    if wants_questions:
                        if course_id:
                            questions = self.db_session.query(Question).filter_by(course_id=course_id).all()
                            return f"❓ You have **{len(questions)}** question(s) in this course."
                        else:
                            questions = self.db_session.query(Question).all()
                            return f"❓ You have **{len(questions)}** total question(s)."
                
                if wants_list and wants_lessons:
                    if course_id:
                        lessons = self.db_session.query(Lesson).filter_by(course_id=course_id).all()
                        if lessons:
                            lesson_list = "\n".join([f"- **{l.title}**" for l in lessons[:20]])
                            return f"📖 Lessons in this course:\n{lesson_list}" + (f"\n... and {len(lessons)-20} more" if len(lessons) > 20 else "")
                        else:
                            return "No lessons in this course yet."
                    
                    courses = self.db_session.query(Course).all()
                    if courses:
                        first_course_id = courses[0].id
                        lessons = self.db_session.query(Lesson).filter_by(course_id=first_course_id).all()
                        if lessons:
                            lesson_list = "\n".join([f"- **{l.title}**" for l in lessons[:20]])
                            return f"📖 Lessons in '{courses[0].name}':\n{lesson_list}" + (f"\n... and {len(lessons)-20} more" if len(lessons) > 20 else "")
                        else:
                            return f"The course '{courses[0].name}' has no lessons yet."
                    else:
                        return "You don't have any courses yet. Create one to get started!"
                
                if wants_list and (wants_courses or not wants_lessons):
                    courses = self.db_session.query(Course).all()
                    if courses:
                        course_list = "\n".join([f"- **{c.name}**: {c.description[:50]}..." if c.description else f"- **{c.name}**" for c in courses])
                        return f"📚 Your Courses:\n{course_list}"
                    
                    return "You don't have any courses yet. Create one to get started!"
                
            except Exception as e:
                print(f"[ChatbotService] Database error: {e}")
                import traceback
                traceback.print_exc()
        
        # Search through learning content (only if not a database query)
        content_result = self._search_learning_content(user_message, course_id)
        if content_result:
            return content_result
        
        # Generic responses for various question types
        if any(word in message_lower for word in ["what", "how", "why", "explain", "tell"]):
            return f"That's a great question about '{user_message}'. To give you a better answer, I would need more context about your course material. Can you provide more details or let me know which lesson or topic this relates to?"
        
        if any(word in message_lower for word in ["quiz", "question", "answer", "test", "exam"]):
            return "I can help you understand quiz questions! Please provide the question and answer, and I'll explain the concept to you."
        
        if any(word in message_lower for word in ["study", "learn", "tip", "advice", "help"]):
            return "Great! Here are some study tips:\n1. Review concepts regularly\n2. Practice with examples\n3. Test yourself with quizzes\n4. Connect concepts to real-world scenarios\n5. Discuss with others\n\nWhat specific topic would you like help with?"
        
        # Default response
        return "I'm in offline mode. I can help with basic questions. For detailed explanations, please ensure Ollama is running. What would you like to know?"

    def _get_response_from_ollama(self, prompt: str) -> Optional[str]:
        """Get response from the active LLM provider (Ollama or Anthropic)."""
        from core.llm_provider import call_llm
        try:
            result = call_llm(
                prompt, role="chatbot",
                temperature=0.7, json_mode=False,
                use_cache=False, timeout=120,
            )
            return result.strip() if result else None
        except Exception as e:
            print(f"[ChatbotService] LLM error: {e}")
            return None

    def _get_relevant_context(self, user_message: str, course_id: Optional[int] = None) -> str:
        """
        Fetch relevant content from database to provide context for the AI
        """
        if not self.db_session:
            return ""
        
        try:
            from models import Course, Lesson, Section, LearningObject
            
            query_lower = user_message.lower()
            stop_words = ["what", "is", "a", "an", "the", "whats", "what's", "how", "why", "does", "do", "can", "you", "tell", "me", "about", "explain", "?"]
            query_terms = [w for w in query_lower.split() if w not in stop_words and len(w) > 2]
            
            if not query_terms:
                return ""
            
            context_parts = []
            
            # Search Learning Objects for relevant content
            learning_objects = self.db_session.query(LearningObject).all()
            relevant_los = []
            for lo in learning_objects:
                lo_text = f"{lo.title or ''} {lo.description or ''}".lower()
                match_score = sum(1 for term in query_terms if term in lo_text)
                # Boost if term in title
                for term in query_terms:
                    if term in (lo.title or '').lower():
                        match_score += 3
                if match_score > 0:
                    relevant_los.append((match_score, lo))
            
            # Sort and get top 5 most relevant
            relevant_los.sort(key=lambda x: x[0], reverse=True)
            for score, lo in relevant_los[:5]:
                if lo.description:
                    context_parts.append(f"**{lo.title}**: {lo.description[:500]}")
            
            # Also get relevant sections
            sections = self.db_session.query(Section).all()
            relevant_sections = []
            for section in sections:
                section_text = f"{section.title or ''} {section.content or ''}".lower()
                match_score = sum(1 for term in query_terms if term in section_text)
                if match_score > 0:
                    relevant_sections.append((match_score, section))
            
            relevant_sections.sort(key=lambda x: x[0], reverse=True)
            for score, section in relevant_sections[:3]:
                if section.content:
                    context_parts.append(f"**Section - {section.title}**: {section.content[:400]}")
            
            if context_parts:
                return "\n\n".join(context_parts)
            
            return ""
            
        except Exception as e:
            print(f"[ChatbotService] Context fetch error: {e}")
            return ""

    def generate_response(
        self,
        user_message: str,
        course_context: Optional[str] = None,
        lesson_context: Optional[str] = None,
        conversation_history: Optional[List[Dict]] = None,
        course_id: Optional[int] = None
    ) -> Dict:
        """
        Generate chatbot response based on user message and context
        """
        
        # FIRST: Check if this is a simple database query that we can answer directly
        db_answer = self._check_database_query(user_message, course_id)
        if db_answer:
            print(f"[ChatbotService] Answered from database query")
            return {
                "response": db_answer,
                "service": "database",
                "success": True
            }
        
        # Build system prompt with project knowledge
        system_prompt = """You are an intelligent Learning Assistant embedded in an educational platform. 
You are knowledgeable, conversational, and helpful. Your capabilities include:

1. **Course Knowledge**: You understand the user's courses, lessons, sections, and learning objects
2. **Quiz Management**: You can discuss quiz questions, provide explanations, and help students prepare
3. **Ontological Relationships**: You understand concept relationships and knowledge graphs in the system
4. **Teaching**: You explain complex concepts clearly, breaking them down into understandable parts
5. **Encouragement**: You're supportive and motivating in helping students learn

IMPORTANT INSTRUCTIONS:
- Answer ALL questions thoughtfully, not just about courses
- If asked general knowledge questions, answer based on your training
- When discussing course content, reference the provided materials
- Be conversational and natural, like ChatGPT
- Ask clarifying questions if needed
- Provide detailed, helpful answers
- Always be honest - if you don't know something, say so

When relevant course content is provided below, use it to give contextual answers."""

        # Fetch relevant content from database
        db_context = self._get_relevant_context(user_message, course_id)
        
        # Add context if provided
        context_parts = []
        if course_context:
            context_parts.append(f"📚 Current Course: {course_context}")
        if lesson_context:
            truncated_lesson = lesson_context[:self.max_context_length]
            context_parts.append(f"📖 Lesson Content:\n{truncated_lesson}")
        
        # Add database context
        if db_context:
            context_parts.append(f"📚 Relevant Learning Materials:\n{db_context}")

        # Build conversation history
        history_text = ""
        if conversation_history:
            for msg in conversation_history[-6:]:  # Keep last 6 messages for better context
                role = msg.get("role", "user")
                content = msg.get("content", "")
                history_text += f"{role.capitalize()}: {content}\n"

        # Combine into full prompt
        context_section = "\n".join(context_parts) if context_parts else "No specific course context available."
        
        full_prompt = f"""{system_prompt}

===== AVAILABLE CONTEXT =====
{context_section}

===== CONVERSATION HISTORY =====
{history_text}

User: {user_message}
Assistant:"""

        # Debug
        if db_context:
            print(f"[ChatbotService] Found relevant context: {len(db_context)} chars")

        # Try Ollama first
        response_text = None
        used_service = "ollama"
        ollama_available = self._test_ollama_connection()
        
        if ollama_available:
            print("[ChatbotService] Using Ollama for response")
            response_text = self._get_response_from_ollama(full_prompt)
        
        # Fall back to offline mode
        if not response_text:
            print("[ChatbotService] Using offline mode")
            used_service = "offline"
            response_text = self._get_offline_response(user_message, course_id)

        return {
            "response": response_text.strip(),
            "service": used_service,
            "success": True
        }

    def generate_quiz_explanation(self, question: str, correct_answer: str, user_answer: Optional[str] = None) -> Dict:
        """
        Generate an explanation for a quiz question and answer
        """
        
        if user_answer and user_answer != correct_answer:
            prompt = f"""Please explain why the answer to this question is "{correct_answer}" and not "{user_answer}".

Question: {question}
Correct Answer: {correct_answer}
User's Answer: {user_answer}

Provide a brief, educational explanation that helps the student understand the concept."""
        else:
            prompt = f"""Please explain why this answer to the question is correct.

Question: {question}
Answer: {correct_answer}

Keep the explanation clear and educational."""

        response_text = None
        
        if self._test_ollama_connection():
            response_text = self._get_response_from_ollama(prompt)
        
        return {
            "explanation": response_text.strip() if response_text else "Unable to generate explanation",
            "success": response_text is not None
        }


# Singleton instance
chatbot_service = ChatbotService()
