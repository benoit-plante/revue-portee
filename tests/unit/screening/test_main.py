"""Main screening, batches of the AI and reconciliation (EF-SEL-08, EF-SEL-10, EF-SEL-12,
ENF-COU-02, ENF-COU-04), with FakeProvider and fake batches."""

from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from revue_portee.ai.base import BatchStatus, ModelProvider, TaskInput
from revue_portee.ai.providers.fake import FakeBatches, FakeProvider
from revue_portee.ai.settings import AITaskConfig
from revue_portee.domain.criteria import CriterionKind, PccElement
from revue_portee.domain.journal import EntryType
from revue_portee.domain.screening import AIBatchEnd, DecisionContext, DecisionValue, disagree
from revue_portee.protocol import criteria, notes
from revue_portee.screening import ai_screening, batch_ai, main, pilot, settings
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import ai as ai_repo
from revue_portee.storage.repositories import screening as screening_repo
from support import TOOL_VERSION

from .common import Clock, answer

IN, EX, UN = DecisionValue.INCLUDE, DecisionValue.EXCLUDE, DecisionValue.UNCERTAIN
Factory = Callable[[AITaskConfig], ModelProvider]


def factory(
    batches: FakeBatches,
    responder: Callable[[TaskInput], dict[str, Any]] = answer,
    cost: str = "0.002",
) -> Factory:
    def build(config: AITaskConfig) -> ModelProvider:
        return FakeProvider(
            model=str(config.model),
            model_returned="fake-screener-2026-10-08",
            responder=responder,
            cost_per_call=Decimal(cost),
            batches=batches,
        )

    return build


def begin(folder: ProjectFolder, clock: Clock, seed: int = 5) -> str:
    return main.start_main(folder, seed=seed, now=clock, tool_version=TOOL_VERSION).id


def budget(folder: ProjectFolder, clock: Clock, amount: str = "10") -> None:
    settings.set_budget(folder, Decimal(amount), now=clock, tool_version=TOOL_VERSION)


def screen_all_with_ai(
    folder: ProjectFolder, clock: Clock, round_id: str, chosen: Factory, size: int = 4
) -> batch_ai.SubmitResult:
    sent = batch_ai.submit(
        folder,
        round_id,
        batch_limit=Decimal(5),
        factory=chosen,
        size=size,
        now=clock,
        tool_version=TOOL_VERSION,
    )
    batch_ai.follow(
        folder, round_id, factory=chosen, now=clock, tool_version=TOOL_VERSION, wait=lambda _: None
    )
    return sent


