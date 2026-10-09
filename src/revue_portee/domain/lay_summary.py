"""Plain-language summaries of the results (EF-CON-01, tranche 4.1).

A summary is written for a language level (general public, informed readers,
professionals) from the narrative synthesis the person revised. The AI may propose it;
the person revises it, and only revised summaries are exported. A summary is never
changed: a revision is a new version that supersedes the previous one. Its
readability index (``domain.readability``) is reported with it, against the target of
its level.
"""

from collections.abc import Iterable
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from revue_portee.domain.project import ReviewerKind
from revue_portee.domain.readability import Readability, readability

__all__ = [
    "TARGET_INDEX",
    "LayLevel",
    "LaySummary",
    "SummaryStatus",
    "current_summaries",
    "meets_target",
    "revised_summaries",
]


class LayLevel(StrEnum):
    GENERAL = "general"  # readers without training in the field
    INFORMED = "informed"  # community organisations, patients' associations
    PROFESSIONAL = "professional"  # practitioners and decision-makers


# Lowest readability index aimed at for each level (Kandel-Moles in French, Flesch in
# English): « standard » for the general public, « fairly difficult » for informed
# readers, « difficult » for professionals.
TARGET_INDEX: dict[LayLevel, float] = {
    LayLevel.GENERAL: 60.0,
    LayLevel.INFORMED: 50.0,
    LayLevel.PROFESSIONAL: 30.0,
}


class SummaryStatus(StrEnum):
    PROPOSED = "proposed"  # by the AI, not revised yet
    REVISED = "revised"  # by the person


class LaySummary(BaseModel):
    """One version of the summary of one level (table ``lay_summary``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    level: LayLevel
    language: str
    title: str
    text: str = Field(min_length=1)  # paragraphs separated by a blank line
    status: SummaryStatus
    reviewer_id: str
    reviewer_kind: ReviewerKind
    ai_call_id: str | None = None
    supersedes_id: str | None = None
    narrative_ids: tuple[str, ...] = ()  # the revised narrative drafts it rests on
    created_at: AwareDatetime

    @property
    def paragraphs(self) -> tuple[str, ...]:
        return tuple(p.strip() for p in self.text.split("\n\n") if p.strip())

    @property
    def readability(self) -> Readability | None:
        """The index of the text, its title aside."""
        return readability(self.text, self.language)


def meets_target(level: LayLevel, found: Readability | None) -> bool:
    return found is not None and found.index >= TARGET_INDEX[level]


def _latest(summaries: Iterable[LaySummary]) -> dict[LayLevel, LaySummary]:
    found: dict[LayLevel, LaySummary] = {}
    for summary in sorted(summaries, key=lambda s: (s.created_at, s.id)):
        found[summary.level] = summary
    return found


def current_summaries(summaries: Iterable[LaySummary]) -> dict[LayLevel, LaySummary]:
    """The latest version of each level, the AI's or the person's."""
    return _latest(summaries)


def revised_summaries(summaries: Iterable[LaySummary]) -> dict[LayLevel, LaySummary]:
    """The latest version a person revised, for each level: the only ones exported."""
    return _latest(s for s in summaries if s.status is SummaryStatus.REVISED)
