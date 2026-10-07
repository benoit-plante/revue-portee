"""AI configuration of a project: which provider and model run each task, and how the
AI is supervised (EF-CAD-07). Stored in ``projet.toml`` ([ia]); defaults come from
``resources/ai_defaults.yaml``. No model name is ever written in the code.
"""

from decimal import Decimal
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from revue_portee.i18n import gettext as _

__all__ = [
    "AISettings",
    "AITaskConfig",
    "SupervisionSettings",
    "TaskNotAvailableError",
    "TaskStatus",
]


class TaskStatus(StrEnum):
    ENABLED = "enabled"
    PLANNED = "planned"  # described in the protocol, not runnable yet


class AITaskConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: TaskStatus
    provider: str | None = None
    model: str | None = None
    params: dict[str, JsonValue] = Field(default_factory=dict)
    expected_output_tokens: int = Field(default=1000, ge=0)

    @model_validator(mode="after")
    def _runnable(self) -> Self:
        if self.status is TaskStatus.ENABLED and not (self.provider and self.model):
            raise ValueError("an enabled task needs a provider and a model")
        return self


class SupervisionSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal["second_reviewer"] = "second_reviewer"
    ai_alone_may_exclude: Literal[False] = False  # V1: never (D-014)
    pilot_sample_size: int = Field(ge=1)
    target_sensitivity: Decimal = Field(gt=0, le=1)
    calibration_method: Literal["isotonic", "platt", "none"]


class TaskNotAvailableError(LookupError):
    def __init__(self, task: str) -> None:
        self.task = task
        super().__init__(
            _("The AI task “{task}” is not enabled in the project configuration.").format(task=task)
        )


class AISettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    supervision: SupervisionSettings
    tasks: dict[str, AITaskConfig]

    def enabled_task(self, name: str) -> AITaskConfig:
        """Configuration of a runnable task, or :class:`TaskNotAvailableError`."""
        config = self.tasks.get(name)
        if config is None or config.status is not TaskStatus.ENABLED:
            raise TaskNotAvailableError(name)
        return config
