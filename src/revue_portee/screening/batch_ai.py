"""Screening by the AI through the provider's asynchronous batch API (ENF-COU-04).

Used by the main screening and by the reassessment of references touched by a
criteria change. References are sent in batches of at most ``BATCH_SIZE`` requests,
recorded as soon as the provider accepts them (``ai_batch``) with the criteria version
given to the model. The batch is followed until it ends; its results are then recorded
one call at a time, each with its raw response (D-041), and the end of the batch last
(``ai_batch_end``). Collecting again after an interruption skips the calls already
recorded, so a batch is never paid twice.

Before each batch, its estimated cost (batch price) is added to what is spent and to
the estimates of the batches still running: no batch is sent that would pass the
project budget or the ceiling of this submission (ENF-COU-02). A reference whose AI
answer was unusable is sent again in a later submission, at most ``MAX_ATTEMPTS``
times in all.
"""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from revue_portee.ai.base import BatchProvider, BatchStatus, ProviderCallError
from revue_portee.ai.providers import ProviderFactory
from revue_portee.ai.tasks.screening import SCREEN_REFERENCE, ScreenReferenceInput
from revue_portee.collect.enrichment import references_with_enrichment
from revue_portee.domain.criteria import CriteriaVersion
from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.domain.screening import AIBatch, AIBatchEnd, RoundKind, ScreeningRound
from revue_portee.i18n import french
from revue_portee.i18n import gettext as _
from revue_portee.protocol.ai_assist import (
    CostPreview,
    default_provider_factory,
    record_call,
    record_unusable,
)
from revue_portee.resources import price_table
from revue_portee.screening.ai_screening import (
    MAX_ATTEMPTS,
    UnusableAnswerError,
    ai_reviewer,
    check_answer,
    inputs_for,
    record_ai_failure,
    store_ai_decision,
)
from revue_portee.screening.pilot import UnknownRoundError, active_criteria
from revue_portee.screening.settings import BudgetNotSetError, thresholds_in_force
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import criteria as criteria_repo
from revue_portee.storage.repositories import journal
from revue_portee.storage.repositories import screening as screening_repo

__all__ = [
    "BATCH_SIZE",
    "NotBatchCapableError",
    "SubmitResult",
    "collect",
    "follow",
    "pending_batches",
    "preview",
    "submit",
    "waiting_for_ai",
]

Clock = Callable[[], datetime]
# Requests per batch: well under the provider's limits (100 000 requests, 256 MB).
BATCH_SIZE = 5_000
POLL_SECONDS = 60


class NotBatchCapableError(TypeError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            _("The AI provider “{provider}” cannot screen in batches.").format(provider=provider)
        )


def _round(folder: ProjectFolder, round_id: str) -> ScreeningRound:
    with folder.engine.connect() as connection:
        found = screening_repo.get_screening_round(connection, round_id)
    if found is None or found.kind is RoundKind.PILOT:
        raise UnknownRoundError
    return found


def _label(screening: ScreeningRound) -> str:
    if screening.kind is RoundKind.MAIN:
        return french("Main screening")
    return french("Reassessment {number}").format(number=screening.number)


def _provider(folder: ProjectFolder, factory: ProviderFactory) -> BatchProvider:
    provider = factory(folder.ai_settings().enabled_task(SCREEN_REFERENCE.name))
    if not isinstance(provider, BatchProvider):
        raise NotBatchCapableError(provider.name)
    return provider


def pending_batches(folder: ProjectFolder, round_id: str) -> list[AIBatch]:
    """Batches of the round whose results are not all recorded yet."""
    with folder.engine.connect() as connection:
        return [
            batch
            for batch in screening_repo.list_ai_batches(connection, round_id)
            if screening_repo.batch_end(connection, batch.id) is None
        ]


