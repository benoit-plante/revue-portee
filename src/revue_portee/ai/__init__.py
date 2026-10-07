"""Model abstraction layer: tasks, providers, prompts, calibration, costs."""

from revue_portee.ai.base import (
    AICallRecord,
    CostEstimate,
    ModelProvider,
    PromptRef,
    TaskInput,
    TaskOutput,
    TaskResult,
    TaskSpec,
    UnsupportedTaskError,
)
from revue_portee.ai.runner import run_task

__all__ = [
    "AICallRecord",
    "CostEstimate",
    "ModelProvider",
    "PromptRef",
    "TaskInput",
    "TaskOutput",
    "TaskResult",
    "TaskSpec",
    "UnsupportedTaskError",
    "run_task",
]
