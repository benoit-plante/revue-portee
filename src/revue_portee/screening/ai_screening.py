"""Title and abstract screening by the AI reviewer (EF-SEL-06, EF-SEL-07, ENF-TRA-01,
ENF-REP-02, ENF-COU-01, ENF-COU-02).

The cost of a batch is shown before it starts. Each call is recorded in its own
transaction with its raw response (D-041); an answer that does not match the criteria
of the round is asked again once, then the failure is recorded. Before each call, its
estimated cost is added to what is spent: the batch stops cleanly at the ceiling of
the project or of the batch, and what was screened stays recorded. A decision can be
rebuilt from the raw response without calling the model again.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from pydantic import JsonValue

from revue_portee.ai.base import ProviderCallError
from revue_portee.ai.providers import ProviderFactory
from revue_portee.ai.runner import run_task
from revue_portee.ai.tasks.screening import (
    SCREEN_REFERENCE,
    CriterionText,
    ReferenceText,
    ScreenReferenceInput,
    ScreenReferenceOutput,
)
from revue_portee.collect.deduplication import dedup_state
from revue_portee.dedup.normalize import normalize_text
from revue_portee.domain.criteria import CriteriaVersion
from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.domain.project import Reviewer
from revue_portee.domain.references import Reference
from revue_portee.domain.screening import (
    AssessmentStatus,
    CalibrationRecord,
    CriterionAssessment,
    Decision,
    DecisionContext,
    DecisionValue,
    PilotRound,
    ReviewerKind,
    Thresholds,
    ai_value,
    detect_language,
    must_not_exclude,
)
from revue_portee.i18n import french
from revue_portee.protocol.ai_assist import (
    CostPreview,
    call_summary,
    default_provider_factory,
    preview,
    record_call,
    record_unusable,
)
from revue_portee.protocol.framing import current_framing
from revue_portee.screening.pilot import STAGE, criteria_of, get_round, latest_by_reference
from revue_portee.screening.settings import BudgetNotSetError, thresholds_in_force
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.raw import read_raw_response
from revue_portee.storage.repositories import ai as ai_repo
from revue_portee.storage.repositories import criteria as criteria_repo
from revue_portee.storage.repositories import journal, projects
from revue_portee.storage.repositories import screening as screening_repo
from revue_portee.storage.repositories.ai import StoredCall

__all__ = [
    "MAX_ATTEMPTS",
    "AIBatchResult",
    "UnusableAnswerError",
    "ai_reviewer",
    "check_answer",
    "decision_context",
    "inputs_for",
    "preview_ai",
    "record_ai_failure",
    "replay_decision",
    "run_ai",
    "store_ai_decision",
]

Clock = Callable[[], datetime]
# An answer that does not match the schema or the criteria is asked again once.
MAX_ATTEMPTS = 2


class UnusableAnswerError(ValueError):
    """An answer valid against the schema but not against the criteria of the round."""


def decision_context(folder: ProjectFolder) -> DecisionContext:
    """Context of an AI decision: final in a replication project (D-104), otherwise
    independent of the person's."""
    return DecisionContext.REPLICATION if folder.replication else DecisionContext.INDEPENDENT


def inputs_for(
    folder: ProjectFolder,
    version: CriteriaVersion,
    reference_ids: Sequence[str],
    references: Mapping[str, Reference] | None = None,
) -> list[ScreenReferenceInput]:
    """What the model sees of each reference, with the criteria of ``version``."""
    if references is None:
        references = dedup_state(folder).references
    with folder.engine.connect() as connection:
        language = projects.get_project(connection).language
    framing = current_framing(folder)
    criteria = tuple(CriterionText.of(c) for c in version.criteria)
    return [
        ScreenReferenceInput(
            item_id=ref_id,
            language=language,
            review_question="" if framing is None else framing.framing.question,
            criteria=criteria,
            reference=_reference_text(references[ref_id]),
        )
        for ref_id in reference_ids
    ]


def _reference_text(ref: Reference) -> ReferenceText:
    return ReferenceText(
        title=ref.title,
        abstract=ref.abstract,
        year=ref.year,
        container_title=ref.container_title,
        doc_type=ref.doc_type,
        language=ref.language,
    )


def _waiting_for_ai(folder: ProjectFolder, pilot: PilotRound) -> list[str]:
    with folder.engine.connect() as connection:
        decided = latest_by_reference(
            screening_repo.list_decisions(connection, round_id=pilot.id), ReviewerKind.AI
        )
    return [ref_id for ref_id in pilot.reference_ids if ref_id not in decided]


