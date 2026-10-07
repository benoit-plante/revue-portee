"""Versioned eligibility criteria (EF-CAD-03 to 05, EF-VER-01, EF-VER-02).

A criteria version is a snapshot of the whole set of criteria. A ``draft`` can be
edited; once ``active`` it is immutable, and the next change produces a new draft
(number + 1) that becomes active in its turn, the previous one being ``superseded``.
Criterion codes are stable: the same code designates the same criterion in every
version.
"""

import re
from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "CODE_PREFIXES",
    "CRITERION_CODE",
    "CriteriaDiff",
    "CriteriaVersion",
    "Criterion",
    "CriterionKind",
    "CriterionModification",
    "EmptyCriteriaError",
    "ImmutableVersionError",
    "MissingRationaleError",
    "PccElement",
    "VersionStatus",
    "activate",
    "code_sort_key",
    "diff_versions",
    "first_draft",
    "new_draft_from",
    "supersede",
    "with_criteria",
]


class PccElement(StrEnum):
    POPULATION = "population"
    CONCEPT = "concept"
    CONTEXT = "context"
    OTHER = "other"  # cross-cutting: source type, language, period, design


class CriterionKind(StrEnum):
    INCLUSION = "inclusion"
    EXCLUSION = "exclusion"


class VersionStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUPERSEDED = "superseded"


# Code prefix per PCC element: P1, C2, CTX1, and X1 for cross-cutting dimensions
# (source type, language, period, design), as in EF-CAD-03.
CODE_PREFIXES: dict[PccElement, str] = {
    PccElement.POPULATION: "P",
    PccElement.CONCEPT: "C",
    PccElement.CONTEXT: "CTX",
    PccElement.OTHER: "X",
}
CRITERION_CODE = re.compile(r"^(?P<prefix>CTX|P|C|X)(?P<number>[1-9][0-9]*)$")
_PREFIX_ORDER = {"P": 0, "C": 1, "CTX": 2, "X": 3}


def code_sort_key(code: str) -> tuple[int, int, str]:
    """Natural order of codes: P1, P2, …, C1, …, CTX1, …, X1, … (P10 after P9)."""
    match = CRITERION_CODE.match(code)
    if match is None:
        return (len(_PREFIX_ORDER), 0, code)
    return (_PREFIX_ORDER[match.group("prefix")], int(match.group("number")), code)


class Criterion(BaseModel):
    """One eligibility criterion, identified by its stable code."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(pattern=CRITERION_CODE.pattern)
    pcc_element: PccElement
    kind: CriterionKind
    text: str = Field(min_length=1)
    guidance: str = ""
    examples: tuple[str, ...] = ()
    counterexamples: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _code_matches_element(self) -> Self:
        match = CRITERION_CODE.match(self.code)
        if match is None or match.group("prefix") != CODE_PREFIXES[self.pcc_element]:
            raise ValueError(f"code {self.code} does not match element {self.pcc_element}")
        return self


class ImmutableVersionError(Exception):
    """Raised on any attempt to change a criteria version that is not a draft."""


class MissingRationaleError(ValueError):
    """Raised when a new version (number > 1) is activated without a rationale (EF-VER-01)."""


class EmptyCriteriaError(ValueError):
    """Raised when a version without any criterion is activated."""


class CriteriaVersion(BaseModel):
    """Immutable snapshot of the criteria (table ``criteria_version`` + ``criterion``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    number: int = Field(ge=1)
    parent_id: str | None
    status: VersionStatus
    created_at: AwareDatetime
    author_id: str
    rationale: str = ""
    activated_at: AwareDatetime | None = None
    after_protocol_registration: bool = False
    criteria: tuple[Criterion, ...] = ()

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.number == 1) != (self.parent_id is None):
            raise ValueError("only version 1 has no parent")
        codes = [criterion.code for criterion in self.criteria]
        if len(codes) != len(set(codes)):
            raise ValueError("criterion codes must be unique within a version")
        if (self.status is VersionStatus.DRAFT) != (self.activated_at is None):
            raise ValueError("activated_at is set exactly when the version left draft")
        return self

    def criterion(self, code: str) -> Criterion | None:
        return next((c for c in self.criteria if c.code == code), None)

    def sorted_criteria(self) -> tuple[Criterion, ...]:
        return tuple(sorted(self.criteria, key=lambda c: code_sort_key(c.code)))


