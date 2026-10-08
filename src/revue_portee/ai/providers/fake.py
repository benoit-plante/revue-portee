"""Deterministic provider for automated tests (the only provider used by the test suite)."""

import hashlib
import itertools
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from revue_portee.ai.base import (
    AICallRecord,
    BatchError,
    BatchStatus,
    CostEstimate,
    ProviderCallError,
    TaskInput,
    TaskOutput,
    TaskResult,
    TaskSpec,
    UnsupportedTaskError,
    result_type,
    utc_now,
)

__all__ = ["FakeBatches", "FakeProvider", "Responder"]

type Responder = Callable[[TaskInput], BaseModel | Mapping[str, Any]]


# Batch identifiers are unique across stores, as they are at a real provider.
_BATCH_NUMBERS = itertools.count(1)


class FakeBatches:
    """Batches submitted to fake providers, shared between provider instances (a
    service builds a new provider for each step). A batch ends after ``polls`` status
    requests; the items of ``failing`` come back as errored requests."""

    def __init__(
        self, *, polls: int = 1, failing: Collection[str] = (), refuse: bool = False
    ) -> None:
        self.polls = polls
        self.failing = frozenset(failing)
        self.refuse = refuse  # every submission fails (no network, for instance)
        self.submitted: dict[str, tuple[str, tuple[str, ...]]] = {}
        self._remaining: dict[str, int] = {}

    def submit(self, task: str, item_ids: Sequence[str]) -> str:
        if self.refuse:
            raise BatchError("fake batch refused")
        batch_id = f"fakebatch_{next(_BATCH_NUMBERS)}"
        self.submitted[batch_id] = (task, tuple(item_ids))
        self._remaining[batch_id] = self.polls
        return batch_id

    def status(self, batch_id: str) -> BatchStatus:
        if batch_id not in self.submitted:
            raise BatchError(f"unknown fake batch {batch_id}")
        self._remaining[batch_id] = max(0, self._remaining[batch_id] - 1)
        items = self.submitted[batch_id][1]
        ended = self._remaining[batch_id] == 0
        failed = sum(item in self.failing for item in items)
        return BatchStatus(
            provider_batch_id=batch_id,
            ended=ended,
            processing=0 if ended else len(items),
            succeeded=len(items) - failed if ended else 0,
            errored=failed if ended else 0,
        )


