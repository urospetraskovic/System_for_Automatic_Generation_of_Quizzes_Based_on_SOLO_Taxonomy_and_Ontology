"""
Tests for the page-aware section count guideline used in
_plan_lesson_outline. The point of these tests is to verify the math: slide
decks (short pages) get a per-page target; prose gets a per-char target.

We can't easily test the full _plan_lesson_outline (it calls Ollama), so we
test the heuristic logic in isolation by reading the same `rough_target`
formula and asserting the numbers come out reasonable.
"""


def _rough_target(char_count: int, page_count: int) -> int:
    """Mirror of the heuristic inside _plan_lesson_outline for test purposes."""
    if page_count and char_count / max(1, page_count) < 600:
        return max(5, min(40, page_count // 2))
    return max(3, min(35, char_count // 1800))


def test_short_page_slide_deck_uses_page_heuristic():
    """32-page slide deck with 8.5k chars: ~265 chars/page → slide heuristic."""
    target = _rough_target(char_count=8456, page_count=32)
    assert target == 16  # 32 // 2
    # Sanity: under the OLD prose heuristic this would have been 4.
    assert target > 4


def test_large_slide_deck_caps_at_40():
    target = _rough_target(char_count=20000, page_count=120)
    assert target == 40  # would be 60 without the cap


def test_prose_lesson_uses_char_heuristic():
    """Dense prose: 12k chars in 6 pages = 2000 chars/page → prose heuristic."""
    target = _rough_target(char_count=12000, page_count=6)
    assert target == 6  # 12000 // 1800


def test_no_pages_meta_falls_back_to_char_heuristic():
    """If page_count is 0, we can't use the slide heuristic — use chars only."""
    target = _rough_target(char_count=8456, page_count=0)
    assert target == 4  # 8456 // 1800 = 4


def test_short_slide_deck_has_floor_of_5():
    target = _rough_target(char_count=500, page_count=4)  # very small slide deck
    assert target == 5  # the min for the slide heuristic


def test_03_procesi_estimate():
    """The Procesi lesson: 65 pages, 17k chars → should target ~32 sections."""
    target = _rough_target(char_count=17001, page_count=65)
    assert target == 32  # 65 // 2
