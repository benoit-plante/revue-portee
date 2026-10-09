"""Full-text screening (EF-SEL-16, D-102): pilot, blind and assisted rounds, quotes
checked at their page, primary reasons. Counts of the demonstration made by hand
(tests/fixtures/demo/README.md)."""

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from demo import (
    AI_FT,
    Demo,
    _factory,
    broaden_and_reassess,
    build,
    create,
    deduplicate,
    reconcile,
    retrieve_texts,
    screen,
)
from revue_portee.ai.tasks.fulltext import ScreenFulltextOutput
from revue_portee.domain.changes import ChangeType
from revue_portee.domain.criteria import CriterionKind
from revue_portee.domain.fulltext import QuoteCheck
from revue_portee.domain.journal import EntryType
from revue_portee.domain.screening import (
    DecisionContext,
    DecisionValue,
    ScreeningMode,
    Stage,
    page_quote_counts,
)
from revue_portee.protocol import criteria, notes
from revue_portee.screening import batch_ai, fulltext, reassessment, settings
from revue_portee.screening.ai_screening import AIBatchResult, UnusableAnswerError
from revue_portee.screening.main import NotADisagreementError
from revue_portee.screening.methods import methods_data
from revue_portee.screening.pilot import NotInRoundError, UnknownCriterionError, UnknownRoundError
from support import TOOL_VERSION, make_pdf

IN, EX, UN = DecisionValue.INCLUDE, DecisionValue.EXCLUDE, DecisionValue.UNCERTAIN


def _with_texts(tmp_path: Path) -> Demo:
    """The demonstration up to the full texts obtained (two texts)."""
    demo = create(tmp_path)
    deduplicate(demo)
    screen(demo)
    reconcile(demo)
    broaden_and_reassess(demo)
    retrieve_texts(demo)
    return demo


def _run(
    demo: Demo, round_id: str, answers: dict[str, Any] = AI_FT, limit: str = "5"
) -> AIBatchResult:
    return fulltext.run_ai(
        demo.folder, round_id, batch_limit=Decimal(limit), factory=_factory(answers),
        now=demo.clock, tool_version=TOOL_VERSION,
    )  # fmt: skip


def test_demonstration_counted_by_hand(tmp_path: Path) -> None:
    demo = build(tmp_path)
    try:
        ids = demo.ids()
        trial = fulltext.pilot_round(demo.folder)
        assert trial is not None
        pilot = fulltext.pilot_state(demo.folder, trial.id)
        state = fulltext.main_state(demo.folder)
        replayed = fulltext.replay_decision(demo.folder, state.ai[ids["loneliness"]].id)
    finally:
        demo.folder.close()
    # the pilot holds both texts (fewer than 40), screened by the person and the AI
    assert sorted(pilot.round.reference_ids) == sorted([ids["housing"], ids["loneliness"]])
    assert pilot.complete
    assert pilot.metrics is not None
    assert pilot.metrics.agreement == 1.0
    # the blind main round: the pilot's decisions count, no disagreement
    assert state.round.mode is ScreeningMode.BLIND
    assert set(state.final) == {ids["housing"], ids["loneliness"]}
    assert state.final[ids["housing"]].value is EX
    assert state.reason(ids["housing"]) == "P1"
    assert state.reason(ids["loneliness"]) is None
    assert state.disagreements == []
    assert fulltext.kept(state) == [ids["loneliness"]]
    # quotes of the AI in the main round: 3 at their page, 1 elsewhere, 1 not found
    counts = page_quote_counts(a for d in state.ai.values() for a in d.assessments)
    assert counts == {QuoteCheck.AT_PAGE: 3, QuoteCheck.OTHER_PAGE: 1, QuoteCheck.NOT_FOUND: 1}
    loneliness = {a.code: a for a in state.ai[ids["loneliness"]].assessments}
    assert (loneliness["C1"].page, loneliness["C1"].quote_check) == (1, QuoteCheck.OTHER_PAGE)
    assert loneliness["C1"].quote_found
    assert loneliness["X1"].quote_found is False
    assert state.ai[ids["housing"]].assessments[2].quote_check is None  # no quote
    assert replayed == state.ai[ids["loneliness"]]