def preview_ai(
    folder: ProjectFolder, round_id: str, *, factory: ProviderFactory = default_provider_factory
) -> CostPreview:
    """Cost of screening the references of the round that the AI has not decided yet."""
    pilot = get_round(folder, round_id)
    return preview(
        folder,
        SCREEN_REFERENCE,
        inputs_for(folder, criteria_of(folder, pilot), _waiting_for_ai(folder, pilot)),
        factory=factory,
    )


def check_answer(output: ScreenReferenceOutput, codes: Sequence[str]) -> None:
    """UnusableAnswerError unless each criterion is assessed exactly once and the
    decisive criteria are criteria of the version."""
    assessed = [a.code for a in output.assessments]
    if sorted(assessed) != sorted(codes):
        raise UnusableAnswerError("each criterion must be assessed exactly once")
    if not set(output.decisive_criteria) <= set(codes):
        raise UnusableAnswerError("decisive criteria must be criteria of the version")


def _ai_decision(
    output: ScreenReferenceOutput,
    *,
    reference: Reference,
    version: CriteriaVersion,
    thresholds: Thresholds,
    calibration: CalibrationRecord | None,
    decision_id: str,
    round_id: str,
    reviewer_id: str,
    call_id: str,
    tool_version: str,
    moment: datetime,
    context: DecisionContext = DecisionContext.INDEPENDENT,
) -> Decision:
    """The AI decision derived from an answer: the same answer always gives the same
    decision, which is how a decision is rebuilt without calling the model again."""
    kinds = {c.code: c.kind for c in version.criteria}
    text = searchable_text(reference.title, reference.abstract)
    assessments = tuple(
        CriterionAssessment(
            code=a.code,
            kind=kinds[a.code],
            status=AssessmentStatus(a.status),
            evidence_quote=a.evidence_quote,
            quote_found=quote_found(a.evidence_quote, text),
        )
        for a in sorted(output.assessments, key=lambda a: list(kinds).index(a.code))
    )
    raw = output.inclusion_probability
    calibrated = None if calibration is None else calibration.calibration.apply(raw)
    probability = raw if calibrated is None else calibrated
    return Decision(
        id=decision_id,
        reference_id=reference.id,
        stage=STAGE,
        round_id=round_id,
        reviewer_id=reviewer_id,
        reviewer_kind=ReviewerKind.AI,
        value=ai_value(probability, thresholds, assessments),
        confidence_raw=raw,
        confidence_calibrated=calibrated,
        rationale=output.rationale,
        criteria_cited=tuple(dict.fromkeys(output.decisive_criteria)),
        assessments=assessments,
        model_decision=DecisionValue(output.decision),
        thresholds=thresholds,
        calibration_id=None if calibration is None else calibration.id,
        criteria_version_id=version.id,
        language=detect_language(reference.language, reference.title, reference.abstract),
        context=context,
        ai_call_id=call_id,
        tool_version=tool_version,
        created_at=moment,
    )


def ai_reviewer(folder: ProjectFolder, stored: StoredCall, *, now: Clock, tool_version: str) -> str:
    """The reviewer row of the AI configuration that made the call (created once)."""
    with folder.write() as connection:
        for reviewer in projects.list_reviewers(connection):
            if reviewer.ai_config_id == stored.ai_config_id:
                return reviewer.id
        moment = now()
        reviewer = Reviewer(
            id=new_ulid(moment),
            kind=ReviewerKind.AI,
            display_name=f"IA ({stored.record.provider} {stored.record.model_requested})",
            role="second_reviewer",
            ai_config_id=stored.ai_config_id,
        )
        projects.insert_reviewer(connection, reviewer, now=moment)
        journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.REVIEWER_AI_RECORDED,
            subject_type="reviewer",
            subject_id=reviewer.id,
            summary_fr=french("AI reviewer recorded: {name}").format(name=reviewer.display_name),
            tool_version=tool_version,
            payload={"ai_config": stored.ai_config_id, "name": reviewer.display_name},
        )
        return reviewer.id


def searchable_text(title: str, abstract: str) -> str:
    """Title and abstract as quotes are looked for in them (``quote_found``)."""
    return normalize_text(f"{title} {abstract}")


def quote_found(quote: str, text: str) -> bool | None:
    """Whether the AI's ``quote`` is in ``text`` (from :func:`searchable_text`), word for
    word once case, accents and punctuation are set aside; ``None`` without a quote."""
    return (normalize_text(quote) in text) if quote else None


