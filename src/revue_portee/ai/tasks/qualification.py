"""Task ``qualify_criterion_change``: type of a criterion modification (EF-VER-03)."""

from typing import Literal

from pydantic import Field

from revue_portee.ai.base import TaskInput, TaskOutput, TaskSpec
from revue_portee.ai.prompts import prompt_ref
from revue_portee.domain.criteria import Criterion

__all__ = [
    "QUALIFY_CRITERION_CHANGE",
    "CriterionSnapshot",
    "QualifyChangeInput",
    "QualifyChangeOutput",
]


class CriterionSnapshot(TaskOutput):
    """What the model sees of a criterion (its code and element are given apart)."""

    kind: str
    text: str
    guidance: str = ""
    examples: tuple[str, ...] = ()
    counterexamples: tuple[str, ...] = ()

    @classmethod
    def of(cls, criterion: Criterion) -> "CriterionSnapshot":
        return cls(
            kind=criterion.kind.value,
            text=criterion.text,
            guidance=criterion.guidance,
            examples=criterion.examples,
            counterexamples=criterion.counterexamples,
        )


class QualifyChangeInput(TaskInput):
    """``item_id`` is the criterion code."""

    language: str = Field(pattern=r"^[a-z]{2}$")
    code: str
    pcc_element: str
    before: CriterionSnapshot
    after: CriterionSnapshot


class QualifyChangeOutput(TaskOutput):
    change_type: Literal["broadening", "narrowing", "clarification"]
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


QUALIFY_CRITERION_CHANGE: TaskSpec[QualifyChangeInput, QualifyChangeOutput] = TaskSpec(
    name="qualify_criterion_change",
    version="1",
    input_model=QualifyChangeInput,
    output_model=QualifyChangeOutput,
    prompt=prompt_ref("qualify_criterion_change"),
)
