"""Task definitions (docs/03-architecture.md §6.1): what is asked, independently of the
model, with Pydantic input and output schemas."""

from revue_portee.ai.tasks.framing import (
    SUGGEST_PCC,
    PccSuggestion,
    SuggestPccInput,
    SuggestPccOutput,
)
from revue_portee.ai.tasks.qualification import (
    QUALIFY_CRITERION_CHANGE,
    CriterionSnapshot,
    QualifyChangeInput,
    QualifyChangeOutput,
)
from revue_portee.ai.tasks.screening import (
    SCREEN_REFERENCE,
    AssessmentOutput,
    CriterionText,
    ReferenceText,
    ScreenReferenceInput,
    ScreenReferenceOutput,
)
from revue_portee.ai.tasks.search import (
    SUGGEST_TERMS,
    BlockSnapshot,
    SuggestTermsInput,
    SuggestTermsOutput,
    TermProposal,
)

__all__ = [
    "QUALIFY_CRITERION_CHANGE",
    "SCREEN_REFERENCE",
    "SUGGEST_PCC",
    "SUGGEST_TERMS",
    "AssessmentOutput",
    "BlockSnapshot",
    "CriterionSnapshot",
    "CriterionText",
    "PccSuggestion",
    "QualifyChangeInput",
    "QualifyChangeOutput",
    "ReferenceText",
    "ScreenReferenceInput",
    "ScreenReferenceOutput",
    "SuggestPccInput",
    "SuggestPccOutput",
    "SuggestTermsInput",
    "SuggestTermsOutput",
    "TermProposal",
]
