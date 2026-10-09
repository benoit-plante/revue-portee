"""Task ``draft_synthesis``: a draft of the narrative synthesis of one field of the
grid (EF-SYN-04, tranche 3.6).

The model sees, for each included study whose value on the field a person decided, a
short key (S1, S2…), its label, the value and the quote it rests on. It writes a few
descriptive sentences, each citing the keys of the studies it rests on. The tool
refuses a sentence without a study or citing an unknown key; a person revises the
draft before it is used anywhere.
"""

from pydantic import Field

from revue_portee.ai.base import TaskInput, TaskOutput, TaskSpec
from revue_portee.ai.prompts import prompt_ref
from revue_portee.ai.tasks.extraction import FieldText

__all__ = [
    "DRAFT_SYNTHESIS",
    "DraftSynthesisInput",
    "DraftSynthesisOutput",
    "StudyValue",
    "SynthesisSentence",
]


class StudyValue(TaskOutput):
    """What the model sees of one study on the field."""

    key: str  # S1, S2…: short and stable within the call
    label: str  # first author and year
    reported: bool
    value: str = ""  # several choices separated by « | »
    quote: str = ""


class DraftSynthesisInput(TaskInput):
    """``item_id`` is the code of the field."""

    language: str = Field(pattern=r"^[a-z]{2}$")
    review_question: str = ""
    field: FieldText
    studies: tuple[StudyValue, ...] = Field(min_length=1)


class SynthesisSentence(TaskOutput):
    text: str = Field(description="One sentence of the synthesis, in the requested language.")
    studies: tuple[str, ...] = Field(
        description="The keys (S1, S2…) of the studies the sentence rests on; at least one."
    )


class DraftSynthesisOutput(TaskOutput):
    sentences: tuple[SynthesisSentence, ...] = Field(min_length=1)


DRAFT_SYNTHESIS: TaskSpec[DraftSynthesisInput, DraftSynthesisOutput] = TaskSpec(
    name="draft_synthesis",
    version="1",
    input_model=DraftSynthesisInput,
    output_model=DraftSynthesisOutput,
    prompt=prompt_ref("draft_synthesis"),
)
