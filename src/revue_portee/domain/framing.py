"""Review question framed with PCC: Population, Concept, Context (EF-CAD-01).

The framing is versioned like everything that shapes the method: each change is a new
immutable version, never an update.
"""

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

__all__ = ["Framing", "FramingVersion"]


class Framing(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=1)
    population: str = ""
    concept: str = ""
    context: str = ""
    secondary_questions: tuple[str, ...] = ()


class FramingVersion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    number: int = Field(ge=1)
    created_at: AwareDatetime
    author_id: str
    framing: Framing
