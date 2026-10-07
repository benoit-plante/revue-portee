"""Task ``suggest_terms``: synonyms, variants and descriptors for concept blocks (EF-REC-02)."""

from pydantic import Field

from revue_portee.ai.base import TaskInput, TaskOutput, TaskSpec
from revue_portee.ai.prompts import prompt_ref
from revue_portee.domain.search import BLOCK_CODE, TermSuggestionKind

__all__ = [
    "SUGGEST_TERMS",
    "BlockSnapshot",
    "SuggestTermsInput",
    "SuggestTermsOutput",
    "TermProposal",
]


class BlockSnapshot(TaskInput):
    code: str = Field(pattern=BLOCK_CODE.pattern)
    label: str = ""
    pcc_element: str = ""
    role: str
    terms: tuple[str, ...] = ()  # in the term syntax


class SuggestTermsInput(TaskInput):
    language: str = Field(pattern=r"^[a-z]{2}$")
    question: str = ""
    population: str = ""
    concept: str = ""
    context: str = ""
    blocks: tuple[BlockSnapshot, ...] = Field(min_length=1)


class TermProposal(TaskOutput):
    block_code: str = Field(pattern=BLOCK_CODE.pattern)
    kind: TermSuggestionKind
    line: str = Field(min_length=1)
    rationale: str


class SuggestTermsOutput(TaskOutput):
    suggestions: tuple[TermProposal, ...] = Field(max_length=60)


SUGGEST_TERMS: TaskSpec[SuggestTermsInput, SuggestTermsOutput] = TaskSpec(
    name="suggest_terms",
    version="1",
    input_model=SuggestTermsInput,
    output_model=SuggestTermsOutput,
    prompt=prompt_ref("suggest_terms"),
)
