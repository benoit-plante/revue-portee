"""Model abstraction layer (docs/03-architecture.md §6).

Application services only know :class:`ModelProvider` and :class:`TaskSpec`. A provider
receives the model name from configuration: no model name is ever hard-coded.
"""

from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from revue_portee.i18n import gettext as _

__all__ = [
    "AICallRecord",
    "CallStatus",
    "CostEstimate",
    "ModelProvider",
    "PromptRef",
    "TaskInput",
    "TaskOutput",
    "TaskResult",
    "TaskSpec",
    "UnsupportedTaskError",
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
    """Base class for structured task outputs (validated against the task schema)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


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
    model_returned: str = Field(description="Exact model identifier returned by the API.")
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
    """Validated output of a task for one input, with its call record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    output: OutputT
    raw_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    call: AICallRecord


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
