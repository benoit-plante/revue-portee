"""Readability index (EF-CON-01): Kandel-Moles in French, Flesch in English, on texts
counted by hand (words, sentences, syllables written out below)."""

import pytest

from revue_portee.domain.readability import (
    Band,
    band,
    readability,
    sentences,
    syllables,
    words,
)


def test_french_counted_by_hand() -> None:
    # Le(1) chat(1) dort(1). Il(1) fait(1) beau(1).  6 words, 2 sentences, 6 syllables
    # 207 - 1.015 x 3 - 73.6 x 1 = 130.355
    short = readability("Le chat dort. Il fait beau.", "fr")
    assert short is not None
    assert (short.formula, short.words, short.sentences, short.syllables) == (
        "Kandel-Moles", 6, 2, 6,
    )  # fmt: skip
    assert short.index == 130.4
    assert short.band is Band.VERY_EASY
    # Les(1) études(é-u-[es] 2) incluses(i-u-[es] 2) décrivent(é-i-e 3)
    # l'observance(o-e-a-[e] 3) du(1) traitement(ai-e-e 3): 7 words, 1 sentence, 15
    # 207 - 1.015 x 7 - 73.6 x 15 / 7 = 42.18
    long = readability("Les études incluses décrivent l'observance du traitement.", "fr")
    assert long is not None
    assert (long.words, long.sentences, long.syllables, long.index) == (7, 1, 15, 42.2)
    assert long.band is Band.DIFFICULT
    assert long.words_per_sentence == 7
    assert long.syllables_per_word == 15 / 7


def test_english_counted_by_hand() -> None:
    # The(1) cat(1) sleeps(1). It(1) is(1) a(1) simple(2) table(2).  8, 2, 10
    # 206.835 - 1.015 x 4 - 84.6 x 1.25 = 97.025
    found = readability("The cat sleeps. It is a simple table.", "en")
    assert found is not None
    assert (found.formula, found.words, found.sentences, found.syllables) == (
        "Flesch", 8, 2, 10,
    )  # fmt: skip
    assert found.index == 97.0


@pytest.mark.parametrize(
    ("word", "language", "count"),
    [
        ("tables", "fr", 1), ("rue", "fr", 1), ("été", "fr", 2), ("jeunes", "fr", 1),
        ("2024", "fr", 1), ("make", "en", 1), ("free", "en", 1), ("simple", "en", 2),
        ("rhythm", "en", 1), ("the", "en", 1), ("adherence", "en", 3),
    ],
)  # fmt: skip
def test_syllables(word: str, language: str, count: int) -> None:
    assert syllables(word, language) == count


def test_words_and_sentences() -> None:
    apostrophe = chr(0x2019)
    assert words(f"l{apostrophe}étude, peut-être 3,5 % qu'il a)b") == [
        f"l{apostrophe}étude", "peut-être", "3,5", "qu'il", "a", "b",
    ]  # fmt: skip
    assert sentences("Un. Deux? Trois!") == 3
    assert sentences("Pas de fin") == 1
    assert sentences("3.5 est un nombre.") == 1  # a point inside a number ends nothing
    assert sentences("Fin… Suite.") == 2
    assert readability(" … ", "fr") is None


@pytest.mark.parametrize(
    ("index", "expected"),
    [
        (90, Band.VERY_EASY), (89.9, Band.EASY), (80, Band.EASY), (70, Band.FAIRLY_EASY),
        (60, Band.STANDARD), (59.9, Band.FAIRLY_DIFFICULT), (30, Band.DIFFICULT),
        (29.9, Band.VERY_DIFFICULT), (-12, Band.VERY_DIFFICULT),
    ],
)  # fmt: skip
def test_bands(index: float, expected: Band) -> None:
    assert band(index) is expected
