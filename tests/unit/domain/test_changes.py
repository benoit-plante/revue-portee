"""Qualification of criteria changes (EF-VER-03), cases checked by hand."""

from datetime import UTC, datetime

import pytest

from revue_portee.domain.changes import (
    ChangeType,
    QualificationError,
    QualificationProposal,
    qualify,
)
from revue_portee.domain.criteria import (
    CriteriaVersion,
    Criterion,
    CriterionKind,
    PccElement,
    VersionStatus,
    diff_versions,
)

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
INC = CriterionKind.INCLUSION


def crit(code: str, text: str, element: PccElement = PccElement.POPULATION) -> Criterion:
    return Criterion(code=code, pcc_element=element, kind=INC, text=text)


def version(number: int, *criteria: Criterion, status: VersionStatus) -> CriteriaVersion:
    return CriteriaVersion(
        id=f"v{number}",
        number=number,
        parent_id=None if number == 1 else f"v{number - 1}",
        status=status,
        created_at=NOW,
        activated_at=None if status is VersionStatus.DRAFT else NOW,
        author_id="r",
        criteria=criteria,
    )


V1 = version(
    1,
    crit("P1", "Parents"),
    crit("P2", "Tuteurs"),
    crit("C1", "Soutien", PccElement.CONCEPT),
    status=VersionStatus.ACTIVE,
)
# P1 modified, P2 removed, C1 modified, P3 added.
V2 = version(
    2,
    crit("P1", "Parents et beaux-parents"),
    crit("P3", "Grands-parents"),
    crit("C1", "Soutien parental", PccElement.CONCEPT),
    status=VersionStatus.DRAFT,
)


def test_every_change_is_qualified_in_code_order() -> None:
    result = qualify(
        diff_versions(V1, V2),
        {"P1": ChangeType.BROADENING, "C1": ChangeType.CLARIFICATION},
    )
    assert result == [
        ("P1", ChangeType.BROADENING),
        ("P2", ChangeType.REMOVED),
        ("P3", ChangeType.ADDED),
        ("C1", ChangeType.CLARIFICATION),
    ]


def test_missing_qualification_is_reported() -> None:
    with pytest.raises(QualificationError) as raised:
        qualify(diff_versions(V1, V2), {"P1": ChangeType.NARROWING})
    assert (raised.value.missing, raised.value.invalid) == (("C1",), ())


def test_added_removed_or_unknown_codes_cannot_be_chosen() -> None:
    choices = {
        "P1": ChangeType.ADDED,  # not a modification type
        "C1": ChangeType.NARROWING,
        "P2": ChangeType.CLARIFICATION,  # removed: qualified automatically
        "X9": ChangeType.BROADENING,  # unknown
    }
    with pytest.raises(QualificationError) as raised:
        qualify(diff_versions(V1, V2), choices)
    assert raised.value.invalid == ("P1", "P2", "X9")


def test_identical_versions_need_no_qualification() -> None:
    same = version(2, *V1.criteria, status=VersionStatus.DRAFT)
    assert qualify(diff_versions(V1, same), {}) == []


def test_proposal_only_applies_to_the_criterion_it_qualified() -> None:
    proposal = QualificationProposal(
        id="q1",
        draft_version_id="v2",
        code="P1",
        ai_call_id="c1",
        change_type=ChangeType.BROADENING,
        confidence=0.8,
        after=crit("P1", "Parents et beaux-parents"),
        created_at=NOW,
    )
    assert proposal.applies_to(V2)
    edited = version(2, crit("P1", "Parents seulement"), status=VersionStatus.DRAFT)
    assert not proposal.applies_to(edited)
    other_draft = V2.model_copy(update={"id": "v2b"})
    assert not proposal.applies_to(other_draft)
