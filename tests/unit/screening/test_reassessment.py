"""Impact analysis of a criteria change during the main screening, and reassessment by
the AI then the human (EF-VER-04, EF-VER-05, EF-VER-07)."""

from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest

from revue_portee.ai.base import ModelProvider, TaskInput
from revue_portee.ai.providers.fake import FakeBatches, FakeProvider
from revue_portee.ai.settings import AITaskConfig
from revue_portee.ai.tasks.screening import ScreenReferenceInput
from revue_portee.domain.changes import ChangeType
from revue_portee.domain.criteria import CriterionKind
from revue_portee.domain.journal import EntryType
from revue_portee.domain.screening import DecisionContext, DecisionValue, RoundKind
from revue_portee.protocol import criteria, notes
from revue_portee.screening import batch_ai, main, pilot, reassessment, settings
from revue_portee.storage.project_folder import ProjectFolder
from support import TOOL_VERSION

from .common import Clock, answer

IN, EX, UN = DecisionValue.INCLUDE, DecisionValue.EXCLUDE, DecisionValue.UNCERTAIN


def factory(
    store: FakeBatches, responder: Callable[[TaskInput], dict[str, Any]] = answer
) -> Callable[[AITaskConfig], ModelProvider]:
    def build(config: AITaskConfig) -> ModelProvider:
        return FakeProvider(
            model=str(config.model),
            responder=responder,
            cost_per_call=Decimal("0.002"),
            batches=store,
        )

    return build


def broad(item: TaskInput) -> dict[str, Any]:
    """After the broadening of P1 (any adult), every reference about housing is kept."""
    assert isinstance(item, ScreenReferenceInput)
    output = answer(item)
    title = item.reference.title.lower()
    if any(word in title for word in ("housing", "logement", "home")):
        output["decision"] = "include"
        output["inclusion_probability"] = 0.9
        output["assessments"] = [
            {"code": a["code"], "status": "not_met" if a["code"] == "X1" else "met",
             "evidence_quote": ""}
            for a in output["assessments"]
        ]  # fmt: skip
    return output


def screen_with_ai(
    folder: ProjectFolder,
    clock: Clock,
    round_id: str,
    chosen: Callable[[AITaskConfig], ModelProvider],
) -> None:
    batch_ai.submit(
        folder, round_id, batch_limit=Decimal(5), factory=chosen, now=clock,
        tool_version=TOOL_VERSION,
    )  # fmt: skip
    batch_ai.follow(
        folder, round_id, factory=chosen, now=clock, tool_version=TOOL_VERSION, wait=lambda _: None
    )


@pytest.fixture
def screened(
    setup: tuple[ProjectFolder, Clock],
) -> tuple[ProjectFolder, Clock, str, dict[str, str]]:
    """A main screening where the human excluded the references without older adults
    (P1), kept the others, and the AI screened everything."""
    folder, clock = setup
    round_id = main.start_main(folder, seed=3, now=clock, tool_version=TOOL_VERSION).id
    settings.set_budget(folder, Decimal(10), now=clock, tool_version=TOOL_VERSION)
    screen_with_ai(folder, clock, round_id, factory(FakeBatches()))
    titles: dict[str, str] = {}
    from revue_portee.collect.enrichment import enriched_reference

    for ref in main.main_state(folder, round_id).members:
        found = enriched_reference(folder, ref)
        assert found is not None
        titles[ref] = found.title
        older = "older" in found.title.lower() or "aînés" in found.title.lower()
        if older:
            main.record_decision(folder, round_id, ref, IN, now=clock, tool_version=TOOL_VERSION)
        else:
            main.record_decision(
                folder, round_id, ref, EX, criteria_cited=["P1"], now=clock,
                tool_version=TOOL_VERSION,
            )  # fmt: skip
    return folder, clock, round_id, titles


def broaden_p1(folder: ProjectFolder, clock: Clock) -> None:
    criteria.update_criterion(
        folder, "P1", kind=CriterionKind.INCLUSION, text="Adults (18 and over).",
        now=clock, tool_version=TOOL_VERSION,
    )  # fmt: skip
    criteria.activate_draft(
        folder,
        rationale="Population élargie à tous les adultes.",
        qualifications={"P1": ChangeType.BROADENING},
        now=clock,
        tool_version=TOOL_VERSION,
    )


def test_nothing_to_assess_before_a_new_version(
    screened: tuple[ProjectFolder, Clock, str, dict[str, str]],
) -> None:
    folder, clock, round_id, _titles = screened
    assert reassessment.next_version_to_assess(folder, round_id) is None
    with pytest.raises(reassessment.NothingToAssessError):
        reassessment.assess(folder, round_id, now=clock, tool_version=TOOL_VERSION)


