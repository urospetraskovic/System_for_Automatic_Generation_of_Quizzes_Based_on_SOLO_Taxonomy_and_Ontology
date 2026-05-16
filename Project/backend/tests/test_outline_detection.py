"""
Tests for ContentParser._detect_outline — language-agnostic detection of a
table-of-contents page. The detector keys on STRUCTURE (short page, list-like,
items reappear later) rather than label keywords, so it should fire whether
the TOC is called "Sadržaj", "Contents", "Curriculum", or nothing at all.
"""

from core.content_parser import ContentParser


def _build(pages):
    """Build (content, pages_meta) from a list of page strings."""
    parts, meta = [], []
    offset = 0
    for i, text in enumerate(pages, start=1):
        marker = f"\n--- Page {i} ---\n"
        parts.append(marker)
        offset += len(marker)
        start = offset
        parts.append(text)
        offset += len(text)
        meta.append({
            'page': i,
            'char_count': len(text.strip()),
            'start_offset': start,
            'end_offset': offset,
        })
    return "".join(parts), meta


def test_serbian_sadrzaj_detected():
    """The original failing case: Sadržaj page with 6 chapters that all reappear."""
    pages = [
        "Title slide",
        "Sadržaj\nPojam procesa\nStanja procesa\nUpravljačke strukture procesa\nUpravljanje procesom\nMeđuprocesna komunikacija\nIzvršavanje OS",
        "OS upravlja izvršavanjem aplikacija...",
        "Pojam procesa\nProces je program u izvršavanju.",
        "Stanja procesa\nProces ima više stanja.",
        "Upravljačke strukture procesa\nUBP je struktura...",
        "Upravljanje procesom\nKomutiranje između procesa...",
        "Međuprocesna komunikacija\nDeljena memorija i razmena poruka.",
        "Izvršavanje OS\nKako se OS izvršava.",
    ]
    content, meta = _build(pages)
    outline = ContentParser._detect_outline(content, meta)
    assert outline is not None
    assert "Pojam procesa" in outline
    assert "Izvršavanje OS" in outline


def test_english_contents_detected():
    """Same structure with 'Contents' label, English chapter names."""
    pages = [
        "Title slide",
        "Contents\nIntroduction to Threads\nThread Lifecycle\nSynchronization Primitives\nDeadlock Avoidance\nThread Pools",
        "Introduction to Threads\nA thread is a unit of execution.",
        "Thread Lifecycle\nThreads go through states.",
        "Synchronization Primitives\nMutexes and semaphores.",
        "Deadlock Avoidance\nFour conditions for deadlock.",
        "Thread Pools\nReusing worker threads.",
    ]
    content, meta = _build(pages)
    outline = ContentParser._detect_outline(content, meta)
    assert outline is not None
    assert "Introduction to Threads" in outline
    assert "Thread Pools" in outline


def test_unlabelled_outline_detected_via_reappearance():
    """No 'Contents' / 'Sadržaj' label at all — pure structure."""
    pages = [
        "Course slides",
        "Curriculum overview:\nVariables\nFunctions\nClasses\nModules",
        "Variables\nA variable holds a value.",
        "Functions\nA function is a reusable block of code.",
        "Classes\nA class encapsulates state and behaviour.",
        "Modules\nA module groups related code.",
    ]
    content, meta = _build(pages)
    outline = ContentParser._detect_outline(content, meta)
    assert outline is not None
    assert "Variables" in outline
    assert "Modules" in outline


def test_random_short_page_not_a_toc():
    """A short page whose lines DON'T reappear later is not a TOC."""
    pages = [
        "Title slide",
        "Author info\nJohn Doe\nUniversity of X\n2024",  # short, list-like, but items don't reappear
        "Page three with prose about photosynthesis and chlorophyll.",
        "Page four about Calvin cycle and carbon fixation.",
    ]
    content, meta = _build(pages)
    outline = ContentParser._detect_outline(content, meta)
    assert outline is None  # items don't reappear → not a TOC


def test_too_few_items_not_a_toc():
    """A short page with only 1-2 list items isn't enough to call it a TOC."""
    pages = [
        "Title slide",
        "Header\nOne item",  # only 1 candidate item
        "Header\nOne item appears here later.",
    ]
    content, meta = _build(pages)
    outline = ContentParser._detect_outline(content, meta)
    assert outline is None


def test_no_pages_meta_returns_none():
    assert ContentParser._detect_outline("any content", None) is None
    assert ContentParser._detect_outline("any content", []) is None


def test_long_page_excluded():
    """A page with >800 chars can't be a TOC (TOCs are short slides)."""
    long_page = "Sadržaj\n" + "Pojam procesa\n" * 200  # very long
    pages = [
        "Title",
        long_page,
        "Pojam procesa",
        "Pojam procesa",
        "Pojam procesa",
    ]
    content, meta = _build(pages)
    outline = ContentParser._detect_outline(content, meta)
    assert outline is None
