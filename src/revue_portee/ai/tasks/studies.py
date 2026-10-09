"""Task ``group_reports``: are two included reports reports of the same study?
(EF-SEL-17, tranche 2.3).

The rules propose the pair (``dedup.reports``); the model compares the two texts and
names what they share or not, with a quote and its page in each report, which the tool
looks for. A person decides.
"""

from typing import Literal

from pydantic import Field

from revue_portee.ai.base import TaskInput, TaskOutput, TaskSpec
from revue_portee.ai.prompts import prompt_ref
from revue_portee.ai.tasks.fulltext import PageOfText

__all__ = [
    "GROUP_REPORTS",
    "GroupReportsInput",
    "GroupReportsOutput",
    "LinkEvidenceOutput",
    "ReportExcerpt",
]


class ReportExcerpt(TaskOutput):
    """What the model sees of a report: its metadata and the first pages of its text."""

    title: str = ""
    authors: tuple[str, ...] = ()
    year: int | None = None
    container_title: str = ""
    registrations: tuple[str, ...] = ()  # trial registration numbers found by the tool
    pages: tuple[PageOfText, ...] = ()


class GroupReportsInput(TaskInput):
    """``item_id`` names the pair (``<reference a>-<reference b>``)."""

    language: str = Field(pattern=r"^[a-z]{2}$")  # language of the rationale
    report_a: ReportExcerpt
    report_b: ReportExcerpt


class LinkEvidenceOutput(TaskOutput):
    aspect: Literal[
        "registration", "authors", "setting", "period", "sample", "intervention", "design",
        "other",
    ]  # fmt: skip
    quote_a: str = Field(description="Exact words of report A; empty if it says nothing.")
    page_a: int | None = Field(default=None, ge=1)
    quote_b: str = Field(description="Exact words of report B; empty if it says nothing.")
    page_b: int | None = Field(default=None, ge=1)


class GroupReportsOutput(TaskOutput):
    verdict: Literal["same", "different", "uncertain"]
    evidence: tuple[LinkEvidenceOutput, ...] = Field(min_length=1)
    rationale: str = Field(min_length=1)


GROUP_REPORTS: TaskSpec[GroupReportsInput, GroupReportsOutput] = TaskSpec(
    name="group_reports",
    version="1",
    input_model=GroupReportsInput,
    output_model=GroupReportsOutput,
    prompt=prompt_ref("group_reports"),
)