def first_draft(*, version_id: str, author_id: str, now: datetime) -> CriteriaVersion:
    """Empty version 1, in draft."""
    return CriteriaVersion(
        id=version_id,
        number=1,
        parent_id=None,
        status=VersionStatus.DRAFT,
        created_at=now,
        author_id=author_id,
    )


def new_draft_from(
    base: CriteriaVersion, *, version_id: str, author_id: str, now: datetime
) -> CriteriaVersion:
    """Draft of the next version, starting from the criteria of ``base``."""
    if base.status is VersionStatus.DRAFT:
        raise ValueError("a new draft starts from an active or superseded version")
    return CriteriaVersion(
        id=version_id,
        number=base.number + 1,
        parent_id=base.id,
        status=VersionStatus.DRAFT,
        created_at=now,
        author_id=author_id,
        criteria=base.criteria,
    )


def with_criteria(version: CriteriaVersion, criteria: Iterable[Criterion]) -> CriteriaVersion:
    """Same draft with another set of criteria. Only drafts can change."""
    if version.status is not VersionStatus.DRAFT:
        raise ImmutableVersionError(f"criteria version {version.number} is {version.status}")
    return CriteriaVersion.model_validate(version.model_dump() | {"criteria": tuple(criteria)})


def activate(version: CriteriaVersion, *, rationale: str, now: datetime) -> CriteriaVersion:
    """Make a draft the version in force. A rationale is required from version 2 on."""
    if version.status is not VersionStatus.DRAFT:
        raise ImmutableVersionError(f"criteria version {version.number} is {version.status}")
    if not version.criteria:
        raise EmptyCriteriaError("a criteria version needs at least one criterion")
    rationale = rationale.strip()
    if version.number > 1 and not rationale:
        raise MissingRationaleError("a new criteria version needs a rationale")
    return version.model_copy(
        update={"status": VersionStatus.ACTIVE, "rationale": rationale, "activated_at": now}
    )


def supersede(version: CriteriaVersion) -> CriteriaVersion:
    """Mark the active version as replaced by a newer one."""
    if version.status is not VersionStatus.ACTIVE:
        raise ValueError("only the active version can be superseded")
    return version.model_copy(update={"status": VersionStatus.SUPERSEDED})


_COMPARED_FIELDS = ("pcc_element", "kind", "text", "guidance", "examples", "counterexamples")


class CriterionModification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    before: Criterion
    after: Criterion
    changed_fields: tuple[str, ...]


class CriteriaDiff(BaseModel):
    """Criterion-by-criterion difference between two versions (EF-VER-02)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    from_number: int
    to_number: int
    added: tuple[Criterion, ...]
    removed: tuple[Criterion, ...]
    modified: tuple[CriterionModification, ...]
    unchanged: tuple[str, ...]

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.modified)


def diff_versions(old: CriteriaVersion, new: CriteriaVersion) -> CriteriaDiff:
    """Added, removed and modified criteria from ``old`` to ``new``, matched by code."""
    old_by_code = {c.code: c for c in old.criteria}
    new_by_code = {c.code: c for c in new.criteria}
    codes = sorted(old_by_code.keys() | new_by_code.keys(), key=code_sort_key)
    added: list[Criterion] = []
    removed: list[Criterion] = []
    modified: list[CriterionModification] = []
    unchanged: list[str] = []
    for code in codes:
        before, after = old_by_code.get(code), new_by_code.get(code)
        if before is None and after is not None:
            added.append(after)
        elif after is None and before is not None:
            removed.append(before)
        elif before is not None and after is not None:
            changed = tuple(f for f in _COMPARED_FIELDS if getattr(before, f) != getattr(after, f))
            if changed:
                modified.append(
                    CriterionModification(
                        code=code, before=before, after=after, changed_fields=changed
                    )
                )
            else:
                unchanged.append(code)
    return CriteriaDiff(
        from_number=old.number,
        to_number=new.number,
        added=tuple(added),
        removed=tuple(removed),
        modified=tuple(modified),
        unchanged=tuple(unchanged),
    )
