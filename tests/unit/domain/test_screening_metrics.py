"""Screening rules, metrics and calibration (EF-SEL-03, 05, 07, 09), on cases computed
by hand."""

from datetime import UTC, datetime

import pytest

from revue_portee.domain.calibration import (
    Calibration,
    fit_calibration,
    suggest_exclusion_threshold,
)
from revue_portee.domain.criteria import CriterionKind
from revue_portee.domain.metrics import (
    Confusion,
    cohen_kappa,
    confusion,
    disagreements_by_criterion,
    gwet_ac1,
    pilot_metrics,
    threshold_curve,
    wilson_interval,
)
from revue_portee.domain.screening import (
    AssessmentStatus,
    CriterionAssessment,
    Decision,
    DecisionValue,
    PilotRound,
    ReviewerKind,
    Stage,
    Thresholds,
    ai_value,
    detect_language,
    draw_sample,
    must_not_exclude,
)

IN, EX, UN = DecisionValue.INCLUDE, DecisionValue.EXCLUDE, DecisionValue.UNCERTAIN
MET, NOT_MET, UNKNOWN = (
    AssessmentStatus.MET,
    AssessmentStatus.NOT_MET,
    AssessmentStatus.CANNOT_TELL,
)
NOW = datetime(2026, 10, 8, tzinfo=UTC)
DEFAULT = Thresholds(exclude_below=0.1, include_above=0.6)


def assess(*items: tuple[str, CriterionKind, AssessmentStatus]) -> list[CriterionAssessment]:
    return [CriterionAssessment(code=c, kind=k, status=s) for c, k, s in items]


INC, EXC = CriterionKind.INCLUSION, CriterionKind.EXCLUSION


def test_rule_sel_07_never_excludes_what_cannot_be_told() -> None:
    # an exclusion criterion "not met" means its reason does not apply: no failure
    unknown = assess(("P1", INC, UNKNOWN), ("C1", INC, MET), ("X1", EXC, NOT_MET))
    assert must_not_exclude(unknown)
    assert ai_value(0.01, DEFAULT, unknown) is UN  # thresholds say exclude, the rule says no
    assert not must_not_exclude(assess(("P1", INC, UNKNOWN), ("C1", INC, NOT_MET)))
    assert ai_value(0.01, DEFAULT, assess(("P1", INC, UNKNOWN), ("C1", INC, NOT_MET))) is EX
    # an exclusion criterion that applies fails the reference
    assert not must_not_exclude(assess(("P1", INC, UNKNOWN), ("X1", EXC, MET)))
    # an exclusion criterion that cannot be told does not protect the reference
    assert not must_not_exclude(assess(("P1", INC, MET), ("X1", EXC, UNKNOWN)))


@pytest.mark.parametrize(("probability", "value"), [(0.09, EX), (0.1, UN), (0.59, UN), (0.6, IN)])
def test_thresholds(probability: float, value: DecisionValue) -> None:
    assert ai_value(probability, DEFAULT, assess(("P1", INC, MET))) is value


def test_threshold_order_is_checked() -> None:
    with pytest.raises(ValueError, match="exclude_below"):
        Thresholds(exclude_below=0.7, include_above=0.6)


def test_metrics_computed_by_hand() -> None:
    # 20 pairs: 8 both positive, 2 missed by the AI, 3 kept by the AI only, 7 excluded
    pairs = [(IN, IN)] * 6 + [(UN, IN)] + [(IN, UN)] + [(IN, EX)] * 2 + [(EX, IN)] * 2 + [(EX, UN)]
    pairs += [(EX, EX)] * 7
    m = pilot_metrics(pairs)
    assert m.confusion == Confusion(tp=8, fn=2, fp=3, tn=7)
    assert m.agreement == 0.75
    # kappa: po = 0.75, pe = (11 x 10 + 9 x 10) / 400 = 0.5 -> 0.25 / 0.5
    assert m.kappa == pytest.approx(0.5)
    # AC1: pi = (0.55 + 0.5) / 2 = 0.525, pe = 2 x 0.525 x 0.475 = 0.49875
    assert m.ac1 == pytest.approx(0.25125 / 0.50125)
    assert (m.sensitivity, m.specificity) == (0.8, 0.7)
    assert m.sensitivity_interval == pytest.approx((0.4902, 0.9433), abs=1e-4)


def test_metrics_without_data_or_variation() -> None:
    assert pilot_metrics([]).agreement is None
    assert cohen_kappa(Confusion(0, 0, 0, 0)) is None
    assert gwet_ac1(Confusion(0, 0, 0, 0)) is None
    one_category = confusion([(IN, IN), (IN, UN)])
    assert cohen_kappa(one_category) is None  # chance agreement is total
    assert gwet_ac1(one_category) == pytest.approx(1.0)
    assert wilson_interval(0, 0) is None


OBSERVATIONS = [
    (0.05, False, False),
    (0.1, True, False),
    (0.2, False, False),
    (0.3, False, True),  # protected by EF-SEL-07
    (0.6, True, False),
    (0.9, True, False),
]


def test_threshold_curve_by_hand() -> None:
    points = threshold_curve(OBSERVATIONS, [0.15, 0.35, 0.7])
    assert [p.avoided for p in points] == [2, 3, 4]  # 0.3 is protected
    assert [p.sensitivity for p in points] == pytest.approx([2 / 3, 2 / 3, 1 / 3])
    assert points[0].avoided_share == pytest.approx(2 / 6)
    assert threshold_curve([], [0.5])[0].avoided_share == 0.0