def waiting_for_ai(folder: ProjectFolder, round_id: str) -> list[str]:
    """Members of the round, in order, that the AI has not decided, that no running
    batch holds, and that have had fewer than ``MAX_ATTEMPTS`` calls."""
    screening = _round(folder, round_id)
    with folder.engine.connect() as connection:
        members = screening_repo.member_ids(connection, screening.id)
        decided = screening_repo.latest_by_reference(connection, [screening.id], reviewer_kind="ai")
        batches = screening_repo.list_ai_batches(connection, screening.id)
        attempts = screening_repo.batch_attempts(connection, [b.provider_batch_id for b in batches])
        running = {
            item
            for batch in batches
            if screening_repo.batch_end(connection, batch.id) is None
            for item in batch.item_ids
        }
    return [
        ref
        for ref in members
        if ref not in decided and ref not in running and attempts.get(ref, 0) < MAX_ATTEMPTS
    ]


def _inputs(
    folder: ProjectFolder, version: CriteriaVersion, reference_ids: Sequence[str]
) -> list[ScreenReferenceInput]:
    references = {r.id: r for r in references_with_enrichment(folder)}
    return inputs_for(folder, version, reference_ids, references)


def preview(
    folder: ProjectFolder, round_id: str, *, factory: ProviderFactory = default_provider_factory
) -> CostPreview:
    """Cost, at the batch price, of screening what the AI has not decided yet."""
    screening = _round(folder, round_id)
    config = folder.ai_settings().enabled_task(SCREEN_REFERENCE.name)
    provider = _provider(folder, factory)
    items = _inputs(folder, active_criteria(folder), waiting_for_ai(folder, screening.id))
    return CostPreview(
        task=SCREEN_REFERENCE.name,
        provider=provider.name,
        model=str(config.model),
        items=len(items),
        estimate=provider.estimate_batch_cost(SCREEN_REFERENCE, items),
        prices_as_of=price_table().as_of,
    )


@dataclass(frozen=True, slots=True)
class SubmitResult:
    batches: list[AIBatch] = field(default_factory=list)
    stopped: str = ""  # "", "project_budget" or "batch_budget"
    left: int = 0  # references still waiting for the AI


def submit(
    folder: ProjectFolder,
    round_id: str,
    *,
    batch_limit: Decimal,
    factory: ProviderFactory = default_provider_factory,
    size: int = BATCH_SIZE,
    now: Clock,
    tool_version: str,
) -> SubmitResult:
    """Send what the AI has not decided yet, in batches, without passing the project
    budget nor ``batch_limit`` (the ceiling of this submission)."""
    screening = _round(folder, round_id)
    with folder.engine.connect() as connection:
        budget = screening_repo.latest_budget(connection)
        spent = screening_repo.total_spent(connection)
    if budget is None:
        raise BudgetNotSetError
    provider = _provider(folder, factory)
    version = active_criteria(folder)
    items = _inputs(folder, version, waiting_for_ai(folder, screening.id))
    reserved = sum((b.estimate for b in pending_batches(folder, screening.id)), Decimal(0))
    submitted: list[AIBatch] = []
    this_submission = Decimal(0)
    stopped = ""
    position = 0
    while position < len(items):
        chunk = items[position : position + size]
        estimate = provider.estimate_batch_cost(SCREEN_REFERENCE, chunk).amount
        room_project = budget.limit_amount - spent - reserved
        room_batch = batch_limit - this_submission
        room = min(room_project, room_batch)
        if estimate > room:
            per_item = estimate / len(chunk)
            fit = int(room / per_item) if per_item > 0 else len(chunk)
            if fit <= 0:
                stopped = "project_budget" if room_project <= room_batch else "batch_budget"
                break
            chunk = chunk[:fit]
            estimate = provider.estimate_batch_cost(SCREEN_REFERENCE, chunk).amount
        provider_batch_id = provider.submit_batch(SCREEN_REFERENCE, chunk)
        batch = _record_batch(
            folder,
            screening,
            version,
            provider.name,
            provider_batch_id,
            [item.item_id for item in chunk],
            estimate,
            now=now,
            tool_version=tool_version,
        )
        submitted.append(batch)
        reserved += estimate
        this_submission += estimate
        position += len(chunk)
    if stopped:
        _journal_stop(
            folder, screening, stopped, this_submission, now=now, tool_version=tool_version
        )
    return SubmitResult(batches=submitted, stopped=stopped, left=len(items) - position)


