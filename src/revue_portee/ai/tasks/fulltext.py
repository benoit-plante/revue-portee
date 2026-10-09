"""Task ``screen_fulltext``: full-text screening by the AI reviewer (EF-SEL-16, D-102).

The model reads the text of the report page by page, without its bibliography, and
assesses each criterion with an exact quote and the page it is on; the tool then looks
for each quote at that page (``domain.fulltext.check_quote``).
"""

from typing import Literal

from pydantic import Field

from revue_portee.ai.base import TaskInput, TaskOutput, TaskSpec
from revue_portee.ai.prompts import prompt_ref
from revue_portee.ai.tasks.screening import CriterionText

__all__ = [
    "SCREEN_FULLTEXT",
    "FulltextAssessmentOutput",
    "PageOfText",
    "ReportText",
    "ScreenFulltextInput",
    "ScreenFulltextOutput",
]


class PageOfText(TaskOutput):
    number: int = Field(ge=1)  # page of the PDF
    text: str


class ReportText(TaskOutput):
    """What the model sees of a report: its title and its text by page."""

    title: str = ""
    year: int | None = None
    container_title: str = ""
    pages: tuple[PageOfText, ...] = Field(min_length=1)


class ScreenFulltextInput(TaskInput):
    """``item_id`` is the reference identifier. ``criteria`` come first in the prompt
    and are the same for every report: the cached prefix (ENF-COU-04)."""

    language: str = Field(pattern=r"^[a-z]{2}$")  # language of the rationale
    review_question: str = ""
    criteria: tuple[CriterionText, ...] = Field(min_length=1)
    report: ReportText


class FulltextAssessmentOutput(TaskOutput):
    code: str
    status: Literal["met", "not_met", "cannot_tell"]
    evidence_quote: str = Field(
        description="Exact words of the text the assessment rests on (at most about 40 "
        "words); empty when the report says nothing about the criterion."
    )
    page: int | None = Field(
        default=None, ge=1, description="Page number of the quote, as marked [p. N]."
    )


class ScreenFulltextOutput(TaskOutput):
    assessments: tuple[FulltextAssessmentOutput, ...] = Field(min_length=1)
    decision: Literal["include", "exclude", "uncertain"]
    inclusion_probability: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1)
    decisive_criteria: tuple[str, ...] = Field(min_length=1)


SCREEN_FULLTEXT: TaskSpec[ScreenFulltextInput, ScreenFulltextOutput] = TaskSpec(
    name="screen_fulltext",
    version="1",
    input_model=ScreenFulltextInput,
    output_model=ScreenFulltextOutput,
    prompt=prompt_ref("screen_fulltext"),
)
