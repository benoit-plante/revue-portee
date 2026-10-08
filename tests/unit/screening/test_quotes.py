"""The rule that tells whether a quote of the AI is in the title or abstract."""

import pytest

from revue_portee.screening.ai_screening import quote_found, searchable_text

TEXT = searchable_text(
    "Logement et santé mentale des aînés",
    "Cette étude porte sur les <i>aînés</i> vivant seuls, à Montréal.",
)


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("santé mentale des aînés", True),  # word for word
        ("SANTE MENTALE", True),  # case and accents set aside
        ("aînés vivant seuls a Montreal", True),  # markup and punctuation set aside
        ("des personnes aînées", False),  # paraphrase
        ("older adults", False),  # made up
        ("", None),  # no quote: not checked
    ],
)
def test_quote_found(quote: str, expected: bool | None) -> None:
    assert quote_found(quote, TEXT) is expected