def _record_batch(
    folder: ProjectFolder,
    screening: ScreeningRound,
    version: CriteriaVersion,
    provider: str,
    provider_batch_id: str,
    item_ids: Sequence[str],
    estimate: Decimal,
    *,
    now: Clock,
    tool_version: str,
) -> AIBatch:
    with folder.write() as connection:
        moment = now()
        batch = AIBatch(
            id=new_ulid(moment),
            round_id=screening.id,
            task=SCREEN_REFERENCE.name,
            criteria_version_id=version.id,
            provider=provider,
            provider_batch_id=provider_batch_id,
            item_ids=tuple(item_ids),
            estimate=estimate,
            created_at=moment,
            reviewer_id=folder.reviewer_id,
        )
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.SCREENING_AI_BATCH_SUBMITTED,
            subject_type="ai_batch",
            subject_id=batch.id,
            summary_fr=french("{label}: {count} references sent to the AI in a batch").format(
                label=_label(screening), count=len(item_ids)
            ),
            tool_version=tool_version,
            payload={
                "round_id": screening.id,
                "provider": provider,
                "provider_batch_id": provider_batch_id,
                "references": len(item_ids),
                "estimate": str(estimate),
                "criteria_version": version.number,
            },
        )
        screening_repo.insert_ai_batch(connection, batch, journal_entry_id=entry.id)
    return batch


def _journal_stop(
    folder: ProjectFolder,
    screening: ScreeningRound,
    stopped: str,
    submitted: Decimal,
    *,
    now: Clock,
    tool_version: str,
) -> None:
    with folder.write() as connection:
        journal.append_entry(
            connection,
            now=now(),
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.BUDGET_REACHED,
            subject_type="screening_round",
            subject_id=screening.id,
            summary_fr=french("Budget reached: the AI batch stopped before the next call"),
            tool_version=tool_version,
            payload={"ceiling": stopped, "estimate_sent": str(submitted)},
        )


