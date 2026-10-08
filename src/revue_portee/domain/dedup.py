"""Deduplication runs, candidate pairs and decisions (EF-COL-06, EF-COL-07).

Nothing is deleted: a run records the pairs it found; a person's decision on a pair is
added and the latest one counts; duplicates are grouped under a primary reference,
computed from the links in force, so any grouping can be undone by a new decision.
"""

from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "ALGORITHM_VERSION",
    "DedupRun",
    "DedupSettings",
    "DuplicatePair",
    "PairDecision",
    "PairKind",
    "PairOutcome",
    "Proposal",
]

# Incremented whenever the matching rules change, so that every run says which it used.
ALGORITHM_VERSION = "1"


class PairKind(StrEnum):
    IDENTIFIER = "identifier"  # same DOI, PMID or OpenAlex identifier
    FUZZY = "fuzzy"  # similar fields
    VERSION = "version"  # two versions of one work (preprint and article…)


class Proposal(StrEnum):
    DUPLICATE = "duplicate"  # grouped automatically
    REVIEW = "review"  # left to a person


class PairOutcome(StrEnum):
    DUPLICATE = "duplicate"
    NOT_DUPLICATE = "not_duplicate"


class DedupSettings(BaseModel):
    """Adjustable thresholds of approximate matching (scores from 0 to 1)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    review_from: float = Field(default=0.75, ge=0, le=1)
    auto_from: float = Field(default=0.93, ge=0, le=1)
    algorithm_version: str = ALGORITHM_VERSION

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.review_from > self.auto_from:
            raise ValueError("review_from must not exceed auto_from")
        return self


class DedupRun(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    created_at: AwareDatetime
    reviewer_id: str
    settings: DedupSettings
    reference_count: int = Field(ge=0)
    automatic_pairs: int = Field(ge=0)
    review_pairs: int = Field(ge=0)


class DuplicatePair(BaseModel):
    """A pair found by a run; ``reference_a_id`` < ``reference_b_id``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    run_id: str
    reference_a_id: str
    reference_b_id: str
    kind: PairKind
    rule: str  # e.g. "doi", "similarity", "preprint"
    score: float = Field(ge=0, le=1)
    proposal: Proposal
    details: dict[str, float | str | None] = {}

    @model_validator(mode="after")
    def _order(self) -> Self:
        if self.reference_a_id >= self.reference_b_id:
            raise ValueError("reference_a_id must sort before reference_b_id")
        return self


class PairDecision(BaseModel):
    """A person's decision on a pair of references; the latest one counts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    reference_a_id: str
    reference_b_id: str
    pair_id: str | None  # the pair shown, if any
    outcome: PairOutcome
    reviewer_id: str
    note: str = ""
    created_at: AwareDatetime

    @model_validator(mode="after")
    def _order(self) -> Self:
        if self.reference_a_id >= self.reference_b_id:
            raise ValueError("reference_a_id must sort before reference_b_id")
        return self
