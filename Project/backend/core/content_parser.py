"""
Content Parser Module - Local Ollama Version
Extracts sections and learning objects from PDF lesson content using local LLM (Ollama)

MAXIMUM QUALITY VERSION:
- Multi-pass extraction for comprehensive section coverage
- No concern for API costs - running locally
- Splits content into chunks for thorough analysis
- Extracts MORE sections and learning objects
"""

import json
import re
import time
from typing import Dict, List, Any, Optional
from PyPDF2 import PdfReader
import requests

# Single source of truth for Ollama URL/model lives in backend/config.py
from config import OLLAMA_BASE_URL, OLLAMA_MODEL


class ContentParser:
    """
    Parses PDF lessons to extract structured content using local Ollama models:
    - Sections (major topic divisions)
    - Learning Objects (specific concepts, definitions, procedures)
    
    MAXIMUM QUALITY APPROACH:
    - Splits content into smaller chunks
    - Does multiple passes over content
    - Extracts MORE sections (6-15 instead of 2-5)
    - No concern for time - quality is the priority
    """
    
    def __init__(self):
        """Initialize the content parser with Ollama configuration"""
        self.ollama_base_url = OLLAMA_BASE_URL
        self.ollama_model = OLLAMA_MODEL
        self.provider = "ollama"
        
        print(f"[ContentParser] Initialized with Ollama (14B model)")
        print(f"[ContentParser] Mode: MAXIMUM QUALITY - multi-pass extraction")
        
        # Test connection
        if not self._test_ollama_connection():
            print("[ContentParser] WARNING: Could not connect to Ollama server!")
            print(f"[ContentParser] Make sure Ollama is running on {self.ollama_base_url}")
    
    def _test_ollama_connection(self) -> bool:
        """Test if Ollama server is responding"""
        try:
            response = requests.get(f"{self.ollama_base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception as e:
            print(f"[ContentParser] Connection test failed: {e}")
            return False
    
    def _call_ollama(self, prompt: str, timeout: int = 300, use_cache: bool = True) -> Optional[str]:
        """
        Call Ollama with SQLite-backed response caching.

        Parsing is deterministic-friendly (same PDF, same prompt -> same
        output is fine), so caching is on by default. Pass use_cache=False
        to force a fresh extraction.
        """
        from core import llm_cache

        temperature = 0.7
        # ContentParser never uses Ollama's JSON-format mode (it sometimes
        # wants arrays, sometimes objects, sometimes prose).
        json_mode = False
        if use_cache:
            cached = llm_cache.get(self.ollama_model, prompt, temperature, json_mode)
            if cached is not None:
                print(f"[ContentParser] Cache HIT ({len(cached)} chars)")
                return cached

        try:
            url = f"{self.ollama_base_url}/api/generate"
            payload = {
                "model": self.ollama_model,
                "prompt": prompt,
                "stream": False,
                "temperature": temperature,
            }

            print(f"[ContentParser] Calling Ollama ({len(prompt)} chars prompt)...")
            response = requests.post(url, json=payload, timeout=timeout)

            if response.status_code == 200:
                data = response.json()
                result = data.get("response", "")
                print(f"[ContentParser] Ollama returned {len(result)} chars")
                if len(result) < 50:
                    print(f"[ContentParser] WARNING: Very short response: {result}")
                if result and use_cache:
                    llm_cache.put(self.ollama_model, prompt, temperature, json_mode, result)
                return result
            else:
                print(f"[ContentParser] Ollama error: {response.status_code}")
                print(f"[ContentParser] Response: {response.text[:200]}")
                return None
                
        except requests.Timeout:
            print(f"[ContentParser] Ollama request timed out after {timeout}s")
            return None
        except Exception as e:
            print(f"[ContentParser] Ollama error: {e}")
            return None
    
    def _extract_pages(self, pdf_reader) -> Dict[str, Any]:
        """Build full_text + per-page offset/char-count metadata from a PdfReader."""
        text_parts = []
        pages_meta = []
        offset = 0

        for page_num, page in enumerate(pdf_reader.pages, start=1):
            page_text = page.extract_text() or ""
            marker = f"\n--- Page {page_num} ---\n"
            text_parts.append(marker)
            offset += len(marker)
            page_start = offset
            text_parts.append(page_text)
            offset += len(page_text)
            pages_meta.append({
                "page": page_num,
                "char_count": len(page_text.strip()),
                "start_offset": page_start,
                "end_offset": offset,
            })

        full_text = "".join(text_parts)
        return {
            "success": True,
            "content": full_text,
            "full_text": full_text,
            "pages": len(pdf_reader.pages),
            "pages_meta": pages_meta,
        }

    def extract_pdf_text(self, filepath: str) -> Dict[str, Any]:
        """Extract text + per-page metadata from a PDF file path."""
        try:
            with open(filepath, 'rb') as file:
                result = self._extract_pages(PdfReader(file))
            result["filepath"] = filepath
            return result
        except Exception as e:
            print(f"[ContentParser] PDF extraction error: {e}")
            return {"success": False, "error": str(e), "filepath": filepath}

    def extract_pdf_text_from_stream(self, stream) -> Dict[str, Any]:
        """Extract text + per-page metadata from a PDF stream."""
        try:
            result = self._extract_pages(PdfReader(stream))
            result["filepath"] = None
            return result
        except Exception as e:
            print(f"[ContentParser] PDF extraction error: {e}")
            return {"success": False, "error": str(e), "filepath": None}
    
    @staticmethod
    def _offset_to_page(offset: int, pages_meta: List[Dict[str, Any]]) -> Optional[int]:
        """Map a character offset in raw_content to its page number."""
        if not pages_meta:
            return None
        for meta in pages_meta:
            if meta["start_offset"] <= offset < meta["end_offset"]:
                return meta["page"]
        return pages_meta[-1]["page"]

    def _locate_section_in_content(
        self,
        content: str,
        section: Dict[str, Any],
        pages_meta: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """
        Find where a section lives in the raw content by searching for its
        title + key topics. Returns start_page, end_page, and a content snippet.
        """
        title = section.get("title", "") or ""
        topics = section.get("key_topics", []) or []
        search_terms = [t for t in [title, *topics] if t and len(t) >= 3]

        offsets: List[int] = []
        content_lower = content.lower()
        for term in search_terms:
            term_lower = term.lower()
            start = 0
            while True:
                pos = content_lower.find(term_lower, start)
                if pos == -1:
                    break
                offsets.append(pos)
                start = pos + len(term_lower)
                # Avoid pathological cases for very common words.
                if len(offsets) > 200:
                    break

        if not offsets:
            return {"start_page": None, "end_page": None, "content_snippet": ""}

        start_offset = min(offsets)
        end_offset = max(offsets)
        snippet_end = min(end_offset + 600, len(content))
        snippet = content[start_offset:snippet_end][:3000]

        return {
            "start_page": self._offset_to_page(start_offset, pages_meta) if pages_meta else None,
            "end_page": self._offset_to_page(end_offset, pages_meta) if pages_meta else None,
            "content_snippet": snippet,
        }

    def _assign_lo_pages(
        self,
        learning_objects: List[Dict[str, Any]],
        content: str,
        pages_meta: Optional[List[Dict[str, Any]]],
        section: Dict[str, Any],
    ) -> None:
        """Annotate each learning object with the pages where its title/keywords appear."""
        if not pages_meta or not learning_objects:
            for lo in learning_objects:
                lo['source_pages'] = []
            return

        content_lower = content.lower()
        for lo in learning_objects:
            terms = [lo.get('title', '')] + list(lo.get('keywords') or [])
            pages_seen = set()
            for term in terms:
                if not term or len(term) < 3:
                    continue
                term_lower = term.lower()
                start = 0
                hits = 0
                while hits < 50:
                    pos = content_lower.find(term_lower, start)
                    if pos == -1:
                        break
                    page = self._offset_to_page(pos, pages_meta)
                    if page:
                        pages_seen.add(page)
                    start = pos + len(term_lower)
                    hits += 1

            # Constrain to the section's page range when available.
            sp, ep = section.get('start_page'), section.get('end_page')
            if sp and ep:
                pages_seen = {p for p in pages_seen if sp <= p <= ep}
                if not pages_seen:
                    pages_seen = {sp}
            lo['source_pages'] = sorted(pages_seen)

    def parse_lesson_structure(
        self,
        content: str,
        lesson_title: str,
        pages_meta: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Parse lesson content into sections with learning objects.

        OPTIMIZED FOR MEMORY: Single-pass analysis to reduce RAM usage.

        Args:
            content: Full lesson content
            lesson_title: Title of the lesson
            pages_meta: Optional per-page offset metadata (from PDF extraction).
                If provided, each section is annotated with start_page/end_page
                and a content snippet from the actual source text.

        Returns:
            List of section dictionaries with learning objects
        """
        print(f"\n[ContentParser] === MEMORY-OPTIMIZED PARSING ===")
        print(f"[ContentParser] Content length: {len(content)} characters")
        
        # Split content into smaller chunks (reduced from 3000 to 2000 chars per chunk)
        chunks = self._split_content_into_chunks(content, chunk_size=2000, overlap=200)
        print(f"[ContentParser] Split into {len(chunks)} chunks (smaller chunks for memory efficiency)")
        
        all_sections = []
        
        # Single pass: Analyze each chunk for sections
        for i, chunk in enumerate(chunks):
            print(f"\n[ContentParser] --- Analyzing chunk {i+1}/{len(chunks)} ---")
            chunk_sections = self._extract_sections_from_chunk(chunk, lesson_title, i+1, len(chunks))
            if chunk_sections:
                all_sections.extend(chunk_sections)
                print(f"[ContentParser] Chunk {i+1}: Found {len(chunk_sections)} sections")
        
        # Merge and deduplicate sections
        print(f"\n[ContentParser] Merging {len(all_sections)} sections...")
        merged_sections = self._merge_similar_sections(all_sections)
        print(f"[ContentParser] After merge: {len(merged_sections)} unique sections")
        
        # Limit sections to reasonable amount (allow natural number, max 15 to prevent excessive sections)
        if len(merged_sections) > 15:
            print(f"[ContentParser] Limiting to 15 sections (was {len(merged_sections)}) - too many redundant sections")
            merged_sections = merged_sections[:15]
        
        # If too few sections, extract from full content once
        if len(merged_sections) < 2:
            print(f"[ContentParser] Too few sections, extracting from full content...")
            merged_sections = self._extract_comprehensive_sections(content[:5000], lesson_title)
        
        # Assign section numbers
        for i, section in enumerate(merged_sections):
            section['section_number'] = i + 1
            section['id'] = i + 1
        
        # Extract learning objects for each section
        print(f"\n[ContentParser] Extracting learning objects for {len(merged_sections)} sections...")
        for section in merged_sections:
            section_title = section.get('title', f"Section {section.get('section_number', 1)}")
            key_topics = section.get('key_topics', [])

            # Locate section in source text -> pages + real content snippet
            location = self._locate_section_in_content(content, section, pages_meta)
            section['start_page'] = location['start_page']
            section['end_page'] = location['end_page']
            section_content = location['content_snippet'] or self._extract_section_content(
                content, " ".join(key_topics), section_title
            )
            section['content'] = section_content

            # Extract learning objects (reduced from 5-12 to 3-6)
            learning_objects = self._extract_learning_objects(
                section_content,
                section_title,
                lesson_title
            )

            # Annotate each LO with its source page(s) inside the section's page range.
            self._assign_lo_pages(learning_objects, content, pages_meta, section)

            section['learning_objects'] = learning_objects
            print(
                f"[ContentParser] Section '{section_title}': {len(learning_objects)} learning objects"
                + (f" (pages {section['start_page']}-{section['end_page']})" if section.get('start_page') else "")
            )
        
        print(f"\n[ContentParser] === PARSING COMPLETE ===")
        print(f"[ContentParser] Total sections: {len(merged_sections)}")
        total_los = sum(len(s.get('learning_objects', [])) for s in merged_sections)
        print(f"[ContentParser] Total learning objects: {total_los}")
        
        return merged_sections
    
    def _split_content_into_chunks(self, content: str, chunk_size: int = 3000, overlap: int = 400) -> List[str]:
        """
        Split content into overlapping chunks for analysis.
        BALANCED: Larger chunks (3000 chars) for better extraction while avoiding huge frontload.
        """
        chunks = []
        content_len = len(content)
        
        if content_len <= chunk_size:
            return [content]
        
        # Allow more chunks for better extraction
        max_chunks = 10
        
        start = 0
        chunk_count = 0
        while start < content_len and chunk_count < max_chunks:
            end = min(start + chunk_size, content_len)
            chunk = content[start:end]
            
            # Try to end at a paragraph break for cleaner chunks
            if end < content_len:
                last_break = chunk.rfind('\n\n')
                if last_break > chunk_size // 2:
                    chunk = chunk[:last_break]
                    end = start + last_break
            
            chunks.append(chunk)
            start = end - overlap
            chunk_count += 1
            
            if start >= content_len:
                break
        
        return chunks
    
    def _extract_sections_from_chunk(self, chunk: str, lesson_title: str, chunk_num: int, total_chunks: int) -> List[Dict]:
        """Extract sections from a single chunk with ENHANCED multi-level analysis"""

        # Detect language once per chunk so titles match the source.
        from core.lang_detect import detect_language, language_name
        chunk_lang = detect_language(chunk)
        lang_clause = (
            f"Write all titles and key_topics in {language_name(chunk_lang)}, matching the source content."
        )

        # LEVEL 1: identify the distinct topic areas covered by this chunk.
        prompt_l1 = f"""You are an expert educational content analyst. Your job is to identify the distinct sections that appear in one PART of a lesson.

LESSON: {lesson_title}
PART {chunk_num} OF {total_chunks}

CONTENT:
{chunk}

WORKED EXAMPLE (study STRUCTURE, do not copy topic):
[
  {{"title": "Definition of a Process", "key_topics": ["process", "instance", "execution"]}},
  {{"title": "Process States and Transitions", "key_topics": ["ready", "running", "blocked", "state diagram"]}}
]

INSTRUCTIONS:
  - Identify between 5 and 12 distinct sections in this chunk.
  - A section = a concept, definition, procedure, component, technique, or relationship.
  - Prefer specific section titles over generic ones (e.g. "Process Control Block" not "More Info").
  - {lang_clause}
  - key_topics should be 2-5 short search terms a reader could find in the chunk.

OUTPUT (strict JSON array, no other text):
[{{"title": "...", "key_topics": ["...", "..."]}}, ...]"""
        
        print(f"[ContentParser] [SECTION EXTRACTION] Analyzing chunk {chunk_num}/{total_chunks}...")
        response_l1 = self._call_ollama(prompt_l1, timeout=150)
        sections = self._extract_json_from_response(response_l1) if response_l1 else []
        
        if not isinstance(sections, list):
            sections = []
        
        print(f"[ContentParser] Level 1 found {len(sections)} initial sections")
        
        # LEVEL 2: Validate and enrich sections with context
        if len(sections) > 0:
            sections_str = ", ".join([s.get('title', '') for s in sections[:10]])
            
            prompt_l2 = f"""Validate and enrich these sections identified from "{lesson_title}":

SECTIONS: {sections_str}

CONTENT SNIPPET:
{chunk[:1500]}

---

For each section, determine:
1. Importance level: [foundational, core, supporting, advanced]
2. Related_sections: Which other identified sections relate to this one
3. Learning_prerequisites: What must be known before understanding this
4. Subtopics: 2-4 subtopics or related concepts within this section

Return ONLY JSON array:
[{{"title": "SectionName", "importance": "...", "related_sections": [...], "learning_prerequisites": [...], "subtopics": [...]}}]"""
            
            response_l2 = self._call_ollama(prompt_l2, timeout=120)
            enriched = self._extract_json_from_response(response_l2) if response_l2 else {}
            
            if isinstance(enriched, list):
                for section in sections:
                    for enrich_data in enriched:
                        if enrich_data.get('title', '').lower() == section.get('title', '').lower():
                            section['importance'] = enrich_data.get('importance', 'core')
                            section['related_sections'] = enrich_data.get('related_sections', [])
                            section['learning_prerequisites'] = enrich_data.get('learning_prerequisites', [])
                            section['subtopics'] = enrich_data.get('subtopics', [])
                            break
            
            print(f"[ContentParser] Level 2 enriched sections with context")
        
        # LEVEL 3: Gap detection - look for missing sections
        if len(sections) < 4:
            print(f"[ContentParser] Level 3 gap detection - found only {len(sections)} sections, looking for more...")
            
            prompt_l3 = f"""This chunk appears to have limited sections. Are there any major topics or concepts NOT in this list?

IDENTIFIED: {", ".join([s.get('title', '') for s in sections])}

CONTENT:
{chunk[:2000]}

---

List any significant topics, concepts, or sections that should be added. Be thorough.

Return ONLY JSON:
{{"additional_sections": [{{\"title\": \"...\", \"key_topics\": [...]}}]}}"""
            
            response_l3 = self._call_ollama(prompt_l3, timeout=120)
            additional = self._extract_json_from_response(response_l3) if response_l3 else {}
            
            if isinstance(additional, dict) and additional.get('additional_sections'):
                for add_section in additional.get('additional_sections', [])[:3]:
                    if add_section.get('title'):
                        sections.append(add_section)
                
                print(f"[ContentParser] Level 3 added {len(additional.get('additional_sections', []))} missing sections")
        
        # Return all found sections (up to 12 per chunk naturally)
        return sections[:12]
    
    def _merge_similar_sections(self, sections: List[Dict]) -> List[Dict]:
        """Merge sections that are too similar to avoid duplication"""
        if not sections:
            return []
        
        merged = []
        used = set()
        
        for i, section in enumerate(sections):
            if i in used:
                continue
            
            title = section.get('title', '').lower()
            topics = set(t.lower() for t in section.get('key_topics', []))
            
            # Find similar sections to merge with
            similar_topics = list(section.get('key_topics', []))
            
            for j, other in enumerate(sections[i+1:], start=i+1):
                if j in used:
                    continue
                
                other_title = other.get('title', '').lower()
                other_topics = set(t.lower() for t in other.get('key_topics', []))
                
                # Check multiple similarity metrics
                # 1. Title word overlap
                title_words = set(title.split())
                other_title_words = set(other_title.split())
                
                title_similarity = 0.0
                if len(title_words) > 0 and len(other_title_words) > 0:
                    title_similarity = len(title_words.intersection(other_title_words)) / max(len(title_words), len(other_title_words))
                
                # 2. Topic overlap (if any topics are the same, likely duplicates)
                topic_similarity = 0.0
                if len(topics) > 0 and len(other_topics) > 0:
                    topic_similarity = len(topics.intersection(other_topics)) / min(len(topics), len(other_topics))
                
                # 3. Combined score (title similarity matters more)
                combined_score = (title_similarity * 0.7) + (topic_similarity * 0.3)
                
                # More aggressive merging: 50% combined similarity OR >70% title similarity
                should_merge = (combined_score > 0.5) or (title_similarity > 0.7) or (topic_similarity > 0.6)
                
                if should_merge:
                    used.add(j)
                    similar_topics.extend(other.get('key_topics', []))
                    print(f"[ContentParser] Merging similar sections (score={combined_score:.2f}):")
                    print(f"  - '{section.get('title')}' + '{other.get('title')}'")
            
            # Remove duplicate topics
            unique_topics = list(dict.fromkeys(similar_topics))
            
            merged.append({
                'title': section.get('title', ''),
                'key_topics': unique_topics[:10]  # Limit topics
            })
        
        print(f"[ContentParser] After merging: {len(merged)} sections (was {len(sections)})")
        return merged
    
    def _extract_comprehensive_sections(self, content: str, lesson_title: str) -> List[Dict]:
        """Fallback: extract sections from a full snippet when chunked extraction produced too few."""

        from core.lang_detect import detect_language, language_name
        lang_name = language_name(detect_language(content))

        prompt = f"""You are an expert educational content analyst. Extract the distinct sections (5-15) covered by this lesson snippet.

LESSON: {lesson_title}

CONTENT:
{content[:6000]}

WORKED EXAMPLE (study the STRUCTURE; do not copy this topic):
[
  {{"title": "Definition of a Process", "key_topics": ["process", "instance", "execution"]}},
  {{"title": "Process States and Transitions", "key_topics": ["ready", "running", "blocked"]}}
]

INSTRUCTIONS:
  - Identify 5-15 sections. Only include sections the content actually covers — do not invent.
  - Each section = a concept, definition, procedure, component, technique, or relationship.
  - Write titles and key_topics in {lang_name}, matching the source content.

OUTPUT (strict JSON array, no other text):
[{{"title": "...", "key_topics": ["..."]}}, ...]"""
        
        response = self._call_ollama(prompt, timeout=120)
        
        if not response:
            return [{"title": lesson_title, "key_topics": []}]
        
        sections = self._extract_json_from_response(response)
        if isinstance(sections, list) and len(sections) > 0:
            return sections[:15]  # Allow up to 15 sections naturally
        
        return [{"title": lesson_title, "key_topics": []}]
    
    def _extract_json_from_response(self, response: str) -> Any:
        """Extract JSON from LLM response with detailed logging"""
        try:
            # Try to find JSON in the response
            json_match = re.search(r'\[.*\]|\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                result = json.loads(json_str)
                print(f"[ContentParser] Successfully extracted JSON: {type(result).__name__}")
                return result
            else:
                print(f"[ContentParser] WARNING: No JSON found in response. Response preview: {response[:200]}")
        except json.JSONDecodeError as e:
            print(f"[ContentParser] JSON parse error: {e}")
            print(f"[ContentParser] Response preview: {response[:300]}")
        
        return None
    
    def _extract_section_content(self, full_content: str, keywords: str, section_title: str) -> str:
        """
        Extract relevant content for a section based on keywords
        
        Args:
            full_content: Full lesson content
            keywords: Keywords to search for
            section_title: Title of the section
            
        Returns:
            Extracted section content
        """
        # Simple approach: find content around keywords
        lines = full_content.split('\n')
        keyword_list = keywords.lower().split()
        
        relevant_lines = []
        for line in lines:
            line_lower = line.lower()
            if any(kw in line_lower for kw in keyword_list) or section_title.lower() in line_lower:
                relevant_lines.append(line)
        
        # If we found matching lines, use them. Otherwise use first part
        if relevant_lines:
            return '\n'.join(relevant_lines[:50])  # Limit to 50 lines
        
        return full_content[:1500]  # Fallback: use first 1500 chars
    
    def _extract_learning_objects(self, section_content: str, section_title: str, lesson_title: str) -> List[Dict]:
        """
        Extract educational learning objects with ENHANCED QUALITY multi-pass analysis.
        
        ENHANCEMENT: Uses 3-pass extraction for comprehensive coverage:
        1. Primary extraction: Get main concepts
        2. Relationship analysis: Find connections and prerequisites
        3. Quality refinement: Ensure completeness and accuracy
        """
        content_preview = section_content[:3000].strip()  # Increased from 2000
        
        # PASS 1: identify the core learning objects in this section.
        from core.lang_detect import detect_language, language_name
        section_lang = detect_language(content_preview)
        lang_name = language_name(section_lang)

        print(f"[ContentParser] [PASS 1] Extracting core learning objects from: {section_title}")
        prompt_pass1 = f"""You are an expert educational content analyst. Your job is to extract the distinct learning objects from one section of a lesson.

LESSON: {lesson_title}
SECTION: {section_title}

CONTENT:
{content_preview}

WORKED EXAMPLE (study the STRUCTURE; do not copy this topic):
[
  {{"title": "Process Control Block (PCB)",
    "type": "concept",
    "description": "A data structure maintained by the OS for every active process. Stores process state, program counter, register values, memory limits, and scheduling info so the OS can suspend and resume the process correctly.",
    "key_points": ["holds the program counter", "stores CPU register contents", "tracks process state"],
    "keywords": ["PCB", "process control block", "context", "scheduling"]}}
]

INSTRUCTIONS:
  - Identify every distinct, valuable concept actually present in the content. Do not invent.
  - Quality over quantity — prefer 4 excellent objects over 10 forced ones.
  - Allowed values for `type`: concept, definition, process, principle, component, example, technique, structure.
  - title: 3-8 words.
  - description: 2-4 sentences.
  - key_points: 2-4 specific facts or characteristics drawn from the content.
  - keywords: 3-6 short terms a reader could search for in the source.
  - Write every field in {lang_name}, matching the source content (do not translate).

OUTPUT (strict JSON array, no other text):
[{{"title": "...", "type": "...", "description": "...", "key_points": ["..."], "keywords": ["..."]}}]"""
        
        response_pass1 = self._call_ollama(prompt_pass1, timeout=180)
        objects_pass1 = self._extract_json_from_response(response_pass1) if response_pass1 else []
        
        if not isinstance(objects_pass1, list):
            objects_pass1 = []
        
        print(f"[ContentParser] [PASS 1] Found {len(objects_pass1)} initial objects")
        
        # PASS 2: Relationship and context analysis
        print(f"[ContentParser] [PASS 2] Analyzing relationships and prerequisites...")
        if len(objects_pass1) > 0:
            titles_str = ", ".join([obj.get('title', '') for obj in objects_pass1[:10]])
            
            prompt_pass2 = f"""Analyze these concepts from "{section_title}" and enhance them with relationship information.

EXTRACTED CONCEPTS: {titles_str}

SECTION CONTENT:
{content_preview[:2000]}

---

For each concept listed, add:
1. Prerequisites: What concepts must be understood first
2. Related_concepts: Connected or similar concepts
3. Learning_outcomes: What should students be able to do after learning this
4. Common_misconceptions: Typical student misunderstandings (if applicable)
5. Real_world_applications: Practical uses or examples (if applicable)

Return ONLY a JSON array with enhanced details:
[{{"title": "ConceptName", "prerequisites": [...], "related_concepts": [...], "learning_outcomes": [...], "common_misconceptions": [...], "real_world_applications": [...]}}]"""
            
            response_pass2 = self._call_ollama(prompt_pass2, timeout=180)
            relationships = self._extract_json_from_response(response_pass2) if response_pass2 else {}
            
            # Merge relationship data into objects
            if isinstance(relationships, list):
                for obj in objects_pass1:
                    for rel_data in relationships:
                        if rel_data.get('title', '').lower() == obj.get('title', '').lower():
                            obj['prerequisites'] = rel_data.get('prerequisites', [])
                            obj['related_concepts'] = rel_data.get('related_concepts', [])
                            obj['learning_outcomes'] = rel_data.get('learning_outcomes', [])
                            obj['common_misconceptions'] = rel_data.get('common_misconceptions', [])
                            obj['real_world_applications'] = rel_data.get('real_world_applications', [])
                            break
        
        print(f"[ContentParser] [PASS 2] Enhanced with relationship data")
        
        # PASS 3: Quality check and gap filling
        print(f"[ContentParser] [PASS 3] Quality verification and gap analysis...")
        
        if len(objects_pass1) > 2:
            # Ask AI to identify any missing concepts
            prompt_pass3 = f"""Review the extracted concepts for "{section_title}" and identify ANY important concepts we missed.

EXTRACTED: {", ".join([obj.get('title', '') for obj in objects_pass1[:8]])}

ORIGINAL CONTENT:
{content_preview[:2500]}

---

Are there important concepts, definitions, or principles NOT in the extracted list? 
List any MISSING key concepts that should be included.

Return ONLY a JSON object with missing concepts (or empty array if complete):
{{"missing_concepts": [{{\"title\": \"...\", \"description\": \"...\", \"type\": \"...\"}}]}}"""
            
            response_pass3 = self._call_ollama(prompt_pass3, timeout=150)
            missing = self._extract_json_from_response(response_pass3) if response_pass3 else {}
            
            if isinstance(missing, dict) and missing.get('missing_concepts'):
                for missing_obj in missing.get('missing_concepts', [])[:3]:  # Add up to 3 missing
                    if missing_obj.get('title'):
                        objects_pass1.append({
                            'title': missing_obj.get('title', 'Unknown')[:150],
                            'type': missing_obj.get('type', 'concept'),
                            'description': missing_obj.get('description', '')[:600],
                            'key_points': [],
                            'keywords': []
                        })
            
            print(f"[ContentParser] [PASS 3] Added {len(missing.get('missing_concepts', []))} missing concepts")
        
        # Validate and clean all objects
        validated_objects = []
        seen_titles = set()
        
        for obj in objects_pass1:
            if not obj.get('title'):
                continue
            
            title_lower = obj.get('title', '').lower()
            if title_lower in seen_titles:
                continue
            seen_titles.add(title_lower)
            
            validated = {
                'title': obj.get('title', 'Unknown')[:150],
                'type': obj.get('type', 'concept'),
                'description': obj.get('description', '')[:600],
                'key_points': obj.get('key_points', []) if isinstance(obj.get('key_points'), list) else [],
                'keywords': obj.get('keywords', [])[:6] if isinstance(obj.get('keywords'), list) else [],
                'prerequisites': obj.get('prerequisites', []) if isinstance(obj.get('prerequisites'), list) else [],
                'related_concepts': obj.get('related_concepts', []) if isinstance(obj.get('related_concepts'), list) else [],
                'learning_outcomes': obj.get('learning_outcomes', []) if isinstance(obj.get('learning_outcomes'), list) else [],
            }
            validated_objects.append(validated)
        
        # Limit to 12 max (but keep all that were found)
        if len(validated_objects) > 12:
            validated_objects = validated_objects[:12]
        
        print(f"[ContentParser] [FINAL] Extracted {len(validated_objects)} high-quality learning objects (quality-focused extraction)")
        return validated_objects
    
    def _extract_learning_objects_simple(self, section_content: str, section_title: str, lesson_title: str) -> List[Dict]:
        """Simpler fallback for learning object extraction"""
        content_preview = section_content[:1500].strip()
        
        prompt = f"""Extract 5-8 key concepts from this educational content.

LESSON: {lesson_title}
SECTION: {section_title}

CONTENT:
{content_preview}

For each concept provide (JSON array):
- title: Concept name (MUST BE IN ENGLISH)
- type: One of [concept, definition, process, component]
- description: 2-3 sentence explanation (MUST BE IN ENGLISH)
- keywords: 3-4 related terms (MUST BE IN ENGLISH)

Extract 5-8 distinct concepts. Return ONLY JSON array."""
        
        response = self._call_ollama(prompt, timeout=120)
        if not response:
            return []
        
        objects = self._extract_json_from_response(response)
        if isinstance(objects, list):
            return [{'title': o.get('title', ''), 'type': o.get('type', 'concept'), 
                     'description': o.get('description', ''), 'key_points': o.get('key_points', []), 
                     'keywords': o.get('keywords', [])} for o in objects if o.get('title')][:8]
        return []
    
    def extract_ontology_relationships(self, content: str, learning_objects: List[Dict], lesson_title: str) -> List[Dict]:
        """
        Extract meaningful relationships between learning objects.
        Focus on quality educational connections WITH PROPER TAXONOMIC HIERARCHY.
        
        IMPROVED: Better fallback if AI extraction fails or times out.
        """
        if not learning_objects:
            print("[ContentParser] No learning objects to relate")
            return []
        
        # Build descriptions for ALL learning objects
        lo_descriptions = []
        all_lo_titles = []
        
        for lo in learning_objects:
            title = lo.get("title", lo.get("name", ""))
            desc = lo.get("description", "")[:80]
            type_str = lo.get("type", lo.get("object_type", "concept"))
            lo_descriptions.append(f"- {title} ({type_str}): {desc}")
            all_lo_titles.append(title)
        
        lo_context = "\n".join(lo_descriptions[:50])
        
        print("[ContentParser] === MULTI-PASS RELATIONSHIP EXTRACTION (High Quality Mode) ===")
        print(f"[ContentParser] Analyzing {len(all_lo_titles)} learning objects across 5 specialized passes...")
        
        all_relationships = []
        
        # ============= PASS 1: HIERARCHICAL TAXONOMY =============
        print("[ContentParser] [PASS 1] Extracting hierarchical relationships...")
        prompt_p1 = f"""SPECIALIST TASK: Find HIERARCHICAL and TAXONOMIC relationships ONLY.

LEARNING OBJECTS ({len(all_lo_titles)}):
{lo_context}

Find relationships where one concept is TYPE, PART, or CATEGORY of another:
- part_of: A is component/part of B
- is_type_of: A is a type/kind of B  
- is_example_of: A exemplifies B
- specialization_of: A is more specific than B

For EACH pair with hierarchy, output: source, target, type, description
Be EXHAUSTIVE. Find ALL hierarchical links.

JSON ONLY:
[{{"source": "...", "target": "...", "type": "part_of", "description": "..."}}]"""
        
        r1 = self._call_ollama(prompt_p1, timeout=1200)
        rels1 = self._extract_json_from_response(r1) if r1 else []
        if isinstance(rels1, list):
            all_relationships.extend(rels1)
            print(f"[ContentParser] [PASS 1] ✓ Found {len(rels1)} hierarchical relationships")
        
        # ============= PASS 2: PREREQUISITES & ENABLING =============
        print("[ContentParser] [PASS 2] Extracting prerequisite relationships...")
        prompt_p2 = f"""SPECIALIST TASK: Find PREREQUISITE, ENABLING, and BUILDING relationships.

LEARNING OBJECTS:
{lo_context}

Find dependencies showing learning order:
- prerequisite: A must be learned before B
- builds_upon: B extends/elaborates A
- enables: A makes B possible or easier
- foundation_for: A is foundational for B

Think: What knowledge comes first? What builds on what? What enables what?

JSON ONLY:
[{{"source": "...", "target": "...", "type": "prerequisite", "description": "..."}}]"""
        
        r2 = self._call_ollama(prompt_p2, timeout=1200)
        rels2 = self._extract_json_from_response(r2) if r2 else []
        if isinstance(rels2, list):
            all_relationships.extend(rels2)
            print(f"[ContentParser] [PASS 2] ✓ Found {len(rels2)} prerequisite relationships")
        
        # ============= PASS 3: SEMANTIC RELATIONSHIPS =============
        print("[ContentParser] [PASS 3] Extracting semantic relationships...")
        prompt_p3 = f"""SPECIALIST TASK: Find SEMANTIC and FUNCTIONAL relationships.

LEARNING OBJECTS:
{lo_context}

Find connections:
- relates_to: Concepts that naturally go together
- contrasts_with: Opposite or different approaches
- implements: How a concept is used/applied
- uses: What a concept depends on
- defines: Relationship to terminology
- is_mechanism_of: How it works in broader context

Be creative finding semantic links between all concepts.

JSON ONLY:
[{{"source": "...", "target": "...", "type": "relates_to", "description": "..."}}]"""
        
        r3 = self._call_ollama(prompt_p3, timeout=1200)
        rels3 = self._extract_json_from_response(r3) if r3 else []
        if isinstance(rels3, list):
            all_relationships.extend(rels3)
            print(f"[ContentParser] [PASS 3] ✓ Found {len(rels3)} semantic relationships")
        
        # ============= PASS 4: CROSS-SECTION INTEGRATION =============
        print("[ContentParser] [PASS 4] Extracting cross-section relationships...")
        prompt_p4 = f"""SPECIALIST TASK: Find relationships ACROSS topics (integration points).

LEARNING OBJECTS:
{lo_context}

Find connections between distant concepts:
- How general concepts apply in specific domains
- Concepts appearing in multiple contexts  
- Integration points spanning topics
- Applied uses of theoretical concepts

Look for creative semantic bridges.

JSON ONLY:
[{{"source": "...", "target": "...", "type": "relates_to", "description": "..."}}]"""
        
        r4 = self._call_ollama(prompt_p4, timeout=1200)
        rels4 = self._extract_json_from_response(r4) if r4 else []
        if isinstance(rels4, list):
            all_relationships.extend(rels4)
            print(f"[ContentParser] [PASS 4] ✓ Found {len(rels4)} cross-section relationships")
        
        # ============= PASS 5: META-RELATIONSHIPS =============
        print("[ContentParser] [PASS 5] Extracting meta-relationships...")
        rel_sample = []
        for rel in all_relationships[:20]:
            rel_sample.append(f"{rel.get('source', '')} --[{rel.get('type', '')}]--> {rel.get('target', '')}")
        sample_str = "\n".join(rel_sample) if rel_sample else "No relationships yet"
        
        prompt_p5 = f"""SPECIALIST TASK: Find META-RELATIONSHIPS (relationships between relationships).

Sample relationships found:
{sample_str}

Find patterns like:
- If A "prerequisite" B AND B "enables" C → create: prerequisite "leads_into" enables
- Concept HUBS (connect many others)
- Relationship chains and dependencies
- Conceptual bridges

JSON ONLY:
[{{"source": "...", "target": "...", "type": "meta_relationship", "description": "..."}}]"""
        
        r5 = self._call_ollama(prompt_p5, timeout=1200)
        rels5 = self._extract_json_from_response(r5) if r5 else []
        if isinstance(rels5, list):
            all_relationships.extend(rels5)
            print(f"[ContentParser] [PASS 5] ✓ Found {len(rels5)} meta-relationships")
        
        print(f"[ContentParser] Total raw relationships: {len(all_relationships)}")
        
        valid_relationships = self._validate_relationships(all_relationships, all_lo_titles)
        
        # Deduplicate
        seen = set()
        unique_rels = []
        for rel in valid_relationships:
            key = (rel.get('source'), rel.get('target'), rel.get('type'))
            if key not in seen:
                seen.add(key)
                unique_rels.append(rel)
        
        print(f"[ContentParser] Valid unique relationships: {len(unique_rels)}")
        
        # Only fall back when the LLM produced literally nothing. Topping up
        # an already-good extraction with inferred edges (especially a fake
        # "prerequisite" chain in document order) pollutes the ontology and
        # then pollutes the questions generated from it.
        if not unique_rels:
            print("[ContentParser] LLM produced no relationships, applying conservative fallback...")
            fallback = self._generate_smart_fallback_relationships(all_lo_titles, learning_objects)
            unique_rels.extend(fallback)

        return unique_rels
    
    def _generate_smart_fallback_relationships(self, all_lo_titles: List[str], learning_objects: List[Dict]) -> List[Dict]:
        """
        Defensible fallback relationships when LLM extraction yields nothing.

        We deliberately do NOT chain LOs as `prerequisite` in document order —
        that fabricates pedagogical structure that often isn't there. We keep
        only relationships that have a real basis in the parsed data:
          1. Type hierarchies: LOs of the same type are siblings under a head LO.
          2. Keyword co-occurrence: LOs sharing >=1 keyword are `relates_to`.
        Each inferred edge is marked `[inferred]` in its description so consumers
        can tell them apart from LLM-extracted edges.
        """
        relationships: List[Dict[str, Any]] = []

        # Strategy 1: Type-based hierarchies
        type_groups: Dict[str, List[str]] = {}
        for lo in learning_objects:
            obj_type = lo.get('type', lo.get('object_type', 'concept')).lower()
            type_groups.setdefault(obj_type, []).append(lo['title'])

        for _, titles in type_groups.items():
            if len(titles) > 1:
                general = titles[0]
                for specific in titles[1:]:
                    if specific and general and specific != general:
                        relationships.append({
                            "source": specific,
                            "target": general,
                            "type": "is_type_of",
                            "description": f"[inferred] {specific} shares a type with {general}",
                        })

        # Strategy 2: Keyword co-occurrence
        for i, lo1 in enumerate(learning_objects):
            keywords1 = set(lo1.get('keywords', []) or [])
            if not keywords1:
                continue
            for j in range(i + 1, min(i + 4, len(learning_objects))):
                lo2 = learning_objects[j]
                keywords2 = set(lo2.get('keywords', []) or [])
                shared = keywords1 & keywords2
                if shared and lo1.get('title') and lo2.get('title') and lo1['title'] != lo2['title']:
                    relationships.append({
                        "source": lo1['title'],
                        "target": lo2['title'],
                        "type": "relates_to",
                        "description": f"[inferred] shared keywords: {', '.join(list(shared)[:3])}",
                    })

        print(f"[ContentParser] Generated {len(relationships)} conservative fallback relationships (no fabricated prerequisites)")
        return relationships
    
    def _validate_relationships(self, relationships: List[Dict], all_lo_titles: List[str]) -> List[Dict]:
        """Validate relationships and match against learning object titles"""
        valid_relationships = []
        title_set = set(all_lo_titles)
        
        # Create normalized mapping
        normalized_to_original = {}
        for title in all_lo_titles:
            normalized = title.strip().lower()
            normalized_to_original[normalized] = title
        
        def clean_title(title):
            """Remove type metadata like (concept), (definition), etc"""
            cleaned = re.sub(r'\s*\([^)]*\)\s*$', '', title).strip()
            return cleaned
        
        for rel in relationships:
            source = rel.get("source", "").strip()
            target = rel.get("target", "").strip()
            
            source_clean = clean_title(source)
            target_clean = clean_title(target)
            
            # Try exact match first
            if source_clean in title_set and target_clean in title_set and source_clean != target_clean:
                rel["source"] = source_clean
                rel["target"] = target_clean
                valid_relationships.append(rel)
            else:
                # Try fuzzy matching (normalized comparison)
                source_normalized = source_clean.lower()
                target_normalized = target_clean.lower()
                
                if source_normalized in normalized_to_original and target_normalized in normalized_to_original:
                    rel["source"] = normalized_to_original[source_normalized]
                    rel["target"] = normalized_to_original[target_normalized]
                    if rel["source"] != rel["target"]:
                        valid_relationships.append(rel)
        
        return valid_relationships
    
    def generate_lesson_summary(self, content: str, lesson_title: str) -> Optional[str]:
        """
        Generate a concise summary of the lesson content.
        
        Args:
            content: Full lesson content
            lesson_title: Title of the lesson
            
        Returns:
            Summary text or None if generation fails
        """
        prompt = f"""Create a concise educational summary of this lesson.

LESSON: {lesson_title}

CONTENT:
{content[:4000]}

---

Write a 3-5 paragraph summary that covers:
1. Main topic and scope
2. Key concepts introduced
3. Important takeaways

Write in clear, academic English. Keep it concise but comprehensive."""

        response = self._call_ollama(prompt, timeout=120)
        
        if response and len(response) > 50:
            return response.strip()
        
        return None


# Create global instance
content_parser = ContentParser()
