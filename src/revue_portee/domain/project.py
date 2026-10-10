"""Review project and reviewers (EF-PRJ-01, EF-PRJ-05).

A project created by the replication benchmark carries a :class:`ReplicationMarker`
(D-104): the AI's decisions are final in it, which no ordinary project allows.
"""

from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

__all__ = [
    "FORMAT_VERSION",
    "Project",
    "ReplicationMarker",
    "ReplicationMode",
    "Reviewer",
    "ReviewerKind",
]

# Version of the project folder format (docs/03-architecture.md §4).
FORMAT_VERSION = "1.0"


class ReviewerKind(StrEnum):
    HUMAN = "human"
    AI = "ai"


class Reviewer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: ReviewerKind
    display_name: str = Field(min_length=1)
    role: str = ""
    ai_config_id: str | None = None
    active: bool = True


class Project(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    title: str = Field(min_length=1)
    language: str = Field(pattern=r"^[a-z]{2}$")
    description: str = ""
    created_at: AwareDatetime
    format_version: str = FORMAT_VERSION


class ReplicationMode(StrEnum):
    """How a published review is replayed (docs/11-plan-de-replication.md §3)."""

    STEPWISE = "stepwise"  # « par étape »: each step gets the published inputs
    CHAINED = "chained"  # « en chaîne »: each step gets the AI's outputs of the previous


class ReplicationMarker(BaseModel):
    """The project replays a published review without anyone (D-104), set only when
    the project is created (table ``replication_marker`` and ``projet.toml``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    review_id: str = Field(min_length=1)
    mode: ReplicationMode