def test_broadening_reassessed_by_the_ai_then_verified(
    screened: tuple[ProjectFolder, Clock, str, dict[str, str]],
) -> None:
    folder, clock, round_id, titles = screened
    state = main.main_state(folder, round_id)
    excluded = sorted(ref for ref, d in state.final.items() if d.value is EX)
    broaden_p1(folder, clock)
    version = reassessment.next_version_to_assess(folder, round_id)
    assert version is not None
    assert version.number == 2
    impact = reassessment.assess(folder, round_id, seed=4, now=clock, tool_version=TOOL_VERSION)
    (change,) = impact.impact.changes
    assert (change.code, change.change_type) == ("P1", ChangeType.BROADENING)
    assert list(change.reference_ids) == excluded  # excluded and citing P1
    assert reassessment.next_version_to_assess(folder, round_id) is None
    entry = next(
        e for e in notes.journal_entries(folder) if e.entry_type == EntryType.IMPACT_ASSESSED
    )
    assert entry.payload["from_version"] == 1
    assert entry.payload["to_version"] == 2
    assert entry.payload["justification"] == "Population élargie à tous les adultes."
    assert entry.payload["changes"] == [
        {"code": "P1", "change_type": "broadening", "touched": len(excluded),
         "reassessed": len(excluded)}
    ]  # fmt: skip

    state_r = reassessment.reassessment_state(folder, impact.id)
    assert state_r.round.kind is RoundKind.REASSESSMENT
    assert sorted(state_r.members) == excluded
    assert state_r.ai_waiting == len(excluded)
    with pytest.raises(reassessment.ReassessmentNotFinishedError):
        reassessment.complete(folder, impact.id, now=clock, tool_version=TOOL_VERSION)

    screen_with_ai(folder, clock, state_r.round.id, factory(FakeBatches(), broad))
    state_r = reassessment.reassessment_state(folder, impact.id)
    housing = sorted(
        ref
        for ref in excluded
        if any(w in titles[ref].lower() for w in ("housing", "logement", "home"))
    )
    assert housing  # the hand-made set has excluded references about housing
    assert sorted(state_r.changed) == housing
    unchanged = next(ref for ref in excluded if ref not in housing)
    with pytest.raises(reassessment.NotAChangeError):
        reassessment.verify(folder, impact.id, unchanged, IN, now=clock, tool_version=TOOL_VERSION)

    keep, refuse = housing[0], housing[1:]
    verified = reassessment.verify(
        folder, impact.id, keep, IN, rationale="Adultes, logement.", now=clock,
        tool_version=TOOL_VERSION,
    )  # fmt: skip
    assert verified.context is DecisionContext.REASSESSMENT
    assert verified.criteria_version_id == version.id
    old = state_r.previous[keep]
    assert verified.supersedes_decision_id == old.id
    for ref in refuse:
        reassessment.verify(
            folder, impact.id, ref, EX, criteria_cited=["C1"], now=clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
    total = reassessment.complete(folder, impact.id, now=clock, tool_version=TOOL_VERSION)
    assert total == {
        "reassessed": len(excluded),
        "screened_by_ai": len(excluded),
        "ai_changes": len(housing),
        "decisions_changed": 1,
        "confirmed": len(excluded) - 1,
    }
    final = main.main_state(folder, round_id).final
    assert final[keep].id == verified.id  # the new decision is the current state
    # the old decisions are kept
    from revue_portee.storage.repositories import screening as screening_repo

    with folder.engine.connect() as connection:
        history = screening_repo.list_decisions(connection, reference_id=keep)
    assert old.id in {d.id for d in history}
    completed = notes.journal_entries(folder)[-1]
    assert completed.entry_type == EntryType.REASSESSMENT_COMPLETED
    assert completed.payload["changes"] == [{"code": "P1", "change_type": "broadening"} | total]
    assert reassessment.reassessment_state(folder, impact.id).completed
    assert notes.verify_journal(folder).valid


def test_clarification_is_reassessed_on_a_sample(
    screened: tuple[ProjectFolder, Clock, str, dict[str, str]],
) -> None:
    folder, clock, round_id, _titles = screened
    criteria.update_criterion(
        folder, "P1", kind=CriterionKind.INCLUSION, text="Older adults (65 and over), any setting.",
        now=clock, tool_version=TOOL_VERSION,
    )  # fmt: skip
    criteria.activate_draft(
        folder,
        rationale="Précision du contexte.",
        qualifications={"P1": ChangeType.CLARIFICATION},
        now=clock,
        tool_version=TOOL_VERSION,
    )
    impact = reassessment.assess(folder, round_id, seed=9, now=clock, tool_version=TOOL_VERSION)
    touched = impact.impact.changes[0].reference_ids
    assert impact.sampled
    # fewer than 20 references cite P1: all of them are reassessed
    state_r = reassessment.reassessment_state(folder, impact.id)
    assert sorted(state_r.members) == sorted(touched)


def test_a_change_touching_nothing_has_no_reassessment(
    screened: tuple[ProjectFolder, Clock, str, dict[str, str]],
) -> None:
    folder, clock, round_id, _titles = screened
    criteria.remove_criterion(folder, "X1", now=clock, tool_version=TOOL_VERSION)
    criteria.activate_draft(
        folder, rationale="Critère retiré.", now=clock, tool_version=TOOL_VERSION
    )
    impact = reassessment.assess(folder, round_id, now=clock, tool_version=TOOL_VERSION)
    assert impact.impact.touched == ()  # no exclusion cites X1 only
    assert impact.reassessment_round_id is None
    with pytest.raises(pilot.UnknownRoundError):
        reassessment.reassessment_state(folder, impact.id)
