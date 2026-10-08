"""Numbers and rendering of the flow diagram (EF-DEC-01): each number on a case
computed by hand."""

import xml.etree.ElementTree as ET
from datetime import UTC, datetime

import pytest

from revue_portee.dedup.counts import FlowCounts
from revue_portee.domain.criteria import CriterionKind
from revue_portee.domain.screening import (
    AssessmentStatus,
    CriterionAssessment,
    Decision,
    DecisionValue,
    ReviewerKind,
    Stage,
    Thresholds,
)
from revue_portee.reporting.flow import (
    FlowNumbers,
    Pending,
    ReassessmentCounts,
    StageStatus,
    flow_numbers,
    reassessment_counts,
)
from revue_portee.reporting.flow_svg import FlowContext, render_flow_svg
from revue_portee.resources import flow_template

IN, EX, UN = DecisionValue.INCLUDE, DecisionValue.EXCLUDE, DecisionValue.UNCERTAIN
MOMENT = datetime(2026, 10, 8, 12, tzinfo=UTC)
SVG = "{http://www.w3.org/2000/svg}"


def decision(ref: str, value: DecisionValue, kind: ReviewerKind = ReviewerKind.HUMAN) -> Decision:
    common: dict[str, object] = {
        "id": f"D-{ref}-{value.value}",
        "reference_id": ref,
        "stage": Stage.TITLE_ABSTRACT,
        "round_id": "ROUND",
        "reviewer_id": "R",
        "value": value,
        "criteria_cited": ("P1",) if value is EX else (),
        "criteria_version_id": "V1",
        "tool_version": "test",
        "created_at": MOMENT,
    }
    if kind is ReviewerKind.HUMAN:
        return Decision.model_validate({**common, "reviewer_kind": kind})
    return Decision.model_validate(
        {
            **common,
            "reviewer_kind": kind,
            "ai_call_id": "CALL",
            "confidence_raw": 0.01,
            "rationale": "P1 non satisfait.",
            "assessments": (
                CriterionAssessment(
                    code="P1", kind=CriterionKind.INCLUSION, status=AssessmentStatus.NOT_MET
                ),
            ),
            "model_decision": value,
            "thresholds": Thresholds(exclude_below=0.05, include_above=0.6),
        }
    )


COUNTS = FlowCounts(
    identified_by_source={"OpenAlex": 6, "PubMed": 4},
    identified=10,
    duplicates_removed=3,
    after_deduplication=7,
    pending_pairs=0,
)
REMAINING = ["a", "b", "c", "d", "e", "f", "g"]


def test_numbers_counted_by_hand() -> None:
    # 7 references after deduplication: 2 excluded, 2 included, 1 uncertain, 2 not
    # screened yet; a decision on "z", since grouped as a duplicate, is not counted.
    final = {
        "a": decision("a", EX),
        "b": decision("b", EX),
        "c": decision("c", IN),
        "d": decision("d", IN),
        "e": decision("e", UN),
        "z": decision("z", EX),
    }
    numbers = flow_numbers(COUNTS, REMAINING, final, screened_by_ai=["a", "b", "c", "d", "e", "f"])
    assert numbers.identified_by_source == {"OpenAlex": 6, "PubMed": 4}
    assert (numbers.identified, numbers.registers, numbers.duplicates_removed) == (10, 0, 3)
    assert (numbers.removed_by_automation, numbers.removed_other) == (0, 0)
    assert (numbers.screened, numbers.excluded, numbers.sought) == (5, 2, 3)
    assert (numbers.excluded_by_person, numbers.excluded_by_automation) == (2, 0)
    assert numbers.pending == Pending(not_screened=2, without_ai=1)
    assert numbers.provisional


def test_final_when_nothing_is_left() -> None:
    final = {ref: decision(ref, IN if ref in "abc" else EX) for ref in REMAINING}
    numbers = flow_numbers(COUNTS, REMAINING, final, screened_by_ai=REMAINING)
    assert (numbers.screened, numbers.excluded, numbers.sought) == (7, 4, 3)
    assert numbers.pending == Pending()
    assert not numbers.provisional


def test_an_exclusion_by_the_ai_alone_would_be_shown() -> None:
    final = {ref: decision(ref, IN) for ref in REMAINING} | {
        "a": decision("a", EX, ReviewerKind.AI)
    }
    numbers = flow_numbers(COUNTS, REMAINING, final, screened_by_ai=REMAINING)
    assert (numbers.excluded, numbers.excluded_by_person, numbers.excluded_by_automation) == (
        1,
        0,
        1,
    )


@pytest.mark.parametrize(
    ("pending", "expected"),
    [
        (Pending(), False),
        (Pending(not_screened=1), True),
        (Pending(without_ai=1), True),
        (Pending(disagreements=1), True),
        (Pending(duplicate_pairs=1), True),
        (Pending(reassessments=1), True),
        (Pending(screening_not_started=True), True),
    ],
)
def test_every_thing_left_makes_the_diagram_provisional(pending: Pending, expected: bool) -> None:
    assert pending.any is expected


def test_before_the_screening() -> None:
    numbers = flow_numbers(
        FlowCounts(
            identified_by_source=COUNTS.identified_by_source,
            identified=10,
            duplicates_removed=3,
            after_deduplication=7,
            pending_pairs=2,
        ),
        REMAINING,
        {},
        screening_started=False,
    )
    assert numbers.screened == 0
    assert numbers.pending == Pending(not_screened=7, duplicate_pairs=2, screening_not_started=True)


