"""Pilot round of title and abstract screening (EF-SEL-01 to 07, EF-SEL-09, ENF-TRA-01,
ENF-REP-02, ENF-COU-01 and 02), with FakeProvider."""

import json
import sqlite3
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from revue_portee.ai.base import ModelProvider, TaskInput
from revue_portee.ai.providers.fake import FakeProvider
from revue_portee.ai.settings import AITaskConfig
from revue_portee.domain.criteria import CriterionKind, PccElement
from revue_portee.domain.journal import EntryType
from revue_portee.domain.screening import DecisionValue, ReviewerKind, Thresholds
from revue_portee.protocol import criteria, notes
from revue_portee.screening import ai_screening, pilot, settings
from revue_portee.storage.project_folder import DATABASE_FILE, ProjectFolder
from revue_portee.storage.repositories import ai as ai_repo
from revue_portee.storage.repositories import screening as screening_repo
from support import TOOL_VERSION, make_clock, new_project, raw_sqlite

from .common import TITLES, Clock, answer


def provider(
    responder: Callable[[TaskInput], dict[str, Any]] = answer, cost: str = "0"
) -> Callable[[AITaskConfig], ModelProvider]:
    def factory(config: AITaskConfig) -> ModelProvider:
        return FakeProvider(
            model=str(config.model),
            model_returned="fake-screener-2026-10-08",
            responder=responder,
            cost_per_call=Decimal(cost),
        )

    return factory


def start(folder: ProjectFolder, clock: Clock, size: int = 10) -> str:
    return pilot.start_pilot(folder, size=size, seed=11, now=clock, tool_version=TOOL_VERSION).id


def budget(folder: ProjectFolder, clock: Clock, amount: str = "10") -> None:
    settings.set_budget(folder, Decimal(amount), now=clock, tool_version=TOOL_VERSION)


def run(
    folder: ProjectFolder,
    clock: Clock,
    round_id: str,
    *,
    factory: Callable[[AITaskConfig], ModelProvider] | None = None,
    batch_limit: Decimal = Decimal(5),
) -> ai_screening.AIBatchResult:
    return ai_screening.run_ai(
        folder,
        round_id,
        batch_limit=batch_limit,
        factory=factory or provider(),
        now=clock,
        tool_version=TOOL_VERSION,
    )