def test_pilot_required_and_ai_blind_until_decided(tmp_path: Path) -> None:
    demo = _with_texts(tmp_path)
    try:
        ids = demo.ids()
        started = fulltext.start_main(
            demo.folder, ScreeningMode.BLIND, seed=1, now=demo.clock, tool_version=TOOL_VERSION
        )
        with pytest.raises(fulltext.PilotRequiredError):
            _run(demo, started.id)
        with pytest.raises(fulltext.FulltextMainExistsError):
            fulltext.start_main(
                demo.folder, ScreeningMode.BLIND, now=demo.clock, tool_version=TOOL_VERSION
            )
        trial = fulltext.start_pilot(demo.folder, seed=3, now=demo.clock, tool_version=TOOL_VERSION)
        preview = fulltext.preview_ai(demo.folder, trial.id, factory=_factory(AI_FT))
        assert preview.items == 2
        _run(demo, trial.id)
        pilot = fulltext.pilot_state(demo.folder, trial.id)
        assert pilot.visible_ai(ids["housing"]) is None  # the person has not decided
        assert pilot.next_reference in {ids["housing"], ids["loneliness"]}
        assert not pilot.complete
        fulltext.record_decision(
            demo.folder, trial.id, ids["housing"], IN, now=demo.clock, tool_version=TOOL_VERSION
        )
        pilot = fulltext.pilot_state(demo.folder, trial.id)
        assert pilot.visible_ai(ids["housing"]) is not None
    finally:
        demo.folder.close()


