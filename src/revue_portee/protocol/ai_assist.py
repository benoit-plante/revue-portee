"""Running AI tasks for a project: cost preview, call, recording (ENF-COU-01, ENF-TRA-01).

The cost of a call is always estimated and shown before the call is made: the
interface first calls :func:`preview`, then :func:`run_and_record` once the person has
confirmed. The model call happens outside any write transaction (it can take a
while). The call is then recorded in its own transaction (configuration if new, call,
raw response), so that a paid call is never lost; what the use case derives from the
output is stored in a second transaction. If that second step fails, the call stays
recorded and the failure is written to the journal.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from pydantic import JsonValue
from sqlalchemy import Connection

from revue_portee.ai.base import (
    AICallRecord,
    CostEstimate,
    ModelProvider,
    ProviderCallError,
    TaskInput,
    TaskOutput,
    TaskResult,
    TaskSpec,
)
from revue_portee.ai.providers import ProviderFactory, build_provider
from revue_portee.ai.runner import run_task
from revue_portee.ai.settings import AITaskConfig
from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.i18n import french
from revue_portee.i18n import gettext as _
from revue_portee.resources import price_table
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.raw import remove_raw_response, write_raw_response
from revue_portee.storage.repositories import ai as ai_repo
from revue_portee.storage.repositories import journal
from revue_portee.storage.repositories.ai import StoredCall

__all__ = [
    "AITaskError",
    "CostPreview",
    "call_summary",
    "default_provider_factory",
    "preview",
    "record_call",
    "record_unusable",
    "run_and_record",
]

Clock = Callable[[], datetime]


class AITaskError(RuntimeError):
    """A model call failed; the call is recorded (French message for the interface)."""

    def __init__(self, message: str, *, call_id: str) -> None:
        self.call_id = call_id
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class CostPreview:
    """What is shown before any call (ENF-COU-01)."""

    task: str
    provider: str
    model: str
    items: int
    estimate: CostEstimate
    prices_as_of: date


def default_provider_factory(config: AITaskConfig) -> ModelProvider:
    return build_provider(config, prices=price_table())


def _provider(
    folder: ProjectFolder, task: TaskSpec[Any, Any], factory: ProviderFactory
) -> tuple[AITaskConfig, ModelProvider]:
    config = folder.ai_settings().enabled_task(task.name)
    return config, factory(config)


def preview[InputT: TaskInput, OutputT: TaskOutput](
    folder: ProjectFolder,
    task: TaskSpec[InputT, OutputT],
    inputs: Sequence[InputT],
    *,
    factory: ProviderFactory = default_provider_factory,
) -> CostPreview:
    config, provider = _provider(folder, task, factory)
    return CostPreview(
        task=task.name,
        provider=provider.name,
        model=str(config.model),
        items=len(inputs),
        estimate=provider.estimate_cost(task, inputs),
        prices_as_of=price_table().as_of,
    )


def _call_summary(call: AICallRecord) -> dict[str, JsonValue]:
    return {
        "provider": call.provider,
        "model_requested": call.model_requested,
        "model_returned": call.model_returned,
        "prompt_template": f"{call.prompt_template_id}@{call.prompt_template_version}",
        "prompt_sha256": call.prompt_sha256,
        "input_tokens": call.input_tokens,
        "output_tokens": call.output_tokens,
        "cache_read_tokens": call.cache_read_tokens,
        "cache_write_tokens": call.cache_write_tokens,
        "cost_estimate": str(call.cost_estimate),
        "currency": call.currency,
        "status": call.status,
        "error_code": call.error_code,
    }


def record_call(
    folder: ProjectFolder,
    *,
    task: str,
    item_id: str,
    call: AICallRecord,
    raw_response: JsonValue,
    now: Clock,
    tool_version: str,
) -> StoredCall:
    """Record one call in its own transaction (a raw response written for a
    transaction that fails is removed)."""
    call_id = new_ulid(call.created_at)
    response_path = None
    if raw_response is not None:
        response_path = write_raw_response(folder.path, call_id, call.created_at, raw_response)
    try:
        with folder.write() as connection:
            return _insert_call(
                connection,
                folder,
                task=task,
                item_id=item_id,
                call=call,
                call_id=call_id,
                response_path=response_path,
                now=now,
                tool_version=tool_version,
            )
    except BaseException:
        if response_path is not None:
            remove_raw_response(folder.path, response_path)
        raise


def _insert_call(
    connection: Connection,
    folder: ProjectFolder,
    *,
    task: str,
    item_id: str,
    call: AICallRecord,
    call_id: str,
    response_path: str | None,
    now: Clock,
    tool_version: str,
) -> StoredCall:
    moment = now()
    config_id, created = ai_repo.ensure_config(
        connection,
        config_id=new_ulid(moment),
        task=task,
        provider=call.provider,
        model=call.model_requested,
        template_id=call.prompt_template_id,
        template_version=call.prompt_template_version,
        params=call.params,
        now=moment,
    )
    if created:
        journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.AI_CONFIG_RECORDED,
            subject_type="ai_config",
            subject_id=config_id,
            summary_fr=french("AI configuration recorded for the task {task}: {model}").format(
                task=task, model=call.model_requested
            ),
            tool_version=tool_version,
            payload={
                "task": task,
                "provider": call.provider,
                "model_requested": call.model_requested,
                "prompt_template": f"{call.prompt_template_id}@{call.prompt_template_version}",
                "params": call.params,
            },
        )
    stored = ai_repo.insert_call(
        connection,
        call_id=call_id,
        ai_config_id=config_id,
        task=task,
        item_id=item_id,
        record=call,
        response_path=response_path,
    )
    if call.status == "error":
        journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.AI_CALL_FAILED,
            subject_type="ai_call",
            subject_id=call_id,
            summary_fr=french("AI call failed for the task {task} ({error})").format(
                task=task, error=call.error_code
            ),
            tool_version=tool_version,
            payload={"task": task, "item_id": item_id} | _call_summary(call),
        )
    return stored


def call_summary(stored: StoredCall) -> dict[str, JsonValue]:
    """What a journal entry derived from a call records about it."""
    return {"ai_call_id": stored.id, "task": stored.task} | _call_summary(stored.record)


type OnResult[OutputT: TaskOutput] = Callable[[Connection, StoredCall, TaskResult[OutputT]], None]


def run_and_record[InputT: TaskInput, OutputT: TaskOutput](
    folder: ProjectFolder,
    task: TaskSpec[InputT, OutputT],
    inputs: Sequence[InputT],
    *,
    on_result: OnResult[OutputT],
    now: Clock,
    tool_version: str,
    factory: ProviderFactory = default_provider_factory,
) -> list[StoredCall]:
    """Run ``task`` on each input, one call at a time, recording each call as it ends.

    ``on_result`` stores what the use case derives from a valid output, in a
    transaction of its own. A failed call, or an output that cannot be used, is
    recorded, then :class:`AITaskError` is raised; the calls already made stay recorded.
    """
    _config, provider = _provider(folder, task, factory)
    stored_calls: list[StoredCall] = []
    for item in inputs:
        try:
            (result,) = run_task(provider, task, [item])
        except ProviderCallError as error:
            failed = record_call(
                folder,
                task=task.name,
                item_id=error.item_id,
                call=error.call,
                raw_response=error.raw_response,
                now=now,
                tool_version=tool_version,
            )
            raise AITaskError(str(error), call_id=failed.id) from error
        stored = record_call(
            folder,
            task=task.name,
            item_id=result.item_id,
            call=result.call,
            raw_response=result.raw_response,
            now=now,
            tool_version=tool_version,
        )
        try:
            with folder.write() as connection:
                on_result(connection, stored, result)
        except Exception as error:
            record_unusable(folder, stored, error, now=now, tool_version=tool_version)
            raise AITaskError(
                _("The answer of the model could not be used; the call is recorded."),
                call_id=stored.id,
            ) from error
        stored_calls.append(stored)
    return stored_calls


def record_unusable(
    folder: ProjectFolder, stored: StoredCall, error: Exception, *, now: Clock, tool_version: str
) -> None:
    with folder.write() as connection:
        journal.append_entry(
            connection,
            now=now(),
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.AI_RESULT_UNUSABLE,
            subject_type="ai_call",
            subject_id=stored.id,
            summary_fr=french("AI answer recorded but not usable for the task {task}").format(
                task=stored.task
            ),
            tool_version=tool_version,
            payload=call_summary(stored) | {"error": type(error).__name__},
        )
