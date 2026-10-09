"""Versioned data extraction grid (EF-EXT-01, EF-EXT-02, tranche 3.1).

Same principles as the eligibility criteria (``domain.criteria``): a version is a
snapshot of every field; a ``draft`` can be edited, an ``active`` version never
changes, and the next change produces a new draft that becomes active in its turn, the
previous one being ``superseded``. Field codes (D1, D2…) are stable: the same code
designates the same field in every version, and a code is never given to another field.
"""

import datetime as dt
import re
from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from revue_portee.domain.criteria import (
    EmptyCriteriaError,
    ImmutableVersionError,
    MissingRationaleError,
    VersionStatus,
)

__all__ = [
    "CHOICE_TYPES",
    "FIELD_CODE",
    "FieldModification",
    "FieldType",
    "GridDiff",
    "GridField",
    "GridTemplate",
    "GridVersion",
    "TemplateField",
    "activate",
    "diff_versions",
    "field_sort_key",
    "first_draft",
    "new_draft_from",
    "next_field_code",
    "supersede",
    "with_fields",
]


class FieldType(StrEnum):
    TEXT = "text"
    NUMBER = "number"
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    HIERARCHICAL = "hierarchical"  # choices written as paths: "Intervention > Psychological"
    BOOLEAN = "boolean"
    DATE = "date"


CHOICE_TYPES = frozenset(
    {FieldType.SINGLE_CHOICE, FieldType.MULTIPLE_CHOICE, FieldType.HIERARCHICAL}
)
FIELD_CODE = re.compile(r"^D(?P<number>[1-9][0-9]*)$")


def field_sort_key(code: str) -> tuple[int, str]:
    match = FIELD_CODE.match(code)
    return (int(match.group("number")), code) if match else (10**9, code)


def next_field_code(used: Iterable[str]) -> str:
    """The next free code: one more than the largest ever given (never reused)."""
    numbers = [int(m.group("number")) for code in used if (m := FIELD_CODE.match(code))]
    return f"D{max(numbers, default=0) + 1}"


class GridField(BaseModel):
    """One field of the grid, identified by its stable code."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(pattern=FIELD_CODE.pattern)
    label: str = Field(min_length=1)
    type: FieldType
    definition: str = ""
    guidance: str = ""
    examples: tuple[str, ...] = ()
    choices: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _choices(self) -> Self:
        if self.type in CHOICE_TYPES:
            if len(self.choices) < 2:
                raise ValueError("a choice field needs at least two choices")
            if len(set(self.choices)) != len(self.choices):
                raise ValueError("choices must be distinct")
        elif self.choices:
            raise ValueError("only choice fields have choices")
        return self


class GridVersion(BaseModel):
    """Immutable snapshot of the grid (tables ``grid_version`` + ``grid_field``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    number: int = Field(ge=1)
    parent_id: str | None
    status: VersionStatus
    created_at: AwareDatetime
    author_id: str
    rationale: str = ""
    activated_at: AwareDatetime | None = None
    fields: tuple[GridField, ...] = ()

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.number == 1) != (self.parent_id is None):
            raise ValueError("only version 1 has no parent")
        codes = [f.code for f in self.fields]
        if len(codes) != len(set(codes)):
            raise ValueError("field codes must be unique within a version")
        if (self.status is VersionStatus.DRAFT) != (self.activated_at is None):
            raise ValueError("activated_at is set exactly when the version left draft")
        return self

    def field(self, code: str) -> GridField | None:
        return next((f for f in self.fields if f.code == code), None)

    def sorted_fields(self) -> tuple[GridField, ...]:
        return tuple(sorted(self.fields, key=lambda f: field_sort_key(f.code)))


def first_draft(*, version_id: str, author_id: str, now: datetime) -> GridVersion:
    return GridVersion(
        id=version_id,
        number=1,
        parent_id=None,
        status=VersionStatus.DRAFT,
        created_at=now,
        author_id=author_id,
    )


