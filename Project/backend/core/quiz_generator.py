"""
Quiz Generator - Local Ollama Model Version
Generates SOLO taxonomy-based quiz questions using local AI (no API keys needed)

MAXIMUM QUALITY VERSION:
- Uses comprehensive SOLO taxonomy prompts with detailed level definitions
- Multiple validation passes for question uniqueness
- Rich distractor guidance to avoid obvious wrong answers
- No concern for API costs - running locally
"""

import json
import re
import requests
import hashlib
import random
from datetime import datetime
from typing import Dict, List, Any, Optional, Set, Callable

# Single source of truth for Ollama URL/model lives in backend/config.py
from config import OLLAMA_BASE_URL, OLLAMA_MODEL


class SoloQuizGeneratorLocal:
    """
    SOLO Taxonomy Quiz Generator using Local Ollama Model
    Generates educational quizzes without requiring API keys
    
    MAXIMUM QUALITY APPROACH:
    - Uses the same comprehensive prompts as the API version
    - Tracks generated questions to avoid repetition
    - Does multiple passes to ensure question diversity
    """
    
    def __init__(self):
        """Initialize the quiz generator with Ollama configuration"""
        self.ollama_base_url = OLLAMA_BASE_URL
        self.ollama_model = OLLAMA_MODEL
        self.provider = "ollama_local"
        
        # Class name is historical — actual call routing goes through
        # core.llm_provider.call_llm, which picks Ollama or Anthropic per
        # request. So we just announce readiness, not a fixed provider.
        print(f"[QuizGenerator] Ready (provider chosen per call via LLM provider abstraction)")
        
        # Test connection
        if not self._test_ollama_connection():
            print("[QuizGenerator-Local] WARNING: Could not connect to Ollama server!")
            print(f"[QuizGenerator-Local] Make sure Ollama is running on {self.ollama_base_url}")
        
        self.api_exhausted = False
        self._content_summary_cache = {}

        # Track generated questions to avoid duplicates.
        # _generated_question_hashes is keyed by hash(question_text) for exact matches.
        # _generated_answer_keys is keyed by (anchor_id, normalized_correct_answer)
        # which catches "different wording, same anchor + same answer".
        self._generated_question_hashes: Set[str] = set()
        self._generated_answer_keys: Set[str] = set()
    
    def _test_ollama_connection(self) -> bool:
        """Test if Ollama server is responding"""
        try:
            response = requests.get(f"{self.ollama_base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception as e:
            print(f"[QuizGenerator-Local] Connection test failed: {e}")
            return False
    
    def _get_question_hash(self, question_text: str) -> str:
        """Generate a hash for question deduplication"""
        # Normalize the question text
        normalized = question_text.lower().strip()
        # Remove punctuation for better matching
        normalized = re.sub(r'[^\w\s]', '', normalized)
        return hashlib.md5(normalized.encode()).hexdigest()
    
    @staticmethod
    def _answer_key(question: Dict[str, Any]) -> Optional[str]:
        """
        Build a deterministic key for a question based on its anchor (LO or
        section) and its normalized correct answer. Two questions with the
        same key are testing the same fact and are functional duplicates.
        """
        anchor = question.get('learning_object_id') or question.get('section_id')
        if anchor is None:
            return None
        correct = (question.get('correct_answer') or '').lower().strip()
        correct = re.sub(r'^[a-d]\)\s*', '', correct)
        correct = re.sub(r'[^\w\s]', '', correct).strip()
        if not correct:
            return None
        return f"{anchor}::{correct}"

    def _is_question_unique(self, question: Dict[str, Any]) -> bool:
        """
        A question is unique if its (anchor, correct_answer) key has not been
        seen, AND its question text hasn't been seen verbatim. Looser checks
        like word-overlap caused false positives on short MCQ questions, so we
        drop them.
        """
        text = question.get('question_text', '') or ''
        if not text:
            return False

        q_hash = self._get_question_hash(text)
        if q_hash in self._generated_question_hashes:
            print(f"[QuizGenerator-Local] Duplicate question detected (exact text match)")
            return False

        key = self._answer_key(question)
        if key and key in self._generated_answer_keys:
            print(f"[QuizGenerator-Local] Duplicate question detected (same anchor + correct answer): {key}")
            return False

        return True

    def _register_question(self, question: Dict[str, Any]) -> None:
        """Register a question as generated to avoid future duplicates."""
        text = question.get('question_text', '') or ''
        if text:
            self._generated_question_hashes.add(self._get_question_hash(text))
        key = self._answer_key(question)
        if key:
            self._generated_answer_keys.add(key)
    
    def _call_ollama(
        self,
        prompt: str,
        timeout: int = 300,
        json_mode: bool = True,
        use_cache: bool = True,
    ) -> Optional[str]:
        """Route the generator's LLM call through the provider abstraction.

        Despite the historical name `_call_ollama`, this now dispatches to
        whichever provider is active for the current request (Ollama or
        Anthropic). The function name is kept so existing call sites don't
        have to change.
        """
        from core.llm_provider import call_llm

        temperature = 0.7
        print(f"[Generator] Dispatching LLM call ({len(prompt)} chars prompt, json_mode={json_mode})...")
        result = call_llm(
            prompt, role="generator",
            temperature=temperature, json_mode=json_mode,
            use_cache=use_cache, timeout=timeout,
        )
        if result is None:
            print(f"[Generator] LLM call returned None (provider error or timeout)")
        else:
            print(f"[Generator] LLM returned {len(result)} chars")
        return result
    
    def generate_solo_questions(
        self,
        lessons_data: List[Dict[str, Any]],
        solo_levels: List[str],
        questions_per_level: int = 3,
        section_ids: List[int] = None,
        ontology_relationships: List[Dict[str, Any]] = None,
        progress_cb: Optional[Callable[..., None]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate questions based on SOLO taxonomy levels from parsed lessons.
        NOW WITH ONTOLOGY SUPPORT: Uses domain knowledge relationships to enhance questions!
        
        Args:
            lessons_data: List of lesson dicts with sections and learning objects
            solo_levels: List of SOLO levels to generate questions for
            questions_per_level: Number of questions per SOLO level (max 2 for memory)
            section_ids: Optional list of specific section IDs to use
            ontology_relationships: Optional domain ontology relationships for enhanced context
            
        Returns:
            List of question dicts ready for database storage
        """
        print(f"\n[SOLO-Local] Starting MEMORY-OPTIMIZED question generation")
        print(f"[SOLO-Local] Lessons: {len(lessons_data)}, Levels: {solo_levels}")
        
        # Store ontology relationships for use in all question generators
        self.ontology_relationships = ontology_relationships or []
        if self.ontology_relationships:
            print(f"[SOLO-Local] ✓ Using {len(self.ontology_relationships)} ontology relationships to enhance questions")

        # Detect lesson language once and apply to every generated question.
        from core.lang_detect import detect_language, language_name
        primary = lessons_data[0] if lessons_data else None
        sample_text = ""
        if primary:
            for section in primary.get('sections', []):
                if section.get('content'):
                    sample_text = section['content']
                    break
            if not sample_text:
                sample_text = primary.get('summary') or primary.get('title') or ""
        self.language = detect_language(sample_text)
        print(f"[SOLO-Local] Detected lesson language: {language_name(self.language)} ({self.language})")

        # Honor requested questions per level (no artificial cap - running locally)
        # The user can request whatever they want, we'll generate it
        print(f"[SOLO-Local] Questions per level: {questions_per_level}")
        
        # Reset question tracking for this generation session
        self._generated_question_hashes.clear()
        self._generated_answer_keys.clear()
        
        generated_questions = []
        primary_lesson = lessons_data[0] if lessons_data else None

        if not primary_lesson:
            raise ValueError("At least one lesson is required")

        # Skip content summary generation to save memory
        content_summary = ""

        total_target = questions_per_level * len(solo_levels)
        total_generated = 0

        def _emit(msg: str) -> None:
            if progress_cb:
                try:
                    progress_cb(message=msg, current=total_generated, total=total_target)
                except Exception:
                    pass

        _emit(f"Starting generation of {total_target} questions")

        for level in solo_levels:
            print(f"\n[SOLO-Local] Generating {questions_per_level} {level} questions...")
            _emit(f"Generating {level} questions (0/{questions_per_level})")

            level_questions = 0
            max_attempts = questions_per_level * 2  # Allow up to 2x attempts for uniqueness
            attempts = 0

            while level_questions < questions_per_level and attempts < max_attempts:
                attempts += 1
                
                try:
                    # Use different learning object for each attempt to encourage diversity
                    lo_offset = attempts - 1
                    
                    if level == 'unistructural':
                        question = self._generate_unistructural_question(
                            primary_lesson, section_ids, content_summary, lo_offset
                        )
                    elif level == 'multistructural':
                        question = self._generate_multistructural_question(
                            primary_lesson, section_ids, content_summary, lo_offset
                        )
                    elif level == 'relational':
                        question = self._generate_relational_question(
                            primary_lesson, section_ids, content_summary, lo_offset
                        )
                    elif level == 'extended_abstract':
                        # For extended abstract, use both lessons if available
                        secondary_lesson = lessons_data[1] if len(lessons_data) > 1 else None
                        question = self._generate_extended_abstract_question(
                            primary_lesson, content_summary, secondary_lesson, lo_offset
                        )
                    else:
                        question = None
                    
                    if question and self._is_question_unique(question):
                        question['solo_level'] = level
                        generated_questions.append(question)
                        self._register_question(question)
                        level_questions += 1
                        total_generated += 1
                        print(f"[SOLO-Local] ✓ Generated {level} question {level_questions}/{questions_per_level}")
                        _emit(f"Generated {level} question {level_questions}/{questions_per_level}")
                    elif question:
                        print(f"[SOLO-Local] ✗ Question rejected (not unique), retrying...")
                    
                except Exception as e:
                    print(f"[SOLO-Local] Error generating {level} question: {e}")
            
            if level_questions < questions_per_level:
                print(f"[SOLO-Local] Generated {level_questions}/{questions_per_level} {level} questions")
        
        print(f"\n[SOLO-Local] Total questions generated: {len(generated_questions)}")
        return generated_questions
    
    def _build_ontology_context(self, learning_objects: List[Dict] = None) -> str:
        """
        Build ontology context from domain relationships.
        Shows prerequisites, hierarchies, and semantic connections.
        """
        if not self.ontology_relationships:
            return ""
        
        # Filter relationships relevant to the learning objects if provided
        relevant_rels = self.ontology_relationships
        if learning_objects:
            lo_titles = {lo.get('title', '') for lo in learning_objects}
            relevant_rels = [
                r for r in self.ontology_relationships
                if r.get('source_title', '') in lo_titles or r.get('target_title', '') in lo_titles
            ]
        
        if not relevant_rels:
            return ""
        
        # Build a formatted ontology context
        ontology_lines = ["DOMAIN ONTOLOGY (concept relationships):"]
        
        # Group by relationship type
        rels_by_type = {}
        for rel in relevant_rels[:20]:  # Limit to top 20 to keep it concise
            rel_type = rel.get('relationship_type', 'related_to')
            if rel_type not in rels_by_type:
                rels_by_type[rel_type] = []
            rels_by_type[rel_type].append(rel)
        
        # Format relationships
        for rel_type, rels in sorted(rels_by_type.items()):
            ontology_lines.append(f"\n{rel_type.upper().replace('_', ' ')}:")
            for rel in rels[:5]:  # Max 5 per type
                source = rel.get('source_title', '')
                target = rel.get('target_title', '')
                desc = rel.get('description', '')
                ontology_lines.append(f"  • {source} → {target}")
                if desc:
                    ontology_lines.append(f"    ({desc[:80]})")
        
        return "\n".join(ontology_lines)
    
    def _generate_content_summary(self, lesson: Dict[str, Any]) -> str:
        """Generate a summary of the lesson content for higher-order questions"""
        lesson_title = lesson.get('title', 'Lesson')
        
        # Collect all content
        all_content = []
        for section in lesson.get('sections', []):
            all_content.append(f"## {section.get('title', '')}")
            for lo in section.get('learning_objects', []):
                all_content.append(f"- {lo.get('title', '')}: {lo.get('description', '')[:200]}")
        
        content_text = "\n".join(all_content)[:3000]
        
        prompt = f"""Summarize the key concepts, themes, and relationships in this educational content.

LESSON: {lesson_title}

CONTENT:
{content_text}

Write a 3-4 paragraph summary focusing on:
1. Main concepts and how they relate
2. Key principles that can be applied
3. Important distinctions between concepts

Be concise but comprehensive."""
        
        print("[SOLO-Local] Generating content summary for higher-order questions...")
        summary = self._call_ollama(prompt, timeout=120, json_mode=False)
        return summary or ""
    
    def _generate_unistructural_question(
        self,
        lesson: Dict[str, Any],
        section_ids: List[int] = None,
        content_summary: str = "",
        lo_offset: int = 0
    ) -> Dict[str, Any]:
        """
        Generate UNISTRUCTURAL question from LEARNING OBJECTS
        
        Uses comprehensive SOLO taxonomy definitions and detailed distractor guidance.
        """
        
        lesson_title = lesson.get('title', 'Lesson')
        sections = lesson.get('sections', [])
        
        if section_ids:
            sections = [s for s in sections if s.get('id') in section_ids]
        
        # Collect all learning objects with their parent section content for grounding
        learning_objects = []
        for section in sections:
            section_content = section.get('content', '') or ''
            for lo in section.get('learning_objects', []):
                learning_objects.append({
                    'id': lo.get('id'),
                    'section_id': section.get('id'),
                    'title': lo.get('title', ''),
                    'description': lo.get('description', ''),
                    'type': lo.get('object_type', lo.get('type', 'concept')),
                    'keywords': lo.get('keywords', []) or [],
                    'key_points': lo.get('key_points', []) or [],
                    'section_content': section_content,
                })

        if not learning_objects:
            return None

        # Pick a learning object based on offset for diversity
        lo_index = lo_offset % len(learning_objects)
        lo = learning_objects[lo_index]

        from core.prompt_lib import build_question_prompt

        # LO metadata for the CONTENT block.
        keywords = ", ".join(lo.get("keywords", []))
        key_points = "; ".join(lo.get("key_points", [])[:3])
        content_block = (
            f"LEARNING OBJECT TITLE: {lo['title']}\n"
            f"TYPE: {lo['type']}\n"
            f"DESCRIPTION: {lo['description']}\n"
            f"KEYWORDS: {keywords}\n"
            f"KEY POINTS: {key_points}"
        )
        source_excerpt = (lo.get("section_content") or "")[:1500]

        prompt = build_question_prompt(
            level="unistructural",
            lesson_title=lesson_title,
            content_block=content_block,
            source_text=source_excerpt,
            language=getattr(self, "language", "en"),
        )
        
        response = self._call_ollama(prompt, timeout=300)
        if not response:
            return None
        
        question_data = self._parse_question_response(response)
        if question_data:
            # Shuffle options to randomize correct answer position
            question_data = self._shuffle_options(question_data)
            return {
                'question_text': question_data.get('question', ''),
                'question_type': 'multiple_choice',
                'options': question_data.get('options', []),
                'correct_answer': question_data.get('correct_answer', ''),
                'correct_option_index': self._find_correct_index(
                    question_data.get('options', []),
                    question_data.get('correct_answer', '')
                ),
                'explanation': question_data.get('explanation', ''),
                'source_line': question_data.get('source_line', ''),
                'bloom_level': 'remember',
                'learning_object_id': lo.get('id'),
                'section_id': lo.get('section_id'),
            }
        return None

    def _generate_multistructural_question(
        self,
        lesson: Dict[str, Any],
        section_ids: List[int] = None,
        content_summary: str = "",
        lo_offset: int = 0
    ) -> Dict[str, Any]:
        """
        Generate MULTISTRUCTURAL question from SECTIONS
        
        Uses comprehensive SOLO taxonomy definitions and detailed distractor guidance.
        """
        
        lesson_title = lesson.get('title', 'Lesson')
        sections = lesson.get('sections', [])
        
        if section_ids:
            sections = [s for s in sections if s.get('id') in section_ids]
        
        if not sections:
            return None
        
        # Pick a section based on offset for diversity
        section_index = lo_offset % len(sections)
        section = sections[section_index]
        
        section_title = section.get('title', '')
        
        # Build comprehensive content from all learning objects in section
        los_content = []
        for lo in section.get('learning_objects', [])[:6]:
            los_content.append(f"- {lo.get('title', '')}: {lo.get('description', '')[:150]}")
            if lo.get('key_points'):
                for point in lo.get('key_points', [])[:2]:
                    los_content.append(f"  • {point}")

        from core.prompt_lib import build_question_prompt

        content_block = (
            f"SECTION TITLE: {section_title}\n"
            "LEARNING OBJECTS IN THIS SECTION:\n" + "\n".join(los_content)
        )
        source_excerpt = (section.get("content") or "")[:2000]
        ontology_context = self._build_ontology_context(section.get("learning_objects", []))
        ontology_anchor_block = f"\n\n{ontology_context}" if ontology_context else ""

        prompt = build_question_prompt(
            level="multistructural",
            lesson_title=lesson_title,
            content_block=content_block,
            source_text=source_excerpt,
            language=getattr(self, "language", "en"),
            ontology_anchor_block=ontology_anchor_block,
        )
        
        response = self._call_ollama(prompt, timeout=300)
        if not response:
            return None
        
        question_data = self._parse_question_response(response)
        if question_data:
            # Shuffle options to randomize correct answer position
            question_data = self._shuffle_options(question_data)
            return {
                'question_text': question_data.get('question', ''),
                'question_type': 'multiple_choice',
                'options': question_data.get('options', []),
                'correct_answer': question_data.get('correct_answer', ''),
                'correct_option_index': self._find_correct_index(
                    question_data.get('options', []),
                    question_data.get('correct_answer', '')
                ),
                'explanation': question_data.get('explanation', ''),
                'source_line': question_data.get('source_line', ''),
                'bloom_level': 'understand',
                'section_id': section.get('id'),
            }
        return None

    def _pick_relationship(self, sections: List[Dict[str, Any]], offset: int) -> Optional[Dict[str, Any]]:
        """Pick a single ConceptRelationship that involves the given sections' LOs."""
        if not self.ontology_relationships:
            return None
        lo_titles = {
            lo.get('title')
            for section in sections
            for lo in section.get('learning_objects', [])
        }
        candidates = [
            r for r in self.ontology_relationships
            if r.get('source_title') in lo_titles or r.get('target_title') in lo_titles
        ]
        if not candidates:
            candidates = self.ontology_relationships
        return candidates[offset % len(candidates)] if candidates else None

    def _find_lo_by_title(self, lessons: List[Dict[str, Any]], title: str) -> Optional[Dict[str, Any]]:
        """Locate an LO (and remember its section) by its title across the given lessons."""
        for lesson in lessons:
            for section in lesson.get('sections', []):
                for lo in section.get('learning_objects', []):
                    if lo.get('title') == title:
                        return {'lo': lo, 'section': section, 'lesson': lesson}
        return None

    def _generate_relational_question(
        self,
        lesson: Dict[str, Any],
        section_ids: List[int] = None,
        content_summary: str = "",
        lo_offset: int = 0
    ) -> Dict[str, Any]:
        """
        Generate RELATIONAL question from SECTIONS + LEARNING OBJECTS
        
        Uses comprehensive SOLO taxonomy definitions and detailed distractor guidance.
        Requires understanding of relationships between concepts.
        """
        
        lesson_title = lesson.get('title', 'Lesson')
        sections = lesson.get('sections', [])
        
        if section_ids:
            sections = [s for s in sections if s.get('id') in section_ids]
        
        if not sections:
            return None
        
        # Pick ONE specific relationship to ground this question on.
        rel = self._pick_relationship(sections, lo_offset)
        rel_block = ""
        anchor_section_id = sections[0].get('id') if sections else None
        anchor_lo_id = None
        rel_tags = None

        if rel:
            src_title = rel.get('source_title', '')
            tgt_title = rel.get('target_title', '')
            rel_type = rel.get('relationship_type', 'related_to')
            rel_desc = rel.get('description', '') or ''
            src_info = self._find_lo_by_title([lesson], src_title)
            tgt_info = self._find_lo_by_title([lesson], tgt_title)
            anchor_lo_id = (src_info or {}).get('lo', {}).get('id')
            anchor_section_id = (src_info or {}).get('section', {}).get('id') or anchor_section_id

            def _lo_summary(info: Optional[Dict[str, Any]], fallback_title: str) -> str:
                if not info:
                    return fallback_title
                lo = info['lo']
                src_excerpt = (info.get('section', {}).get('content') or '')[:600]
                lines = [
                    f"TITLE: {lo.get('title', '')}",
                    f"DESCRIPTION: {lo.get('description', '')[:300]}",
                ]
                if lo.get('key_points'):
                    lines.append("KEY POINTS: " + "; ".join(lo['key_points'][:3]))
                if src_excerpt:
                    lines.append(f"SOURCE EXCERPT:\n{src_excerpt}")
                return "\n".join(lines)

            rel_block = f"""

ONTOLOGY ANCHOR — the question MUST test THIS exact relationship:
  {src_title} --[{rel_type}]--> {tgt_title}
  Relationship description: {rel_desc}

SOURCE CONCEPT:
{_lo_summary(src_info, src_title)}

TARGET CONCEPT:
{_lo_summary(tgt_info, tgt_title)}
"""
            rel_tags = {
                'ontology_anchor': {
                    'source': src_title,
                    'target': tgt_title,
                    'type': rel_type,
                    'description': rel_desc[:200],
                }
            }

        from core.prompt_lib import build_question_prompt

        # Build a compact content block: titles + descriptions across involved sections.
        content_lines: List[str] = []
        source_excerpts: List[str] = []
        for section in sections[:4]:
            content_lines.append(f"### {section.get('title', '')}")
            for lo in section.get("learning_objects", [])[:5]:
                content_lines.append(f"- {lo.get('title', '')}: {lo.get('description', '')[:200]}")
                for point in lo.get("key_points", [])[:2]:
                    content_lines.append(f"  • {point}")
            if section.get("content") and not rel_block:
                source_excerpts.append(f"### {section.get('title','')}\n{section.get('content','')[:800]}")
        content_block = "\n".join(content_lines)[:2500]
        source_text = "\n\n".join(source_excerpts)[:2500] if source_excerpts else ""

        extra_task = (
            "Your question MUST test the specific ontology anchor below — the named "
            "relationship between the two named concepts. Do not invent a different relationship."
            if rel_block else
            "Choose a real cause/effect, structural, or dependency relationship between concepts in the CONTENT."
        )

        prompt = build_question_prompt(
            level="relational",
            lesson_title=lesson_title,
            content_block=content_block,
            source_text=source_text,
            language=getattr(self, "language", "en"),
            ontology_anchor_block=rel_block,
            extra_task_line=extra_task,
        )
        
        response = self._call_ollama(prompt, timeout=300)
        if not response:
            return None
        
        question_data = self._parse_question_response(response)
        if question_data:
            # Shuffle options to randomize correct answer position
            question_data = self._shuffle_options(question_data)
            return {
                'question_text': question_data.get('question', ''),
                'question_type': 'multiple_choice',
                'options': question_data.get('options', []),
                'correct_answer': question_data.get('correct_answer', ''),
                'correct_option_index': self._find_correct_index(
                    question_data.get('options', []),
                    question_data.get('correct_answer', '')
                ),
                'explanation': question_data.get('explanation', ''),
                'source_line': question_data.get('source_line', ''),
                'bloom_level': 'analyze',
                'section_id': anchor_section_id,
                'learning_object_id': anchor_lo_id,
                'tags': rel_tags,
            }
        return None

    def _generate_extended_abstract_question(
        self,
        lesson: Dict[str, Any],
        content_summary: str = "",
        secondary_lesson: Dict[str, Any] = None,
        lo_offset: int = 0
    ) -> Dict[str, Any]:
        """
        Generate EXTENDED ABSTRACT question requiring synthesis and cross-lesson application
        
        Uses comprehensive SOLO taxonomy definitions and detailed distractor guidance.
        For maximum effectiveness, combines concepts from TWO lessons to test transfer of knowledge.
        Requires applying learned concepts to NEW situations that synthesize both topics.
        """
        
        lesson_title = lesson.get('title', 'Lesson')
        
        # Get key concepts + source excerpts from primary lesson
        concepts_primary = []
        primary_excerpts = []
        for section in lesson.get('sections', []):
            for lo in section.get('learning_objects', [])[:4]:
                concepts_primary.append(f"- {lo.get('title', '')}: {lo.get('description', '')[:150]}")
            if section.get('content'):
                primary_excerpts.append(section.get('content', '')[:600])

        concepts_text = "\n".join(concepts_primary[:15])
        primary_source = "\n\n".join(primary_excerpts)[:2000]

        # Get concepts from secondary lesson if provided
        concepts_secondary_text = ""
        secondary_title = ""
        secondary_source = ""
        if secondary_lesson:
            secondary_title = secondary_lesson.get('title', 'Lesson 2')
            concepts_secondary = []
            secondary_excerpts = []
            for section in secondary_lesson.get('sections', []):
                for lo in section.get('learning_objects', [])[:4]:
                    concepts_secondary.append(f"- {lo.get('title', '')}: {lo.get('description', '')[:150]}")
                if section.get('content'):
                    secondary_excerpts.append(section.get('content', '')[:600])
            secondary_concepts = "\n".join(concepts_secondary[:15])
            concepts_secondary_text = f"\n\nSECONDARY TOPIC ({secondary_title}) CONCEPTS:\n{secondary_concepts}"
            secondary_source = "\n\n".join(secondary_excerpts)[:2000]
        
        # Pick a relationship to anchor the synthesis on. Prefer one that spans both lessons.
        all_lessons = [lesson] + ([secondary_lesson] if secondary_lesson else [])
        primary_titles = {
            lo.get('title')
            for s in lesson.get('sections', [])
            for lo in s.get('learning_objects', [])
        }
        secondary_titles = {
            lo.get('title')
            for s in (secondary_lesson.get('sections', []) if secondary_lesson else [])
            for lo in s.get('learning_objects', [])
        }
        cross_rels = [
            r for r in (self.ontology_relationships or [])
            if (r.get('source_title') in primary_titles and r.get('target_title') in secondary_titles)
            or (r.get('source_title') in secondary_titles and r.get('target_title') in primary_titles)
        ]
        within_rels = [
            r for r in (self.ontology_relationships or [])
            if r.get('source_title') in primary_titles and r.get('target_title') in primary_titles
        ]
        rel_pool = cross_rels or within_rels
        ea_rel = rel_pool[lo_offset % len(rel_pool)] if rel_pool else None
        ea_rel_tags = None
        ea_anchor_section_id = None
        ea_anchor_lo_id = None
        ea_rel_block = ""
        if ea_rel:
            src_info = self._find_lo_by_title(all_lessons, ea_rel.get('source_title', ''))
            tgt_info = self._find_lo_by_title(all_lessons, ea_rel.get('target_title', ''))
            ea_anchor_lo_id = (src_info or {}).get('lo', {}).get('id')
            ea_anchor_section_id = (src_info or {}).get('section', {}).get('id')
            ea_rel_block = (
                "\n\nONTOLOGY ANCHOR — the synthesis MUST be built around this relationship:\n"
                f"  {ea_rel.get('source_title','')} --[{ea_rel.get('relationship_type','related_to')}]--> {ea_rel.get('target_title','')}\n"
                f"  Description: {ea_rel.get('description','') or '(none)'}\n"
            )
            ea_rel_tags = {
                'ontology_anchor': {
                    'source': ea_rel.get('source_title', ''),
                    'target': ea_rel.get('target_title', ''),
                    'type': ea_rel.get('relationship_type', 'related_to'),
                    'description': (ea_rel.get('description', '') or '')[:200],
                    'spans_lessons': bool(cross_rels),
                }
            }

        from core.prompt_lib import (
            build_extended_abstract_pass1_prompt,
            build_extended_abstract_pass2_prompt,
            DISTRACTOR_STRATEGIES,
        )

        language = getattr(self, "language", "en")

        # --- PASS 1: produce question + correct answer + source_line ---
        pass1_prompt = build_extended_abstract_pass1_prompt(
            lesson_title=lesson_title,
            secondary_title=secondary_title or None,
            primary_content=concepts_text,
            secondary_content=concepts_secondary_text.lstrip(),
            primary_source=primary_source,
            secondary_source=secondary_source,
            ontology_anchor_block=ea_rel_block,
            language=language,
        )
        pass1_response = self._call_ollama(pass1_prompt, timeout=300)
        if not pass1_response:
            return None
        pass1_data = self._parse_question_response(pass1_response)
        if not pass1_data or not pass1_data.get("question") or not pass1_data.get("correct_answer"):
            return None

        question_text = pass1_data["question"]
        correct_answer = pass1_data["correct_answer"]
        explanation = pass1_data.get("explanation", "")
        source_line = pass1_data.get("source_line", "")

        # --- PASS 2: predictive prompting for three typed distractors ---
        combined_source = "\n\n".join(filter(None, [primary_source, secondary_source]))[:3000]
        pass2_prompt = build_extended_abstract_pass2_prompt(
            question=question_text,
            correct_answer=correct_answer,
            explanation=explanation,
            source_text=combined_source,
            language=language,
        )
        pass2_response = self._call_ollama(pass2_prompt, timeout=300)
        distractors: List[str] = []
        distractor_strategies: List[str] = []
        if pass2_response:
            pass2_data = self._parse_question_response(pass2_response)
            if isinstance(pass2_data, dict) and isinstance(pass2_data.get("distractors"), list):
                for d in pass2_data["distractors"][:3]:
                    if isinstance(d, dict) and d.get("text"):
                        distractors.append(d["text"])
                        distractor_strategies.append(d.get("strategy", ""))

        # If pass 2 failed to give three usable distractors, abort this attempt
        # rather than ship a degenerate question — the outer retry loop will try
        # again with the next ontology anchor.
        if len(distractors) < 3:
            print(f"[SOLO-Local] Extended-abstract pass 2 returned {len(distractors)} distractors, skipping")
            return None

        # Strip any leading letter from the correct answer (the model sometimes
        # echoes "A) ..." back), then assemble the 4 options and shuffle.
        correct_text = re.sub(r"^[A-Da-d]\)\s*", "", correct_answer).strip()
        option_texts = [correct_text] + distractors[:3]
        random.shuffle(option_texts)
        letters = ["A", "B", "C", "D"]
        new_options = [f"{letters[i]}) {t}" for i, t in enumerate(option_texts)]
        new_correct_index = option_texts.index(correct_text)
        new_correct_answer = new_options[new_correct_index]

        # Merge in the typed-distractor metadata so we can later evaluate which
        # distractor strategies the model actually used.
        final_tags = dict(ea_rel_tags or {})
        final_tags["distractor_strategies"] = distractor_strategies

        return {
            "question_text": question_text,
            "question_type": "multiple_choice",
            "options": new_options,
            "correct_answer": new_correct_answer,
            "correct_option_index": new_correct_index,
            "explanation": explanation,
            "source_line": source_line,
            "bloom_level": "create",
            "section_id": ea_anchor_section_id,
            "learning_object_id": ea_anchor_lo_id,
            "tags": final_tags,
        }

    def _parse_question_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse API response to extract question data"""
        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                return None
        except json.JSONDecodeError:
            return None
    
    def _find_correct_index(self, options: List[str], correct_answer: str) -> int:
        """Find the index of the correct answer in options list"""
        if not options or not correct_answer:
            return 0
        
        for i, opt in enumerate(options):
            if opt == correct_answer:
                return i
        
        # Try matching by letter prefix
        correct_letter = correct_answer[0].upper() if correct_answer else 'A'
        for i, opt in enumerate(options):
            if opt.startswith(correct_letter):
                return i
        
        return 0

    def _shuffle_options(self, question_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Shuffle the options to randomize correct answer position.
        This prevents all correct answers from being option A.
        
        Args:
            question_data: Dict with 'options' and 'correct_answer' keys
            
        Returns:
            Updated question_data with shuffled options and updated correct_answer
        """
        options = question_data.get('options', [])
        correct_answer = question_data.get('correct_answer', '')
        
        if not options or len(options) < 2:
            return question_data
        
        # Extract the text content from each option (remove A), B), etc. prefix)
        option_texts = []
        correct_text = None
        
        for opt in options:
            # Remove letter prefix like "A) ", "B) ", etc.
            text = re.sub(r'^[A-Da-d]\)\s*', '', opt).strip()
            option_texts.append(text)
        
        # Find the correct answer text
        correct_text = re.sub(r'^[A-Da-d]\)\s*', '', correct_answer).strip()
        
        # Shuffle the options
        random.shuffle(option_texts)
        
        # Find new position of correct answer
        new_correct_index = -1
        for i, text in enumerate(option_texts):
            if text == correct_text:
                new_correct_index = i
                break
        
        # If we couldn't find the correct answer (shouldn't happen), default to 0
        if new_correct_index == -1:
            new_correct_index = 0
        
        # Rebuild options with new letter prefixes
        letters = ['A', 'B', 'C', 'D']
        new_options = [f"{letters[i]}) {text}" for i, text in enumerate(option_texts)]
        new_correct_answer = new_options[new_correct_index]
        
        # Update the question data
        question_data['options'] = new_options
        question_data['correct_answer'] = new_correct_answer
        
        return question_data


# Create global instance
quiz_generator_local = SoloQuizGeneratorLocal()
