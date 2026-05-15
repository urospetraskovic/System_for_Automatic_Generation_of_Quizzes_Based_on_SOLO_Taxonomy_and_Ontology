"""Tests for the Serbian/English language heuristic in core/lang_detect.py."""

from core.lang_detect import detect_language, language_name


def test_empty_input_defaults_to_english():
    assert detect_language("") == "en"
    assert detect_language(None) == "en"


def test_cyrillic_detected_as_serbian():
    text = "Процес је инстанца програма који се извршава."
    assert detect_language(text) == "sr"


def test_latin_diacritics_detected_as_serbian():
    # Two-plus diacritics is the strong-signal threshold.
    text = "Šta je proces? Ovo je primer čekanja i raspoređivanja zadataka."
    assert detect_language(text) == "sr"


def test_english_text_detected_as_english():
    text = (
        "A process is an instance of a program that is currently executing. "
        "The operating system schedules processes for execution."
    )
    assert detect_language(text) == "en"


def test_serbian_stopwords_outvote_english_on_short_input():
    text = "Ovo je primer koji ilustruje pojam."
    assert detect_language(text) == "sr"


def test_language_name_mapping():
    assert language_name("en") == "English"
    assert language_name("sr") == "Serbian"
    # Unknown codes fall back to English (defensive default).
    assert language_name("xx") == "English"