def collect(
    folder: ProjectFolder,
    batch_id: str,
    *,
    factory: ProviderFactory = default_provider_factory,
    now: Clock,
    tool_version: str,
) -> AIBatchEnd | BatchStatus:
    """Record the results of an ended batch, or return its status while it runs."""
    with folder.engine.connect() as connection:
        batch = screening_repo.get_ai_batch(connection, batch_id)
        if batch is None:
            raise LookupError(batch_id)
        ended = screening_repo.batch_end(connection, batch.id)
        if ended is not None:
            return ended
        version = criteria_repo.get_version(connection, batch.criteria_version_id)
        recorded = screening_repo.batch_item_ids_recorded(connection, batch.provider_batch_id)
        screening = screening_repo.get_screening_round(connection, batch.round_id)
    assert version is not None  # noqa: S101 - a batch always points to a version
    assert screening is not None  # noqa: S101 - and to its round
    provider = _provider(folder, factory)
    status = provider.batch_status(batch.provider_batch_id)
    if not status.ended:
        return status
    references = {r.id: r for r in references_with_enrichment(folder)}
    remaining = [ref for ref in batch.item_ids if ref not in recorded]
    inputs = inputs_for(folder, version, remaining, references)
    thresholds, calibration = thresholds_in_force(folder)
    with folder.engine.connect() as connection:
        attempts = screening_repo.batch_attempts(
            connection,
            [b.provider_batch_id for b in screening_repo.list_ai_batches(connection, screening.id)],
        )
    codes = [c.code for c in version.criteria]
    label = _label(screening)

    def failed_once(reference_id: str) -> None:
        if attempts.get(reference_id, 0) + 1 >= MAX_ATTEMPTS:
            record_ai_failure(
                folder,
                screening.id,
                french(
                    "{label}: the AI could not screen a reference (attempts: {attempts})"
                ).format(label=label, attempts=MAX_ATTEMPTS),
                reference_id,
                now=now,
                tool_version=tool_version,
            )

    for outcome in provider.batch_results(SCREEN_REFERENCE, batch.provider_batch_id, inputs):
        if isinstance(outcome, ProviderCallError):
            record_call(
                folder,
                task=SCREEN_REFERENCE.name,
                item_id=outcome.item_id,
                call=outcome.call,
                raw_response=outcome.raw_response,
                now=now,
                tool_version=tool_version,
            )
            failed_once(outcome.item_id)
            continue
        stored = record_call(
            folder,
            task=SCREEN_REFERENCE.name,
            item_id=outcome.item_id,
            call=outcome.call,
            raw_response=outcome.raw_response,
            now=now,
            tool_version=tool_version,
        )
        try:
            check_answer(outcome.output, codes)
        except UnusableAnswerError as error:
            record_unusable(folder, stored, error, now=now, tool_version=tool_version)
            failed_once(outcome.item_id)
            continue
        store_ai_decision(
            folder,
            screening.id,
            french("{label}: AI decision recorded").format(label=label),
            stored,
            outcome.output,
            references[outcome.item_id],
            version,
            thresholds,
            calibration,
            ai_reviewer(folder, stored, now=now, tool_version=tool_version),
            now=now,
            tool_version=tool_version,
        )
    return _end(folder, screening, batch, label, now=now, tool_version=tool_version)


def _end(
    folder: ProjectFolder,
    screening: ScreeningRound,
    batch: AIBatch,
    label: str,
    *,
    now: Clock,
    tool_version: str,
) -> AIBatchEnd:
    with folder.write() as connection:
        decided = screening_repo.latest_by_reference(connection, [screening.id], reviewer_kind="ai")
        failed = tuple(ref for ref in batch.item_ids if ref not in decided)
        moment = now()
        end = AIBatchEnd(
            batch_id=batch.id,
            screened=len(batch.item_ids) - len(failed),
            failed=failed,
            spent=screening_repo.batch_spent(connection, [batch.provider_batch_id]),
            created_at=moment,
        )
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.SCREENING_AI_BATCH_ENDED,
            subject_type="ai_batch",
            subject_id=batch.id,
            summary_fr=french(
                "{label}: AI batch ended, references screened: {screened}, failed: {failed}"
            ).format(label=label, screened=end.screened, failed=len(end.failed)),
            tool_version=tool_version,
            payload={
                "round_id": screening.id,
                "provider_batch_id": batch.provider_batch_id,
                "screened": end.screened,
                "failed": list(end.failed),
                "spent": str(end.spent),
            },
        )
        screening_repo.insert_batch_end(connection, end, journal_entry_id=entry.id)
    return end


def follow(
    folder: ProjectFolder,
    round_id: str,
    *,
    factory: ProviderFactory = default_provider_factory,
    now: Clock,
    tool_version: str,
    wait: Callable[[float], None] = time.sleep,
    poll_seconds: float = POLL_SECONDS,
    max_polls: int | None = None,
) -> list[AIBatchEnd]:
    """Follow the running batches of the round until they all end (or ``max_polls``
    rounds of status requests), recording their results as they come."""
    ended: list[AIBatchEnd] = []
    polls = 0
    while True:
        pending = pending_batches(folder, round_id)
        if not pending:
            return ended
        for batch in pending:
            outcome = collect(folder, batch.id, factory=factory, now=now, tool_version=tool_version)
            if isinstance(outcome, AIBatchEnd):
                ended.append(outcome)
        polls += 1
        if max_polls is not None and polls >= max_polls:
            return ended
        if pending_batches(folder, round_id):
            wait(poll_seconds)