def test_blind_round_disagreement_and_reconciliation(tmp_path: Path) -> None:
    demo = build(tmp_path)
    try:
        ids = demo.ids()
        housing = ids["housing"]
        # the person changes their mind in the main round: include, against the AI
        fulltext.record_decision(
            demo.folder, demo.fulltext_round_id, housing, IN, now=demo.clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
        state = fulltext.main_state(demo.folder)
        assert state.disagreements == [housing]
        assert state.queue == [housing]
        assert state.visible_ai(housing) is not None
        assert state.visible_ai(ids["loneliness"]) is None
        with pytest.raises(NotADisagreementError):
            fulltext.reconcile(
                demo.folder, ids["loneliness"], IN, now=demo.clock, tool_version=TOOL_VERSION
            )
        with pytest.raises(UnknownCriterionError):
            fulltext.reconcile(
                demo.folder, housing, EX, criteria_cited=["Z9"], now=demo.clock,
                tool_version=TOOL_VERSION,
            )  # fmt: skip
        final = fulltext.reconcile(
            demo.folder, housing, EX, criteria_cited=["X1", "P1"], rationale="Adolescents.",
            now=demo.clock, tool_version=TOOL_VERSION,
        )  # fmt: skip
        state = fulltext.main_state(demo.folder)
        entries = notes.journal_entries(demo.folder)
    finally:
        demo.folder.close()
    assert final.context is DecisionContext.RECONCILIATION
    assert final.criteria_cited == ("P1", "X1")  # in the order of the criteria
    assert state.queue == []
    assert state.reason(housing) == "P1"  # the first criterion cited
    assert entries[-1].entry_type == EntryType.SCREENING_RECONCILED


def test_assisted_round(tmp_path: Path) -> None:
    demo = _with_texts(tmp_path)
    try:
        ids = demo.ids()
        trial = fulltext.start_pilot(demo.folder, seed=3, now=demo.clock, tool_version=TOOL_VERSION)
        started = fulltext.start_main(
            demo.folder, ScreeningMode.ASSISTED, seed=1, now=demo.clock, tool_version=TOOL_VERSION
        )
        state = fulltext.main_state(demo.folder)
        assert fulltext.next_text(state) is None  # the AI first
        with pytest.raises(fulltext.AIFirstError):
            fulltext.record_decision(
                demo.folder, started.id, ids["housing"], IN, now=demo.clock,
                tool_version=TOOL_VERSION,
            )  # fmt: skip
        for key, value, cited in (("housing", EX, ["P1"]), ("loneliness", IN, [])):
            fulltext.record_decision(
                demo.folder, trial.id, ids[key], value, criteria_cited=cited, now=demo.clock,
                tool_version=TOOL_VERSION,
            )  # fmt: skip
        _run(demo, trial.id)
        _run(demo, started.id)
        state = fulltext.main_state(demo.folder)
        # the pilot's blind decisions count; the assisted round shows the AI before
        assert state.visible_ai(ids["housing"]) is not None
        assert fulltext.next_text(state) is None
        decided = fulltext.record_decision(
            demo.folder, started.id, ids["loneliness"], EX, criteria_cited=["C1"],
            now=demo.clock, tool_version=TOOL_VERSION,
        )  # fmt: skip
        state = fulltext.main_state(demo.folder)
        with pytest.raises(fulltext.NotBlindError):
            fulltext.reconcile(
                demo.folder, ids["loneliness"], IN, now=demo.clock, tool_version=TOOL_VERSION
            )
    finally:
        demo.folder.close()
    assert decided.context is DecisionContext.ASSISTED
    assert not decided.blinded
    assert state.disagreements == []  # no reconciliation in assisted mode
    assert state.final[ids["loneliness"]].value is EX
    assert state.followed_ai == (0, 1)  # the person excluded what the AI included


def test_errors_and_new_texts(tmp_path: Path) -> None:
    demo = _with_texts(tmp_path)
    try:
        ids = demo.ids()
        with pytest.raises(UnknownRoundError):
            fulltext.main_state(demo.folder)
        assert fulltext.add_new_texts(demo.folder, now=demo.clock, tool_version=TOOL_VERSION) == 0
        started = fulltext.start_main(
            demo.folder, ScreeningMode.BLIND, now=demo.clock, tool_version=TOOL_VERSION
        )
        with pytest.raises(NotInRoundError):
            fulltext.record_decision(
                demo.folder, started.id, ids["gardens"], IN, now=demo.clock,
                tool_version=TOOL_VERSION,
            )  # fmt: skip
        with pytest.raises(UnknownCriterionError):
            fulltext.record_decision(
                demo.folder, started.id, ids["housing"], EX, criteria_cited=["Z9"],
                now=demo.clock, tool_version=TOOL_VERSION,
            )  # fmt: skip
        with pytest.raises(UnknownRoundError):
            fulltext.pilot_state(demo.folder, started.id)
        with pytest.raises(UnknownRoundError):
            fulltext.preview_ai(demo.folder, "nope")
        # a text obtained after the start goes at the end of the round
        from revue_portee.fulltext import retrieval

        retrieval.add_upload(
            demo.folder, ids["caregivers"], make_pdf(["Family caregivers" + "\nx" * 300]),
            filename="c.pdf", now=demo.clock, tool_version=TOOL_VERSION,
        )  # fmt: skip
        added = fulltext.add_new_texts(demo.folder, now=demo.clock, tool_version=TOOL_VERSION)
        state = fulltext.main_state(demo.folder)
    finally:
        demo.folder.close()
    assert added == 1
    assert state.members[-1] == ids["caregivers"]
    assert fulltext.next_text(state, skip=state.members[:2]) == ids["caregivers"]


def test_no_texts(tmp_path: Path) -> None:
    demo = create(tmp_path)
    try:
        with pytest.raises(fulltext.NoTextsError):
            fulltext.start_pilot(demo.folder, now=demo.clock, tool_version=TOOL_VERSION)
        with pytest.raises(fulltext.NoTextsError):
            fulltext.start_main(
                demo.folder, ScreeningMode.BLIND, now=demo.clock, tool_version=TOOL_VERSION
            )
        assert not fulltext.pilot_complete(demo.folder)
    finally:
        demo.folder.close()


def test_scanned_text_is_left_to_the_person(tmp_path: Path) -> None:
    demo = _with_texts(tmp_path)
    try:
        ids = demo.ids()
        from revue_portee.fulltext import retrieval

        retrieval.add_upload(
            demo.folder, ids["caregivers"], make_pdf(["", ""]), filename="scan.pdf",
            now=demo.clock, tool_version=TOOL_VERSION,
        )  # fmt: skip
        trial = fulltext.start_pilot(demo.folder, seed=3, now=demo.clock, tool_version=TOOL_VERSION)
        answers = AI_FT | {"caregivers": AI_FT["loneliness"]}
        result = _run(demo, trial.id, answers)
        state = fulltext.pilot_state(demo.folder, trial.id)
        for ref in trial.reference_ids:
            fulltext.record_decision(
                demo.folder, trial.id, ref, UN, now=demo.clock, tool_version=TOOL_VERSION
            )
        complete = fulltext.pilot_complete(demo.folder)
    finally:
        demo.folder.close()
    assert result.screened == 2
    assert state.unreadable == [ids["caregivers"]]
    assert complete


def test_unusable_answers_and_ceilings(tmp_path: Path) -> None:
    demo = _with_texts(tmp_path)
    try:
        trial = fulltext.start_pilot(demo.folder, seed=3, now=demo.clock, tool_version=TOOL_VERSION)
        broken = {k: v | {"decisive_criteria": ["Z9"]} for k, v in AI_FT.items()}
        failed = _run(demo, trial.id, broken)
        stopped = _run(demo, trial.id, limit="0.001")
        settings.set_budget(
            demo.folder, Decimal("0.009"), now=demo.clock, tool_version=TOOL_VERSION
        )
        project = _run(demo, trial.id)
    finally:
        demo.folder.close()
    assert (failed.screened, len(failed.failed)) == (0, 2)
    assert (stopped.screened, stopped.stopped) == (0, "batch_budget")
    assert project.stopped == "project_budget"


def test_missing_criterion_is_unusable() -> None:
    output = ScreenFulltextOutput.model_validate(AI_FT["housing"])
    with pytest.raises(UnusableAnswerError):
        fulltext.check_answer(output, ["P1", "C1", "X1", "X2"])


def test_batches_of_the_main_round_need_the_pilot(tmp_path: Path) -> None:
    demo = _with_texts(tmp_path)
    try:
        started = fulltext.start_main(
            demo.folder, ScreeningMode.BLIND, seed=1, now=demo.clock, tool_version=TOOL_VERSION
        )
        preview = batch_ai.preview(demo.folder, started.id, factory=_factory(AI_FT))
        with pytest.raises(fulltext.PilotRequiredError):
            batch_ai.submit(
                demo.folder, started.id, batch_limit=Decimal(5), factory=_factory(AI_FT),
                now=demo.clock, tool_version=TOOL_VERSION,
            )  # fmt: skip
    finally:
        demo.folder.close()
    assert (preview.task, preview.items) == ("screen_fulltext", 2)


def test_criteria_change_reassessed_at_the_full_text(tmp_path: Path) -> None:
    """Version 3 broadens P1 to any age: the housing study, excluded for P1 at the full
    text, is touched; the AI screens it again and would now include it; the person
    verifies it and includes it. The other text keeps its decision."""
    demo = build(tmp_path)
    folder, clock = demo.folder, demo.clock
    try:
        ids = demo.ids()
        criteria.update_criterion(
            folder, "P1", kind=CriterionKind.INCLUSION, text="People of any age.", now=clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
        criteria.activate_draft(
            folder, rationale="Population élargie à tous les âges.",
            qualifications={"P1": ChangeType.BROADENING}, now=clock, tool_version=TOOL_VERSION,
        )  # fmt: skip
        main_id = demo.fulltext_round_id
        assert reassessment.next_version_to_assess(folder, main_id) is not None
        impact = reassessment.assess(folder, main_id, seed=4, now=clock, tool_version=TOOL_VERSION)
        assert impact.reassessment_round_id is not None
        state = reassessment.reassessment_state(folder, impact.id)
        assert state.round.stage is Stage.FULL_TEXT
        assert state.members == [ids["housing"]]
        v3 = AI_FT | {
            "housing": AI_FT["loneliness"] | {"rationale": "P1 satisfait : tous les âges."}
        }
        chosen = _factory(v3)
        batch_ai.submit(
            folder, impact.reassessment_round_id, batch_limit=Decimal(5), factory=chosen,
            now=clock, tool_version=TOOL_VERSION,
        )  # fmt: skip
        batch_ai.follow(
            folder, impact.reassessment_round_id, factory=chosen, now=clock,
            tool_version=TOOL_VERSION, wait=lambda _: None,
        )  # fmt: skip
        state = reassessment.reassessment_state(folder, impact.id)
        assert state.queue == [ids["housing"]]
        verified = reassessment.verify(
            folder, impact.id, ids["housing"], IN, now=clock, tool_version=TOOL_VERSION
        )
        reassessment.complete(folder, impact.id, now=clock, tool_version=TOOL_VERSION)
        after = fulltext.main_state(folder)
        summary = methods_data(folder, now=clock, tool_version=TOOL_VERSION).full_text
    finally:
        folder.close()
    assert verified.stage is Stage.FULL_TEXT
    assert after.final[ids["housing"]].value is IN
    assert after.reason(ids["housing"]) is None
    assert fulltext.kept(after) == [r for r in after.members]
    assert summary is not None
    assert (summary.changes, summary.reassessed, summary.changed) == (1, 1, 1)
