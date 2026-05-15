"""
Lightweight language detection for lesson content.

We only need to distinguish Serbian (Latin or Cyrillic) from English here —
the Ollama model handles generation in either. A heuristic on diacritics +
Cyrillic ranges + a tiny stop-word check is enough; adding a full langdetect
dependency for two languages would be overkill.
"""

import re
from typing import Literal

LANG_EN = "en"
LANG_SR = "sr"
LangCode = Literal["en", "sr"]

# Serbian Latin-script diacritics (NFC).
_SR_DIACRITICS = re.compile(r"[čćžšđČĆŽŠĐ]")
# Cyrillic range (covers Serbian Cyrillic — close enough for this use case).
_CYRILLIC = re.compile(r"[Ѐ-ӿ]")
# Very common Serbian words (Latin + Cyrillic forms) that English doesn't share.
_SR_WORDS = re.compile(
    r"\b(je|su|nije|jeste|koji|koja|koje|sa|kao|ali|ili|ovo|onaj|takođe|pojam|primer|"
    r"је|су|није|који|која|које|са|као|али|или|ово|онај|такође|појам|пример)\b",
    re.IGNORECASE,
)
# A couple of generic English words to push the score toward English on short EN samples.
_EN_WORDS = re.compile(
    r"\b(the|of|and|is|are|that|this|with|from|which|because)\b",
    re.IGNORECASE,
)


def detect_language(text: str) -> LangCode:
    """Return 'sr' or 'en' for the given text. Defaults to 'en' for empty input."""
    if not text:
        return LANG_EN
    sample = text[:5000]

    if _CYRILLIC.search(sample):
        return LANG_SR

    sr_diacritic_hits = len(_SR_DIACRITICS.findall(sample))
    sr_word_hits = len(_SR_WORDS.findall(sample))
    sr_hits = sr_diacritic_hits + sr_word_hits
    en_hits = len(_EN_WORDS.findall(sample))

    # Diacritics are the strongest signal — even one or two means Serbian Latin.
    if sr_diacritic_hits >= 2:
        return LANG_SR
    # Otherwise compare relative counts: Serbian wins on any tie or majority.
    if sr_hits > en_hits and sr_hits >= 1:
        return LANG_SR
    return LANG_EN


def language_name(code: LangCode) -> str:
    return {"sr": "Serbian", "en": "English"}.get(code, "English")
