"""Extracted values (EF-EXT-03): values checked against the type of their field,
quotes placed at the page where they are, value in force."""

from datetime import UTC, datetime, timedelta

import pytest

from revue_portee.domain.extraction import (
    ExtractionValue,
    InvalidValueError,
    ValueStatus,
    current_values,
    parse_value,
    place_quote,
    quote_summary,
)
from revue_portee.domain.fulltext import QuoteCheck, TextPage
from revue_portee.domain.grid import FieldType, GridField
from revue_portee.domain.project import ReviewerKind

T0 = datetime(2026, 10, 9, tzinfo=UTC)


def _field(type: FieldType, choices: tuple[str, ...] = ()) -> GridField:
    return GridField(code="D1", label="Champ", type=type, choices=choices)


def test_values_of_each_type() -> None:
    assert parse_value(_field(FieldType.TEXT), "  Montréal ") == "Montréal"
    assert parse_value(_field(FieldType.NUMBER), "24") == 24
    assert parse_value(_field(FieldType.NUMBER), "42,5") == 42.5
    assert parse_value(_field(FieldType.NUMBER), 12) == 12
    assert parse_value(_field(FieldType.BOOLEAN), "Oui") is True
    assert parse_value(_field(FieldType.BOOLEAN), "no") is False
    assert parse_value(_field(FieldType.BOOLEAN), False) is False
    assert parse_value(_field(FieldType.DATE), "2019-03") == "2019-03"
    choices = ("Qualitatif", "Quantitatif", "Mixte")
    assert parse_value(_field(FieldType.SINGLE_CHOICE, choices), "Mixte") == "Mixte"
    assert parse_value(_field(FieldType.HIERARCHICAL, ("A > B", "A > C")), "A > C") == "A > C"
    # in the order of the choices
    assert parse_value(_field(FieldType.MULTIPLE_CHOICE, choices), ["Mixte", "Qualitatif"]) == [
        "Qualitatif", "Mixte",
    ]  # fmt: skip
    assert parse_value(_field(FieldType.MULTIPLE_CHOICE, choices), "Mixte") == ["Mixte"]


@pytest.mark.parametrize(
    ("type", "choices", "raw"),
    [
        (FieldType.TEXT, (), " "),
        (FieldType.TEXT, (), None),
        (FieldType.TEXT, (), ["a"]),
        (FieldType.NUMBER, (), "environ 24"),
        (FieldType.BOOLEAN, (), "peut-être"),
        (FieldType.DATE, (), "mars 2019"),
        (FieldType.DATE, (), "2019-13"),
        (FieldType.SINGLE_CHOICE, ("A", "B"), "C"),
        (FieldType.MULTIPLE_CHOICE, ("A", "B"), ["A", "C"]),
        (FieldType.MULTIPLE_CHOICE, ("A", "B"), []),
    ],
)
def test_invalid_values(type: FieldType, choices: tuple[str, ...], raw: object) -> None:
    with pytest.raises(InvalidValueError):
        parse_value(_field(type, choices), raw)  # type: ignore[arg-type]


PAGES = (
    TextPage(number=1, text="Title of the report"),
    TextPage(number=2, text="We interviewed 24 older adults living in three residences."),
)


def test_quotes_placed_at_their_page() -> None:
    assert place_quote(PAGES, "24 older adults", 2) == (2, QuoteCheck.AT_PAGE)
    assert place_quote(PAGES, "24 older adults", 1) == (2, QuoteCheck.OTHER_PAGE)  # corrected
    assert place_quote(PAGES, "24 older adults", None) == (2, QuoteCheck.OTHER_PAGE)
    assert place_quote(PAGES, "48 young adults", 2) == (None, QuoteCheck.NOT_FOUND)
    assert place_quote(PAGES, "", 2) == (None, None)


def _value(field: str, minute: int, check: QuoteCheck | None = None) -> ExtractionValue:
    return ExtractionValue(
        id=f"V{minute}",
        reference_id="R",
        field_code=field,
        grid_version_id="G",
        reported=True,
        value="x",
        quote_check=check,
        status=ValueStatus.PROPOSED,
        reviewer_id="AI",
        reviewer_kind=ReviewerKind.AI,
        ai_call_id="C",
        created_at=T0 + timedelta(minutes=minute),
    )


def test_value_in_force_and_quote_summary() -> None:
    values = [
        _value("D1", 2, QuoteCheck.AT_PAGE),
        _value("D1", 1),
        _value("D2", 3, QuoteCheck.NOT_FOUND),
    ]
    current = current_values(values)
    assert current["R", "D1"].id == "V2"
    assert set(current) == {("R", "D1"), ("R", "D2")}
    assert quote_summary(values) == {
        QuoteCheck.AT_PAGE: 1, QuoteCheck.OTHER_PAGE: 0, QuoteCheck.NOT_FOUND: 1,
    }  # fmt: skip
