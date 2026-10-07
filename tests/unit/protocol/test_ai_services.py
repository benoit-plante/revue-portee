"""AI-assisted framing and qualification, with FakeProvider (EF-CAD-02, EF-VER-03,
ENF-COU-01, ENF-TRA-01)."""

import sqlite3
import tomllib
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import tomli_w

from revue_portee.ai.base import (
    AICallRecord,
    CostEstimate,
    ModelProvider,
    ProviderCallError,
    TaskInput,
    TaskOutput,
    TaskResult,
    TaskSpec,
    result_type,
)
from revue_portee.ai.settings import AITaskConfig, TaskNotAvailableError
from revue_portee.ai.tasks import QualifyChangeInput
from revue_portee.domain.changes import ChangeType
from revue_portee.domain.criteria import CriterionKind, PccElement
from revue_portee.domain.framing import Framing
from revue_portee.domain.journal import EntryType
from revue_portee.domain.project import ReviewerKind
from revue_portee.domain.protocol import ProtocolSection, ProtocolText
from revue_portee.domain.suggestions import SuggestionKind, SuggestionOutcome
from revue_portee.protocol import criteria, framing, notes, qualification, registration, suggestions
from revue_portee.protocol.ai_assist import AITaskError
from revue_portee.storage.project_folder import PROJECT_FILE, ProjectFolder, ProjectFolderError
from revue_portee.storage.raw import read_raw_response
from revue_portee.storage.repositories import ai as ai_repo
from support import TOOL_VERSION, fake_factory, make_clock, new_project, raw_sqlite

Clock = Callable[[], datetime]
POP, CON = PccElement.POPULATION, PccElement.CONCEPT
INC = CriterionKind.INCLUSION


def pcc_answer(_item: object) -> dict[str, Any]:
    return {
        "suggestions": [
            {
                "kind": "reformulation",
                "text": "Quelles interventions existent ?",
                "rationale": "R1",
            },
            {"kind": "secondary_question", "text": "Dans quels contextes ?", "rationale": "R2"},
            {"kind": "population", "text": "Parents et tuteurs", "rationale": "R3"},
        ]
    }


def qualify_answer(item: object) -> dict[str, Any]:
    assert isinstance(item, QualifyChangeInput)
    return {"change_type": "broadening", "confidence": 0.75, "rationale": f"{item.code} élargi"}


FACTORY = fake_factory({"SuggestPccInput": pcc_answer, "QualifyChangeInput": qualify_answer})


@pytest.fixture
def setup(tmp_path: Path) -> Iterator[tuple[ProjectFolder, Clock]]:
    clock = make_clock()
    folder = new_project(tmp_path, clock)
    yield folder, clock
    folder.close()


def frame(folder: ProjectFolder, clock: Clock) -> None:
    framing.save_framing(
        folder,
        Framing(question="Quelles interventions ?", population="Parents"),
        now=clock,
        tool_version=TOOL_VERSION,
    )


def types(folder: ProjectFolder) -> list[str]:
    return [e.entry_type for e in notes.journal_entries(folder)]


# --- Framing suggestions --------------------------------------------------------------


def test_preview_shows_the_configured_model_and_writes_nothing(
    setup: tuple[ProjectFolder, Clock],
) -> None:
    folder, clock = setup
    frame(folder, clock)
    before = types(folder)
    preview = suggestions.preview_suggestions(folder, factory=FACTORY)
    assert (preview.task, preview.provider, preview.items) == ("suggest_pcc", "fake", 1)
    assert preview.model == folder.ai_settings().enabled_task("suggest_pcc").model
    assert preview.prices_as_of == date(2026, 10, 6)
    assert types(folder) == before


