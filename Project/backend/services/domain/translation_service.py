"""
Comprehensive Translation Service for All Content
Handles translating questions, lessons, sections, learning objects, and ontologies
Uses local Ollama model (qwen2.5:14b) for all translations
"""

import json
import logging
import requests
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from models.models import (
    Question, QuestionTranslation,
    Lesson, LessonTranslation,
    Section, SectionTranslation,
    LearningObject, LearningObjectTranslation,
    ConceptRelationship, OntologyTranslation
)

# Single source of truth for Ollama URL/model lives in backend/config.py
from config import OLLAMA_BASE_URL, OLLAMA_MODEL

# Setup logging
logger = logging.getLogger(__name__)

# Supported languages for translation
SUPPORTED_LANGUAGES = {
    'sr': 'Serbian',
    'fr': 'French',
    'es': 'Spanish',
    'de': 'German',
    'ru': 'Russian',
    'zh': 'Chinese (Simplified)',
    'ja': 'Japanese',
    'pt': 'Portuguese',
    'it': 'Italian'
}


class TranslationService:
    """Service for translating all content types into multiple languages"""
    
    def __init__(self):
        """Initialize translation service with local Ollama as the translation backend"""
        self.ollama_base_url = OLLAMA_BASE_URL
        self.ollama_model = OLLAMA_MODEL
        self.supported_languages = SUPPORTED_LANGUAGES
    
    def _call_ollama(self, prompt: str, timeout: int = 300) -> Optional[str]:
        """Call local Ollama model for text generation"""
        prompt_size = len(prompt)
        logger.info(f"[OLLAMA] Calling for translation | Prompt size: {prompt_size} chars")
        print(f"[TRANSLATION] Ollama call | Prompt: {prompt_size} chars")
        
        try:
            url = f"{self.ollama_base_url}/api/generate"
            payload = {
                "model": self.ollama_model,
                "prompt": prompt,
                "stream": False,
                "temperature": 0.7,
            }
            
            response = requests.post(url, json=payload, timeout=timeout)
            
            if response.status_code == 200:
                data = response.json()
                response_text = data.get("response", "")
                response_size = len(response_text)
                logger.info(f"[OLLAMA] Success | Response size: {response_size} chars")
                print(f"[TRANSLATION] Response received | Size: {response_size} chars")
                return response_text
            else:
                logger.error(f"Ollama API error: Status {response.status_code}")
                print(f"[TRANSLATION] ❌ Ollama error {response.status_code}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error(f"Ollama request timeout after {timeout} seconds")
            print(f"[TRANSLATION] ❌ Timeout after {timeout}s")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama request error: {str(e)}")
            print(f"[TRANSLATION] ❌ Request error: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error calling Ollama: {str(e)}")
            print(f"[TRANSLATION] ❌ Error: {str(e)}")
            return None
    
    # ==================== QUESTION TRANSLATION ====================
    
    def translate_question(
        self,
        question: Question,
        target_language_code: str,
        session: Session
    ) -> Optional[QuestionTranslation]:
        """Translate a single question to target language"""
        
        if target_language_code not in self.supported_languages:
            logger.error(f"Unsupported language code: {target_language_code}")
            return None
        
        # Check if translation already exists
        existing_translation = session.query(QuestionTranslation).filter(
            QuestionTranslation.question_id == question.id,
            QuestionTranslation.language_code == target_language_code
        ).first()
        if existing_translation:
            language_name = self.supported_languages[target_language_code]
            print(f"[TRANSLATION] ⊘ Skipping Question #{question.id} - already translated to {language_name}")
            return existing_translation
        
        try:
            language_name = self.supported_languages[target_language_code]
            print(f"[TRANSLATION] Translating Question #{question.id} to {language_name}...")
            
            # Retry up to 5 times if translation fails
            max_retries = 5
            for attempt in range(max_retries):
                # Use more forceful prompt on retries
                prompt = self._build_question_translation_prompt(question, target_language_code, language_name, attempt)
                response_text = self._call_ollama(prompt)
                
                if not response_text:
                    logger.error(f"Failed to translate question {question.id} (attempt {attempt + 1})")
                    if attempt < max_retries - 1:
                        print(f"[TRANSLATION] ⟳ Retry {attempt + 2}/{max_retries} for question {question.id}...")
                        continue
                    print(f"[TRANSLATION] ❌ Failed to translate question {question.id} after {max_retries} attempts")
                    return None
                
                translation_data = self._parse_translation_response(response_text)
                
                if not translation_data or 'question_text' not in translation_data:
                    logger.error(f"Failed to parse question translation (attempt {attempt + 1})")
                    if attempt < max_retries - 1:
                        print(f"[TRANSLATION] ⟳ Retry {attempt + 2}/{max_retries} for question {question.id}...")
                        continue
                    print(f"[TRANSLATION] ❌ Failed to parse translation after {max_retries} attempts")
                    return None
                
                # Validate that translation is actually different from original (reject if same)
                translated_text = translation_data['question_text'].strip()
                original_text = question.question_text.strip()
                # Check if identical or if first 30 chars are the same (likely not translated)
                if translated_text.lower() == original_text.lower() or translated_text[:30].lower() == original_text[:30].lower():
                    logger.error(f"Translation identical to original (attempt {attempt + 1})")
                    if attempt < max_retries - 1:
                        print(f"[TRANSLATION] ⟳ Retry {attempt + 2}/{max_retries} - AI returned original text...")
                        continue
                    print(f"[TRANSLATION] ❌ Translation still identical after {max_retries} attempts - skipping question {question.id}")
                    return None
                
                # Success - create translation record
                translation = QuestionTranslation(
                    question_id=question.id,
                    language_code=target_language_code,
                    language_name=language_name,
                    translated_question_text=translation_data['question_text'],
                    translated_options=translation_data.get('options'),
                    translated_correct_answer=translation_data.get('correct_answer'),
                    translated_explanation=translation_data.get('explanation')
                )
                
                session.add(translation)
                session.commit()
                logger.info(f"Translated question {question.id} to {language_name}")
                return translation
            
            return None  # Should not reach here
            
        except Exception as e:
            logger.error(f"Error translating question: {str(e)}")
            session.rollback()
            return None
    
    def _build_question_translation_prompt(self, question: Question, lang_code: str, lang_name: str, attempt: int = 0) -> str:
        """Build prompt for question translation - more forceful on retries"""
        
        options_text = ""
        if question.options:
            options_text = "Options:\n" + "\n".join([f"- {opt}" for opt in question.options])
        
        # For Serbian, be very specific
        if lang_code == "sr":
            lang_desc = "Serbian (srpski jezik) - NOT Croatian, NOT Bosnian - use Serbian Latin alphabet (latinica)"
        else:
            lang_desc = lang_name
        
        # Base translation instruction
        if attempt == 0:
            intro = f"You are a professional translator. Translate this quiz question from English to {lang_desc}."
        elif attempt == 1:
            intro = f"TRANSLATE the following English text to {lang_desc}. DO NOT return English text."
        elif attempt == 2:
            intro = f"I need this text in {lang_desc}, NOT English. Please translate everything below."
        elif attempt == 3:
            intro = f"Convert this English quiz to {lang_desc}. The output MUST NOT be in English. English output is WRONG."
        else:
            intro = f"MANDATORY: Output must be 100% in {lang_desc}. Zero English words allowed. Translate now:"
        
        prompt = f"""{intro}

RULES:
1. ALL text must be translated to {lang_name} - NO English in output
2. {"Use Serbian Latin alphabet (latinica, NOT ćirilica). This is SERBIAN language, not Croatian!" if lang_code == "sr" else "Use proper " + lang_name + " characters"}
3. Return valid JSON only

ENGLISH INPUT:
Question: {question.question_text}

{options_text}

Correct answer: {question.correct_answer}
Explanation: {question.explanation if question.explanation else "N/A"}

OUTPUT (JSON with ALL values in {lang_name}):
{{"question_text": "[{lang_name} translation]", "options": ["[{lang_name}]", ...], "correct_answer": "[{lang_name}]", "explanation": "[{lang_name}]"}}"""
        
        return prompt
    
    # ==================== LESSON TRANSLATION ====================
    
    def translate_lesson(
        self,
        lesson: Lesson,
        target_language_code: str,
        session: Session
    ) -> Optional[LessonTranslation]:
        """Translate a lesson to target language"""
        
        if target_language_code not in self.supported_languages:
            logger.error(f"Unsupported language code: {target_language_code}")
            return None
        
        # Check if translation already exists
        existing_translation = session.query(LessonTranslation).filter(
            LessonTranslation.lesson_id == lesson.id,
            LessonTranslation.language_code == target_language_code
        ).first()
        if existing_translation:
            language_name = self.supported_languages[target_language_code]
            print(f"[TRANSLATION] ⊘ Skipping Lesson '{lesson.title}' - already translated to {language_name}")
            return existing_translation
        
        try:
            language_name = self.supported_languages[target_language_code]
            prompt = self._build_lesson_translation_prompt(lesson, target_language_code, language_name)
            response_text = self._call_ollama(prompt)
            
            if not response_text:
                logger.error(f"Failed to translate lesson {lesson.id}")
                return None
            
            translation_data = self._parse_translation_response(response_text)
            
            if not translation_data or 'title' not in translation_data:
                logger.error(f"Failed to parse lesson translation")
                return None
            
            translation = LessonTranslation(
                lesson_id=lesson.id,
                language_code=target_language_code,
                language_name=language_name,
                translated_title=translation_data['title'],
                translated_summary=translation_data.get('summary')
            )
            
            session.add(translation)
            session.commit()
            logger.info(f"Translated lesson {lesson.id} to {language_name}")
            return translation
            
        except Exception as e:
            logger.error(f"Error translating lesson: {str(e)}")
            session.rollback()
            return None
    
    def _build_lesson_translation_prompt(self, lesson: Lesson, lang_code: str, lang_name: str) -> str:
        """Build prompt for lesson translation"""
        
        prompt = f"""Translate this lesson metadata to {lang_name} ({lang_code}).
IMPORTANT CONSTRAINTS:
1. Use ONLY Latin characters (a-z, A-Z, 0-9, and standard punctuation)
2. Do NOT use Cyrillic characters
3. For Serbian: use Latin script only (NO Cyrillic)
4. Maintain educational value and clarity

Return ONLY a valid JSON object with keys: title, summary.

Lesson title: {lesson.title}
Summary: {lesson.summary if lesson.summary else "N/A"}

Return ONLY JSON, no other text:"""
        
        return prompt
    
    # ==================== SECTION TRANSLATION ====================
    
    def translate_section(
        self,
        section: Section,
        target_language_code: str,
        session: Session
    ) -> Optional[SectionTranslation]:
        """Translate a section to target language"""
        
        if target_language_code not in self.supported_languages:
            logger.error(f"Unsupported language code: {target_language_code}")
            return None
        
        # Check if translation already exists
        existing_translation = session.query(SectionTranslation).filter(
            SectionTranslation.section_id == section.id,
            SectionTranslation.language_code == target_language_code
        ).first()
        if existing_translation:
            language_name = self.supported_languages[target_language_code]
            print(f"[TRANSLATION] ⊘ Skipping Section '{section.title}' - already translated to {language_name}")
            return existing_translation
        
        try:
            language_name = self.supported_languages[target_language_code]
            prompt = self._build_section_translation_prompt(section, target_language_code, language_name)
            response_text = self._call_ollama(prompt)
            
            if not response_text:
                logger.error(f"Failed to translate section {section.id}")
                return None
            
            translation_data = self._parse_translation_response(response_text)
            
            if not translation_data or 'title' not in translation_data:
                logger.error(f"Failed to parse section translation")
                return None
            
            translation = SectionTranslation(
                section_id=section.id,
                language_code=target_language_code,
                language_name=language_name,
                translated_title=translation_data['title'],
                translated_content=translation_data.get('content'),
                translated_summary=translation_data.get('summary')
            )
            
            session.add(translation)
            session.commit()
            logger.info(f"Translated section {section.id} to {language_name}")
            return translation
            
        except Exception as e:
            logger.error(f"Error translating section: {str(e)}")
            session.rollback()
            return None
    
    def _build_section_translation_prompt(self, section: Section, lang_code: str, lang_name: str) -> str:
        """Build prompt for section translation"""
        
        content_preview = section.content[:500] if section.content else "N/A"
        
        prompt = f"""Translate this educational section to {lang_name} ({lang_code}).
IMPORTANT CONSTRAINTS:
1. Use ONLY Latin characters (a-z, A-Z, 0-9, and standard punctuation)
2. Do NOT use Cyrillic characters
3. For Serbian: use Latin script only (NO Cyrillic)
4. Preserve technical accuracy and educational structure
5. Translate naturally while maintaining clarity

Return ONLY a valid JSON object with keys: title, content, summary.

Section title: {section.title}
Content preview: {content_preview}...
Summary: {section.summary if section.summary else "N/A"}

Return ONLY JSON, no other text:"""
        
        return prompt
    
    # ==================== LEARNING OBJECT TRANSLATION ====================
    
    def translate_learning_object(
        self,
        learning_object: LearningObject,
        target_language_code: str,
        session: Session
    ) -> Optional[LearningObjectTranslation]:
        """Translate a learning object to target language"""
        
        if target_language_code not in self.supported_languages:
            logger.error(f"Unsupported language code: {target_language_code}")
            return None
        
        # Check if translation already exists
        existing_translation = session.query(LearningObjectTranslation).filter(
            LearningObjectTranslation.learning_object_id == learning_object.id,
            LearningObjectTranslation.language_code == target_language_code
        ).first()
        if existing_translation:
            language_name = self.supported_languages[target_language_code]
            print(f"[TRANSLATION] ⊘ Skipping Learning Object '{learning_object.title}' - already translated to {language_name}")
            return existing_translation
        
        try:
            language_name = self.supported_languages[target_language_code]
            prompt = self._build_learning_object_translation_prompt(learning_object, target_language_code, language_name)
            response_text = self._call_ollama(prompt)
            
            if not response_text:
                logger.error(f"Failed to translate learning object {learning_object.id}")
                return None
            
            translation_data = self._parse_translation_response(response_text)
            
            if not translation_data or 'title' not in translation_data:
                logger.error(f"Failed to parse learning object translation")
                return None
            
            translation = LearningObjectTranslation(
                learning_object_id=learning_object.id,
                language_code=target_language_code,
                language_name=language_name,
                translated_title=translation_data['title'],
                translated_content=translation_data.get('content'),
                translated_description=translation_data.get('description'),
                translated_key_points=translation_data.get('key_points'),
                translated_keywords=translation_data.get('keywords')
            )
            
            session.add(translation)
            session.commit()
            logger.info(f"Translated learning object {learning_object.id} to {language_name}")
            return translation
            
        except Exception as e:
            logger.error(f"Error translating learning object: {str(e)}")
            session.rollback()
            return None
    
    def _build_learning_object_translation_prompt(self, lo: LearningObject, lang_code: str, lang_name: str) -> str:
        """Build prompt for learning object translation"""
        
        key_points_text = ""
        if lo.key_points:
            key_points_text = "Key points: " + ", ".join(lo.key_points) if isinstance(lo.key_points, list) else str(lo.key_points)
        
        keywords_text = ""
        if lo.keywords:
            keywords_text = "Keywords: " + ", ".join(lo.keywords) if isinstance(lo.keywords, list) else str(lo.keywords)
        
        content_preview = lo.content[:500] if lo.content else "N/A"
        
        prompt = f"""Translate this learning object to {lang_name} ({lang_code}).
IMPORTANT CONSTRAINTS:
1. Use ONLY Latin characters (a-z, A-Z, 0-9, and standard punctuation)
2. Do NOT use Cyrillic characters
3. For Serbian: use Latin script only (NO Cyrillic)
4. Translate key concepts accurately and consistently
5. Make the translation clear and educationally sound
6. Keep keywords relevant and searchable

Return ONLY a valid JSON object with keys: title, content, description, key_points, keywords.

Title: {lo.title}
Content preview: {content_preview}...
Description: {lo.description if lo.description else "N/A"}
{key_points_text}
{keywords_text}

Return ONLY JSON, no other text:"""
        
        return prompt
    
    # ==================== ONTOLOGY TRANSLATION ====================
    
    def translate_ontology_relationship(
        self,
        relationship: ConceptRelationship,
        target_language_code: str,
        session: Session
    ) -> Optional[OntologyTranslation]:
        """Translate an ontology relationship to target language"""
        
        if target_language_code not in self.supported_languages:
            logger.error(f"Unsupported language code: {target_language_code}")
            return None
        
        # Check if translation already exists
        existing_translation = session.query(OntologyTranslation).filter(
            OntologyTranslation.concept_relationship_id == relationship.id,
            OntologyTranslation.language_code == target_language_code
        ).first()
        if existing_translation:
            language_name = self.supported_languages[target_language_code]
            print(f"[TRANSLATION] ⊘ Skipping Ontology Relationship '{relationship.relationship_type}' - already translated to {language_name}")
            return existing_translation
        
        try:
            language_name = self.supported_languages[target_language_code]
            prompt = self._build_ontology_translation_prompt(relationship, target_language_code, language_name)
            response_text = self._call_ollama(prompt)
            
            if not response_text:
                logger.error(f"Failed to translate ontology relationship {relationship.id}")
                return None
            
            translation_data = self._parse_translation_response(response_text)
            
            if not translation_data or 'relationship_type' not in translation_data:
                logger.error(f"Failed to parse ontology translation")
                return None
            
            translation = OntologyTranslation(
                concept_relationship_id=relationship.id,
                language_code=target_language_code,
                language_name=language_name,
                translated_relationship_type=translation_data['relationship_type'],
                translated_description=translation_data.get('description')
            )
            
            session.add(translation)
            session.commit()
            logger.info(f"Translated ontology relationship {relationship.id} to {language_name}")
            return translation
            
        except Exception as e:
            logger.error(f"Error translating ontology relationship: {str(e)}")
            session.rollback()
            return None
    
    def _build_ontology_translation_prompt(self, rel: ConceptRelationship, lang_code: str, lang_name: str) -> str:
        """Build prompt for ontology relationship translation"""
        
        source_title = rel.source.title if rel.source else "Unknown"
        target_title = rel.target.title if rel.target else "Unknown"
        
        prompt = f"""Translate this ontology relationship to {lang_name} ({lang_code}).
IMPORTANT CONSTRAINTS:
1. Use ONLY Latin characters (a-z, A-Z, 0-9, and standard punctuation)
2. Do NOT use Cyrillic characters
3. For Serbian: use Latin script only (NO Cyrillic)
4. Maintain semantic accuracy for ontological relationships
5. Use consistent terminology

Return ONLY a valid JSON object with keys: relationship_type, description.

From concept: {source_title}
Relationship type: {rel.relationship_type}
To concept: {target_title}
Description: {rel.description if rel.description else "N/A"}

Return ONLY JSON, no other text:"""
        
        return prompt
    
    # ==================== HELPER METHODS ====================
    
    def _parse_translation_response(self, response_text: str) -> Optional[Dict]:
        """Parse translation response from Ollama model"""
        
        try:
            response_text = response_text.strip()
            
            # Remove markdown code blocks if present
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.startswith('```'):
                response_text = response_text[3:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            
            response_text = response_text.strip()
            translation_data = json.loads(response_text)
            return translation_data
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse translation JSON: {str(e)}")
            logger.error(f"Response was: {response_text[:200]}")
            return None
        except Exception as e:
            logger.error(f"Error parsing translation response: {str(e)}")
            return None
    
    def translate_course_content(self, lesson_ids: List[int], target_language: str, session: Session) -> Dict:
        """Translate all content in a course (all lessons, sections, learning objects, questions, ontologies)"""
        stats = {
            'lessons': 0,
            'sections': 0,
            'learning_objects': 0,
            'questions': 0,
            'ontologies': 0,
            'errors': []
        }
        
        if target_language not in self.supported_languages:
            raise ValueError(f"Unsupported language: {target_language}")
        
        lang_name = self.supported_languages[target_language]
        print(f"\n[COURSE TRANSLATION] Starting batch translation to {lang_name}")
        print(f"[COURSE TRANSLATION] Processing {len(lesson_ids)} lessons...")
        
        try:
            for idx, lesson_id in enumerate(lesson_ids, 1):
                lesson = session.get(Lesson, lesson_id)
                if not lesson:
                    stats['errors'].append(f"Lesson {lesson_id} not found")
                    continue
                
                print(f"\n[COURSE TRANSLATION] [{idx}/{len(lesson_ids)}] Translating lesson: {lesson.title}")
                
                # Translate lesson
                try:
                    self.translate_lesson(lesson, target_language, session)
                    stats['lessons'] += 1
                    print(f"[COURSE TRANSLATION] ✓ Lesson translated")
                except Exception as e:
                    stats['errors'].append(f"Error translating lesson {lesson_id}: {str(e)}")
                    print(f"[COURSE TRANSLATION] ❌ Error: {str(e)}")
                
                # Translate all sections in lesson
                section_count = len(lesson.sections)
                for section_idx, section in enumerate(lesson.sections, 1):
                    try:
                        print(f"  Section {section_idx}/{section_count}: {section.title}")
                        self.translate_section(section, target_language, session)
                        stats['sections'] += 1
                        
                        # Translate all learning objects in section
                        for lo in section.learning_objects:
                            try:
                                self.translate_learning_object(lo, target_language, session)
                                stats['learning_objects'] += 1
                            except Exception as e:
                                stats['errors'].append(f"Error translating learning object {lo.id}: {str(e)}")
                    except Exception as e:
                        stats['errors'].append(f"Error translating section {section.id}: {str(e)}")
            
            print(f"\n[COURSE TRANSLATION] Translating questions...")
            # Translate all questions (get all questions, as they're not directly tied to course)
            all_questions = session.query(Question).all()
            print(f"[COURSE TRANSLATION] Found {len(all_questions)} questions")
            for question in all_questions:
                try:
                    self.translate_question(question, target_language, session)
                    stats['questions'] += 1
                except Exception as e:
                    stats['errors'].append(f"Error translating question {question.id}: {str(e)}")
            
            print(f"\n[COURSE TRANSLATION] Translating ontology relationships...")
            # Translate ontology relationships
            all_relationships = session.query(ConceptRelationship).all()
            print(f"[COURSE TRANSLATION] Found {len(all_relationships)} relationships")
            for rel in all_relationships:
                try:
                    self.translate_ontology_relationship(rel, target_language, session)
                    stats['ontologies'] += 1
                except Exception as e:
                    stats['errors'].append(f"Error translating ontology {rel.id}: {str(e)}")
            
            session.commit()
            print(f"\n[COURSE TRANSLATION] ✓ Batch translation complete!")
            print(f"[COURSE TRANSLATION] Summary: {stats['lessons']} lessons, {stats['sections']} sections, {stats['learning_objects']} LOs, {stats['questions']} questions, {stats['ontologies']} ontologies")
        except Exception as e:
            session.rollback()
            stats['errors'].append(f"Critical error during course translation: {str(e)}")
            logger.error(f"Critical error translating course: {str(e)}")
            print(f"[COURSE TRANSLATION] ❌ Critical error: {str(e)}")
        finally:
            session.close()
        
        return stats

    def get_supported_languages(self) -> Dict[str, str]:
        """Get dictionary of supported languages"""
        return self.supported_languages.copy()


# Global instance
_translation_service = None


def get_translation_service() -> TranslationService:
    """Get or create the translation service instance"""
    global _translation_service
    if _translation_service is None:
        _translation_service = TranslationService()
    return _translation_service
