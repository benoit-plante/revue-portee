"""Impact analysis of a criteria change (EF-VER-04, docs/03-architecture.md §7).

For each qualified change of a new criteria version, the references touched are found
from the current state of the screening, that is the final human decision on each
reference (reconciliation or reassessment if any, else the independent decision):

- broadening of a criterion: references excluded that cite it;
- narrowing: references included or uncertain;
- clarification: references whose decision cites it, whatever its value;
- added criterion: references still in the stage (included or uncertain);
- removed criterion: references excluded for that criterion only.

References not screened yet are not touched: they will be screened with the new
version. A clarification is reassessed on a random sample of the references it
touches, drawn with a recorded seed; the other changes reassess every reference.
"""

import math
from collections.abc import Iterable, Mapping, Sequence

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from revue_portee.domain.changes import ChangeType
from revue_portee.domain.criteria import code_sort_key
from revue_portee.domain.screening import DecisionValue, draw_sample, keeps

__all__ = [
    "CLARIFICATION_SAMPLE_FRACTION",
    "CLARIFICATION_SAMPLE_MINIMUM",
    "ChangeImpact",
    "Impact",
    "ImpactAssessment",
    "ReferenceState",
    "affected",
    "assess_impact",
    "clarification_sample_size",
    "reassessment_set",
]

# Share and minimum number of the references touched by clarifications only that are
# reassessed (D-077); every reference is reassessed when there are fewer.
CLARIFICATION_SAMPLE_FRACTION = 0.2
CLARIFICATION_SAMPLE_MINIMUM = 20


class ReferenceState(BaseModel):
    """Current state of a screened reference: its final human decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reference_id: str
    value: DecisionValue
    criteria_cited: tuple[str, ...] = ()


class ChangeImpact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    change_type: ChangeType
    reference_ids: tuple[str, ...]  # sorted


class Impact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    changes: tuple[ChangeImpact, ...]  # in code order
    touched: tuple[str, ...] = Field(description="every reference touched, sorted")

    def by_reference(self) -> dict[str, tuple[ChangeImpact, ...]]:
        found: dict[str, list[ChangeImpact]] = {}
        for change in self.changes:
            for reference_id in change.reference_ids:
                found.setdefault(reference_id, []).append(change)
        return {ref: tuple(changes) for ref, changes in found.items()}


class ImpactAssessment(BaseModel):
    """An impact analysis recorded for a new criteria version (``impact_assessment``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    from_version_id: str
    to_version_id: str
    main_round_id: str
    impact: Impact
    reassessment_round_id: str | None = None
    seed: int
    sampled: bool  # clarifications reassessed on a sample
    created_at: AwareDatetime
    reviewer_id: str


def affected(code: str, change_type: ChangeType, state: ReferenceState) -> bool:
    """Whether the change of the criterion ``code`` touches a reference (EF-VER-04)."""
    cited = code in state.criteria_cited
    excluded = state.value is DecisionValue.EXCLUDE
    match change_type:
        case ChangeType.BROADENING:
            return excluded and cited
        case ChangeType.NARROWING | ChangeType.ADDED:
            return keeps(state.value)
        case ChangeType.CLARIFICATION:
            return cited
        case ChangeType.REMOVED:
            return excluded and set(state.criteria_cited) == {code}


def assess_impact(
    changes: Iterable[tuple[str, ChangeType]], states: Mapping[str, ReferenceState]
) -> Impact:
    """References touched by each change of a version, and by the version as a whole."""
    impacts = tuple(
        ChangeImpact(
            code=code,
            change_type=change_type,
            reference_ids=tuple(
                sorted(ref for ref, state in states.items() if affected(code, change_type, state))
            ),
        )
        for code, change_type in sorted(changes, key=lambda change: code_sort_key(change[0]))
    )
    touched = sorted({ref for impact in impacts for ref in impact.reference_ids})
    return Impact(changes=impacts, touched=tuple(touched))


def clarification_sample_size(count: int) -> int:
    """20 % of the references, at least 20, at most all of them."""
    wanted = max(CLARIFICATION_SAMPLE_MINIMUM, math.ceil(count * CLARIFICATION_SAMPLE_FRACTION))
    return min(count, wanted)


def reassessment_set(impact: Impact, *, seed: int, sample_clarifications: bool = True) -> list[str]:
    """References to reassess: every reference touched by a change other than a
    clarification, and a sample, drawn with ``seed``, of those touched by
    clarifications only (all of them when ``sample_clarifications`` is false)."""
    must: set[str] = set()
    clarified: set[str] = set()
    for change in impact.changes:
        target = clarified if change.change_type is ChangeType.CLARIFICATION else must
        target.update(change.reference_ids)
    only_clarified: Sequence[str] = sorted(clarified - must)
    if sample_clarifications:
        only_clarified = draw_sample(
            only_clarified, clarification_sample_size(len(only_clarified)), seed
        )
    return sorted(must | set(only_clarified))