def test_suggestions_need_a_framing(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    with pytest.raises(suggestions.NoFramingError, match="question principale"):
        suggestions.preview_suggestions(folder, factory=FACTORY)
    with pytest.raises(suggestions.NoFramingError):
        suggestions.request_suggestions(
            folder, now=clock, tool_version=TOOL_VERSION, factory=FACTORY
        )


def test_suggestions_are_recorded_with_their_call(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    frame(folder, clock)
    received = suggestions.request_suggestions(
        folder, now=clock, tool_version=TOOL_VERSION, factory=FACTORY
    )
    assert [s.kind for s in received] == [
        SuggestionKind.REFORMULATION,
        SuggestionKind.SECONDARY_QUESTION,
        SuggestionKind.POPULATION,
    ]
    with folder.engine.connect() as connection:
        (call,) = ai_repo.list_calls(connection)
    assert all(s.ai_call_id == call.id for s in received)
    record = call.record
    assert (call.task, record.provider, record.model_returned) == (
        "suggest_pcc",
        "fake",
        "fake-model-2026-10-07",
    )
    assert record.model_requested == folder.ai_settings().enabled_task("suggest_pcc").model
    assert (record.prompt_template_id, record.prompt_template_version) == ("suggest_pcc", "1")
    assert len(record.prompt_sha256) == 64
    assert record.status == "ok"
    assert types(folder)[-2:] == [
        EntryType.AI_CONFIG_RECORDED,
        EntryType.FRAMING_SUGGESTIONS_RECEIVED,
    ]
    entry = notes.journal_entries(folder)[-1]
    assert entry.payload["ai_call_id"] == call.id
    assert entry.payload["model_returned"] == "fake-model-2026-10-07"
    recorded = entry.payload["suggestions"]
    assert isinstance(recorded, list)
    assert [s["text"] for s in recorded if isinstance(s, dict)] == [s.text for s in received]


def test_same_configuration_is_recorded_once(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    frame(folder, clock)
    for _ in range(2):
        suggestions.request_suggestions(
            folder, now=clock, tool_version=TOOL_VERSION, factory=FACTORY
        )
    assert types(folder).count(EntryType.AI_CONFIG_RECORDED) == 1
    with folder.engine.connect() as connection:
        calls = ai_repo.list_calls(connection)
    assert len({c.ai_config_id for c in calls}) == 1
    assert len(suggestions.list_suggestions(folder)) == 6


def test_accept_modify_reject(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    frame(folder, clock)
    reformulation, secondary, population = suggestions.request_suggestions(
        folder, now=clock, tool_version=TOOL_VERSION, factory=FACTORY
    )
    review = suggestions.review_suggestion(
        folder,
        reformulation.id,
        SuggestionOutcome.ACCEPTED,
        now=clock,
        tool_version=TOOL_VERSION,
    )
    assert review.final_text == "Quelles interventions existent ?"
    suggestions.review_suggestion(
        folder,
        population.id,
        SuggestionOutcome.MODIFIED,
        text="Parents, tuteurs et beaux-parents",
        now=clock,
        tool_version=TOOL_VERSION,
    )
    rejected = suggestions.review_suggestion(
        folder, secondary.id, SuggestionOutcome.REJECTED, now=clock, tool_version=TOOL_VERSION
    )
    assert (rejected.final_text, rejected.framing_version_id) == ("", None)

    current = framing.current_framing(folder)
    assert current is not None
    assert current.number == 3
    assert current.framing.question == "Quelles interventions existent ?"
    assert current.framing.population == "Parents, tuteurs et beaux-parents"
    assert current.framing.secondary_questions == ()
    assert types(folder)[-5:] == [
        EntryType.FRAMING_UPDATED,
        EntryType.FRAMING_SUGGESTION_REVIEWED,
        EntryType.FRAMING_UPDATED,
        EntryType.FRAMING_SUGGESTION_REVIEWED,
        EntryType.FRAMING_SUGGESTION_REVIEWED,
    ]
    reviewed = notes.journal_entries(folder)[-2]
    assert reviewed.payload == {
        "ai_call_id": population.ai_call_id,
        "kind": "population",
        "outcome": "modified",
        "proposed_text": "Parents et tuteurs",
        "final_text": "Parents, tuteurs et beaux-parents",
        "framing_version_id": current.id,
    }
    views = {v.suggestion.id: v for v in suggestions.list_suggestions(folder)}
    assert views[secondary.id].review == rejected
    assert views[secondary.id].model_returned == "fake-model-2026-10-07"
    assert notes.verify_journal(folder).valid


def test_review_rules(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    frame(folder, clock)
    first, second, _ = suggestions.request_suggestions(
        folder, now=clock, tool_version=TOOL_VERSION, factory=FACTORY
    )
    with pytest.raises(suggestions.UnknownSuggestionError):
        suggestions.review_suggestion(
            folder, "nope", SuggestionOutcome.ACCEPTED, now=clock, tool_version=TOOL_VERSION
        )
    with pytest.raises(suggestions.MissingTextError):
        suggestions.review_suggestion(
            folder, first.id, SuggestionOutcome.MODIFIED, text=" ", now=clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
    unchanged = suggestions.review_suggestion(
        folder, first.id, SuggestionOutcome.MODIFIED, text=first.text, now=clock,
        tool_version=TOOL_VERSION,
    )  # fmt: skip
    assert unchanged.outcome is SuggestionOutcome.ACCEPTED
    with pytest.raises(suggestions.AlreadyReviewedError):
        suggestions.review_suggestion(
            folder, first.id, SuggestionOutcome.REJECTED, now=clock, tool_version=TOOL_VERSION
        )
    # A duplicate review is also refused by the database (one per suggestion).
    with (
        pytest.raises(sqlite3.IntegrityError),
        raw_sqlite(folder.path / "revue.sqlite") as connection,
    ):
        connection.execute(
            "INSERT INTO suggestion_review SELECT 'X', suggestion_id, outcome, final_text, "
            "reviewer_id, created_at, framing_version_id, journal_entry_id "
            "FROM suggestion_review"
        )
    assert second.id not in {
        v.suggestion.id for v in suggestions.list_suggestions(folder) if v.review
    }


class FailingProvider:
    """Answers with a failed call, as AnthropicProvider does on a refusal."""

    name = "fake"

    def supports(self, task: TaskSpec[Any, Any]) -> bool:
        return True

    def estimate_cost(self, task: TaskSpec[Any, Any], inputs: Sequence[TaskInput]) -> CostEstimate:
        return CostEstimate(input_tokens=1, output_tokens=1, amount=Decimal("0.01"))

    def run(self, task: TaskSpec[Any, Any], inputs: Sequence[TaskInput]) -> Iterator[Any]:
        call = AICallRecord(
            provider="fake",
            model_requested="fake-model",
            model_returned="fake-model",
            prompt_template_id=task.prompt.template_id,
            prompt_template_version=task.prompt.version,
            prompt_sha256="0" * 64,
            input_tokens=12,
            output_tokens=0,
            cost_estimate=Decimal("0.0001"),
            latency_ms=5,
            status="error",
            error_code="refusal",
            created_at=datetime(2026, 10, 7, tzinfo=UTC),
        )
        raise ProviderCallError(
            "Le modèle a refusé.", item_id=inputs[0].item_id, call=call, raw_response={"x": 1}
        )


def test_failed_call_is_recorded_and_reported(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    frame(folder, clock)
    with pytest.raises(AITaskError, match=r"Le modèle a refusé\.") as raised:
        suggestions.request_suggestions(
            folder, now=clock, tool_version=TOOL_VERSION, factory=lambda _c: FailingProvider()
        )
    with folder.engine.connect() as connection:
        call = ai_repo.get_call(connection, raised.value.call_id)
    assert call is not None
    assert (call.record.status, call.record.error_code) == ("error", "refusal")
    assert call.record.response_path is not None
    assert read_raw_response(folder.path, call.record.response_path) == {"x": 1}
    assert types(folder)[-1] == EntryType.AI_CALL_FAILED
    assert suggestions.list_suggestions(folder) == []


class RawProvider:
    """FakeProvider-like provider that also returns a raw response."""

    name = "fake"

    def __init__(self, inner: ModelProvider) -> None:
        self._inner = inner

    def supports(self, task: TaskSpec[Any, Any]) -> bool:
        return True

    def estimate_cost(self, task: TaskSpec[Any, Any], inputs: Sequence[TaskInput]) -> CostEstimate:
        return self._inner.estimate_cost(task, inputs)

    def run[I: TaskInput, O: TaskOutput](
        self, task: TaskSpec[I, O], inputs: Sequence[I]
    ) -> Iterator[TaskResult[O]]:
        for result in self._inner.run(task, inputs):
            yield result_type(task.output_model)(
                **result.model_dump(exclude={"output", "raw_response"}),
                output=result.output,
                raw_response={"id": "msg_1", "content": "brut"},
            )


def test_raw_response_is_kept_compressed(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    frame(folder, clock)

    def factory(config: AITaskConfig) -> ModelProvider:
        return RawProvider(FACTORY(config))

    suggestions.request_suggestions(folder, now=clock, tool_version=TOOL_VERSION, factory=factory)
    with folder.engine.connect() as connection:
        (call,) = ai_repo.list_calls(connection)
    path = call.record.response_path
    assert path is not None
    assert path == f"brut/ia/2026/10/{call.id}.json.gz"
    assert read_raw_response(folder.path, path) == {"content": "brut", "id": "msg_1"}


def test_task_must_be_enabled_in_the_project(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    frame(folder, clock)
    project_file = folder.path / PROJECT_FILE
    settings = folder.ai_settings().model_dump(mode="json", exclude_none=True)
    settings["tasks"]["suggest_pcc"] = {"status": "planned"}
    content = tomllib.loads(project_file.read_text(encoding="utf-8"))
    content["ia"] = settings
    project_file.write_text(tomli_w.dumps(content), encoding="utf-8")
    with pytest.raises(TaskNotAvailableError, match="suggest_pcc"):
        suggestions.preview_suggestions(folder, factory=FACTORY)
    content["ia"] = {"supervision": {}, "tasks": {}}
    project_file.write_text(tomli_w.dumps(content), encoding="utf-8")
    with pytest.raises(ProjectFolderError, match=r"\[ia\]"):
        folder.ai_settings()
    del content["ia"]
    project_file.write_text(tomli_w.dumps(content), encoding="utf-8")
    assert folder.ai_settings().enabled_task("suggest_pcc").status == "enabled"


APPEND_ONLY = (
    "ai_config",
    "ai_call",
    "ai_suggestion",
    "suggestion_review",
    "qualification_proposal",
    "criterion_change",
    "protocol_text_version",
    "protocol_registration",
)


def populate(folder: ProjectFolder, clock: Clock) -> None:
    """One row at least in every table of tranche 1.2."""
    frame(folder, clock)
    (first, *_) = suggestions.request_suggestions(
        folder, now=clock, tool_version=TOOL_VERSION, factory=FACTORY
    )
    suggestions.review_suggestion(
        folder, first.id, SuggestionOutcome.REJECTED, now=clock, tool_version=TOOL_VERSION
    )
    criteria_v1(folder, clock)
    registration.register_protocol(
        folder, "10.17605/OSF.IO/ABCDE", date(2026, 10, 1), now=clock, tool_version=TOOL_VERSION
    )
    registration.save_protocol_text(
        folder,
        ProtocolText(sections={ProtocolSection.FUNDING: "Aucun."}),
        now=clock,
        tool_version=TOOL_VERSION,
    )
    edit_p1(folder, clock, "Parents d'enfants de 0 à 17 ans")
    qualification.request_proposals(folder, now=clock, tool_version=TOOL_VERSION, factory=FACTORY)
    criteria.activate_draft(
        folder,
        rationale="Adolescents",
        qualifications={"P1": ChangeType.BROADENING},
        now=clock,
        tool_version=TOOL_VERSION,
    )


@pytest.mark.parametrize("table", APPEND_ONLY)
@pytest.mark.parametrize("statement", ["UPDATE {table} SET id = id", "DELETE FROM {table}"])
def test_new_tables_are_append_only(
    setup: tuple[ProjectFolder, Clock], table: str, statement: str
) -> None:
    folder, clock = setup
    populate(folder, clock)
    with raw_sqlite(folder.path / "revue.sqlite") as connection:
        assert connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] > 0  # noqa: S608
        with pytest.raises(sqlite3.IntegrityError, match=f"append-only: {table}"):
            connection.execute(statement.format(table=table))


# --- Qualification of criteria changes ------------------------------------------------


def criteria_v1(folder: ProjectFolder, clock: Clock) -> None:
    for element, wording in ((POP, "Parents d'enfants de 0 à 12 ans"), (CON, "Soutien")):
        criteria.add_criterion(
            folder, pcc_element=element, kind=INC, text=wording, now=clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
    criteria.activate_draft(folder, rationale="", now=clock, tool_version=TOOL_VERSION)


def edit_p1(folder: ProjectFolder, clock: Clock, wording: str) -> None:
    criteria.update_criterion(
        folder, "P1", kind=INC, text=wording, now=clock, tool_version=TOOL_VERSION
    )


def test_nothing_to_qualify(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    assert qualification.pending_qualification(folder) is None
    criteria_v1(folder, clock)
    criteria.add_criterion(
        folder, pcc_element=CON, kind=INC, text="Autre", now=clock, tool_version=TOOL_VERSION
    )
    pending = qualification.pending_qualification(folder)
    assert pending is not None
    assert [c.code for c in pending.diff.added] == ["C2"]
    with pytest.raises(qualification.NothingToQualifyError):
        qualification.preview_proposals(folder, factory=FACTORY)


def test_ai_proposes_and_the_human_confirms(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    criteria_v1(folder, clock)
    edit_p1(folder, clock, "Parents d'enfants de 0 à 17 ans")
    criteria.update_criterion(
        folder, "C1", kind=INC, text="Soutien parental", now=clock, tool_version=TOOL_VERSION
    )
    preview = qualification.preview_proposals(folder, factory=FACTORY)
    assert (preview.task, preview.items) == ("qualify_criterion_change", 2)
    proposals = qualification.request_proposals(
        folder, now=clock, tool_version=TOOL_VERSION, factory=FACTORY
    )
    assert [(p.code, p.change_type, p.confidence) for p in proposals] == [
        ("P1", ChangeType.BROADENING, 0.75),
        ("C1", ChangeType.BROADENING, 0.75),
    ]
    assert types(folder).count(EntryType.CRITERIA_CHANGE_PROPOSED) == 2
    pending = qualification.pending_qualification(folder)
    assert pending is not None
    assert set(pending.proposals) == {"P1", "C1"}

    with pytest.raises(qualification.MissingQualificationError, match="C1"):
        criteria.activate_draft(
            folder,
            rationale="Adolescents",
            qualifications={"P1": ChangeType.BROADENING},
            now=clock,
            tool_version=TOOL_VERSION,
        )
    assert criteria.criteria_state(folder).draft is not None  # nothing was activated
    v2 = criteria.activate_draft(
        folder,
        rationale="Adolescents",
        qualifications={"P1": ChangeType.BROADENING, "C1": ChangeType.CLARIFICATION},
        now=clock,
        tool_version=TOOL_VERSION,
    )
    changes = {c.code: c for c in qualification.version_changes(folder, v2.id)}
    assert changes["P1"].proposed_by is ReviewerKind.AI  # the human confirmed the AI
    assert changes["C1"].proposed_by is ReviewerKind.HUMAN  # the human corrected it
    assert changes["C1"].proposal_id == pending.proposals["C1"].id
    assert all(c.confirmed_by == folder.reviewer_id for c in changes.values())
    assert types(folder)[-3:] == [
        EntryType.CRITERIA_CHANGE_QUALIFIED,
        EntryType.CRITERIA_CHANGE_QUALIFIED,
        EntryType.CRITERIA_VERSION_CREATED,
    ]
    assert notes.journal_entries(folder)[-2].payload["ai_proposed_type"] == "broadening"
    assert notes.verify_journal(folder).valid


def test_a_proposal_is_dropped_when_the_criterion_changes_again(
    setup: tuple[ProjectFolder, Clock],
) -> None:
    folder, clock = setup
    criteria_v1(folder, clock)
    edit_p1(folder, clock, "Parents d'enfants de 0 à 17 ans")
    qualification.request_proposals(folder, now=clock, tool_version=TOOL_VERSION, factory=FACTORY)
    edit_p1(folder, clock, "Parents d'enfants de 6 à 12 ans")
    pending = qualification.pending_qualification(folder)
    assert pending is not None
    assert pending.proposals == {}
    v2 = criteria.activate_draft(
        folder,
        rationale="Enfants d'âge scolaire",
        qualifications={"P1": ChangeType.NARROWING},
        now=clock,
        tool_version=TOOL_VERSION,
    )
    (change,) = qualification.version_changes(folder, v2.id)
    assert (change.proposed_by, change.proposal_id) == (ReviewerKind.HUMAN, None)


def test_added_and_removed_criteria_are_qualified_automatically(
    setup: tuple[ProjectFolder, Clock],
) -> None:
    folder, clock = setup
    criteria_v1(folder, clock)
    criteria.remove_criterion(folder, "C1", now=clock, tool_version=TOOL_VERSION)
    criteria.add_criterion(
        folder, pcc_element=CON, kind=INC, text="Soutien parental", now=clock,
        tool_version=TOOL_VERSION,
    )  # fmt: skip
    v2 = criteria.activate_draft(
        folder, rationale="Remplacer C1", now=clock, tool_version=TOOL_VERSION
    )
    changes = [(c.code, c.change_type) for c in qualification.version_changes(folder, v2.id)]
    assert changes == [("C1", ChangeType.REMOVED), ("C2", ChangeType.ADDED)]


# --- Registration and deviations ------------------------------------------------------


def test_registration_marks_later_versions_as_deviations(
    setup: tuple[ProjectFolder, Clock],
) -> None:
    folder, clock = setup
    criteria_v1(folder, clock)
    assert registration.current_registration(folder) is None
    registered = registration.register_protocol(
        folder,
        "https://doi.org/10.17605/osf.io/abcde",
        date(2026, 10, 1),
        now=clock,
        tool_version=TOOL_VERSION,
    )
    v1 = criteria.criteria_state(folder).active
    assert v1 is not None
    assert (registered.doi, registered.criteria_version_id) == ("10.17605/OSF.IO/ABCDE", v1.id)
    assert not v1.after_protocol_registration
    entry = notes.journal_entries(folder)[-1]
    assert entry.entry_type == EntryType.PROTOCOL_REGISTERED
    assert entry.payload["criteria_version_number"] == 1

    edit_p1(folder, clock, "Parents d'enfants de 0 à 17 ans")
    v2 = criteria.activate_draft(
        folder,
        rationale="Adolescents",
        qualifications={"P1": ChangeType.BROADENING},
        now=clock,
        tool_version=TOOL_VERSION,
    )
    assert v2.after_protocol_registration
    assert criteria.version(folder, 2).after_protocol_registration
    assert not criteria.version(folder, 1).after_protocol_registration
    created = notes.journal_entries(folder)[-1]
    assert created.summary_fr.endswith("(écart au protocole enregistré)")
    assert created.payload["protocol_doi"] == "10.17605/OSF.IO/ABCDE"


def test_registration_rules(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    with pytest.raises(registration.InvalidDoiError, match=r"10\.17605/OSF\.IO/ABCDE"):
        registration.register_protocol(
            folder, "osf.io/abcde", date(2026, 10, 1), now=clock, tool_version=TOOL_VERSION
        )
    with pytest.raises(registration.InvalidRegistrationDateError):
        registration.register_protocol(
            folder, "10.17605/OSF.IO/ABCDE", date(2026, 10, 8), now=clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
    done = registration.register_protocol(
        folder, "10.17605/OSF.IO/ABCDE", date(2026, 10, 7), now=clock, tool_version=TOOL_VERSION
    )
    assert done.criteria_version_id is None


def test_protocol_text_is_versioned(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    assert (
        registration.save_protocol_text(
            folder, ProtocolText(), now=clock, tool_version=TOOL_VERSION
        )
        is None
    )
    first = registration.save_protocol_text(
        folder,
        ProtocolText(sections={ProtocolSection.FUNDING: "Aucun financement."}),
        now=clock,
        tool_version=TOOL_VERSION,
    )
    same = registration.save_protocol_text(
        folder,
        ProtocolText(sections={ProtocolSection.FUNDING: " Aucun financement. "}),
        now=clock,
        tool_version=TOOL_VERSION,
    )
    assert first is not None
    assert same == first
    second = registration.save_protocol_text(
        folder,
        ProtocolText(sections={ProtocolSection.CONFLICTS: "Aucun."}),
        now=clock,
        tool_version=TOOL_VERSION,
    )
    assert second is not None
    assert second.number == 2
    assert registration.current_protocol_text(folder) == second
    entry = notes.journal_entries(folder)[-1]
    assert entry.payload["changed_sections"] == ["conflicts", "funding"]