def test_sample_is_drawn_with_a_recorded_seed(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    first = pilot.start_pilot(folder, size=4, seed=11, now=clock, tool_version=TOOL_VERSION)
    second = pilot.start_pilot(folder, size=4, seed=11, now=clock, tool_version=TOOL_VERSION)
    assert first.reference_ids == second.reference_ids  # same seed, same sample
    assert (first.number, second.number, first.sample_size) == (1, 2, 4)
    entries = notes.journal_entries(folder)
    entry = next(e for e in entries if e.entry_type == EntryType.PILOT_STARTED)
    assert entry.payload["seed"] == 11
    assert entry.payload["population"] == 10
    big = pilot.start_pilot(folder, size=500, now=clock, tool_version=TOOL_VERSION)
    assert big.sample_size == 10  # reduced to the references available


def test_ai_decisions_are_complete_and_follow_the_rules(
    setup: tuple[ProjectFolder, Clock],
) -> None:
    folder, clock = setup
    round_id = start(folder, clock)
    with pytest.raises(settings.BudgetNotSetError):
        run(folder, clock, round_id)
    budget(folder, clock)
    preview = ai_screening.preview_ai(folder, round_id, factory=provider())
    assert preview.items == 10
    result = run(folder, clock, round_id)
    assert (result.screened, result.failed, result.stopped) == (10, [], "")
    state = pilot.pilot_state(folder, round_id)
    by_title = {state.references[r].title: d for r, d in state.ai.items()}
    included = by_title[TITLES[0]]
    assert included.value is DecisionValue.INCLUDE
    assert included.reviewer_kind is ReviewerKind.AI
    assert included.assessments[0].quote_found is True
    assert by_title[TITLES[4]].value is DecisionValue.EXCLUDE
    # no abstract: P1 cannot be told, nothing is failed by the abstract -> never excluded
    no_abstract = by_title[TITLES[1]]
    assert no_abstract.confidence_raw == 0.04
    assert no_abstract.value is DecisionValue.UNCERTAIN
    assert by_title[TITLES[2]].language == "fr"
    # ENF-TRA-01: the call holds the model returned, prompt, parameters, tokens, cost
    with folder.engine.connect() as connection:
        call = ai_repo.get_call(connection, str(included.ai_call_id))
    assert call is not None
    assert call.record.model_returned == "fake-screener-2026-10-08"
    assert call.record.prompt_template_id == "screen_reference"
    assert len(call.record.prompt_sha256) == 64
    assert call.record.response_path is not None
    entry = notes.journal_entries(folder)[-1]
    assert entry.entry_type == EntryType.SCREENING_AI_BATCH_ENDED
    assert notes.verify_journal(folder).valid


def test_a_decision_is_rebuilt_without_calling_the_model(
    setup: tuple[ProjectFolder, Clock],
) -> None:
    folder, clock = setup
    round_id = start(folder, clock, size=3)
    budget(folder, clock)
    run(folder, clock, round_id)
    for decision in pilot.pilot_state(folder, round_id).ai.values():
        assert ai_screening.replay_decision(folder, decision.id) == decision


def test_screening_is_blind(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    round_id = start(folder, clock, size=3)
    budget(folder, clock)
    run(folder, clock, round_id)
    state = pilot.pilot_state(folder, round_id)
    first = state.next_reference
    assert first is not None
    assert first in state.ai  # the AI has decided...
    assert state.visible_ai(first) is None  # ...but it is not shown before the human
    pilot.record_human_decision(
        folder, round_id, first, DecisionValue.INCLUDE, now=clock, tool_version=TOOL_VERSION
    )
    state = pilot.pilot_state(folder, round_id)
    assert state.visible_ai(first) is not None
    assert state.next_reference != first
    assert state.human[first].blinded


def test_human_decisions(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    round_id = start(folder, clock, size=3)
    ref = pilot.pilot_state(folder, round_id).round.reference_ids[0]

    def decide(value: DecisionValue, cited: tuple[str, ...] = ()) -> None:
        pilot.record_human_decision(
            folder, round_id, ref, value, criteria_cited=cited, now=clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip

    with pytest.raises(ValueError, match="EF-SEL-12"):
        decide(DecisionValue.EXCLUDE)
    with pytest.raises(ValueError, match="Z9"):
        decide(DecisionValue.EXCLUDE, ("Z9",))
    decide(DecisionValue.EXCLUDE, ("P1",))
    decide(DecisionValue.INCLUDE)
    with folder.engine.connect() as connection:
        first, second = screening_repo.list_decisions(connection, round_id=round_id)
    assert second.supersedes_decision_id == first.id
    assert pilot.pilot_state(folder, round_id).human[ref].value is DecisionValue.INCLUDE
    with pytest.raises(pilot.NotInRoundError):
        pilot.record_human_decision(
            folder, round_id, "UNKNOWN", DecisionValue.INCLUDE, now=clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
    with pytest.raises(pilot.UnknownRoundError):
        pilot.pilot_state(folder, "UNKNOWN")


def test_an_unusable_answer_is_retried_then_recorded_as_failed(
    setup: tuple[ProjectFolder, Clock],
) -> None:
    folder, clock = setup
    round_id = start(folder, clock, size=2)
    budget(folder, clock)
    attempts: list[str] = []

    def flaky(item: TaskInput) -> dict[str, Any]:
        attempts.append(item.item_id)
        good = answer(item)
        first_try = attempts.count(item.item_id) == 1
        if first_try or item.item_id == attempts[0]:  # the first reference never succeeds
            return good | {"assessments": good["assessments"][:2]}  # X1 forgotten
        return good

    result = run(folder, clock, round_id, factory=provider(flaky))
    assert result.screened == 1
    assert result.failed == [attempts[0]]
    assert len(attempts) == 4  # two attempts per reference
    with folder.engine.connect() as connection:
        assert len(ai_repo.list_calls(connection, task="screen_reference")) == 4
    types = [e.entry_type for e in notes.journal_entries(folder)]
    assert types.count(EntryType.AI_RESULT_UNUSABLE) == 3
    assert types.count(EntryType.SCREENING_AI_FAILED) == 1


def test_the_batch_stops_at_the_ceilings_without_losing_work(
    setup: tuple[ProjectFolder, Clock],
) -> None:
    folder, clock = setup
    round_id = start(folder, clock, size=6)
    budget(folder, clock, "0.035")  # three calls at 0.01
    result = run(folder, clock, round_id, factory=provider(cost="0.01"))
    assert (result.screened, result.stopped, result.spent) == (3, "project_budget", Decimal("0.03"))
    assert len(pilot.pilot_state(folder, round_id).ai) == 3
    assert EntryType.BUDGET_REACHED in [e.entry_type for e in notes.journal_entries(folder)]
    budget(folder, clock, "1")
    again = run(folder, clock, round_id, factory=provider(cost="0.01"), batch_limit=Decimal("0.02"))
    assert (again.screened, again.stopped) == (2, "batch_budget")
    last = run(folder, clock, round_id, factory=provider(cost="0.01"))
    assert (last.screened, last.stopped) == (1, "")
    assert pilot.pilot_state(folder, round_id).spent == Decimal("0.06")


def test_calibration_and_thresholds(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    round_id = start(folder, clock)
    with pytest.raises(pilot.NothingToCalibrateError):
        pilot.fit_round_calibration(folder, round_id, now=clock, tool_version=TOOL_VERSION)
    budget(folder, clock)
    run(folder, clock, round_id)
    state = pilot.pilot_state(folder, round_id)
    for ref_id, ai in state.ai.items():  # the human agrees, except on one exclusion
        value = ai.value
        if state.references[ref_id].title == TITLES[7]:
            value = DecisionValue.INCLUDE  # housing first for youth: the human keeps it
        cited = ("P1",) if value is DecisionValue.EXCLUDE else ()
        pilot.record_human_decision(
            folder, round_id, ref_id, value, criteria_cited=cited, now=clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
    state = pilot.pilot_state(folder, round_id)
    assert state.metrics is not None
    c = state.metrics.confusion
    assert c.fn == 1
    assert state.metrics.sensitivity == pytest.approx(c.tp / (c.tp + 1))
    assert state.disagreements == {"C1": 1, "P1": 1}
    assert state.curve
    assert state.suggestion is not None
    record = pilot.fit_round_calibration(folder, round_id, now=clock, tool_version=TOOL_VERSION)
    assert (folder.path / record.artifact_path).exists()
    assert record.calibration.method == "isotonic"
    with pytest.raises(ValueError, match="justification"):
        settings.set_thresholds(
            folder, Thresholds(exclude_below=0.05, include_above=0.6), justification=" ",
            target_sensitivity=Decimal("0.95"), now=clock, tool_version=TOOL_VERSION,
        )  # fmt: skip
    settings.set_thresholds(
        folder, Thresholds(exclude_below=0.05, include_above=0.6),
        justification="Sensibilité de 1 sur le pilote.", target_sensitivity=Decimal("0.95"),
        round_id=round_id, calibration_id=record.id, now=clock, tool_version=TOOL_VERSION,
    )  # fmt: skip
    thresholds, calibration = settings.thresholds_in_force(folder)
    assert thresholds.exclude_below == 0.05
    assert calibration is not None
    assert calibration.id == record.id
    # a new round is screened with the calibrated probability
    second = start(folder, clock, size=2)
    run(folder, clock, second)
    for decision in pilot.pilot_state(folder, second).ai.values():
        assert decision.calibration_id == record.id
        assert decision.confidence_calibrated is not None
        assert ai_screening.replay_decision(folder, decision.id) == decision


def test_the_database_refuses_an_incomplete_ai_decision(
    setup: tuple[ProjectFolder, Clock],
) -> None:
    folder, clock = setup
    round_id = start(folder, clock, size=1)
    budget(folder, clock)
    run(folder, clock, round_id)
    with raw_sqlite(folder.path / DATABASE_FILE) as connection:
        row = connection.execute("SELECT * FROM decision LIMIT 1").fetchone()
        columns = [d[0] for d in connection.execute("SELECT * FROM decision").description]
        values = dict(zip(columns, row, strict=True)) | {"id": "X" * 26, "ai_call_id": None}
        with pytest.raises(sqlite3.IntegrityError, match="ck_decision_ai_traceable"):
            connection.execute(
                f"INSERT INTO decision ({', '.join(values)}) "  # noqa: S608
                f"VALUES ({', '.join('?' for _ in values)})",
                list(values.values()),
            )
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            connection.execute("UPDATE decision SET value = 'exclude'")
    assert json.loads(values["per_criterion_json"])[0]["code"] == "P1"


def test_errors_before_the_pilot(tmp_path: Path) -> None:
    clock = make_clock()
    folder = new_project(tmp_path, clock)
    try:
        with pytest.raises(pilot.NoActiveCriteriaError):
            pilot.start_pilot(folder, now=clock, tool_version=TOOL_VERSION)
        criteria.add_criterion(
            folder, pcc_element=PccElement.POPULATION, kind=CriterionKind.INCLUSION,
            text="Older adults.", now=clock, tool_version=TOOL_VERSION,
        )  # fmt: skip
        criteria.activate_draft(folder, rationale="", now=clock, tool_version=TOOL_VERSION)
        with pytest.raises(pilot.NoReferencesError):
            pilot.start_pilot(folder, now=clock, tool_version=TOOL_VERSION)
    finally:
        folder.close()
