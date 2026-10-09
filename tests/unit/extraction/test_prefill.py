"""Pre-filling of the extraction grid by the AI (EF-EXT-03): values checked against
their type, quotes placed at their page, one study at a time under the ceilings."""

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from demo import build
from revue_portee.ai.base import ModelProvider, TaskInput
from revue_portee.ai.providers.fake import FakeProvider
from revue_portee.ai.settings import AITaskConfig
from revue_portee.ai.tasks.extraction import ExtractFieldsInput
from revue_portee.domain.extraction import ValueStatus
from revue_portee.domain.fulltext import QuoteCheck
from revue_portee.domain.grid import FieldType
from revue_portee.domain.journal import EntryType
from revue_portee.domain.project import ReviewerKind
from revue_portee.extraction import grid, prefill
from revue_portee.protocol import notes
from revue_portee.screening import settings
from support import TOOL_VERSION


def answer(item: TaskInput, *, design: str = "Qualitatif") -> dict[str, Any]:
    assert isinstance(item, ExtractFieldsInput)
    assert [f.code for f in item.fields] == ["D1", "D2", "D3"]
    assert item.report.pages[0].number == 1
    return {
        "values": [
            {"code": "D1", "reported": False},
            # the page given is wrong: the quote is on page 2
            {"code": "D2", "reported": True, "value": "24",
             "quote": "We interviewed 24 older adults", "page": 3},
            {"code": "D3", "reported": True, "value": design,
             "quote": "living in three residences", "page": 2},
        ]
    }  # fmt: skip


def factory(responder: Any) -> Any:  # noqa: ANN401 - a provider factory
    def build_provider(config: AITaskConfig) -> ModelProvider:
        return FakeProvider(
            model=str(config.model), responder=responder, cost_per_call=Decimal("0.002")
        )

    return build_provider


def _with_grid(tmp_path: Path) -> Any:  # noqa: ANN401 - the demonstration
    demo = build(tmp_path)
    for label, type, choices in (
        ("Pays", FieldType.TEXT, ()),
        ("Taille de l'échantillon", FieldType.NUMBER, ()),
        ("Devis", FieldType.SINGLE_CHOICE, ("Qualitatif", "Quantitatif")),
    ):
        grid.add_field(
            demo.folder, label=label, type=type, choices=choices, now=demo.clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
    grid.activate_draft(demo.folder, rationale="", now=demo.clock, tool_version=TOOL_VERSION)
    return demo


def test_studies_prefilled_counted_by_hand(tmp_path: Path) -> None:
    demo = _with_grid(tmp_path)
    try:
        before = prefill.extraction_state(demo.folder)
        assert [s.primary.id for s in before.waiting] == [demo.ids()["loneliness"]]
        preview = prefill.preview_ai(demo.folder, factory=factory(answer))
        result = prefill.run_ai(
            demo.folder, batch_limit=Decimal(1), factory=factory(answer), now=demo.clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
        after = prefill.extraction_state(demo.folder)
        again = prefill.run_ai(
            demo.folder, batch_limit=Decimal(1), factory=factory(answer), now=demo.clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
        entries = notes.journal_entries(demo.folder)
    finally:
        demo.folder.close()
    assert (preview.items, result.screened, again.screened) == (1, 1, 0)
    (study,) = after.studies
    assert study.prefilled
    assert after.waiting == []
    values = study.values
    assert not values["D1"].reported
    assert values["D1"].value is None
    assert values["D1"].quote_check is None
    assert (values["D2"].value, values["D2"].page, values["D2"].model_page) == (24, 2, 3)
    assert values["D2"].quote_check is QuoteCheck.OTHER_PAGE
    assert (values["D3"].value, values["D3"].page) == ("Qualitatif", 2)
    assert values["D3"].quote_check is QuoteCheck.AT_PAGE
    assert {v.status for v in values.values()} == {ValueStatus.PROPOSED}
    assert {v.reviewer_kind for v in values.values()} == {ReviewerKind.AI}
    entry = next(e for e in entries if e.entry_type == EntryType.EXTRACTION_AI_PROPOSED)
    assert entry.payload["reported"] == 2


def test_unusable_answers_ceilings_and_grid(tmp_path: Path) -> None:
    demo = build(tmp_path)
    try:
        with pytest.raises(prefill.NoGridError):
            prefill.run_ai(
                demo.folder, batch_limit=Decimal(1), factory=factory(answer), now=demo.clock,
                tool_version=TOOL_VERSION,
            )  # fmt: skip
    finally:
        demo.folder.close()
    demo = _with_grid(tmp_path / "with-grid")
    try:
        invalid = prefill.run_ai(
            demo.folder, batch_limit=Decimal(1),
            factory=factory(lambda item: answer(item, design="Mixte")), now=demo.clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
        missing = prefill.run_ai(
            demo.folder, batch_limit=Decimal(1),
            factory=factory(lambda item: {"values": answer(item)["values"][:2]}), now=demo.clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
        stopped = prefill.run_ai(
            demo.folder, batch_limit=Decimal("0.000001"), factory=factory(answer), now=demo.clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
        settings.set_budget(
            demo.folder, Decimal("0.000001"), now=demo.clock, tool_version=TOOL_VERSION
        )
        project = prefill.run_ai(
            demo.folder, batch_limit=Decimal(1), factory=factory(answer), now=demo.clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
        entries = notes.journal_entries(demo.folder)
    finally:
        demo.folder.close()
    assert (invalid.screened, len(invalid.failed)) == (0, 1)  # not among the choices, twice
    assert (missing.screened, len(missing.failed)) == (0, 1)
    assert stopped.stopped == "batch_budget"
    assert project.stopped == "project_budget"
    assert sum(1 for e in entries if e.entry_type == EntryType.EXTRACTION_AI_FAILED) == 2


def test_single_choice_answered_in_selected() -> None:
    """Real trial of v1: the model sometimes put a single choice in « selected »."""
    from revue_portee.ai.tasks.extraction import ExtractFieldsOutput
    from revue_portee.domain.grid import GridField
    from revue_portee.screening.ai_screening import UnusableAnswerError

    focus = GridField(
        code="D7", label="Objet", type=FieldType.SINGLE_CHOICE,
        choices=("Adherence", "Non-adherence", "Adherence and non-adherence"),
    )  # fmt: skip
    settings_ = GridField(
        code="D2", label="Milieu", type=FieldType.MULTIPLE_CHOICE, choices=("A", "B")
    )

    def output(**d7: object) -> ExtractFieldsOutput:
        return ExtractFieldsOutput.model_validate(
            {"values": [{"code": "D7", "reported": True, **d7},
                        {"code": "D2", "reported": True, "selected": ["B", "A"]}]}
        )  # fmt: skip

    fields = [focus, settings_]
    one = prefill.check_answer(output(selected=["Non-adherence"]), fields)
    assert one == {"D7": "Non-adherence", "D2": ["A", "B"]}
    both = prefill.check_answer(output(value="Adherence", selected=["Non-adherence"]), fields)
    assert both["D7"] == "Adherence"  # the value prevails
    with pytest.raises(UnusableAnswerError, match="D7: one value expected"):
        prefill.check_answer(output(selected=["Adherence", "Non-adherence"]), fields)
    with pytest.raises(UnusableAnswerError):
        prefill.check_answer(output(value="Other"), fields)