@dataclass(frozen=True, slots=True)
class AIBatchResult:
    screened: int
    failed: list[str] = field(default_factory=list)  # reference ids
    stopped: str = ""  # "", "project_budget" or "batch_budget"
    spent: Decimal = Decimal(0)


def _journal_batch_end(
    folder: ProjectFolder,
    pilot: PilotRound,
    result: AIBatchResult,
    *,
    now: Clock,
    tool_version: str,
) -> None:
    with folder.write() as connection:
        moment = now()
        if result.stopped:
            journal.append_entry(
                connection,
                now=moment,
                actor_reviewer_id=folder.reviewer_id,
                entry_type=EntryType.BUDGET_REACHED,
                subject_type="screening_round",
                subject_id=pilot.id,
                summary_fr=french("Budget reached: the AI batch stopped before the next call"),
                tool_version=tool_version,
                payload={"ceiling": result.stopped, "spent": str(result.spent)},
            )
        journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.SCREENING_AI_BATCH_ENDED,
            subject_type="screening_round",
            subject_id=pilot.id,
            summary_fr=french(
                "Pilot round {number}: AI screening of {screened} references ({failed} failed)"
            ).format(number=pilot.number, screened=result.screened, failed=len(result.failed)),
            tool_version=tool_version,
            payload={
                "screened": result.screened,
                "failed": list(result.failed),
                "stopped": result.stopped,
                "spent": str(result.spent),
            },
        )


def run_ai(
    folder: ProjectFolder,
    round_id: str,
    *,
    batch_limit: Decimal,
    factory: ProviderFactory = default_provider_factory,
    now: Clock,
    tool_version: str,
) -> AIBatchResult:
    """Screen with the AI the references of the round it has not decided yet.

    Before each call, the estimated cost of the call is added to what is spent: the
    batch stops cleanly, before the call, when the project ceiling or ``batch_limit``
    would be passed (ENF-COU-02); what was screened stays recorded."""
    pilot = get_round(folder, round_id)
    version = criteria_of(folder, pilot)
    with folder.engine.connect() as connection:
        budget = screening_repo.latest_budget(connection)
    if budget is None:
        raise BudgetNotSetError
    config = folder.ai_settings().enabled_task(SCREEN_REFERENCE.name)
    provider = factory(config)
    thresholds, calibration = thresholds_in_force(folder)
    references = dedup_state(folder).references
    screened, failed, stopped = 0, [], ""
    batch_spent = Decimal(0)
    waiting = _waiting_for_ai(folder, pilot)
    for item in inputs_for(folder, version, waiting, references):
        estimate = provider.estimate_cost(SCREEN_REFERENCE, [item]).amount
        decided = False
        for _attempt in range(MAX_ATTEMPTS):
            # Checked before every call, retries included (ENF-COU-02).
            with folder.engine.connect() as connection:
                project_spent = screening_repo.total_spent(connection)
            if project_spent + estimate > budget.limit_amount:
                stopped = "project_budget"
                break
            if batch_spent + estimate > batch_limit:
                stopped = "batch_budget"
                break
            try:
                (result,) = run_task(provider, SCREEN_REFERENCE, [item])
            except ProviderCallError as error:
                stored = record_call(
                    folder,
                    task=SCREEN_REFERENCE.name,
                    item_id=error.item_id,
                    call=error.call,
                    raw_response=error.raw_response,
                    now=now,
                    tool_version=tool_version,
                )
                batch_spent += stored.record.cost_estimate
                continue
            stored = record_call(
                folder,
                task=SCREEN_REFERENCE.name,
                item_id=result.item_id,
                call=result.call,
                raw_response=result.raw_response,
                now=now,
                tool_version=tool_version,
            )
            batch_spent += stored.record.cost_estimate
            try:
                check_answer(result.output, [c.code for c in version.criteria])
            except UnusableAnswerError as error:
                record_unusable(folder, stored, error, now=now, tool_version=tool_version)
                continue
            reviewer_id = ai_reviewer(folder, stored, now=now, tool_version=tool_version)
            store_ai_decision(
                folder,
                pilot.id,
                french("Pilot round {number}: AI decision recorded").format(number=pilot.number),
                stored,
                result.output,
                references[item.item_id],
                version,
                thresholds,
                calibration,
                reviewer_id,
                now=now,
                tool_version=tool_version,
            )
            decided = True
            break
        if decided:
            screened += 1
        elif stopped:
            break  # not a failure: the reference waits for the next batch
        else:
            failed.append(item.item_id)
            record_ai_failure(
                folder,
                pilot.id,
                french(
                    "Pilot round {number}: the AI could not screen a reference "
                    "(attempts: {attempts})"
                ).format(number=pilot.number, attempts=MAX_ATTEMPTS),
                item.item_id,
                now=now,
                tool_version=tool_version,
            )
    outcome = AIBatchResult(screened=screened, failed=failed, stopped=stopped, spent=batch_spent)
    _journal_batch_end(folder, pilot, outcome, now=now, tool_version=tool_version)
    return outcome


