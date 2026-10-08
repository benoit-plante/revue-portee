"""Deterministic provider for automated tests (the only provider used by the test suite)."""

import hashlib
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from revue_portee.ai.base import (
    AICallRecord,
    CostEstimate,
    TaskInput,
    TaskOutput,
    TaskResult,
    TaskSpec,
    UnsupportedTaskError,
    result_type,
    utc_now,
)

__all__ = ["FakeProvider", "Responder"]

type Responder = Callable[[TaskInput], BaseModel | Mapping[str, Any]]


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
    ) -> None:
        self._model = model
        self._model_returned = model_returned or model
        self._responder = responder
        self._confidence = confidence
        self._supported = None if supported_tasks is None else frozenset(supported_tasks)
        self._clock = clock
        self._cost = cost_per_call
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
                cost_estimate=self._cost,
                latency_ms=0,
                created_at=self._clock(),
            )
            self.calls.append(call)
            yield result_type(task.output_model)(
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