def test_main_screening_starts_with_a_recorded_seed(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    round_id = begin(folder, clock, seed=5)
    state = main.main_state(folder, round_id)
    assert len(state.members) == 10
    assert state.round.seed == 5
    with pytest.raises(main.MainRoundExistsError):
        begin(folder, clock)
    entry = next(
        e for e in notes.journal_entries(folder) if e.entry_type == EntryType.SCREENING_STARTED
    )
    assert entry.payload["seed"] == 5
    assert entry.payload["references"] == 10
    # the order is the one drawn with the seed, and the first reference comes first
    assert main.next_reference(folder, round_id) == state.members[0]
    assert main.add_new_references(folder, round_id, now=clock, tool_version=TOOL_VERSION) == 0


def test_pilot_decisions_with_the_same_criteria_are_kept(
    setup: tuple[ProjectFolder, Clock],
) -> None:
    folder, clock = setup
    sample = pilot.start_pilot(folder, size=3, seed=1, now=clock, tool_version=TOOL_VERSION)
    for ref in sample.reference_ids[:2]:
        pilot.record_human_decision(
            folder, sample.id, ref, IN, now=clock, tool_version=TOOL_VERSION
        )
    round_id = begin(folder, clock)
    state = main.main_state(folder, round_id)
    assert set(sample.reference_ids[:2]) <= state.human.keys()
    seen: set[str] = set()
    while (following := main.next_reference(folder, round_id)) is not None:
        seen.add(following)
        main.record_decision(folder, round_id, following, IN, now=clock, tool_version=TOOL_VERSION)
    assert len(seen) == 8  # the two references decided in the pilot are not screened again
    entry = next(
        e for e in notes.journal_entries(folder) if e.entry_type == EntryType.SCREENING_STARTED
    )
    assert entry.payload["pilot_decisions_kept"] == 2


def test_pilot_decisions_with_other_criteria_are_not_kept(
    setup: tuple[ProjectFolder, Clock],
) -> None:
    folder, clock = setup
    sample = pilot.start_pilot(folder, size=3, seed=1, now=clock, tool_version=TOOL_VERSION)
    pilot.record_human_decision(
        folder, sample.id, sample.reference_ids[0], IN, now=clock, tool_version=TOOL_VERSION
    )
    criteria.add_criterion(
        folder,
        pcc_element=PccElement.CONTEXT,
        kind=CriterionKind.INCLUSION,
        text="Community settings.",
        now=clock,
        tool_version=TOOL_VERSION,
    )
    criteria.activate_draft(
        folder, rationale="Contexte précisé.", now=clock, tool_version=TOOL_VERSION
    )
    round_id = begin(folder, clock)
    assert main.main_state(folder, round_id).human == {}


def test_human_decisions_of_the_main_screening(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    round_id = begin(folder, clock)
    ref = str(main.next_reference(folder, round_id))
    with pytest.raises(ValidationError):  # an exclusion names its criteria (EF-SEL-12)
        main.record_decision(folder, round_id, ref, EX, now=clock, tool_version=TOOL_VERSION)
    with pytest.raises(pilot.UnknownCriterionError):
        main.record_decision(
            folder, round_id, ref, EX, criteria_cited=["Z9"], now=clock, tool_version=TOOL_VERSION
        )
    with pytest.raises(pilot.NotInRoundError):
        main.record_decision(folder, round_id, "nope", IN, now=clock, tool_version=TOOL_VERSION)
    first = main.record_decision(
        folder, round_id, ref, EX, criteria_cited=["P1"], now=clock, tool_version=TOOL_VERSION
    )
    assert first.blinded
    assert first.context is DecisionContext.INDEPENDENT
    second = main.record_decision(folder, round_id, ref, IN, now=clock, tool_version=TOOL_VERSION)
    assert second.supersedes_decision_id == first.id
    assert main.main_state(folder, round_id).final[ref].value is IN
    assert main.next_reference(folder, round_id) != ref
    with pytest.raises(pilot.UnknownRoundError):
        main.next_reference(folder, "nope")


def test_ai_screens_in_batches_under_the_ceilings(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    round_id = begin(folder, clock)
    store = FakeBatches(polls=2)
    chosen = factory(store)
    with pytest.raises(settings.BudgetNotSetError):
        batch_ai.submit(
            folder, round_id, batch_limit=Decimal(1), factory=chosen, now=clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
    budget(folder, clock)
    preview = batch_ai.preview(folder, round_id, factory=chosen)
    assert preview.items == 10
    assert preview.estimate.amount == Decimal("0.010")  # 10 * 0.002, at half price
    sent = batch_ai.submit(
        folder,
        round_id,
        batch_limit=Decimal(5),
        factory=chosen,
        size=4,
        now=clock,
        tool_version=TOOL_VERSION,
    )
    assert [len(b.item_ids) for b in sent.batches] == [4, 4, 2]
    assert (sent.stopped, sent.left) == ("", 0)
    assert batch_ai.waiting_for_ai(folder, round_id) == []  # all held by running batches
    first = sent.batches[0]
    running = batch_ai.collect(
        folder, first.id, factory=chosen, now=clock, tool_version=TOOL_VERSION
    )
    assert isinstance(running, BatchStatus)
    assert not running.ended
    waits: list[float] = []
    ended = batch_ai.follow(
        folder, round_id, factory=chosen, now=clock, tool_version=TOOL_VERSION, wait=waits.append
    )
    assert sorted(e.screened for e in ended) == [2, 4, 4]
    assert waits == [60]  # one wait between the two rounds of status requests
    state = main.main_state(folder, round_id)
    assert len(state.ai) == 10
    with folder.engine.connect() as connection:
        calls = ai_repo.list_calls(connection, task="screen_reference")
    assert len(calls) == 10
    assert {c.record.batch_id for c in calls} == {b.provider_batch_id for b in sent.batches}
    assert {c.record.cost_estimate for c in calls} == {Decimal("0.001")}  # half price
    again = batch_ai.collect(folder, first.id, factory=chosen, now=clock, tool_version=TOOL_VERSION)
    assert isinstance(again, AIBatchEnd)  # collecting again records nothing more
    with folder.engine.connect() as connection:
        assert len(ai_repo.list_calls(connection, task="screen_reference")) == 10
    types = [e.entry_type for e in notes.journal_entries(folder)]
    assert types.count(EntryType.SCREENING_AI_BATCH_SUBMITTED) == 3
    assert types.count(EntryType.SCREENING_AI_BATCH_ENDED) == 3
    assert notes.verify_journal(folder).valid


def test_a_submission_stops_at_the_ceilings(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    round_id = begin(folder, clock)
    chosen = factory(FakeBatches())
    budget(folder, clock, "10")
    # each reference costs 0.001 at the batch price: a ceiling of 0.0065 sends 6
    sent = batch_ai.submit(
        folder, round_id, batch_limit=Decimal("0.0065"), factory=chosen, size=4,
        now=clock, tool_version=TOOL_VERSION,
    )  # fmt: skip
    assert [len(b.item_ids) for b in sent.batches] == [4, 2]
    assert (sent.stopped, sent.left) == ("batch_budget", 4)
    # the project budget counts the batches still running
    budget(folder, clock, "0.0075")
    more = batch_ai.submit(
        folder, round_id, batch_limit=Decimal(5), factory=chosen, size=4,
        now=clock, tool_version=TOOL_VERSION,
    )  # fmt: skip
    assert [len(b.item_ids) for b in more.batches] == [1]
    assert (more.stopped, more.left) == ("project_budget", 3)
    entries = [e for e in notes.journal_entries(folder) if e.entry_type == EntryType.BUDGET_REACHED]
    assert [e.payload["ceiling"] for e in entries] == ["batch_budget", "project_budget"]


def test_failed_requests_are_sent_again_then_recorded_as_failed(
    setup: tuple[ProjectFolder, Clock],
) -> None:
    folder, clock = setup
    round_id = begin(folder, clock)
    state = main.main_state(folder, round_id)
    failing, unusable = state.members[0], state.members[1]
    calls: list[str] = []

    def flaky(item: TaskInput) -> dict[str, Any]:
        calls.append(item.item_id)
        output = answer(item)
        if item.item_id == unusable and calls.count(unusable) == 1:
            output["assessments"] = output["assessments"][:1]  # asked again later
        return output

    budget(folder, clock)
    chosen = factory(FakeBatches(failing=[failing]), flaky)
    screen_all_with_ai(folder, clock, round_id, chosen)
    assert batch_ai.waiting_for_ai(folder, round_id) == [failing, unusable]
    screen_all_with_ai(folder, clock, round_id, chosen)
    assert batch_ai.waiting_for_ai(folder, round_id) == []  # two attempts each
    decided = main.main_state(folder, round_id).ai
    assert unusable in decided
    assert failing not in decided
    failures = [
        e for e in notes.journal_entries(folder) if e.entry_type == EntryType.SCREENING_AI_FAILED
    ]
    assert [e.subject_id for e in failures] == [failing]
    types = [e.entry_type for e in notes.journal_entries(folder)]
    assert EntryType.AI_RESULT_UNUSABLE in types


def test_an_interrupted_collection_resumes_without_paying_twice(
    setup: tuple[ProjectFolder, Clock],
) -> None:
    folder, clock = setup
    round_id = begin(folder, clock)
    budget(folder, clock)
    store = FakeBatches()
    chosen = factory(store)
    (batch,) = batch_ai.submit(
        folder, round_id, batch_limit=Decimal(5), factory=chosen, now=clock,
        tool_version=TOOL_VERSION,
    ).batches  # fmt: skip
    # the collection stopped after recording the first call (the server was stopped)
    original = ai_screening.store_ai_decision
    recorded: list[str] = []

    def stop_after_one(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        if recorded:
            raise KeyboardInterrupt
        recorded.append("one")
        return original(*args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(batch_ai, "store_ai_decision", stop_after_one)
        with pytest.raises(KeyboardInterrupt):
            batch_ai.collect(folder, batch.id, factory=chosen, now=clock, tool_version=TOOL_VERSION)
    with folder.engine.connect() as connection:
        assert len(ai_repo.list_calls(connection, task="screen_reference")) == 2
    end = batch_ai.collect(folder, batch.id, factory=chosen, now=clock, tool_version=TOOL_VERSION)
    assert isinstance(end, AIBatchEnd)
    with folder.engine.connect() as connection:
        assert len(ai_repo.list_calls(connection, task="screen_reference")) == 10
    # the call recorded without its decision is a failed attempt, sent again later
    assert end.screened == 9
    assert len(batch_ai.waiting_for_ai(folder, round_id)) == 1


def test_disagreements_are_exactly_the_keep_against_exclude_pairs(
    setup: tuple[ProjectFolder, Clock],
) -> None:
    folder, clock = setup
    round_id = begin(folder, clock)
    budget(folder, clock)
    screen_all_with_ai(folder, clock, round_id, factory(FakeBatches()))
    state = main.main_state(folder, round_id)
    choices = [IN, EX, UN, EX, IN, UN, EX, IN, EX, UN]
    for ref, value in zip(state.members, choices, strict=True):
        cited = ["C1"] if value is EX else []
        main.record_decision(
            folder, round_id, ref, value, criteria_cited=cited, now=clock, tool_version=TOOL_VERSION
        )
    state = main.main_state(folder, round_id)
    expected = [
        ref
        for ref, value in zip(state.members, choices, strict=True)
        if disagree(value, state.ai[ref].value)
    ]
    assert expected  # the hand-made choices give disagreements
    assert state.disagreements == expected
    assert state.queue == expected
    agreeing = next(ref for ref in state.members if ref not in expected)
    assert state.visible_ai(agreeing) is None  # the AI is shown only to reconcile
    with pytest.raises(main.NotADisagreementError):
        main.reconcile(folder, round_id, agreeing, IN, now=clock, tool_version=TOOL_VERSION)
    target = expected[0]
    assert state.visible_ai(target) is state.ai[target]
    final = main.reconcile(
        folder,
        round_id,
        target,
        IN,
        rationale="Vu le résumé.",
        now=clock,
        tool_version=TOOL_VERSION,
    )
    assert final.context is DecisionContext.RECONCILIATION
    assert final.supersedes_decision_id == state.human[target].id
    after = main.main_state(folder, round_id)
    assert target not in after.queue
    assert after.final[target].id == final.id
    counts = main.progress(after)
    assert (counts.members, counts.human, counts.ai) == (10, 10, 10)
    assert counts.reconciled == 1
    assert counts.to_reconcile == len(expected) - 1
    entry = notes.journal_entries(folder)[-1]
    assert entry.entry_type == EntryType.SCREENING_RECONCILED
    assert entry.payload["ai_decision"] == state.ai[target].id


def test_priority_by_probability_of_inclusion(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    round_id = begin(folder, clock)
    budget(folder, clock)
    screen_all_with_ai(folder, clock, round_id, factory(FakeBatches()))
    state = main.main_state(folder, round_id)
    first = main.next_reference(folder, round_id, priority=True)
    assert first is not None
    best = max(state.ai[r].confidence_raw or 0 for r in state.members)
    assert state.ai[first].confidence_raw == best
    plain = main.next_reference(folder, round_id)
    assert plain == state.members[0]
    with folder.engine.connect() as connection:
        assert screening_repo.member_count(connection, round_id) == 10


def test_a_provider_without_batches_is_refused(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    round_id = begin(folder, clock)

    class Plain:
        name = "plain"

    with pytest.raises(batch_ai.NotBatchCapableError, match="plain"):
        batch_ai.preview(folder, round_id, factory=lambda _config: Plain())  # type: ignore[arg-type,return-value]


def test_no_main_screening_before_references(tmp_path: Any) -> None:  # noqa: ANN401
    from support import make_clock, new_project

    clock = make_clock()
    folder = new_project(tmp_path, clock)
    try:
        with pytest.raises(pilot.NoActiveCriteriaError):
            begin(folder, clock)
        criteria.add_criterion(
            folder, pcc_element=PccElement.POPULATION, kind=CriterionKind.INCLUSION,
            text="Older adults.", now=clock, tool_version=TOOL_VERSION,
        )  # fmt: skip
        criteria.activate_draft(folder, rationale="", now=clock, tool_version=TOOL_VERSION)
        with pytest.raises(pilot.NoReferencesError):
            begin(folder, clock)
        assert main.main_round(folder) is None
    finally:
        folder.close()
