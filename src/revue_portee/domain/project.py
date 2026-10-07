"""Review project and reviewers (EF-PRJ-01, EF-PRJ-05)."""

from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

__all__ = ["FORMAT_VERSION", "Project", "Reviewer", "ReviewerKind"]

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
