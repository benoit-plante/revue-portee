"""Impact analysis on a set built by hand (EF-VER-04): at least five cases for each of
the five types of change, each with the exact set of references expected."""

import pytest

from revue_portee.domain.changes import ChangeType
from revue_portee.domain.impact import (
    ReferenceState,
    assess_impact,
    clarification_sample_size,
    reassessment_set,
)
from revue_portee.domain.screening import DecisionValue, disagree, keeps

IN, EX, UN = DecisionValue.INCLUDE, DecisionValue.EXCLUDE, DecisionValue.UNCERTAIN
B, N, C = ChangeType.BROADENING, ChangeType.NARROWING, ChangeType.CLARIFICATION
A, R = ChangeType.ADDED, ChangeType.REMOVED

# Criteria P1, C1, C2 (inclusion), X1, X2 (exclusion). Final human decisions:
STATES = {
    ref: ReferenceState(reference_id=ref, value=value, criteria_cited=cited)
    for ref, value, cited in (
        ("r01", EX, ("P1",)),
        ("r02", EX, ("C1",)),
        ("r03", EX, ("P1", "C1")),
        ("r04", EX, ("X1",)),
        ("r05", EX, ("X1", "X2")),
        ("r06", IN, ()),
        ("r07", IN, ("C1",)),
        ("r08", UN, ()),
        ("r09", UN, ("P1",)),
        ("r10", EX, ("X2",)),
        ("r11", EX, ("C2",)),
        ("r12", IN, ("P1",)),
    )
}
KEPT = {"r06", "r07", "r08", "r09", "r12"}
SOME = ("r01", "r06", "r07", "r10")  # a smaller project, for the cases that vary it


def subset(refs: tuple[str, ...] | None) -> dict[str, ReferenceState]:
    return dict(STATES) if refs is None else {ref: STATES[ref] for ref in refs}


CASES = [
    # broadening: excluded references that cite the criterion
    (B, "P1", None, {"r01", "r03"}),
    (B, "C1", None, {"r02", "r03"}),
    (B, "X1", None, {"r04", "r05"}),
    (B, "X2", None, {"r05", "r10"}),
    (B, "C2", None, {"r11"}),
    (B, "P1", SOME, {"r01"}),
    # narrowing: references included or uncertain, whatever they cite
    (N, "P1", None, KEPT),
    (N, "C1", None, KEPT),
    (N, "X1", None, KEPT),
    (N, "C2", SOME, {"r06", "r07"}),
    (N, "X2", ("r01", "r02", "r03"), set()),
    # clarification: references that cite the criterion, whatever their value
    (C, "P1", None, {"r01", "r03", "r09", "r12"}),
    (C, "C1", None, {"r02", "r03", "r07"}),
    (C, "X1", None, {"r04", "r05"}),
    (C, "X2", None, {"r05", "r10"}),
    (C, "C2", None, {"r11"}),
    (C, "C1", SOME, {"r07"}),
    # added criterion: references still in the stage
    (A, "P2", None, KEPT),
    (A, "X3", None, KEPT),
    (A, "C3", SOME, {"r06", "r07"}),
    (A, "O1", ("r08", "r09", "r10"), {"r08", "r09"}),
    (A, "X4", ("r04", "r05"), set()),
    # removed criterion: references excluded for that criterion only
    (R, "P1", None, {"r01"}),
    (R, "C1", None, {"r02"}),
    (R, "X1", None, {"r04"}),
    (R, "X2", None, {"r10"}),
    (R, "C2", None, {"r11"}),
    (R, "O1", None, set()),
]


@pytest.mark.parametrize(("change_type", "code", "refs", "expected"), CASES)
def test_references_touched_by_one_change(
    change_type: ChangeType, code: str, refs: tuple[str, ...] | None, expected: set[str]
) -> None:
    impact = assess_impact([(code, change_type)], subset(refs))
    assert set(impact.changes[0].reference_ids) == expected
    assert set(impact.touched) == expected


def test_five_cases_or_more_for_each_type() -> None:
    for change_type in ChangeType:
        assert sum(case[0] is change_type for case in CASES) >= 5


def test_several_changes_of_one_version() -> None:
    impact = assess_impact([("X1", R), ("C1", B), ("P1", C)], STATES)
    assert [(c.code, c.change_type) for c in impact.changes] == [("P1", C), ("C1", B), ("X1", R)]
    assert impact.touched == ("r01", "r02", "r03", "r04", "r09", "r12")
    assert [c.code for c in impact.by_reference()["r03"]] == ["P1", "C1"]


def test_clarification_sample_size() -> None:
    assert clarification_sample_size(0) == 0
    assert clarification_sample_size(12) == 12  # fewer than 20: all of them
    assert clarification_sample_size(80) == 20
    assert clarification_sample_size(101) == 21  # 20 % rounded up
    assert clarification_sample_size(500) == 100


def test_reassessment_samples_clarifications_only() -> None:
    states = {
        f"c{i:03}": ReferenceState(reference_id=f"c{i:03}", value=EX, criteria_cited=("C1",))
        for i in range(100)
    }
    states["n1"] = ReferenceState(reference_id="n1", value=IN)
    impact = assess_impact([("C1", C), ("P1", N)], states)
    chosen = reassessment_set(impact, seed=7)
    assert "n1" in chosen  # a narrowing is always reassessed
    assert len(chosen) == 21  # 20 of the 100 clarified references, and n1
    assert chosen == reassessment_set(impact, seed=7)
    assert chosen != reassessment_set(impact, seed=8)
    assert len(reassessment_set(impact, seed=7, sample_clarifications=False)) == 101


def test_disagreement_is_keep_against_exclude() -> None:
    assert keeps(IN)
    assert keeps(UN)
    assert not keeps(EX)
    assert disagree(IN, EX)
    assert disagree(EX, UN)
    assert not disagree(IN, UN)
    assert not disagree(EX, EX)