def new_draft_from(
    base: GridVersion, *, version_id: str, author_id: str, now: datetime
) -> GridVersion:
    """Draft of the next version, starting from the fields of ``base``."""
    if base.status is VersionStatus.DRAFT:
        raise ValueError("a new draft starts from an active or superseded version")
    return GridVersion(
        id=version_id,
        number=base.number + 1,
        parent_id=base.id,
        status=VersionStatus.DRAFT,
        created_at=now,
        author_id=author_id,
        fields=base.fields,
    )


def with_fields(version: GridVersion, fields: Iterable[GridField]) -> GridVersion:
    """Same draft with another set of fields. Only drafts can change."""
    if version.status is not VersionStatus.DRAFT:
        raise ImmutableVersionError(f"grid version {version.number} is {version.status}")
    return GridVersion.model_validate(version.model_dump() | {"fields": tuple(fields)})


def activate(version: GridVersion, *, rationale: str, now: datetime) -> GridVersion:
    """Make a draft the version in force; a rationale is required from version 2 on."""
    if version.status is not VersionStatus.DRAFT:
        raise ImmutableVersionError(f"grid version {version.number} is {version.status}")
    if not version.fields:
        raise EmptyCriteriaError("a grid version needs at least one field")
    rationale = rationale.strip()
    if version.number > 1 and not rationale:
        raise MissingRationaleError("a new grid version needs a rationale")
    return version.model_copy(
        update={"status": VersionStatus.ACTIVE, "rationale": rationale, "activated_at": now}
    )


def supersede(version: GridVersion) -> GridVersion:
    if version.status is not VersionStatus.ACTIVE:
        raise ValueError("only the active version can be superseded")
    return version.model_copy(update={"status": VersionStatus.SUPERSEDED})


_COMPARED = ("label", "type", "definition", "guidance", "examples", "choices")


class FieldModification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    before: GridField
    after: GridField
    changed: tuple[str, ...]


class GridDiff(BaseModel):
    """Field-by-field difference between two versions (EF-VER-02)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    from_number: int
    to_number: int
    added: tuple[GridField, ...]
    removed: tuple[GridField, ...]
    modified: tuple[FieldModification, ...]
    unchanged: tuple[str, ...]

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.modified)


def diff_versions(old: GridVersion, new: GridVersion) -> GridDiff:
    """Added, removed and modified fields from ``old`` to ``new``, matched by code."""
    before_by_code = {f.code: f for f in old.fields}
    after_by_code = {f.code: f for f in new.fields}
    added, removed, modified, unchanged = [], [], [], []
    for code in sorted(before_by_code.keys() | after_by_code.keys(), key=field_sort_key):
        before, after = before_by_code.get(code), after_by_code.get(code)
        if before is None and after is not None:
            added.append(after)
        elif after is None and before is not None:
            removed.append(before)
        elif before is not None and after is not None:
            changed = tuple(
                name for name in _COMPARED if getattr(before, name) != getattr(after, name)
            )
            if changed:
                modified.append(
                    FieldModification(code=code, before=before, after=after, changed=changed)
                )
            else:
                unchanged.append(code)
    return GridDiff(
        from_number=old.number,
        to_number=new.number,
        added=tuple(added),
        removed=tuple(removed),
        modified=tuple(modified),
        unchanged=tuple(unchanged),
    )


class TemplateField(BaseModel):
    """A field of a starting grid, in several languages."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: FieldType
    label: dict[str, str]
    definition: dict[str, str] = Field(default_factory=dict)
    choices: dict[str, tuple[str, ...]] = Field(default_factory=dict)

    def text(self, value: dict[str, str], language: str) -> str:
        return value.get(language) or value.get("en", "")


class GridTemplate(BaseModel):
    """A starting grid, dated, with its source (``resources/extraction/``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    version: str
    date: dt.date
    source: str
    fields: tuple[TemplateField, ...] = Field(min_length=1)

    def fields_in(self, language: str) -> list[tuple[str, FieldType, str, tuple[str, ...]]]:
        """Label, type, definition and choices of each field in ``language`` (English
        when the template has no text in it)."""
        return [
            (
                f.text(f.label, language),
                f.type,
                f.text(f.definition, language),
                f.choices.get(language) or f.choices.get("en", ()),
            )
            for f in self.fields
        ]
