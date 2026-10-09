"""Task ``draft_lay_summary``: a draft of a plain-language summary of the results
(EF-CON-01, tranche 4.1).

The model sees the review question, the number of included studies and, field by
field, the narrative synthesis the person revised (never the AI's drafts alone, never
the full texts). It writes a title and a few short paragraphs for the language level
asked; the tool computes the readability index and a person revises the summary before
it is used.
"""

from typing import Literal

from pydantic import Field

from revue_portee.ai.base import TaskInput, TaskOutput, TaskSpec
from revue_portee.ai.prompts import prompt_ref

__all__ = [
    "DRAFT_LAY_SUMMARY",
    "DraftLaySummaryInput",
    "DraftLaySummaryOutput",
    "SynthesisSection",
]


class SynthesisSection(TaskOutput):
    """The revised synthesis of one field of the grid."""

    label: str
    text: str


class DraftLaySummaryInput(TaskInput):
    """``item_id`` is the level."""

    language: str = Field(pattern=r"^[a-z]{2}$")
    level: Literal["general", "informed", "professional"]
    target_index: float
    review_title: str
    review_question: str = ""
    studies: int = Field(ge=1)
    sections: tuple[SynthesisSection, ...] = Field(min_length=1)


class DraftLaySummaryOutput(TaskOutput):
    title: str = Field(description="A short, plain title, in the requested language.")
    paragraphs: tuple[str, ...] = Field(
        min_length=1, description="The summary, a few short paragraphs, in the requested language."
    )


DRAFT_LAY_SUMMARY: TaskSpec[DraftLaySummaryInput, DraftLaySummaryOutput] = TaskSpec(
    name="draft_lay_summary",
    version="1",
    input_model=DraftLaySummaryInput,
    output_model=DraftLaySummaryOutput,
    prompt=prompt_ref("draft_lay_summary"),
)
