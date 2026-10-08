"""Model abstraction layer (docs/03-architecture.md §6).

Application services only know :class:`ModelProvider` and :class:`TaskSpec`. A provider
receives the model name from configuration: no model name is ever hard-coded.
"""

from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue

from revue_portee.i18n import gettext as _

__all__ = [
    "AICallRecord",
    "BatchError",
    "BatchProvider",
    "BatchStatus",
    "CallStatus",
    "CostEstimate",
    "ModelProvider",
    "PromptRef",
    "ProviderCallError",
    "TaskInput",
    "TaskOutput",
    "TaskResult",
    "TaskSpec",
    "UnsupportedTaskError",
    "result_type",
    "utc_now",
]


def utc_now() -> datetime:
    """Current time, timezone-aware, in UTC (ENF-TRA-01)."""
    return datetime.now(UTC)


class TaskInput(BaseModel):
    """Base class for task inputs. ``item_id`` links each result back to its input."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str = Field(min_length=1)


class TaskOutput(BaseModel):
    """Base class for structured task outputs (validated against the task schema).

    Text is stripped before validation, so that a blank answer fails a length
    constraint and the call is recorded as invalid.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


class PromptRef(BaseModel):
    """Versioned prompt template used by a task (docs/03-architecture.md §6.4)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    template_id: str = Field(min_length=1)
    version: str = Field(min_length=1)


class TaskSpec[InputT: TaskInput, OutputT: TaskOutput](BaseModel):
    """What is asked, independently of the model: name, version and I/O schemas."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    input_model: type[InputT]
    output_model: type[OutputT]
    prompt: PromptRef


CallStatus = Literal["ok", "error"]


class AICallRecord(BaseModel):
    """Traceability record of one model call (table ``ai_call``, ENF-TRA-01)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    model_requested: str
    model_returned: str | None = Field(
        description="Exact model identifier returned by the API; None when the call failed "
        "before any model answered."
    )
    provider_request_id: str | None = None
    prompt_template_id: str
    prompt_template_version: str
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    params: dict[str, Any] = Field(default_factory=dict)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_read_tokens: int = Field(default=0, ge=0)
    cache_write_tokens: int = Field(default=0, ge=0)
    cost_estimate: Decimal = Field(ge=0)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    latency_ms: int = Field(ge=0)
    batch_id: str | None = None
    response_path: str | None = None
    status: CallStatus = "ok"
    error_code: str | None = None
    created_at: AwareDatetime


class TaskResult[OutputT: TaskOutput](BaseModel):
    """Validated output of a task for one input, with its call record.

    ``raw_response`` is the provider's response as returned, to be stored in the
    project (ENF-TRA-03) by the service that records the call.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    output: OutputT
    raw_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    call: AICallRecord
    raw_response: JsonValue = None


def result_type[OutputT: TaskOutput](output_model: type[OutputT]) -> type[TaskResult[OutputT]]:
    """``TaskResult`` parametrized with the concrete schema, so that serialization keeps
    every field of the output."""
    return TaskResult[output_model]  # type: ignore[valid-type]


class ProviderCallError(RuntimeError):
    """A model call that did not produce a valid output. The failed call is recorded
    like any other (``call.status == "error"``), with the raw response if any."""

    def __init__(
        self, message: str, *, item_id: str, call: AICallRecord, raw_response: JsonValue = None
    ) -> None:
        self.item_id = item_id
        self.call = call
        self.raw_response = raw_response
        super().__init__(message)


class BatchError(RuntimeError):
    """A batch could not be submitted or followed (French message); no call was made."""


class CostEstimate(BaseModel):
    """Cost estimated before running a batch (ENF-COU-01)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    amount: Decimal = Field(ge=0)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")


class UnsupportedTaskError(ValueError):
    """Raised when a provider is asked to run a task it does not support."""

    def __init__(self, provider: str, task: str) -> None:
        self.provider = provider
        self.task = task
        super().__init__(
            _("The provider “{provider}” does not support the task “{task}”.").format(
                provider=provider, task=task
            )
        )


@runtime_checkable
class ModelProvider(Protocol):
    """How a task is executed by a given engine (docs/03-architecture.md §6.2)."""

    @property
    def name(self) -> str: ...

    def supports(self, task: TaskSpec[Any, Any]) -> bool: ...

    def estimate_cost[InputT: TaskInput, OutputT: TaskOutput](
        self, task: TaskSpec[InputT, OutputT], inputs: Sequence[InputT]
    ) -> CostEstimate: ...

    def run[InputT: TaskInput, OutputT: TaskOutput](
        self, task: TaskSpec[InputT, OutputT], inputs: Sequence[InputT]
    ) -> Iterator[TaskResult[OutputT]]: ...


class BatchStatus(BaseModel):
    """State of an asynchronous batch at the provider."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_batch_id: str
    ended: bool
    processing: int = Field(default=0, ge=0)
    succeeded: int = Field(default=0, ge=0)
    errored: int = Field(default=0, ge=0)
    canceled: int = Field(default=0, ge=0)
    expired: int = Field(default=0, ge=0)


@runtime_checkable
class BatchProvider(ModelProvider, Protocol):
    """A provider that can also run a task asynchronously on many inputs at once, at a
    lower price (ENF-COU-04). Results come back in any order; each is a result or the
    error of its own call, never an exception for the whole batch."""

    def estimate_batch_cost[InputT: TaskInput, OutputT: TaskOutput](
        self, task: TaskSpec[InputT, OutputT], inputs: Sequence[InputT]
    ) -> CostEstimate: ...

    def submit_batch[InputT: TaskInput, OutputT: TaskOutput](
        self, task: TaskSpec[InputT, OutputT], inputs: Sequence[InputT]
    ) -> str: ...

    def batch_status(self, provider_batch_id: str) -> BatchStatus: ...

    def batch_results[InputT: TaskInput, OutputT: TaskOutput](
        self, task: TaskSpec[InputT, OutputT], provider_batch_id: str, inputs: Sequence[InputT]
    ) -> Iterator[TaskResult[OutputT] | ProviderCallError]: ...