def test_reassessment_counts_by_hand() -> None:
    # r1 kept -> excluded, r2 excluded -> kept, r3 confirmed excluded, r4 not verified
    # (the AI did not change it), r5 uncertain -> included (still kept: no change).
    previous = {
        "r1": decision("r1", IN),
        "r2": decision("r2", EX),
        "r3": decision("r3", EX),
        "r4": decision("r4", IN),
        "r5": decision("r5", UN),
    }
    verified = {
        "r1": decision("r1", EX),
        "r2": decision("r2", UN),
        "r3": decision("r3", EX),
        "r5": decision("r5", IN),
    }
    counts = reassessment_counts(
        from_version=1,
        to_version=2,
        members=["r1", "r2", "r3", "r4", "r5", "r1"],
        previous=previous,
        verified=verified,
        completed=False,
    )
    assert counts == ReassessmentCounts(
        from_version=1,
        to_version=2,
        reassessed=5,
        kept_to_excluded=1,
        excluded_to_kept=1,
        completed=False,
    )
    numbers = flow_numbers(COUNTS, REMAINING, {}, reassessments=[counts])
    assert numbers.pending.reassessments == 1


# --- Template and rendering ---------------------------------------------------------


def test_template_is_dated_data_with_its_source() -> None:
    template = flow_template()
    assert template.date.isoformat() == "2026-10-08"
    assert "doi:10.1136/bmj.n71" in template.source
    assert "doi:10.7326/M18-0850" in template.adaptation
    assert [p.id for p in template.phases] == ["identification", "screening", "included"]
    later = {b.id for b in template.boxes if b.stage is StageStatus.LATER}
    assert later == {
        "not_retrieved",
        "assessed",
        "reports_excluded",
        "included",
        "included_reports",
    }
    assert all(b.phase in {p.id for p in template.phases} for b in template.boxes)


def numbers(**changes: object) -> FlowNumbers:
    base = FlowNumbers(
        identified_by_source={"APA PsycInfo (EBSCOhost)": 1200, "PubMed": 34},
        identified=1234,
        registers=0,
        duplicates_removed=234,
        removed_by_automation=0,
        removed_other=0,
        screened=1000,
        excluded=900,
        excluded_by_person=900,
        excluded_by_automation=0,
        sought=100,
        reassessments=(),
        pending=Pending(),
    )
    return base.model_copy(update=changes)


CONTEXT = FlowContext(
    project_title="Parentalité & santé <mentale>",
    criteria_version=2,
    tool_version="0.1.0 (abc123)",
    generated_at=MOMENT,
)


def texts(svg: str) -> list[str]:
    root = ET.fromstring(svg)  # noqa: S314 - our own output
    return [element.text or "" for element in root.iter(f"{SVG}text")]


def test_svg_in_french_and_english() -> None:
    french = render_flow_svg(numbers(), flow_template(), CONTEXT, language="fr")
    english = render_flow_svg(numbers(), flow_template(), CONTEXT, language="en")
    lines = texts(french)
    assert "Références repérées dans :" in lines
    assert "Bases de données (n = 1 234)" in lines
    assert "APA PsycInfo (EBSCOhost) (n = 1 200)" in lines
    assert "Doublons retirés (n = 234)" in lines
    assert "Références triées (n = 1 000)" in lines
    assert "Rapports recherchés pour le texte intégral (n = 100)" in lines
    assert "Parentalité & santé <mentale>" in lines  # escaped, then read back
    assert "par l'IA seule" in " ".join(lines)
    english_lines = texts(english)
    assert "Databases (n = 1,234)" in english_lines
    assert "Records screened (n = 1,000)" in english_lines
    assert "Records excluded (n = 900)" in english_lines
    assert 'xml:lang="en"' in english
    assert "PROVISIONAL" not in english


def test_stages_to_come_are_dashed() -> None:
    root = ET.fromstring(render_flow_svg(numbers(), flow_template(), CONTEXT, language="en"))  # noqa: S314
    dashed = [r for r in root.iter(f"{SVG}rect") if r.get("stroke-dasharray")]
    assert len(dashed) == 4  # not retrieved, assessed, reports excluded, included
    assert texts(ET.tostring(root, encoding="unicode")).count("(stage to come)") == 4


def test_reassessments_and_provisional_notes() -> None:
    changed = numbers(
        reassessments=(
            ReassessmentCounts(
                from_version=1, to_version=2, reassessed=12, kept_to_excluded=2,
                excluded_to_kept=3, completed=True,
            ),
            ReassessmentCounts(
                from_version=2, to_version=3, reassessed=4, kept_to_excluded=0,
                excluded_to_kept=1, completed=False,
            ),
        ),
        pending=Pending(not_screened=5, disagreements=2, reassessments=1),
    )  # fmt: skip
    svg = render_flow_svg(changed, flow_template(), CONTEXT, language="fr")
    lines = texts(svg)
    assert "Références triées (n = 1 000)†" in lines
    notes = " ".join(lines)
    assert "Changements de critères pendant le tri : 2" in notes
    assert "réévaluées" in notes
    assert "PROVISOIRE" in lines
    assert "références non triées par la personne : 5" in notes
    assert "désaccords à réconcilier : 2" in notes


def test_rendering_is_deterministic() -> None:
    first = render_flow_svg(numbers(), flow_template(), CONTEXT, language="fr")
    assert first == render_flow_svg(numbers(), flow_template(), CONTEXT, language="fr")
