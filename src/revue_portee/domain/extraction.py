"""Extracted values (EF-EXT-03, EF-EXT-04, tranche 3.2).

For each included study and each field of the grid in force, the AI proposes a value,
the exact quote it rests on and its page, or says the report does not give it. A value
is never changed: the person's validation, correction or rejection is a new value that
supersedes the AI's (tranche 3.3), and the latest value on a field is in force.

When a new version of the grid is activated (EF-VER-06, tranche 3.4), each change
touches studies: an added field leaves every included study to complete; a modified
field flags the values given under its former definition, to review; a removed field
archives its values, which leave the synthesis but stay recorded (``grid_impact``). A
value is to review as long as the field it was given for differs from the field in
force (``stale``), whatever the versions in between.

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

from revue_portee.domain.fulltext import QuoteCheck, TextPage, canonical, locate_quote
from revue_portee.domain.grid import FieldType, GridDiff, GridField, GridVersion, field_changes
from revue_portee.domain.project import ReviewerKind

__all__ = [
    "HUMAN_KEPT",
    "ChangeKind",
    "ExtractionPilot",
    "ExtractionValue",
    "GridChangeImpact",
    "InvalidValueError",
    "ValueStatus",
    "current_values",
    "fields_due",
    "for_synthesis",
    "grid_impact",
    "holds_value",
    "parse_value",
    "place_quote",
    "quote_summary",
    "same_value",
    "stale",
]


class ValueStatus(StrEnum):
    PROPOSED = "proposed"  # by the AI, not checked yet
    VALIDATED = "validated"  # the person keeps the AI's value
    CORRECTED = "corrected"  # the person gives another value
    REJECTED = "rejected"  # the person rejects the AI's value without giving one
    EXTRACTED = "extracted"  # by the person without seeing the AI (pilot, or no AI value)


# Values a person decided: only they may go into the synthesis (EF-EXT-04).
HUMAN_KEPT = frozenset({ValueStatus.VALIDATED, ValueStatus.CORRECTED, ValueStatus.EXTRACTED})


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


def for_synthesis(
    values: Iterable[ExtractionValue],
) -> dict[tuple[str, str], ExtractionValue]:
    """The values that may go into the synthesis (EF-EXT-04): on each field of each
    report, the latest value a person decided (validated, corrected or extracted). A
    value proposed by the AI never goes in, nor a field whose latest human decision
    rejected the AI's value without giving another."""
    found: dict[tuple[str, str], ExtractionValue] = {}
    for value in sorted(values, key=lambda v: (v.created_at, v.id)):
        if value.reviewer_kind is not ReviewerKind.HUMAN:
            continue
        key = (value.reference_id, value.field_code)
        if value.status in HUMAN_KEPT:
            found[key] = value
        elif value.status is ValueStatus.REJECTED:
            found.pop(key, None)
    return found


def _words(text: str) -> set[str]:
    return {w for w in (canonical(part) for part in text.split()) if w}


def same_value(field: GridField, a: ExtractionValue, b: ExtractionValue) -> bool:
    """Whether two values of a field agree: both not reported, or equal values (the
    same set for a multiple choice); texts agree when one contains the other or they
    share at least half of their words (an automatic, generous measure)."""
    if not a.reported or not b.reported:
        return a.reported == b.reported
    if field.type is FieldType.TEXT:
        left, right = canonical(str(a.value)), canonical(str(b.value))
        if left and right and (left in right or right in left):
            return True
        x, y = _words(str(a.value)), _words(str(b.value))
        return bool(x and y) and len(x & y) / min(len(x), len(y)) >= 0.5
    return a.value == b.value


class ExtractionPilot(BaseModel):
    """Studies drawn with a recorded seed, extracted by the person without seeing the
    AI, to measure the AI field by field (EF-EXT-05; table ``extraction_pilot``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    number: int
    seed: int
    grid_version_id: str
    reference_ids: tuple[str, ...]
    created_at: AwareDatetime
    reviewer_id: str


# --- Changes of the grid (EF-VER-06) ------------------------------------------------


class ChangeKind(StrEnum):
    ADDED = "added"  # every included study to complete
    MODIFIED = "modified"  # the values given under the former definition, to review
    REMOVED = "removed"  # the values archived: out of the synthesis, kept recorded


class GridChangeImpact(BaseModel):
    """The studies one change of the grid touches."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ChangeKind
    code: str
    label: str
    changed: tuple[str, ...] = ()  # attributes of a modified field
    studies: tuple[str, ...]


def holds_value(value: ExtractionValue | None) -> bool:
    """Whether a value in force gives the field a value (« not reported » included): a
    rejection without another value leaves the field empty."""
    return value is not None and value.status is not ValueStatus.REJECTED


def grid_impact(
    diff: GridDiff, studies: Sequence[str], values: Iterable[ExtractionValue]
) -> tuple[GridChangeImpact, ...]:
    """The studies each change from one version to the next touches, in the order of
    ``studies`` (the included studies, by their primary report): an added field, every
    study; a modified or removed field, the studies whose value in force gives it."""
    current = current_values(values)

    def holding(code: str) -> tuple[str, ...]:
        return tuple(s for s in studies if holds_value(current.get((s, code))))

    return (
        *(GridChangeImpact(kind=ChangeKind.ADDED, code=f.code, label=f.label,
                           studies=tuple(studies)) for f in diff.added),
        *(GridChangeImpact(kind=ChangeKind.MODIFIED, code=m.code, label=m.after.label,
                           changed=m.changed, studies=holding(m.code)) for m in diff.modified),
        *(GridChangeImpact(kind=ChangeKind.REMOVED, code=f.code, label=f.label,
                           studies=holding(f.code)) for f in diff.removed),
    )  # fmt: skip


def stale(value: ExtractionValue, versions: Mapping[str, GridVersion], field: GridField) -> bool:
    """Whether ``value`` was given for a field that differs from ``field``, the field in
    force: the value is then to review."""
    made = versions.get(value.grid_version_id)
    before = None if made is None else made.field(value.field_code)
    return before is None or bool(field_changes(before, field))


def fields_due(
    grid: GridVersion,
    versions: Mapping[str, GridVersion],
    values: Iterable[ExtractionValue],
    *,
    pilot: bool = False,
) -> tuple[GridField, ...]:
    """The fields of one study the AI is to pre-fill: those it has not answered under
    their definition in force, unless the person already gave them a value under it.
    In a pilot, every field the AI has not answered, to compare with the person."""
    found = list(values)
    current = {code: v for (_ref, code), v in current_values(found).items()}
    latest_ai = {
        code: v
        for (_ref, code), v in current_values(
            v for v in found if v.reviewer_kind is ReviewerKind.AI
        ).items()
    }
    due = []
    for field in grid.sorted_fields():
        ai = latest_ai.get(field.code)
        if ai is not None and not stale(ai, versions, field):
            continue
        given = current.get(field.code)
        if pilot or given is None or stale(given, versions, field):
            due.append(field)
    return tuple(due)
