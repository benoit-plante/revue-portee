"""Extracted values (EF-EXT-03, EF-EXT-04, tranche 3.2).

For each included study and each field of the grid in force, the AI proposes a value,
the exact quote it rests on and its page, or says the report does not give it. A value
is never changed: the person's validation, correction or rejection is a new value that
supersedes the AI's (tranche 3.3), and the latest value on a field is in force.

Every quote is looked for in the text (``domain.fulltext.check_quote``). A quote found
at another page than the one given is placed at the page where it is, the page the
model gave being kept; a quote found nowhere is kept, flagged, and the value has no
page: the value then needs the person's check before anything else. So every page
shown with a quote is a page where the quote is.
"""

import datetime as dt
import re
from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, JsonValue

from revue_portee.domain.fulltext import QuoteCheck, TextPage, locate_quote
from revue_portee.domain.grid import FieldType, GridField
from revue_portee.domain.project import ReviewerKind

__all__ = [
    "ExtractionValue",
    "InvalidValueError",
    "ValueStatus",
    "current_values",
    "parse_value",
    "place_quote",
    "quote_summary",
]


class ValueStatus(StrEnum):
    PROPOSED = "proposed"  # by the AI, not checked yet
    VALIDATED = "validated"  # the person keeps the AI's value
    CORRECTED = "corrected"  # the person gives another value
    REJECTED = "rejected"  # the person rejects the AI's value without giving one


class InvalidValueError(ValueError):
    """A value that does not fit the type of its field."""


_TRUE = {"yes", "oui", "true", "vrai", "1"}
_FALSE = {"no", "non", "false", "faux", "0"}
_NUMBER = re.compile(r"^-?\d+(?:[.,]\d+)?$")
_DATE = re.compile(r"^\d{4}(?:-\d{2}(?:-\d{2})?)?$")


def parse_value(field: GridField, raw: JsonValue) -> JsonValue:
    """``raw`` as the type of ``field`` wants it: text, a number, one of the choices,
    a list of choices, yes or no (a boolean), or a date (``YYYY``, ``YYYY-MM`` or
    ``YYYY-MM-DD``). InvalidValueError otherwise."""
    if field.type is FieldType.MULTIPLE_CHOICE:
        items = raw if isinstance(raw, list) else [raw]
        values = [str(item).strip() for item in items if str(item).strip()]
        unknown = [v for v in values if v not in field.choices]
        if unknown or not values:
            raise InvalidValueError(f"{field.code}: not among the choices: {unknown}")
        return [c for c in field.choices if c in values]  # in the order of the choices
    if isinstance(raw, list | dict):
        raise InvalidValueError(f"{field.code}: one value expected")
    if field.type is FieldType.BOOLEAN:
        if isinstance(raw, bool):
            return raw
        text = str(raw).strip().casefold()
        if text in _TRUE or text in _FALSE:
            return text in _TRUE
        raise InvalidValueError(f"{field.code}: yes or no expected")
    text = "" if raw is None else str(raw).strip()
    if not text:
        raise InvalidValueError(f"{field.code}: empty value")
    if field.type is FieldType.NUMBER:
        if isinstance(raw, int | float) and not isinstance(raw, bool):
            return raw
        if not _NUMBER.match(text):
            raise InvalidValueError(f"{field.code}: a number expected")
        number = float(text.replace(",", "."))
        return int(number) if number.is_integer() else number
    if field.type in (FieldType.SINGLE_CHOICE, FieldType.HIERARCHICAL):
        if text not in field.choices:
            raise InvalidValueError(f"{field.code}: not among the choices: {text}")
        return text
    if field.type is FieldType.DATE:
        if not _DATE.match(text):
            raise InvalidValueError(f"{field.code}: a date YYYY, YYYY-MM or YYYY-MM-DD expected")
        parts = [int(p) for p in text.split("-")]
        try:
            dt.date(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)
        except ValueError as error:
            raise InvalidValueError(f"{field.code}: not a date: {text}") from error
        return text
    return text


def place_quote(
    pages: Sequence[TextPage], quote: str, page: int | None
) -> tuple[int | None, QuoteCheck | None]:
    """The page to show with ``quote`` and the result of its check: the page given when
    the quote is there, otherwise the first page where it is, otherwise none."""
    if not quote:
        return None, None
    location = locate_quote(pages, quote)
    if not location.found:
        return None, QuoteCheck.NOT_FOUND
    if page is not None and any(page in spanned for spanned in location.pages):
        return page, QuoteCheck.AT_PAGE
    return location.first_page, QuoteCheck.OTHER_PAGE


class ExtractionValue(BaseModel):
    """One value of one field for one report (table ``extraction_value``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    reference_id: str  # the report the value comes from
    field_code: str
    grid_version_id: str
    reported: bool  # False: the report does not give it (« non rapporté »)
    value: JsonValue = None
    quote: str = ""
    page: int | None = None  # a page where the quote is (checked by the tool)
    model_page: int | None = None  # the page the AI gave
    quote_check: QuoteCheck | None = None
    status: ValueStatus
    reviewer_id: str
    reviewer_kind: ReviewerKind
    supersedes_id: str | None = None
    ai_call_id: str | None = None
    note: str = ""
    created_at: AwareDatetime


def current_values(
    values: Iterable[ExtractionValue],
) -> dict[tuple[str, str], ExtractionValue]:
    """The value in force on each field of each report: the latest one."""
    found: dict[tuple[str, str], ExtractionValue] = {}
    for value in sorted(values, key=lambda v: (v.created_at, v.id)):
        found[value.reference_id, value.field_code] = value
    return found


def quote_summary(values: Iterable[ExtractionValue]) -> Mapping[QuoteCheck, int]:
    """Quotes of the AI by result of their check (values without a quote aside)."""
    counts = dict.fromkeys(QuoteCheck, 0)
    for value in values:
        if value.quote_check is not None:
            counts[value.quote_check] += 1
    return counts
