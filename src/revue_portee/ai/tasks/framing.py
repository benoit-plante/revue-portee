"""Task ``suggest_pcc``: reformulations, secondary questions and PCC elements (EF-CAD-02)."""

from pydantic import Field

from revue_portee.ai.base import TaskInput, TaskOutput, TaskSpec
from revue_portee.ai.prompts import prompt_ref
from revue_portee.domain.suggestions import SuggestionKind

__all__ = ["SUGGEST_PCC", "PccSuggestion", "SuggestPccInput", "SuggestPccOutput"]


class SuggestPccInput(TaskInput):
    language: str = Field(pattern=r"^[a-z]{2}$")
    question: str = Field(min_length=1)
    population: str = ""
    concept: str = ""
    context: str = ""
    secondary_questions: tuple[str, ...] = ()


class PccSuggestion(TaskOutput):
    kind: SuggestionKind
    text: str = Field(min_length=1)
    rationale: str


class SuggestPccOutput(TaskOutput):
    suggestions: tuple[PccSuggestion, ...] = Field(max_length=15)


SUGGEST_PCC: TaskSpec[SuggestPccInput, SuggestPccOutput] = TaskSpec(
    name="suggest_pcc",
    version="1",
    input_model=SuggestPccInput,
    output_model=SuggestPccOutput,
    prompt=prompt_ref("suggest_pcc"),
)
