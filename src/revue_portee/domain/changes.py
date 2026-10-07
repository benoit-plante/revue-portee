"""Qualification of the changes between two criteria versions (EF-VER-03).

Every change is qualified: an added or removed criterion is qualified by the change
itself; a modified criterion is a *broadening* (more inclusive), a *narrowing* (more
exclusive) or a *clarification* (no intended change of scope). The AI may propose the
qualification of a modification; a human always confirms it before the new version is
in force. The impact analysis (EF-VER-04) will rely on these qualifications.
"""

from collections.abc import Mapping
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from revue_portee.domain.criteria import CriteriaDiff, CriteriaVersion, Criterion, code_sort_key
from revue_portee.domain.project import ReviewerKind

__all__ = [
    "MODIFICATION_TYPES",
    "ChangeType",
    "CriterionChange",
    "QualificationError",
    "QualificationProposal",
    "qualify",
]


class ChangeType(StrEnum):
    BROADENING = "broadening"
    NARROWING = "narrowing"
    CLARIFICATION = "clarification"
    ADDED = "added"
    REMOVED = "removed"


MODIFICATION_TYPES: tuple[ChangeType, ...] = (
    ChangeType.BROADENING,
    ChangeType.NARROWING,
    ChangeType.CLARIFICATION,
)


class QualificationError(ValueError):
    """The qualifications given do not match the changes of the version."""

    def __init__(self, *, missing: tuple[str, ...] = (), invalid: tuple[str, ...] = ()) -> None:
        self.missing = missing
        self.invalid = invalid
        super().__init__(f"missing: {list(missing)}; invalid: {list(invalid)}")


class QualificationProposal(BaseModel):
    """A qualification proposed by the AI for a criterion modified in a draft.

    It only applies while the draft criterion is still the one that was qualified.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    draft_version_id: str
    code: str
    ai_call_id: str
    change_type: ChangeType
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: str = ""
    after: Criterion
    created_at: AwareDatetime

    def applies_to(self, draft: CriteriaVersion) -> bool:
        return draft.id == self.draft_version_id and draft.criterion(self.code) == self.after


class CriterionChange(BaseModel):
    """Confirmed qualification of one change (table ``criterion_change``, ENF-TRA-01)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    from_version_id: str
    to_version_id: str
    code: str
    change_type: ChangeType
    proposed_by: ReviewerKind  # who proposed the type: the AI or the human
    proposal_id: str | None = None
    confirmed_by: str  # human reviewer id
    created_at: AwareDatetime


def qualify(diff: CriteriaDiff, choices: Mapping[str, ChangeType]) -> list[tuple[str, ChangeType]]:
    """Qualification of every change of ``diff``, in code order.

    Added and removed criteria are qualified automatically. ``choices`` must give a
    modification type (broadening, narrowing or clarification) for each modified
    criterion, and nothing else.
    """
    modified = {m.code for m in diff.modified}
    missing = tuple(sorted(modified - choices.keys(), key=code_sort_key))
    invalid = tuple(
        sorted(
            (
                code
                for code, kind in choices.items()
                if code not in modified or kind not in MODIFICATION_TYPES
            ),
            key=code_sort_key,
        )
    )
    if missing or invalid:
        raise QualificationError(missing=missing, invalid=invalid)
    result = [(c.code, ChangeType.ADDED) for c in diff.added]
    result += [(c.code, ChangeType.REMOVED) for c in diff.removed]
    result += [(code, choices[code]) for code in modified]
    return sorted(result, key=lambda item: code_sort_key(item[0]))