def store_ai_decision(
    folder: ProjectFolder,
    round_id: str,
    summary: str,
    stored: StoredCall,
    output: ScreenReferenceOutput,
    reference: Reference,
    version: CriteriaVersion,
    thresholds: Thresholds,
    calibration: CalibrationRecord | None,
    reviewer_id: str,
    *,
    now: Clock,
    tool_version: str,
) -> Decision:
    with folder.write() as connection:
        moment = now()
        decision = _ai_decision(
            output,
            reference=reference,
            version=version,
            thresholds=thresholds,
            calibration=calibration,
            decision_id=new_ulid(moment),
            round_id=round_id,
            reviewer_id=reviewer_id,
            call_id=stored.id,
            tool_version=tool_version,
            moment=moment,
            context=decision_context(folder),
        )
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.SCREENING_AI_DECIDED,
            subject_type="decision",
            subject_id=decision.id,
            summary_fr=summary,
            tool_version=tool_version,
            payload=call_summary(stored)
            | {
                "reference": reference.id,
                "value": decision.value.value,
                "model_decision": output.decision,
                "confidence_raw": decision.confidence_raw,
                "confidence_calibrated": decision.confidence_calibrated,
                "calibration": None if calibration is None else calibration.id,
                "thresholds": thresholds.model_dump(mode="json"),
                "criteria_cited": list(decision.criteria_cited),
                "language": decision.language,
                "rule_sel_07": must_not_exclude(decision.assessments),
            },
        )
        screening_repo.insert_decision(connection, decision, journal_entry_id=entry.id)
    return decision


def record_ai_failure(
    folder: ProjectFolder,
    round_id: str,
    summary: str,
    reference_id: str,
    *,
    now: Clock,
    tool_version: str,
    attempts: int = MAX_ATTEMPTS,
) -> None:
    with folder.write() as connection:
        journal.append_entry(
            connection,
            now=now(),
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.SCREENING_AI_FAILED,
            subject_type="reference",
            subject_id=reference_id,
            summary_fr=summary,
            tool_version=tool_version,
            payload={"round_id": round_id, "reference": reference_id, "attempts": attempts},
        )


def replay_decision(folder: ProjectFolder, decision_id: str) -> Decision:
    """Rebuild an AI decision from the raw response kept in the project, without any
    call to the model (ENF-REP-02)."""
    with folder.engine.connect() as connection:
        found = next(
            (d for d in screening_repo.list_decisions(connection) if d.id == decision_id), None
        )
        if found is None or found.ai_call_id is None:
            raise LookupError(decision_id)
        stored = ai_repo.get_call(connection, found.ai_call_id)
        version = criteria_repo.get_version(connection, found.criteria_version_id)
        calibration = (
            None
            if found.calibration_id is None
            else screening_repo.get_calibration(connection, found.calibration_id)
        )
    assert stored is not None  # noqa: S101 - an AI decision always has its call
    assert stored.record.response_path is not None  # noqa: S101 - and its raw response
    assert version is not None  # noqa: S101
    assert found.thresholds is not None  # noqa: S101
    raw = read_raw_response(folder.path, stored.record.response_path)
    output = ScreenReferenceOutput.model_validate_json(_answer_text(raw))
    reference = dedup_state(folder).references[found.reference_id]
    return _ai_decision(
        output,
        reference=reference,
        version=version,
        thresholds=found.thresholds,
        calibration=calibration,
        decision_id=found.id,
        round_id=found.round_id or "",
        reviewer_id=found.reviewer_id,
        call_id=stored.id,
        tool_version=found.tool_version,
        moment=found.created_at,
        context=found.context,
    )


def _answer_text(raw: JsonValue) -> str:
    """The text of a Messages API response (the JSON answer)."""
    content = raw.get("content") if isinstance(raw, dict) else None
    if not isinstance(content, list):
        raise ValueError("not a Messages API response")
    return "".join(
        str(block.get("text", ""))
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )
