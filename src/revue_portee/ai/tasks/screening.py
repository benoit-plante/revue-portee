"""Task ``screen_reference``: title and abstract screening by the AI reviewer
(EF-SEL-06, EF-SEL-07, ENF-LAN-05)."""

from typing import Literal

from pydantic import Field

from revue_portee.ai.base import TaskInput, TaskOutput, TaskSpec
from revue_portee.ai.prompts import prompt_ref
from revue_portee.domain.criteria import Criterion

__all__ = [
    "SCREEN_REFERENCE",
    "AssessmentOutput",
    "CriterionText",
    "ReferenceText",
    "ScreenReferenceInput",
    "ScreenReferenceOutput",
]


class CriterionText(TaskOutput):
    """What the model sees of a criterion."""

    code: str
    pcc_element: str
    kind: str
    text: str
    guidance: str = ""
    examples: tuple[str, ...] = ()
    counterexamples: tuple[str, ...] = ()

    @classmethod
    def of(cls, criterion: Criterion) -> "CriterionText":
        return cls(
            code=criterion.code,
            pcc_element=criterion.pcc_element.value,
            kind=criterion.kind.value,
            text=criterion.text,
            guidance=criterion.guidance,
            examples=criterion.examples,
            counterexamples=criterion.counterexamples,
        )


class ReferenceText(TaskOutput):
    """What the model sees of a reference (no identifier that could recall a review)."""

    title: str = ""
    abstract: str = ""
    year: int | None = None
    container_title: str = ""
    doc_type: str = ""
    language: str = ""


class ScreenReferenceInput(TaskInput):
    """``item_id`` is the reference identifier. ``criteria`` come first in the prompt
    and are the same for every reference: the cached prefix (ENF-COU-04)."""

    language: str = Field(pattern=r"^[a-z]{2}$")  # language of the rationale
    review_question: str = ""
    criteria: tuple[CriterionText, ...] = Field(min_length=1)
    reference: ReferenceText


class AssessmentOutput(TaskOutput):
    code: str
    status: Literal["met", "not_met", "cannot_tell"]
    evidence_quote: str = Field(
        description="Exact words of the title or abstract the assessment rests on; "
        "empty when the reference says nothing about the criterion."
    )


class ScreenReferenceOutput(TaskOutput):
    assessments: tuple[AssessmentOutput, ...] = Field(min_length=1)
    decision: Literal["include", "exclude", "uncertain"]
    inclusion_probability: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1)
    decisive_criteria: tuple[str, ...] = Field(min_length=1)


SCREEN_REFERENCE: TaskSpec[ScreenReferenceInput, ScreenReferenceOutput] = TaskSpec(
    name="screen_reference",
    version="1",
    input_model=ScreenReferenceInput,
    output_model=ScreenReferenceOutput,
    prompt=prompt_ref("screen_reference"),
)