def test_suggested_threshold_prefers_sensitivity() -> None:
    lenient = suggest_exclusion_threshold(OBSERVATIONS, 0.66)
    assert (lenient.exclude_below, lenient.avoided) == (0.6, 3)
    strict = suggest_exclusion_threshold(OBSERVATIONS, 0.95)
    assert (strict.exclude_below, strict.sensitivity, strict.avoided) == (0.1, 1.0, 1)
    nothing_known = suggest_exclusion_threshold([(0.2, False, False)], 0.95)
    assert (nothing_known.exclude_below, nothing_known.sensitivity) == (0.0, None)


def test_isotonic_calibration_by_hand() -> None:
    fitted = fit_calibration([0.1, 0.2, 0.3, 0.4], [False, True, False, True])
    assert fitted.points == ((0.1, 0.0), (0.2, 0.5), (0.3, 0.5), (0.4, 1.0))
    assert [fitted.apply(x) for x in (0.0, 0.25, 0.35, 1.0)] == [
        0.0,
        0.5,
        pytest.approx(0.75),
        1.0,
    ]
    tied = fit_calibration([0.5, 0.5, 0.8], [False, True, True])
    assert tied.points == ((0.5, 0.5), (0.8, 1.0))
    assert Calibration.model_validate_json(fitted.model_dump_json()) == fitted


def test_other_calibrations() -> None:
    assert fit_calibration([0.2, 0.4], [True, True]).method == "none"  # one category
    assert fit_calibration([], []).apply(0.3) == 0.3
    assert fit_calibration([0.2, 0.4], [False, True], "none").method == "none"
    platt = fit_calibration([0.1, 0.2, 0.8, 0.9], [False, False, True, True], "platt")
    assert platt.method == "platt"
    assert platt.apply(0.1) < 0.5 < platt.apply(0.9)
    with pytest.raises(ValueError, match="one label"):
        fit_calibration([0.1], [])
    with pytest.raises(ValueError, match="points"):
        Calibration(method="isotonic")


def test_disagreements_by_criterion() -> None:
    rows = [(IN, EX, ("P1", "C2")), (EX, IN, ("C2",)), (IN, IN, ("P1",)), (EX, UN, ())]
    assert disagreements_by_criterion(rows) == {"C2": 2, "": 1, "P1": 1}


def test_sample_is_reproducible() -> None:
    ids = [f"R{i:03d}" for i in range(50)]
    sample = draw_sample(ids, 10, seed=42)
    assert sample == draw_sample(list(reversed(ids)), 10, seed=42)
    assert sample != draw_sample(ids, 10, seed=43)
    assert len(set(sample)) == 10
    with pytest.raises(ValueError, match="larger"):
        draw_sample(ids, 51, seed=1)


@pytest.mark.parametrize(
    ("declared", "text", "language"),
    [
        ("FR", "", "fr"),
        ("French", "", "fr"),
        ("eng", "", "en"),
        ("de", "", "de"),
        ("", "Le logement des aînés et la santé mentale dans les quartiers", "fr"),
        ("", "The housing of older adults and the mental health of their families", "en"),
        ("", "Wohnen im Alter", ""),
    ],
)
def test_language_detection(declared: str, text: str, language: str) -> None:
    assert detect_language(declared, text) == language


def ai_decision(**changes: object) -> Decision:
    values: dict[str, object] = {
        "id": "D1",
        "reference_id": "R1",
        "stage": Stage.TITLE_ABSTRACT,
        "round_id": "P1",
        "reviewer_id": "AI",
        "reviewer_kind": ReviewerKind.AI,
        "value": IN,
        "confidence_raw": 0.8,
        "rationale": "P1 et C1 satisfaits.",
        "criteria_cited": ("P1",),
        "assessments": tuple(assess(("P1", INC, MET))),
        "model_decision": IN,
        "thresholds": DEFAULT,
        "criteria_version_id": "V1",
        "ai_call_id": "CALL1",
        "tool_version": "test",
        "created_at": NOW,
    }
    return Decision.model_validate(values | changes)


@pytest.mark.parametrize(
    "missing",
    [
        "ai_call_id",
        "confidence_raw",
        "rationale",
        "criteria_cited",
        "assessments",
        "model_decision",
        "thresholds",
    ],
)
def test_an_ai_decision_needs_every_traceability_field(missing: str) -> None:
    """ENF-TRA-05: no AI decision without the fields of ENF-TRA-01."""
    ai_decision()
    empty = {"rationale": "", "criteria_cited": (), "assessments": ()}.get(missing)
    with pytest.raises(ValueError, match=missing):
        ai_decision(**{missing: empty})


def test_human_decisions() -> None:
    human = {"reviewer_kind": ReviewerKind.HUMAN, "ai_call_id": None, "reviewer_id": "H"}
    ai_decision(**human, value=IN, assessments=(), rationale="")
    with pytest.raises(ValueError, match="EF-SEL-12"):
        ai_decision(**human, value=EX, criteria_cited=())
    with pytest.raises(ValueError, match="no model call"):
        ai_decision(**(human | {"ai_call_id": "CALL1"}))


def test_pilot_round_is_consistent() -> None:
    values: dict[str, object] = {
        "id": "P1",
        "number": 1,
        "stage": Stage.TITLE_ABSTRACT,
        "criteria_version_id": "V1",
        "seed": 7,
        "sample_size": 2,
        "reference_ids": ("R1", "R2"),
        "created_at": NOW,
        "reviewer_id": "H",
    }
    PilotRound.model_validate(values)
    with pytest.raises(ValueError, match="sample_size"):
        PilotRound.model_validate(values | {"sample_size": 3})
    with pytest.raises(ValueError, match="at most once"):
        PilotRound.model_validate(values | {"reference_ids": ("R1", "R1")})
