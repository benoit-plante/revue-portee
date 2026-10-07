"""AI suggestions for the framing and their human review (EF-CAD-02).

Each suggestion must be explicitly accepted, modified or rejected by a human; the
choice is recorded with the AI call that produced the suggestion. Accepting or
modifying a suggestion changes the framing, which creates a new framing version.
"""

from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from revue_portee.domain.framing import Framing

__all__ = [
    "AISuggestion",
    "SuggestionKind",
    "SuggestionOutcome",
    "SuggestionReview",
    "apply_suggestion",
]


class SuggestionKind(StrEnum):
    REFORMULATION = "reformulation"  # of the main question
    SECONDARY_QUESTION = "secondary_question"
    POPULATION = "population"
    CONCEPT = "concept"
    CONTEXT = "context"


class SuggestionOutcome(StrEnum):
    ACCEPTED = "accepted"
    MODIFIED = "modified"
    REJECTED = "rejected"


class AISuggestion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    ai_call_id: str
    position: int = Field(ge=0)  # order in the model output
    kind: SuggestionKind
    text: str = Field(min_length=1)
    rationale: str = ""
    created_at: AwareDatetime


class SuggestionReview(BaseModel):
    """The human decision on one suggestion (one per suggestion, never changed)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    suggestion_id: str
    outcome: SuggestionOutcome
    final_text: str = ""  # text applied to the framing; empty when rejected
    reviewer_id: str
    created_at: AwareDatetime
    framing_version_id: str | None = None  # version created by the review, if any

    @model_validator(mode="after")
    def _text_matches_outcome(self) -> Self:
        if (self.outcome is SuggestionOutcome.REJECTED) != (not self.final_text.strip()):
            raise ValueError("a rejected suggestion has no final text; any other has one")
        return self


def apply_suggestion(framing: Framing, kind: SuggestionKind, text: str) -> Framing:
    """Framing after applying an accepted (or modified) suggestion.

    A reformulation replaces the main question; an element suggestion replaces the
    population, concept or context; a secondary question is added unless present.
    """
    text = text.strip()
    if not text:
        raise ValueError("an applied suggestion needs a text")
    if kind is SuggestionKind.REFORMULATION:
        return framing.model_copy(update={"question": text})
    if kind is SuggestionKind.SECONDARY_QUESTION:
        if text in framing.secondary_questions:
            return framing
        return framing.model_copy(
            update={"secondary_questions": (*framing.secondary_questions, text)}
        )
    return framing.model_copy(update={kind.value: text})
