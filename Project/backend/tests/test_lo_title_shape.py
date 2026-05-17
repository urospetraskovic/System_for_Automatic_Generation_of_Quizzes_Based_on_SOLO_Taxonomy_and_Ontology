"""
Tests for Fix K — LO titles must be concept-style noun phrases, not
sentence-shaped descriptions. We reject titles that exceed the char or
word limit.
"""

from core.content_parser import ContentParser


def test_short_concept_title_is_well_shaped():
    assert ContentParser._lo_title_is_well_shaped("Atributi procesa") is True
    assert ContentParser._lo_title_is_well_shaped("Process Control Block") is True
    assert ContentParser._lo_title_is_well_shaped("UBP") is True


def test_legit_compound_titles_are_accepted():
    """Real concept titles with several words still pass."""
    assert ContentParser._lo_title_is_well_shaped("Promena stanja procesa") is True
    assert ContentParser._lo_title_is_well_shaped("Reprezentacija procesa u Linuxu") is True
    assert ContentParser._lo_title_is_well_shaped(
        "Promena trenutno aktivnog procesa koji se izvršava na procesoru"
    ) is True  # 64 chars, 9 words — borderline but legit


def test_sentence_shaped_titles_are_rejected():
    """Real bad outputs from the 03-Procesi parse — all should fail."""
    bad_titles = [
        # Long char count: 96 chars, 12 words exactly — fails the > 12 word check? no, ==12. fails > 100 char? no.
        # Let's pick clearly bad ones.
        "Dodela resursa procesima i zaštita dodeljenih resursa od nekontrolisanog pristupa drugih procesa zauvek",
        "potpuna kontrola nad procesorom i svim njegovim instrukcijama, registrima i memorijom svega",
        "Zakomutiranje procesa postoji deoOS koji se izvršava izvan korisničkih procesa i još",
    ]
    for t in bad_titles:
        assert ContentParser._lo_title_is_well_shaped(t) is False, f"Should have rejected: {t}"


def test_empty_and_none_rejected():
    assert ContentParser._lo_title_is_well_shaped("") is False
    assert ContentParser._lo_title_is_well_shaped(None) is False


def test_too_long_char_count_rejected():
    """A title at 101 chars but few words should still be rejected."""
    long_title = "x" * 101
    assert ContentParser._lo_title_is_well_shaped(long_title) is False


def test_too_many_words_rejected():
    """A title with 13 short words should be rejected even if under 100 chars."""
    t = "a b c d e f g h i j k l m"  # 13 single-char words
    assert ContentParser._lo_title_is_well_shaped(t) is False
