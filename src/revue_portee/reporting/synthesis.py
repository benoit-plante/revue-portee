"""Frequency tables, cross tables, evidence maps and gaps (EF-SYN-01 to EF-SYN-03).

Pure functions on the values a person decided (``domain.extraction.for_synthesis``):
each included study gives, for each field, its categories, « not reported », or
nothing yet (« not extracted »). A choice field lists all its choices, even those no
study has, so that the empty cells of a map show; a yes-or-no field gives yes and no; a
date gives its year; a number or a text gives its value. A study counts once in each
category it has (several for a multiple choice); shares are of all included studies.

A cross table places each study in every pair of its categories on two fields; studies
without a value on either field are counted apart. A cell is a gap when it is empty, or
sparse when it holds at most ``sparse_max`` studies.
"""

from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, JsonValue

from revue_portee.domain.grid import CHOICE_TYPES, FieldType, GridField

__all__ = [
    "FRENCH",
    "CategoryLabels",
    "CrossTable",
    "FrequencyRow",
    "FrequencyTable",
    "Gap",
    "GapKind",
    "StudyData",
    "categories",
    "cross_table",
    "frequency_table",
    "gaps",
]

type Translate = Callable[[str], str]


class StudyData(BaseModel):
    """One included study as the synthesis sees it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str  # its primary report
    label: str  # first author and year, or title
    values: Mapping[str, JsonValue] = {}  # by field code: the values a person decided
    not_reported: frozenset[str] = frozenset()  # fields a person said are not reported


class CategoryLabels(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    yes: str = "oui"
    no: str = "non"


FRENCH = CategoryLabels()


def _number(value: JsonValue) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def categories(
    field: GridField, study: StudyData, labels: CategoryLabels = FRENCH
) -> tuple[str, ...] | None:
    """The categories of a study on a field: () when not reported, None when no one
    decided its value yet."""
    if field.code in study.not_reported:
        return ()
    if field.code not in study.values:
        return None
    value = study.values[field.code]
    if field.type is FieldType.MULTIPLE_CHOICE:
        chosen = value if isinstance(value, list) else [value]
        return tuple(c for c in field.choices if c in chosen)
    if field.type is FieldType.BOOLEAN:
        return (labels.yes if value is True else labels.no,)
    if field.type is FieldType.DATE:
        return (str(value)[:4],)
    if field.type is FieldType.NUMBER:
        return (_number(value),)
    return (str(value).strip(),)


def _order(field: GridField, found: set[str], labels: CategoryLabels) -> list[str]:
    if field.type in CHOICE_TYPES:
        return [*field.choices, *sorted(found - set(field.choices), key=str.casefold)]
    if field.type is FieldType.BOOLEAN:
        return [labels.yes, labels.no]
    if field.type is FieldType.NUMBER:
        return sorted(found, key=float)
    return sorted(found, key=lambda c: (c.casefold(), c))


class FrequencyRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    category: str
    studies: tuple[str, ...]  # ids, in the order of the studies given

    @property
    def count(self) -> int:
        return len(self.studies)


class FrequencyTable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    field: GridField
    total: int  # included studies
    rows: tuple[FrequencyRow, ...]
    not_reported: tuple[str, ...]
    not_extracted: tuple[str, ...]

    def share(self, row: FrequencyRow) -> float | None:
        return row.count / self.total if self.total else None


def frequency_table(
    field: GridField, studies: Sequence[StudyData], labels: CategoryLabels = FRENCH
) -> FrequencyTable:
    by_category: dict[str, list[str]] = {}
    not_reported, not_extracted = [], []
    for study in studies:
        found = categories(field, study, labels)
        if found is None:
            not_extracted.append(study.id)
        elif not found:
            not_reported.append(study.id)
        for category in found or ():
            by_category.setdefault(category, []).append(study.id)
    return FrequencyTable(
        field=field,
        total=len(studies),
        rows=tuple(
            FrequencyRow(category=c, studies=tuple(by_category.get(c, ())))
            for c in _order(field, set(by_category), labels)
        ),
        not_reported=tuple(not_reported),
        not_extracted=tuple(not_extracted),
    )


class CrossTable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rows_field: GridField
    columns_field: GridField
    rows: tuple[str, ...]
    columns: tuple[str, ...]
    cells: Mapping[tuple[str, str], tuple[str, ...]]  # (row, column) -> study ids
    placed: tuple[str, ...]  # studies with a value on both fields
    unplaced: tuple[str, ...]  # studies without a value on either field

    def studies(self, row: str, column: str) -> tuple[str, ...]:
        return self.cells.get((row, column), ())

    def count(self, row: str, column: str) -> int:
        return len(self.studies(row, column))

    @property
    def largest(self) -> int:
        return max((len(ids) for ids in self.cells.values()), default=0)


def cross_table(
    rows_field: GridField,
    columns_field: GridField,
    studies: Sequence[StudyData],
    labels: CategoryLabels = FRENCH,
) -> CrossTable:
    cells: dict[tuple[str, str], list[str]] = {}
    seen_rows: set[str] = set()
    seen_columns: set[str] = set()
    placed, unplaced = [], []
    for study in studies:
        across = categories(rows_field, study, labels)
        down = categories(columns_field, study, labels)
        if not across or not down:
            unplaced.append(study.id)
            continue
        placed.append(study.id)
        seen_rows.update(across)
        seen_columns.update(down)
        for row in across:
            for column in down:
                cells.setdefault((row, column), []).append(study.id)
    return CrossTable(
        rows_field=rows_field,
        columns_field=columns_field,
        rows=tuple(_order(rows_field, seen_rows, labels)),
        columns=tuple(_order(columns_field, seen_columns, labels)),
        cells={key: tuple(ids) for key, ids in cells.items()},
        placed=tuple(placed),
        unplaced=tuple(unplaced),
    )


class GapKind(StrEnum):
    EMPTY = "empty"
    SPARSE = "sparse"


class Gap(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    row: str
    column: str
    kind: GapKind
    count: int


def gaps(table: CrossTable, *, sparse_max: int = 1) -> tuple[Gap, ...]:
    """Empty cells, and cells with at most ``sparse_max`` studies, row by row."""
    found = []
    for row in table.rows:
        for column in table.columns:
            count = table.count(row, column)
            if count == 0:
                found.append(Gap(row=row, column=column, kind=GapKind.EMPTY, count=0))
            elif count <= sparse_max:
                found.append(Gap(row=row, column=column, kind=GapKind.SPARSE, count=count))
    return tuple(found)
