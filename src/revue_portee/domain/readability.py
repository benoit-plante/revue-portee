"""Readability of a plain-language summary (EF-CON-01, tranche 4.1).

French: Kandel and Moles (1958), the adaptation of Flesch's reading ease to French,
207 - 1.015 x (words per sentence) - 73.6 x (syllables per word). English: Flesch
(1948), 206.835 - 1.015 x (words per sentence) - 84.6 x (syllables per word). The higher
the index, the easier the text; it is read with the usual bands (90 and more very easy,
60 to 70 standard, under 30 very difficult).

Counting rules, simple and documented, so that anyone can redo the count by hand:

- a **word** is a run of letters (an apostrophe or a hyphen inside joins its parts:
  « l'étude », « peut-être » are one word) or a run of digits;
- a **sentence** ends with « . », « ! », « ? » or « … » followed by a space or the end
  of the text; a text without such an end is one sentence;
- the **syllables** of a word are its groups of vowels (y included), at least one; a
  final silent « e » is not a syllable: in French, a final « e » or « es » after a
  consonant (not « é »), in English a final « e » except « le » after a consonant; a
  number counts one syllable.
"""

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

__all__ = [
    "Band",
    "Readability",
    "band",
    "readability",
    "sentences",
    "syllables",
    "words",
]

_LETTERS = "a-zA-ZÀ-ÖØ-öø-ÿœŒæÆ"
_JOINERS = "'" + chr(0x2019) + "-"  # apostrophes, then the hyphen (last: not a range)
_WORD = re.compile(rf"[{_LETTERS}]+(?:[{_JOINERS}][{_LETTERS}]+)*|\d+(?:[.,]\d+)*")
_VOWELS = {
    "fr": re.compile(r"[aeiouyàâäéèêëîïôöùûüÿœæ]+", re.IGNORECASE),
    "en": re.compile(r"[aeiouy]+", re.IGNORECASE),
}
_SENTENCE_END = re.compile(r"[.!?…]+(?=\s|$)")


def words(text: str) -> list[str]:
    return _WORD.findall(text)


def sentences(text: str) -> int:
    """The number of sentences: the parts between sentence ends that hold a word."""
    return sum(1 for part in _SENTENCE_END.split(text) if words(part))


def syllables(word: str, language: str) -> int:
    if word[0].isdigit():
        return 1
    lower = word.casefold()
    count = len(_VOWELS[language].findall(lower))
    if language == "fr" and count > 1 and re.search(r"[^aeiouyàâäéèêëîïôöùûüÿœæ]es?$", lower):
        count -= 1
    if (
        language == "en"
        and count > 1
        and lower.endswith("e")
        and not re.search(r"[^aeiouy]le$", lower)
        and not lower.endswith(("ee", "ye"))
    ):
        count -= 1
    return max(1, count)


class Band(StrEnum):
    VERY_EASY = "very_easy"  # 90 and more
    EASY = "easy"  # 80 to 90
    FAIRLY_EASY = "fairly_easy"  # 70 to 80
    STANDARD = "standard"  # 60 to 70
    FAIRLY_DIFFICULT = "fairly_difficult"  # 50 to 60
    DIFFICULT = "difficult"  # 30 to 50
    VERY_DIFFICULT = "very_difficult"  # under 30


def band(index: float) -> Band:
    for bound, name in (
        (90, Band.VERY_EASY), (80, Band.EASY), (70, Band.FAIRLY_EASY), (60, Band.STANDARD),
        (50, Band.FAIRLY_DIFFICULT), (30, Band.DIFFICULT),
    ):  # fmt: skip
        if index >= bound:
            return name
    return Band.VERY_DIFFICULT


class Readability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    formula: str  # « Kandel-Moles » or « Flesch »
    index: float
    words: int
    sentences: int
    syllables: int

    @property
    def band(self) -> Band:
        return band(self.index)

    @property
    def words_per_sentence(self) -> float:
        return self.words / self.sentences

    @property
    def syllables_per_word(self) -> float:
        return self.syllables / self.words


def readability(text: str, language: str) -> Readability | None:
    """The readability index of ``text`` in ``language`` (fr or en); None without words."""
    found = words(text)
    if not found:
        return None
    count = sentences(text)
    syllable_count = sum(syllables(w, language) for w in found)
    per_sentence, per_word = len(found) / count, syllable_count / len(found)
    if language == "fr":
        formula, index = "Kandel-Moles", 207 - 1.015 * per_sentence - 73.6 * per_word
    else:
        formula, index = "Flesch", 206.835 - 1.015 * per_sentence - 84.6 * per_word
    return Readability(
        formula=formula, index=round(index, 1), words=len(found), sentences=count,
        syllables=syllable_count,
    )  # fmt: skip
