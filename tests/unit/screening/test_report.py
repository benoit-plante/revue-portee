"""Flow diagram of the demonstration project (EF-DEC-01): the numbers computed from the
data match the count made by hand (tests/fixtures/demo/README.md) at every step."""

import xml.etree.ElementTree as ET
from pathlib import Path

from demo import (
    Demo,
    broaden_and_reassess,
    build,
    create,
    deduplicate,
    reconcile,
    screen,
    screen_by_hand,
)
from revue_portee.reporting.flow import FlowNumbers, Pending, ReassessmentCounts
from revue_portee.screening.report import (
    RetainedFormat,
    export_flow,
    export_retained,
    flow_report,
    retained_references,
)
from support import TOOL_VERSION, make_clock

SVG = "{http://www.w3.org/2000/svg}"


def numbers_of(demo: Demo) -> FlowNumbers:
    return flow_report(demo.folder, now=make_clock(), tool_version=TOOL_VERSION).numbers


def test_demonstration_counted_by_hand(tmp_path: Path) -> None:
    demo = build(tmp_path)
    try:
        numbers = numbers_of(demo)
    finally:
        demo.folder.close()
    assert numbers.identified_by_source == {
        "APA PsycInfo (EBSCOhost)": 4,
        "CINAHL (EBSCOhost)": 3,
        "PubMed": 2,
    }
    assert (numbers.identified, numbers.registers, numbers.duplicates_removed) == (9, 0, 4)
    assert (numbers.removed_by_automation, numbers.removed_other) == (0, 0)
    assert (numbers.screened, numbers.excluded, numbers.sought) == (5, 2, 3)
    assert (numbers.excluded_by_person, numbers.excluded_by_automation) == (2, 0)
    assert numbers.not_retrieved == 1
    assert numbers.reassessments == (
        ReassessmentCounts(
            from_version=1,
            to_version=2,
            reassessed=2,
            kept_to_excluded=0,
            excluded_to_kept=1,
            completed=True,
        ),
    )
    assert numbers.pending == Pending()
    assert not numbers.provisional


def test_provisional_at_every_step(tmp_path: Path) -> None:
    demo = create(tmp_path)
    try:
        before = numbers_of(demo)
        assert (before.identified, before.duplicates_removed, before.screened) == (9, 0, 0)
        assert before.pending == Pending(not_screened=9, screening_not_started=True)
        deduplicate(demo)
        assert numbers_of(demo).pending == Pending(not_screened=5, screening_not_started=True)
        screen(demo, human=False)  # the AI only
        by_ai = numbers_of(demo)
        assert (by_ai.screened, by_ai.excluded) == (0, 0)  # the AI decides nothing alone
        assert by_ai.pending == Pending(not_screened=5)
        screen_by_hand(demo)
        screened = numbers_of(demo)
        # the gardens study, uncertain for the person, excluded by the AI
        assert screened.pending == Pending(disagreements=1)
        assert (screened.screened, screened.excluded, screened.sought) == (5, 2, 3)
        reconcile(demo)
        reconciled = numbers_of(demo)
        assert (reconciled.excluded, reconciled.sought) == (3, 2)
        assert not reconciled.provisional
        broaden_and_reassess(demo, complete=False)
        changing = numbers_of(demo)
        assert changing.pending == Pending(reassessments=1)
        assert (changing.excluded, changing.sought) == (2, 3)  # the verified decision counts
    finally:
        demo.folder.close()


def test_export_in_both_languages(tmp_path: Path) -> None:
    demo = build(tmp_path)
    try:
        paths = [
            export_flow(demo.folder, language=language, now=make_clock(), tool_version="0.1.0")
            for language in ("fr", "en")
        ]
    finally:
        demo.folder.close()
    assert [p.name for p in paths] == ["diagramme-fr.svg", "diagramme-en.svg"]
    french = ET.parse(paths[0]).getroot()  # noqa: S314 - our own output
    lines = [t.text or "" for t in french.iter(f"{SVG}text")]
    assert "Références exclues (n = 2)" in lines
    assert "Soutien à la parentalité et santé mentale des enfants" in lines
    assert any("critères, version 2" in line for line in lines)
    assert "PROVISOIRE" not in lines


def test_references_kept_for_the_full_text(tmp_path: Path) -> None:
    demo = build(tmp_path)
    try:
        kept = retained_references(demo.folder)
        ids = demo.ids()
        exports = [
            export_retained(demo.folder, format=f, now=make_clock(), tool_version=TOOL_VERSION)
            for f in RetainedFormat
        ]
    finally:
        demo.folder.close()
    # counted by hand: the caregivers study (uncertain), the housing study (included after
    # the reassessment) and the loneliness study, sorted by title
    expected = [ids["caregivers"], ids["housing"], ids["loneliness"]]
    assert [k.reference.id for k in kept] == expected
    assert [k.decision.value.value for k in kept] == ["uncertain", "include", "include"]
    assert [k.criteria_version for k in kept] == [1, 2, 1]
    assert [(e.path.name, e.count, e.provisional) for e in exports] == [
        ("references-retenues.ris", 3, False),
        ("references-retenues.csv", 3, False),
    ]
    assert exports[0].path.read_text(encoding="utf-8").count("ER  - ") == 3


def test_nothing_kept_before_the_screening(tmp_path: Path) -> None:
    demo = create(tmp_path)
    try:
        assert retained_references(demo.folder) == []
        result = export_retained(
            demo.folder, format=RetainedFormat.CSV, now=make_clock(), tool_version=TOOL_VERSION
        )
    finally:
        demo.folder.close()
    assert (result.count, result.provisional) == (0, True)
