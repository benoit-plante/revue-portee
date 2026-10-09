"""Task ``extract_fields``: pre-filling of the extraction grid by the AI (EF-EXT-03).

The model reads the text of the primary report of a study, page by page and without
its bibliography, and gives for each field of the grid in force a value with the exact
quote it rests on and its page, or says the report does not give it. The tool checks
each value against the type of its field and looks for each quote in the text.
"""

from pydantic import Field

from revue_portee.ai.base import TaskInput, TaskOutput, TaskSpec
from revue_portee.ai.prompts import prompt_ref
from revue_portee.ai.tasks.fulltext import ReportText
from revue_portee.domain.grid import GridField

__all__ = [
    "EXTRACT_FIELDS",
    "ExtractFieldsInput",
    "ExtractFieldsOutput",
    "ExtractedValueOutput",
    "FieldText",
]


class FieldText(TaskOutput):
    """What the model sees of a field of the grid."""

    code: str
    label: str
    type: str
    definition: str = ""
    guidance: str = ""
    examples: tuple[str, ...] = ()
    choices: tuple[str, ...] = ()

    @classmethod
    def of(cls, field: GridField) -> "FieldText":
        return cls(
            code=field.code,
            label=field.label,
            type=field.type.value,
            definition=field.definition,
            guidance=field.guidance,
            examples=field.examples,
            choices=field.choices,
        )


class ExtractFieldsInput(TaskInput):
    """``item_id`` is the identifier of the report. ``fields`` come first in the prompt
    and are the same for every report: the cached prefix (ENF-COU-04)."""

    language: str = Field(pattern=r"^[a-z]{2}$")
    review_question: str = ""
    fields: tuple[FieldText, ...] = Field(min_length=1)
    report: ReportText


class ExtractedValueOutput(TaskOutput):
    code: str
    reported: bool = Field(description="False when the report does not give this information.")
    value: str = Field(
        default="",
        description="The value: text, a number, yes or no, a date YYYY[-MM[-DD]], or one of "
        "the choices copied exactly; empty when not reported or for a multiple choice.",
    )
    selected: tuple[str, ...] = Field(
        default=(), description="For a multiple choice field: the choices that apply."
    )
    quote: str = Field(
        default="", description="Exact words of the text the value rests on (at most 40 words)."
    )
    page: int | None = Field(default=None, ge=1, description="Page of the quote, as [p. N].")


class ExtractFieldsOutput(TaskOutput):
    values: tuple[ExtractedValueOutput, ...] = Field(min_length=1)


EXTRACT_FIELDS: TaskSpec[ExtractFieldsInput, ExtractFieldsOutput] = TaskSpec(
    name="extract_fields",
    version="1",
    input_model=ExtractFieldsInput,
    output_model=ExtractFieldsOutput,
    prompt=prompt_ref("extract_fields"),
)
