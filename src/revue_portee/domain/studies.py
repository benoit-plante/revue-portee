"""Studies and their reports (EF-SEL-17, tranche 2.3).

An included study may be reported in several references (main results, protocol,
secondary analyses). Pairs of included reports proposed by rules (``dedup.reports``)
are examined by the AI, then decided by a person: « same study » or « different
studies ». A study is a group of reports joined by the person's « same study »
decisions in force (the latest on each pair); nothing is deleted, so separating two
reports again is a new decision. Each study has a primary report: the one the person
chose, otherwise the oldest report (then the smallest identifier).
"""

from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict

from revue_portee.domain.fulltext import QuoteCheck

__all__ = [
    "LinkEvidence",
    "LinkOutcome",
    "LinkVerdict",
    "PrimaryChoice",
    "StudyLinkAssessment",
    "StudyLinkDecision",
    "latest_by_pair",
    "linked_pairs",
    "primary_report",
    "same_pair",
]


def same_pair(a: str, b: str) -> tuple[str, str]:
    """A pair of references in a fixed order."""
    return (a, b) if a <= b else (b, a)


class LinkOutcome(StrEnum):
    SAME = "same"  # the person: reports of one study
    DIFFERENT = "different"


class LinkVerdict(StrEnum):
    SAME = "same"  # the AI: reports of one study
    DIFFERENT = "different"
    UNCERTAIN = "uncertain"


class LinkEvidence(BaseModel):
    """What the AI compared in the two reports, with a quote and its page in each."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    aspect: str  # e.g. registration, setting, sample, intervention, authors
    quote_a: str = ""
    page_a: int | None = None
    check_a: QuoteCheck | None = None
    quote_b: str = ""
    page_b: int | None = None
    check_b: QuoteCheck | None = None


class StudyLinkAssessment(BaseModel):
    """The AI's examination of a pair of reports (table ``study_link_assessment``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    reference_a_id: str
    reference_b_id: str
    rule: str  # the rule that proposed the pair
    verdict: LinkVerdict
    rationale: str
    evidence: tuple[LinkEvidence, ...] = ()
    ai_call_id: str
    created_at: AwareDatetime
    reviewer_id: str


class StudyLinkDecision(BaseModel):
    """The person's decision on a pair of reports (table ``study_link_decision``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    reference_a_id: str
    reference_b_id: str
    outcome: LinkOutcome
    note: str = ""
    created_at: AwareDatetime
    reviewer_id: str


class PrimaryChoice(BaseModel):
    """The report the person chose as the primary report of its study."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    reference_id: str
    created_at: AwareDatetime
    reviewer_id: str


def latest_by_pair[T: (StudyLinkAssessment, StudyLinkDecision)](
    items: Iterable[T],
) -> dict[tuple[str, str], T]:
    """The latest item on each pair, in the order given (oldest first)."""
    latest: dict[tuple[str, str], T] = {}
    for item in items:
        latest[same_pair(item.reference_a_id, item.reference_b_id)] = item
    return latest


def linked_pairs(decisions: Iterable[StudyLinkDecision]) -> list[tuple[str, str]]:
    """Pairs whose latest decision is « same study »."""
    return sorted(
        pair for pair, d in latest_by_pair(decisions).items() if d.outcome is LinkOutcome.SAME
    )


def primary_report(
    group: Sequence[str], years: Mapping[str, int | None], choices: Iterable[PrimaryChoice]
) -> str:
    """The primary report of a study: the latest choice among its reports, otherwise the
    oldest report (unknown years last), then the smallest identifier."""
    members = set(group)
    chosen = [c.reference_id for c in choices if c.reference_id in members]
    if chosen:
        return chosen[-1]
    return min(group, key=lambda ref: (years.get(ref) is None, years.get(ref) or 0, ref))
