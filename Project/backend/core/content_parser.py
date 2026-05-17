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

    # Strict LO type vocabulary. The prompt asks for these values, but the
    # LLM regularly returns out-of-set or cross-language types ("Concept",
    # "Mechanism", "Proces stanja", "Definicija"). Anything outside the set
    # is mapped via the alias table or falls through to "concept".
    _ALLOWED_LO_TYPES = {
        'concept', 'definition', 'process', 'principle',
        'component', 'example', 'technique', 'structure',
    }
    _LO_TYPE_ALIASES = {
        # English variants / lowercase typos
        'concepit': 'concept',
        'procedure': 'process',
        'mechanism': 'process',
        'fact': 'concept',
        'algorithm': 'process',
        'theory': 'principle',
        'law': 'principle',
        'rule': 'principle',
        'method': 'technique',
        # Serbian variants
        'definicija': 'definition',
        'princip': 'principle',
        'procedura': 'process',
        'tehnika': 'technique',
        'struktura': 'structure',
        'komponenta': 'component',
        'primer': 'example',
        'pojam': 'concept',
        # Frequently-seen freeform answers from the model
        'management information': 'concept',
        'processor register': 'component',
        'proces stanja': 'concept',
    }

    @classmethod
    def _normalize_lo_type(cls, raw: Any) -> str:
        """Coerce an LLM-supplied LO type into the allowed vocabulary."""
        if not raw or not isinstance(raw, str):
            return 'concept'
        t = raw.strip().lower()
        if t in cls._ALLOWED_LO_TYPES:
            return t
        return cls._LO_TYPE_ALIASES.get(t, 'concept')

    # LO title shape limits (Fix K). LO titles should be concept-style noun
    # phrases, not sentence-shaped descriptions. The grounding check passes
    # for verbatim bullet-line LO titles, but those titles are unwieldy
    # ("Dodela resursa procesima i zaštita dodeljenih resursa..."). Reject
    # them so the model is pushed to noun-phrase labels.
    _LO_TITLE_MAX_CHARS = 80
    _LO_TITLE_MAX_WORDS = 10

    @classmethod
    def _lo_title_is_well_shaped(cls, title: str) -> bool:
        """Return False if title is sentence-shaped (too long or too many words)."""
        if not title:
            return False
        title = title.strip()
        if len(title) > cls._LO_TITLE_MAX_CHARS:
            return False
        if len(title.split()) > cls._LO_TITLE_MAX_WORDS:
            return False
        return True

    @staticmethod
    def _lo_is_grounded(lo: Dict[str, Any], section_content: str) -> bool:
        """
        Check that an LO is actually rooted in the section text.

        Returns True if either:
          - the LO's title (>= 4 chars) appears verbatim in the section
            content (case-insensitive), or
          - at least one of its keywords (>= 4 chars) appears verbatim.

        This is the anti-hallucination check: if a model invents an LO
        like "Mutex (Mutual Exclusion)" for a lesson that doesn't mention
        mutexes, neither the title nor any keyword will appear in the
        section content, and the LO gets dropped.
        """
        if not section_content:
            return False
        text = section_content.lower()
        title = (lo.get('title') or '').strip().lower()
        if len(title) >= 4 and title in text:
            return True
        for kw in lo.get('keywords') or []:
            if not isinstance(kw, str):
                continue
            kw_clean = kw.strip().lower()
            if len(kw_clean) >= 4 and kw_clean in text:
                return True
        return False
    
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

    # Density-clustering parameter: matches more than CLUSTER_GAP characters
    # apart are treated as belonging to separate clusters. ~3000 chars is
    # roughly 1-2 pages of dense text, which is a reasonable "is this still
    # the same section?" threshold.
    _CLUSTER_GAP = 3000

    @staticmethod
    def _offset_in_excluded(offset: int, excluded_ranges: Optional[List[tuple]]) -> bool:
        """True if `offset` falls inside any (start, end) range."""
        if not excluded_ranges:
            return False
        for start, end in excluded_ranges:
            if start <= offset < end:
                return True
        return False

    def _locate_section_in_content(
        self,
        content: str,
        section: Dict[str, Any],
        pages_meta: Optional[List[Dict[str, Any]]],
        excluded_ranges: Optional[List[tuple]] = None,
    ) -> Dict[str, Any]:
        """
        Find where a section lives in the source text by clustering hits
        of its title and key_topics.

        Why clustering, not min/max: a key_topic like "process" appears all
        over a lesson, so `min(offsets) -> max(offsets)` would span almost
        the entire document. Instead, we group hits that are within
        `_CLUSTER_GAP` characters of each other and pick the cluster with
        the highest total weight — title hits count for more than key_topic
        hits, so an explicit title match anchors the section even when
        keywords are scattered.

        `excluded_ranges` lets the caller blacklist offset ranges (e.g.
        recurring TOC slide pages) so their title bullets don't pollute
        the locator with false "section is here" signals.

        Returns start_page, end_page (or None if no hits), and a content
        snippet drawn from the chosen cluster.
        """
        title = (section.get("title") or "").strip()
        topics = [t for t in (section.get("key_topics") or []) if t and len(t) >= 3]

        content_lower = content.lower()
        matches: List[Dict[str, Any]] = []  # {offset, weight, length, is_title}

        title_matches_anywhere = False
        if len(title) >= 3:
            for off in self._find_all(content_lower, title.lower()):
                if self._offset_in_excluded(off, excluded_ranges):
                    continue
                matches.append({"offset": off, "weight": 3.0, "length": len(title), "is_title": True})
                title_matches_anywhere = True

        for topic in topics:
            for off in self._find_all(content_lower, topic.lower(), max_hits=100):
                if self._offset_in_excluded(off, excluded_ranges):
                    continue
                matches.append({"offset": off, "weight": 1.0, "length": len(topic), "is_title": False})

        if not matches:
            return {"start_page": None, "end_page": None, "content_snippet": ""}

        matches.sort(key=lambda m: m["offset"])
        clusters: List[List[Dict[str, Any]]] = [[matches[0]]]
        for m in matches[1:]:
            if m["offset"] - clusters[-1][-1]["offset"] > self._CLUSTER_GAP:
                clusters.append([m])
            else:
                clusters[-1].append(m)

        # Fix G: when the title appears verbatim somewhere (outside excluded
        # ranges), prefer the cluster that contains the most title hits.
        # Without this, a section like "Komutiranje procesa" can lose to a
        # cluster of generic key_topic hits (e.g. "proces" on many earlier
        # pages) even though the real section is exactly where its title
        # appears. Tie-breakers: total cluster weight, then earliest offset.
        trim_to_title = False
        if title_matches_anywhere:
            title_clusters = [c for c in clusters if any(m["is_title"] for m in c)]
            if title_clusters:
                best = max(
                    title_clusters,
                    key=lambda c: (
                        sum(1 for m in c if m["is_title"]),
                        sum(m["weight"] for m in c),
                        -c[0]["offset"],
                    ),
                )
                trim_to_title = True
            else:
                best = max(clusters, key=lambda c: (sum(m["weight"] for m in c), -c[0]["offset"]))
        else:
            best = max(clusters, key=lambda c: (sum(m["weight"] for m in c), -c[0]["offset"]))

        # Fix J: when a title-bearing cluster wins, trim the section's
        # boundaries to just the title hits inside that cluster. Keyword
        # hits that extended the range beyond the title hits are drive-by
        # mentions, not section content — including them would balloon the
        # range across many pages (the "section spans 5-65" pathology).
        if trim_to_title:
            title_only = [m for m in best if m["is_title"]]
            start_offset = title_only[0]["offset"]
            end_offset = title_only[-1]["offset"] + title_only[-1]["length"]
        else:
            start_offset = best[0]["offset"]
            end_offset = best[-1]["offset"] + best[-1]["length"]

        snippet_end = min(end_offset + 600, len(content))
        snippet = content[start_offset:snippet_end][:3000]

        return {
            "start_page": self._offset_to_page(start_offset, pages_meta) if pages_meta else None,
            "end_page": self._offset_to_page(end_offset, pages_meta) if pages_meta else None,
            "content_snippet": snippet,
        }

    # Max pages we'll attach to one LO. An LO that genuinely lives on more
    # than ~5 pages is probably mis-scoped (should be split, or it's just
    # a vocabulary word the model picked up). Capping prevents the "this LO
    # is tagged with 23 pages" pathology.
    _LO_MAX_PAGES = 5

    def _assign_lo_pages(
        self,
        learning_objects: List[Dict[str, Any]],
        content: str,
        pages_meta: Optional[List[Dict[str, Any]]],
        section: Dict[str, Any],
        excluded_ranges: Optional[List[tuple]] = None,
    ) -> None:
        """
        Annotate each LO with the pages it's actually defined/discussed on.

        Two-tier strategy:
          1. If the LO's title appears verbatim on some pages within the
             parent section, those are the pages — a title match is the
             strongest signal that "this is where the concept is introduced".
          2. Otherwise fall back to keywords, but require at least 2 keyword
             hits on the same page to count it (drops drive-by single-word
             mentions). If even that fails, take the top-hit pages by count.

        All results are constrained to the parent section's page range and
        capped at `_LO_MAX_PAGES` pages. `excluded_ranges` (typically TOC
        slide offsets) are skipped so an LO doesn't get tagged with a
        TOC-bullet page where its title appears only as a bullet.
        """
        if not pages_meta or not learning_objects:
            for lo in learning_objects:
                lo['source_pages'] = []
            return

        content_lower = content.lower()
        sp = section.get('start_page')
        ep = section.get('end_page')

        def in_range(page: int) -> bool:
            if sp is None or ep is None:
                return True
            return sp <= page <= ep

        for lo in learning_objects:
            title = (lo.get('title') or '').strip().lower()
            keywords = [
                kw.strip().lower()
                for kw in (lo.get('keywords') or [])
                if isinstance(kw, str) and len(kw.strip()) >= 4
            ]

            # Tier 1: pages where the title appears verbatim.
            title_pages: List[int] = []
            if len(title) >= 3:
                for off in self._find_all(content_lower, title):
                    if self._offset_in_excluded(off, excluded_ranges):
                        continue
                    page = self._offset_to_page(off, pages_meta)
                    if page is not None and in_range(page) and page not in title_pages:
                        title_pages.append(page)

            if title_pages:
                lo['source_pages'] = sorted(title_pages)[: self._LO_MAX_PAGES]
                continue

            # Tier 2: keyword scoring.
            page_scores: Dict[int, int] = {}
            for kw in keywords:
                for off in self._find_all(content_lower, kw, max_hits=30):
                    if self._offset_in_excluded(off, excluded_ranges):
                        continue
                    page = self._offset_to_page(off, pages_meta)
                    if page is not None and in_range(page):
                        page_scores[page] = page_scores.get(page, 0) + 1

            if not page_scores:
                lo['source_pages'] = [sp] if sp else []
                continue

            # Prefer pages where ≥ 2 different keyword hits land.
            strong = sorted([p for p, c in page_scores.items() if c >= 2])
            if strong:
                lo['source_pages'] = strong[: self._LO_MAX_PAGES]
            else:
                # No page has 2+ hits — fall back to top-N pages by count.
                top = sorted(page_scores.items(), key=lambda x: -x[1])[: self._LO_MAX_PAGES]
                lo['source_pages'] = sorted(p for p, _ in top)

    def parse_lesson_structure(
        self,
        content: str,
        lesson_title: str,
        pages_meta: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Parse lesson content into sections with learning objects.

        Pipeline:
          1. Plan a section outline with ONE LLM call that sees the whole
             lesson (or a per-page-sampled view for very long PDFs). The
             planner is told to scale the section count to the actual content
             and avoid duplicates. This replaces the old chunk-and-dedup
             approach, which always landed at the 15-section cap.
          2. If the planner fails or returns <2 sections, fall back to the
             chunked extraction (kept as a safety net).
          3. For each planned section, locate it in the source text, extract
             learning objects, and annotate pages.

        Args:
            content: Full lesson content.
            lesson_title: Title of the lesson.
            pages_meta: Optional per-page offset metadata. When provided,
                each section is annotated with start_page/end_page and a
                content snippet drawn from the actual source text.

        Returns:
            List of section dictionaries with learning objects.
        """
        print(f"\n[ContentParser] === LESSON PARSING ===")
        print(f"[ContentParser] Content length: {len(content)} characters")

        # Detect outline + TOC pages once, share with planner AND locator.
        # TOC pages are excluded from the locator's search range so that
        # recurring TOC bullets don't make sections span the whole document.
        outline_items = self._detect_outline(content, pages_meta) if pages_meta else None
        toc_pages_meta: List[Dict[str, Any]] = []
        excluded_ranges: List[tuple] = []
        if outline_items and pages_meta:
            toc_pages_meta = self._find_toc_pages(content, pages_meta, outline_items)
            excluded_ranges = [(p['start_offset'], p['end_offset']) for p in toc_pages_meta]
            if toc_pages_meta:
                page_nums = [p['page'] for p in toc_pages_meta]
                print(f"[ContentParser] Excluding {len(toc_pages_meta)} TOC page(s) from locator: {page_nums}")

        # ----- Phase 1: plan-first outline (single- or two-stage) -----
        merged_sections = self._plan_lesson_outline(
            content, lesson_title, pages_meta,
            outline_items=outline_items, toc_pages=toc_pages_meta,
        ) or []
        if merged_sections:
            print(f"[ContentParser] Planner returned {len(merged_sections)} sections")

        # ----- Fallback A: chunked extraction (legacy path, safety net) -----
        if len(merged_sections) < 2:
            print(f"[ContentParser] Planner produced {len(merged_sections)} sections — falling back to chunked extraction")
            merged_sections = self._chunked_section_extraction(content, lesson_title)

        # ----- Fallback B: last-resort single-call extraction from a snippet -----
        if len(merged_sections) < 2:
            print(f"[ContentParser] Chunked fallback also empty — last-resort comprehensive extraction")
            merged_sections = self._extract_comprehensive_sections(content[:5000], lesson_title)

        print(f"[ContentParser] Final section count: {len(merged_sections)}")

        # ----- Phase 2a: locate every section in the source text -----
        # We locate FIRST (no LLM cost), then drop phantoms and inject
        # missing outline chapters, THEN do the expensive per-section LO
        # extraction. This avoids wasting LLM time on sections we'll drop.
        for section in merged_sections:
            location = self._locate_section_in_content(
                content, section, pages_meta, excluded_ranges=excluded_ranges
            )
            section['start_page'] = location['start_page']
            section['end_page'] = location['end_page']
            section['content'] = location['content_snippet']

        # ----- Fix H: drop phantom sections (no page anchor) -----
        with_pages = [s for s in merged_sections if s.get('start_page') is not None]
        if pages_meta and len(with_pages) < len(merged_sections):
            dropped = [s.get('title') for s in merged_sections if s.get('start_page') is None]
            print(f"[ContentParser] Dropping {len(dropped)} phantom section(s) with no page anchor: {dropped}")
            merged_sections = with_pages

        # ----- Fix H: inject missing outline chapters -----
        # If the detected outline lists a chapter that no surviving section
        # represents (by title substring) AND the chapter title can be
        # located in the source, inject it as a section. Belt-and-suspenders
        # for the two-stage planner missing a chapter.
        if outline_items and pages_meta:
            existing_titles_lower = [s.get('title', '').lower() for s in merged_sections]
            for item in outline_items:
                item_lower = item.lower()
                covered = any(item_lower in et or (et and et in item_lower) for et in existing_titles_lower)
                if covered:
                    continue
                synthetic = {'title': item, 'key_topics': []}
                loc = self._locate_section_in_content(
                    content, synthetic, pages_meta, excluded_ranges=excluded_ranges
                )
                if loc['start_page'] is not None:
                    synthetic['start_page'] = loc['start_page']
                    synthetic['end_page'] = loc['end_page']
                    synthetic['content'] = loc['content_snippet']
                    merged_sections.append(synthetic)
                    existing_titles_lower.append(item_lower)
                    print(f"[ContentParser] Injected missing outline chapter: '{item}' (pages {loc['start_page']}-{loc['end_page']})")

        # ----- Fix L: inject sections for runs of uncovered pages -----
        # Now that section page ranges are tight (after Fix J trimming),
        # any consecutive pages with no section coverage probably represent
        # slides the planner missed (e.g. Pipes pp 57-60 in the OS lesson).
        # Inject each run as a section using the first slide's heading as
        # the title.
        if pages_meta:
            covered: set = set()
            for s in merged_sections:
                sp, ep = s.get('start_page'), s.get('end_page')
                if sp and ep:
                    for p in range(sp, ep + 1):
                        covered.add(p)

            toc_set = {p['page'] for p in toc_pages_meta}
            all_page_nums = {m['page'] for m in pages_meta}
            uncovered_pages = sorted(all_page_nums - covered - toc_set)

            page_text_by_num = {
                m['page']: content[m['start_offset']:m['end_offset']]
                for m in pages_meta
            }
            page_chars_by_num = {m['page']: m.get('char_count', 0) for m in pages_meta}

            # Only consider pages with substantive content (skip near-empty
            # slides like "izvor: youtube.com" filler).
            substantive_uncovered = [
                p for p in uncovered_pages if page_chars_by_num.get(p, 0) >= 30
            ]

            existing_titles_lower = {s.get('title', '').lower() for s in merged_sections}
            injected_count = 0

            for run_start, run_end in self._consecutive_runs(substantive_uncovered):
                # Try the first page's heading; fall through to subsequent
                # pages if the first one isn't heading-shaped.
                heading: Optional[str] = None
                for p in range(run_start, run_end + 1):
                    candidate = self._extract_slide_heading(page_text_by_num.get(p, ''))
                    if candidate:
                        heading = candidate
                        break
                if not heading:
                    continue
                # Skip if this title is already a section (case-insensitive).
                if heading.lower() in existing_titles_lower:
                    continue
                # Build a content snippet from the run for LO extraction.
                snippet_parts = []
                for p in range(run_start, run_end + 1):
                    snippet_parts.append(page_text_by_num.get(p, ''))
                snippet = "\n".join(snippet_parts)[:3000]

                merged_sections.append({
                    'title': heading,
                    'key_topics': [],
                    'start_page': run_start,
                    'end_page': run_end,
                    'content': snippet,
                })
                existing_titles_lower.add(heading.lower())
                injected_count += 1
                print(f"[ContentParser] Injected missing-slide section: '{heading}' (pages {run_start}-{run_end})")

            if injected_count:
                print(f"[ContentParser] Total slide-run injections: {injected_count}")

        # Sort by start_page so injected chapters land in document order.
        merged_sections.sort(key=lambda s: (s.get('start_page') or 0, s.get('end_page') or 0))

        # Assign section numbers
        for i, section in enumerate(merged_sections):
            section['section_number'] = i + 1
            section['id'] = i + 1

        # ----- Phase 2b: extract learning objects for each section -----
        print(f"\n[ContentParser] Extracting learning objects for {len(merged_sections)} sections...")
        for section in merged_sections:
            section_title = section.get('title', f"Section {section.get('section_number', 1)}")
            key_topics = section.get('key_topics', [])

            section_content = section.get('content') or self._extract_section_content(
                content, " ".join(key_topics), section_title
            )
            section['content'] = section_content

            learning_objects = self._extract_learning_objects(
                section_content,
                section_title,
                lesson_title
            )

            self._assign_lo_pages(
                learning_objects, content, pages_meta, section,
                excluded_ranges=excluded_ranges,
            )

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
    
    # =====================================================================
    # Planner-first outline (primary path)
    # =====================================================================

    @staticmethod
    def _find_all(haystack: str, needle: str, max_hits: int = 200) -> List[int]:
        """Return up to `max_hits` start offsets of `needle` in `haystack` (case-sensitive)."""
        if not needle:
            return []
        out: List[int] = []
        start = 0
        while True:
            pos = haystack.find(needle, start)
            if pos == -1 or len(out) >= max_hits:
                break
            out.append(pos)
            start = pos + len(needle)
        return out

    @staticmethod
    def _detect_outline(
        content: str,
        pages_meta: Optional[List[Dict[str, Any]]],
    ) -> Optional[List[str]]:
        """
        Detect a table-of-contents / outline page in the lesson, regardless
        of the language or what the page is labelled (Sadržaj, Contents,
        Programme, Curriculum, Headings, "What we'll cover", or no label
        at all).

        The strongest structural signal is that a TOC's items REAPPEAR as
        headings later in the document. This function doesn't keyword-match
        on labels — it scores candidate pages on:

          - short page (a TOC slide is usually 30–800 chars)
          - several short lines (each item ≤ 80 chars), at least 3
          - majority of those items appear verbatim in the text after this
            page (i.e. they predict later headings)

        Only the first ~8 pages are considered (TOC slides are near the
        start in practice; slide decks sometimes repeat them but the first
        one is enough to extract the outline).

        Returns the list of item strings, or None if no convincing TOC is
        found.
        """
        if not pages_meta or len(pages_meta) < 3:
            return None

        content_lower = content.lower()
        best: Optional[Dict[str, Any]] = None

        for meta in pages_meta[: min(8, len(pages_meta))]:
            char_count = meta.get('char_count', 0)
            if char_count < 30 or char_count > 800:
                continue

            text = content[meta['start_offset']:meta['end_offset']].strip()
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            if len(lines) < 4:  # need a label + at least 3 items
                continue

            # Treat the first line as a probable section label; the rest as
            # candidate items. Even if the first line is itself an item,
            # we'll still detect the structure as long as the remaining
            # lines look like a list.
            items = lines[1:]
            if not all(len(item) <= 80 for item in items):
                continue

            # Verification: how many items reappear later in the document?
            after = content_lower[meta['end_offset']:]
            hits = sum(1 for item in items if item.lower() in after)
            ratio = hits / len(items) if items else 0.0

            # Need at least 3 items to reappear AND a majority hit rate.
            if hits < 3 or ratio < 0.6:
                continue

            score = (ratio, hits)  # tuple comparison: prefer ratio then count
            if best is None or score > (best['ratio'], best['hits']):
                best = {
                    'page': meta['page'],
                    'items': items,
                    'ratio': ratio,
                    'hits': hits,
                }

        if best is None:
            return None

        print(
            f"[ContentParser] Detected outline on page {best['page']}: "
            f"{len(best['items'])} items, {best['ratio']*100:.0f}% reappear later"
        )
        return best['items']

    @staticmethod
    def _extract_slide_heading(page_text: str) -> Optional[str]:
        """
        First non-empty line of a slide IF it looks like a heading.

        Slide titles are typically short, no terminal period, ≤ 10 words.
        Used by Fix L to pull a heading from an uncovered page so we can
        inject a section for it.
        """
        if not page_text:
            return None
        for line in page_text.splitlines():
            line = line.strip()
            if not line:
                continue
            # Look only at the first non-empty line.
            if 3 <= len(line) <= 80 and len(line.split()) <= 10 and not line.endswith('.'):
                return line
            return None
        return None

    @staticmethod
    def _consecutive_runs(pages: List[int]) -> List[tuple]:
        """Group a sorted list of page numbers into (start, end) consecutive runs."""
        if not pages:
            return []
        runs = []
        run_start = prev = pages[0]
        for p in pages[1:]:
            if p == prev + 1:
                prev = p
            else:
                runs.append((run_start, prev))
                run_start = prev = p
        runs.append((run_start, prev))
        return runs

    @staticmethod
    def _find_toc_pages(
        content: str,
        pages_meta: List[Dict[str, Any]],
        outline_items: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Find ALL pages that look like table-of-contents slides.

        Slide decks often repeat the TOC throughout the deck as a "where
        we are" indicator. Once `_detect_outline` has identified the
        outline items, we sweep every page and flag any page where most of
        those items appear together. These pages' offset ranges should be
        excluded from the section locator — otherwise the locator picks up
        TOC bullets as if they were content mentions, and a section like
        "Stanja procesa" ends up spanning the whole document because its
        title hits every recurring TOC slide.
        """
        if not outline_items or not pages_meta:
            return []
        items_lower = [it.lower() for it in outline_items if it]
        if not items_lower:
            return []
        threshold = max(2, int(len(items_lower) * 0.6))
        content_lower = content.lower()
        toc_pages = []
        for meta in pages_meta:
            page_text = content_lower[meta['start_offset']:meta['end_offset']]
            hits = sum(1 for item in items_lower if item in page_text)
            if hits >= threshold:
                toc_pages.append(meta)
        return toc_pages

    @staticmethod
    def _build_outline_sample(
        content: str,
        pages_meta: Optional[List[Dict[str, Any]]],
        max_chars: int = 14000,
    ) -> str:
        """
        Build a compact, structure-preserving sample of the lesson for the
        planner LLM call.

        Strategy:
          - If the whole content fits within `max_chars`, return it verbatim.
          - Otherwise sample by page: full text of the first and last pages,
            plus the first ~300 chars of every page in between (headings
            usually appear at the top of a page). This gives the model a
            "table of contents" view without blowing the context window.
          - If pages_meta is unavailable, fall back to a head-and-tail slice.
        """
        if len(content) <= max_chars:
            return content

        if not pages_meta or len(pages_meta) < 2:
            head = content[: int(max_chars * 0.7)]
            tail = content[-int(max_chars * 0.3) :]
            return f"{head}\n\n[... omitted middle ...]\n\n{tail}"

        parts: List[str] = []
        first, last = pages_meta[0], pages_meta[-1]
        parts.append(f"=== PAGE {first['page']} (first page, full) ===")
        parts.append(content[first['start_offset']:first['end_offset']])

        for meta in pages_meta[1:-1]:
            excerpt = content[meta['start_offset']:meta['end_offset']].strip()
            if not excerpt:
                continue
            parts.append(f"=== PAGE {meta['page']} (top excerpt) ===")
            parts.append(excerpt[:300])

        parts.append(f"=== PAGE {last['page']} (last page, full) ===")
        parts.append(content[last['start_offset']:last['end_offset']])

        sample = "\n".join(parts)
        if len(sample) > max_chars:
            sample = sample[:max_chars] + "\n[... truncated ...]"
        return sample

    # =====================================================================
    # Two-stage chapter expansion (Fix I)
    # =====================================================================

    @staticmethod
    def _compute_chapter_ranges(
        outline_items: List[str],
        toc_page_nums: List[int],
        total_pages: int,
    ) -> List[tuple]:
        """
        Derive (chapter_title, start_page, end_page) for each detected
        chapter by using TOC pages as boundaries.

        Slide decks following the "TOC then chapter" pattern (which is what
        `_find_toc_pages` is designed to detect) put each chapter's content
        between consecutive TOCs. So chapter i runs from (toc_i + 1) to
        (toc_{i+1} - 1), and the last chapter runs to the final page.
        """
        if not outline_items or not toc_page_nums or total_pages <= 0:
            return []
        ranges: List[tuple] = []
        toc_sorted = sorted(toc_page_nums)
        for i, chapter_title in enumerate(outline_items):
            if i < len(toc_sorted):
                start_page = toc_sorted[i] + 1
            else:
                start_page = (ranges[-1][2] + 1) if ranges else 1
            if i + 1 < len(toc_sorted):
                end_page = toc_sorted[i + 1] - 1
            else:
                end_page = total_pages
            if start_page > end_page or start_page > total_pages:
                continue
            ranges.append((chapter_title, start_page, end_page))
        return ranges

    @staticmethod
    def _content_for_page_range(
        content: str,
        pages_meta: List[Dict[str, Any]],
        start_page: int,
        end_page: int,
        excluded_page_nums: Optional[set] = None,
    ) -> str:
        """Concatenate raw text for pages [start_page..end_page], skipping excluded pages."""
        if not pages_meta:
            return ""
        excluded = excluded_page_nums or set()
        parts = []
        for meta in pages_meta:
            page = meta['page']
            if start_page <= page <= end_page and page not in excluded:
                parts.append(content[meta['start_offset']:meta['end_offset']])
        return "\n".join(parts)

    def _extract_chapter_subsections(
        self,
        chapter_title: str,
        chapter_content: str,
        lesson_title: str,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Stage 2 of the two-stage planner: given ONE chapter's content,
        ask the LLM to identify its slide-level sub-sections.

        Returns a list of section dicts ({"title": ..., "key_topics": [...]})
        or None on failure / empty response.
        """
        from core.lang_detect import detect_language, language_name

        lang = detect_language(chapter_content)
        lang_clause = f"Write titles and key_topics in {language_name(lang)}, matching the source content."

        prompt = f"""You are an expert educational content analyst. The CHAPTER content below is one part of the lesson "{lesson_title}". Break this chapter into its distinct topical sub-sections — the slide-level topics a student would learn as separate units.

CHAPTER: {chapter_title}

CHAPTER CONTENT:
{chapter_content[:8000]}

INSTRUCTIONS:
  - Identify EVERY distinct sub-section the chapter content covers. A long chapter usually has 4-10 sub-sections; a short one has 2-4. Trust the content over any rough guideline.
  - A sub-section = one slide-level topic: a concept, definition, procedure, comparison, principle, or worked example.
  - Be EXHAUSTIVE — capture every distinct slide topic. But do NOT propose duplicates: if two candidate titles describe the same idea, merge them into one entry.
  - Titles must be specific and content-anchored (use the exact slide heading where possible, e.g. "Atributi procesa", "Komutiranje procesa"). Do NOT invent generic titles like "Overview" or "More info".
  - Only propose sub-sections that actually appear in this chapter content. Do NOT borrow concepts from other chapters of the lesson.
  - {lang_clause}

OUTPUT (strict JSON array, no other text):
[{{"title": "...", "key_topics": ["...", "..."]}}, ...]"""

        response = self._call_ollama(prompt, timeout=300)
        if not response:
            return None

        raw = self._extract_json_from_response(response)
        if not isinstance(raw, list):
            return None

        seen = set()
        out: List[Dict[str, Any]] = []
        for s in raw:
            if not isinstance(s, dict):
                continue
            title = (s.get("title") or "").strip()
            if not title:
                continue
            norm = title.lower()
            if norm in seen:
                continue
            seen.add(norm)
            key_topics = s.get("key_topics") or []
            if not isinstance(key_topics, list):
                key_topics = []
            out.append({
                "title": title,
                "key_topics": [t for t in key_topics if isinstance(t, str)][:8],
            })
        return out or None

    def _expand_chapters_into_sections(
        self,
        content: str,
        lesson_title: str,
        outline_items: List[str],
        pages_meta: List[Dict[str, Any]],
        toc_pages: List[Dict[str, Any]],
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Two-stage planner orchestration. For each detected chapter, fetch
        its page range and ask the LLM to expand it into sub-sections.

        Falls back to None if chapter boundaries can't be derived (caller
        then uses the single-stage planner).
        """
        if not outline_items or not pages_meta or not toc_pages:
            return None

        toc_page_nums = sorted(p['page'] for p in toc_pages)
        total_pages = pages_meta[-1]['page']
        ranges = self._compute_chapter_ranges(outline_items, toc_page_nums, total_pages)
        if not ranges:
            return None

        print(f"[ContentParser] Two-stage planner: expanding {len(ranges)} chapter(s)")
        excluded_set = set(toc_page_nums)
        all_sections: List[Dict[str, Any]] = []

        for chapter_title, start, end in ranges:
            chapter_content = self._content_for_page_range(
                content, pages_meta, start, end, excluded_set
            )
            if len(chapter_content.strip()) < 150:
                # Tiny chapter (e.g. 1-2 sparse slides) — fold into a single section.
                print(f"[ContentParser]   '{chapter_title}' (pp {start}-{end}, {len(chapter_content)} chars): tiny — keep as one section")
                all_sections.append({"title": chapter_title, "key_topics": []})
                continue

            subs = self._extract_chapter_subsections(chapter_title, chapter_content, lesson_title)
            if subs:
                print(f"[ContentParser]   '{chapter_title}' (pp {start}-{end}): {len(subs)} sub-sections")
                all_sections.extend(subs)
            else:
                print(f"[ContentParser]   '{chapter_title}' (pp {start}-{end}): expansion failed — keep as one section")
                all_sections.append({"title": chapter_title, "key_topics": []})

        # Final dedup across chapters (a sub-section title shared between
        # two chapters would be unusual but possible).
        seen = set()
        deduped: List[Dict[str, Any]] = []
        for s in all_sections:
            norm = s["title"].lower()
            if norm in seen:
                continue
            seen.add(norm)
            deduped.append(s)

        return deduped or None

    def _plan_lesson_outline(
        self,
        content: str,
        lesson_title: str,
        pages_meta: Optional[List[Dict[str, Any]]] = None,
        outline_items: Optional[List[str]] = None,
        toc_pages: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Plan the lesson's section structure in ONE LLM call.

        The model is given the whole lesson (or a per-page sampled view for
        very long PDFs) plus a guideline that the section count should scale
        with content size — ~1 section per 1800 chars, with a soft floor of
        3 and soft ceiling of 35. The model is told to trust the content over
        the guideline. Duplicate proposals are filtered out afterward by
        normalised title, as a defensive belt-and-suspenders.

        Returns None on LLM failure or if the response can't be parsed; the
        caller falls back to the chunked extraction.
        """
        from core.lang_detect import detect_language, language_name

        sample = self._build_outline_sample(content, pages_meta)
        char_count = len(content)
        page_count = len(pages_meta) if pages_meta else 0

        lang = detect_language(sample)
        lang_name = language_name(lang)
        lang_clause = (
            f"Write all titles and key_topics in {lang_name}, matching the source content."
        )

        # Pick the section-count guideline based on content shape:
        #
        #   - Slide decks: short pages (~150-500 chars each). Each slide is
        #     usually one topical unit, so target ~1 section per 2 pages.
        #   - Prose / textbook content: dense pages. Target ~1 section per
        #     1800 chars (a paragraph or two of substantive content).
        #
        # Without `pages_meta` we can't tell, so we default to the prose
        # heuristic. Slide-deck content otherwise gets badly under-sectioned
        # (a 32-page slide lesson would only get ~5 sections from the prose
        # heuristic; ~16 sections from the slide heuristic).
        if page_count and char_count / max(1, page_count) < 600:
            rough_target = max(5, min(40, page_count // 2))
        else:
            rough_target = max(3, min(35, char_count // 1800))
        page_clause = f" across {page_count} pages" if page_count else ""

        # Detect a table-of-contents page (language-agnostic). If found,
        # offer it to the planner as a hypothesis it can use OR override.
        # Caller may pass `outline_items` in to avoid re-detecting.
        if outline_items is None:
            outline_items = self._detect_outline(content, pages_meta)

        # Fix I: when we have a real outline AND TOC pages to mark chapter
        # boundaries, run the two-stage planner. It produces noticeably
        # better per-chapter coverage than a single big call.
        if outline_items and len(outline_items) >= 3 and toc_pages and pages_meta:
            print(f"[ContentParser] Using two-stage planner ({len(outline_items)} chapters)")
            two_stage = self._expand_chapters_into_sections(
                content, lesson_title, outline_items, pages_meta, toc_pages
            )
            if two_stage and len(two_stage) >= len(outline_items):
                return two_stage
            print(f"[ContentParser] Two-stage produced {len(two_stage) if two_stage else 0} sections — falling back to single-stage")

        outline_block = ""
        if outline_items:
            bullets = "\n".join(f"  - {item}" for item in outline_items)
            outline_block = f"""

DETECTED OUTLINE — a page early in this lesson appears to list its top-level structure (its items reappear as headings later in the text). Use it as the chapter-level skeleton and expand each item into its sub-sections, UNLESS the items don't actually fit the content — in that case ignore this and structure the lesson from the content directly.

The detected items are:
{bullets}"""

        prompt = f"""You are an expert educational content analyst. Your job is to plan the structure of one lesson by listing every distinct topical section it covers.

LESSON: {lesson_title}
TOTAL LENGTH: {char_count} characters{page_clause}

CONTENT (full lesson, or a structured per-page sample if very long):
{sample}{outline_block}

WHAT COUNTS AS A SECTION:
A section is one coherent unit — a concept, definition, procedure, component, technique, principle, or worked example. It is something a student would learn as a unit and could be asked about.

INSTRUCTIONS:
  - Be EXHAUSTIVE but not redundant. If two candidate sections describe the same concept, merge them into one entry with combined key_topics. Never propose duplicates.
  - Calibrate the count to the actual content. A short 2-page lesson might have 3-4 sections; a 30-page chapter might have 20-30. As a rough starting estimate this lesson holds about {rough_target} sections — but trust the content over the guideline.
  - Titles must be specific and content-anchored ("Process Control Block", "Round-Robin Scheduling"), not generic ("Background", "More Information").
  - key_topics: 2-5 short search terms a reader could find in the source (used downstream to locate the section in the text).
  - {lang_clause}

OUTPUT (strict JSON array, no other text):
[{{"title": "...", "key_topics": ["...", "..."]}}, ...]"""

        response = self._call_ollama(prompt, timeout=300)
        if not response:
            return None

        sections = self._extract_json_from_response(response)
        if not isinstance(sections, list):
            return None

        # Defensive dedup by normalised title — the planner is told not to
        # produce duplicates, but the LLM occasionally ignores instructions.
        seen: set = set()
        cleaned: List[Dict[str, Any]] = []
        for s in sections:
            if not isinstance(s, dict):
                continue
            title = (s.get("title") or "").strip()
            if not title:
                continue
            norm = title.lower()
            if norm in seen:
                continue
            seen.add(norm)
            key_topics = s.get("key_topics") or []
            if not isinstance(key_topics, list):
                key_topics = []
            cleaned.append({
                "title": title,
                "key_topics": [t for t in key_topics if isinstance(t, str)][:8],
            })

        return cleaned if cleaned else None

    def _chunked_section_extraction(
        self,
        content: str,
        lesson_title: str,
    ) -> List[Dict[str, Any]]:
        """
        Legacy chunk-based section extraction, kept as a fallback for when
        the planner returns nothing usable. No hard section cap — the merge
        step handles overcounts.
        """
        chunks = self._split_content_into_chunks(content, chunk_size=2000, overlap=200)
        print(f"[ContentParser] [fallback] Split into {len(chunks)} chunks")

        all_sections: List[Dict[str, Any]] = []
        for i, chunk in enumerate(chunks):
            chunk_sections = self._extract_sections_from_chunk(chunk, lesson_title, i + 1, len(chunks))
            if chunk_sections:
                all_sections.extend(chunk_sections)

        merged = self._merge_similar_sections(all_sections)
        print(f"[ContentParser] [fallback] {len(merged)} sections after merge")
        return merged

    # =====================================================================
    # Chunk-based helpers (used by the fallback path)
    # =====================================================================

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
            prompt_pass3 = f"""Look ONLY at the content below for "{section_title}" and find concepts that the EXTRACTED list missed.

EXTRACTED: {", ".join([obj.get('title', '') for obj in objects_pass1[:8]])}

ORIGINAL CONTENT (the only source of truth — do not draw on outside knowledge):
{content_preview[:2500]}

---

STRICT RULES:
  - Only propose concepts that appear in the ORIGINAL CONTENT above. Do NOT invent.
  - Every proposed title or keyword you give MUST appear verbatim in the content.
  - If the extracted list already covers the content, return an empty array.
  - Match the language of the source content (Serbian source -> Serbian; English source -> English). Do not translate.

Return ONLY a JSON object:
{{"missing_concepts": [{{\"title\": \"...\", \"description\": \"...\", \"type\": \"...\", \"keywords\": [\"...\", \"...\"]}}]}}"""
            
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
                            'keywords': missing_obj.get('keywords', []) or [],
                        })
            
            print(f"[ContentParser] [PASS 3] Added {len(missing.get('missing_concepts', []))} missing concepts")
        
        # Validate, dedup, AND drop hallucinations (LOs whose title and
        # keywords are nowhere in the section content) and sentence-shaped
        # titles (Fix K).
        validated_objects = []
        seen_titles = set()
        dropped_ungrounded = 0
        dropped_unshaped = 0

        for obj in objects_pass1:
            if not obj.get('title'):
                continue

            title = obj.get('title', '')
            title_lower = title.lower()
            if title_lower in seen_titles:
                continue
            seen_titles.add(title_lower)

            if not self._lo_title_is_well_shaped(title):
                dropped_unshaped += 1
                print(f"[ContentParser] Dropping sentence-shaped LO: '{title[:60]}...'")
                continue

            if not self._lo_is_grounded(obj, section_content):
                dropped_ungrounded += 1
                print(f"[ContentParser] Dropping ungrounded LO: '{title}'")
                continue

            validated = {
                'title': obj.get('title', 'Unknown')[:150],
                'type': self._normalize_lo_type(obj.get('type')),
                'description': obj.get('description', '')[:600],
                'key_points': obj.get('key_points', []) if isinstance(obj.get('key_points'), list) else [],
                'keywords': obj.get('keywords', [])[:6] if isinstance(obj.get('keywords'), list) else [],
                'prerequisites': obj.get('prerequisites', []) if isinstance(obj.get('prerequisites'), list) else [],
                'related_concepts': obj.get('related_concepts', []) if isinstance(obj.get('related_concepts'), list) else [],
                'learning_outcomes': obj.get('learning_outcomes', []) if isinstance(obj.get('learning_outcomes'), list) else [],
            }
            validated_objects.append(validated)

        if dropped_ungrounded:
            print(f"[ContentParser] Dropped {dropped_ungrounded} ungrounded LO(s) (likely hallucinations)")
        if dropped_unshaped:
            print(f"[ContentParser] Dropped {dropped_unshaped} sentence-shaped LO(s)")
        
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