class FakeProvider:
    """Answers every input with ``responder`` and records a complete, fake call.

    The model name is supplied by the caller (as it would be by the project
    configuration); ``model_returned`` defaults to the requested name.
    """

    def __init__(
        self,
        *,
        model: str,
        responder: Responder,
        model_returned: str | None = None,
        confidence: float | None = None,
        supported_tasks: Collection[str] | None = None,
        clock: Callable[[], datetime] = utc_now,
        cost_per_call: Decimal = Decimal(0),
        batches: FakeBatches | None = None,
        batch_factor: Decimal = Decimal("0.5"),
    ) -> None:
        self._model = model
        self._model_returned = model_returned or model
        self._responder = responder
        self._confidence = confidence
        self._supported = None if supported_tasks is None else frozenset(supported_tasks)
        self._clock = clock
        self._cost = cost_per_call
        self._batches = batches
        self._batch_factor = batch_factor
        self.calls: list[AICallRecord] = []

    @property
    def name(self) -> str:
        return "fake"

    def supports(self, task: TaskSpec[Any, Any]) -> bool:
        return self._supported is None or task.name in self._supported

    def estimate_cost[InputT: TaskInput, OutputT: TaskOutput](
        self, task: TaskSpec[InputT, OutputT], inputs: Sequence[InputT]
    ) -> CostEstimate:
        self._check(task)
        tokens = sum(_count_tokens(_render(task, item)) for item in inputs)
        return CostEstimate(input_tokens=tokens, output_tokens=0, amount=self._cost * len(inputs))

    def run[InputT: TaskInput, OutputT: TaskOutput](
        self, task: TaskSpec[InputT, OutputT], inputs: Sequence[InputT]
    ) -> Iterator[TaskResult[OutputT]]:
        # Checked eagerly: an unsupported task fails when run() is called, not when the
        # returned iterator is first consumed.
        self._check(task)
        return self._results(task, inputs)

    def _results[InputT: TaskInput, OutputT: TaskOutput](
        self, task: TaskSpec[InputT, OutputT], inputs: Sequence[InputT]
    ) -> Iterator[TaskResult[OutputT]]:
        for item in inputs:
            yield self._answer(task, item, cost=self._cost)

    def _answer[InputT: TaskInput, OutputT: TaskOutput](
        self,
        task: TaskSpec[InputT, OutputT],
        item: InputT,
        *,
        cost: Decimal,
        batch_id: str | None = None,
    ) -> TaskResult[OutputT]:
        validated_input = task.input_model.model_validate(item.model_dump())
        raw = self._responder(validated_input)
        payload = raw.model_dump() if isinstance(raw, BaseModel) else dict(raw)
        output = task.output_model.model_validate(payload)
        prompt = _render(task, validated_input)
        call = AICallRecord(
            provider=self.name,
            model_requested=self._model,
            model_returned=self._model_returned,
            provider_request_id=f"fake-{len(self.calls) + 1}",
            prompt_template_id=task.prompt.template_id,
            prompt_template_version=task.prompt.version,
            prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            params={"temperature": 0},
            input_tokens=_count_tokens(prompt),
            output_tokens=_count_tokens(output.model_dump_json()),
            cost_estimate=cost,
            latency_ms=0,
            batch_id=batch_id,
            created_at=self._clock(),
        )
        self.calls.append(call)
        return result_type(task.output_model)(
            item_id=validated_input.item_id,
            output=output,
            raw_confidence=self._confidence,
            call=call,
            # Shaped like a Messages API response, so that a decision can be rebuilt
            # from it without calling the model again (ENF-REP-02).
            raw_response={
                "id": call.provider_request_id,
                "model": self._model_returned,
                "content": [{"type": "text", "text": output.model_dump_json()}],
            },
        )

    # --- Batches ---------------------------------------------------------------------

    def _store(self) -> FakeBatches:
        if self._batches is None:
            raise BatchError("this fake provider has no batches")
        return self._batches

    def estimate_batch_cost[InputT: TaskInput, OutputT: TaskOutput](
        self, task: TaskSpec[InputT, OutputT], inputs: Sequence[InputT]
    ) -> CostEstimate:
        full = self.estimate_cost(task, inputs)
        return full.model_copy(update={"amount": full.amount * self._batch_factor})

    def submit_batch[InputT: TaskInput, OutputT: TaskOutput](
        self, task: TaskSpec[InputT, OutputT], inputs: Sequence[InputT]
    ) -> str:
        self._check(task)
        return self._store().submit(task.name, [item.item_id for item in inputs])

    def batch_status(self, provider_batch_id: str) -> BatchStatus:
        return self._store().status(provider_batch_id)

    def batch_results[InputT: TaskInput, OutputT: TaskOutput](
        self, task: TaskSpec[InputT, OutputT], provider_batch_id: str, inputs: Sequence[InputT]
    ) -> Iterator[TaskResult[OutputT] | ProviderCallError]:
        store = self._store()
        asked = set(store.submitted[provider_batch_id][1])
        for item in inputs:
            if item.item_id not in asked:
                continue
            if item.item_id in store.failing:
                call = AICallRecord(
                    provider=self.name,
                    model_requested=self._model,
                    model_returned=None,
                    prompt_template_id=task.prompt.template_id,
                    prompt_template_version=task.prompt.version,
                    prompt_sha256=hashlib.sha256(b"failed").hexdigest(),
                    input_tokens=0,
                    output_tokens=0,
                    cost_estimate=Decimal(0),
                    latency_ms=0,
                    batch_id=provider_batch_id,
                    status="error",
                    error_code="batch_errored",
                    created_at=self._clock(),
                )
                yield ProviderCallError(
                    "fake batch request failed", item_id=item.item_id, call=call
                )
                continue
            yield self._answer(
                task, item, cost=self._cost * self._batch_factor, batch_id=provider_batch_id
            )

    def _check(self, task: TaskSpec[Any, Any]) -> None:
        if not self.supports(task):
            raise UnsupportedTaskError(self.name, task.name)


def _render(task: TaskSpec[Any, Any], item: TaskInput) -> str:
    """Deterministic stand-in for prompt rendering."""
    return (
        f"{task.prompt.template_id}@{task.prompt.version}\n"
        f"{task.name}@{task.version}\n"
        f"{item.model_dump_json()}"
    )


def _count_tokens(text: str) -> int:
    return len(text.split())
