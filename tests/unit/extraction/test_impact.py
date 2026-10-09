"""Impact of a new version of the extraction grid on the values (EF-VER-06): recorded
at the activation, followed until done; the AI pre-fills only the fields added or
modified; removed fields are archived, out of the synthesis."""

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from revue_portee.ai.base import TaskInput
from revue_portee.ai.tasks.extraction import ExtractFieldsInput
from revue_portee.domain.extraction import ChangeKind, ValueStatus
from revue_portee.domain.grid import FieldType
from revue_portee.domain.journal import EntryType
from revue_portee.extraction import grid, impact, prefill, validation
from revue_portee.storage.repositories import journal
from support import TOOL_VERSION
from unit.extraction.test_prefill import _with_grid, answer, factory

ANSWERS: dict[str, dict[str, Any]] = {
    "D2": {"code": "D2", "reported": True, "value": "22", "quote": "We interviewed 24 older"},
    "D4": {"code": "D4", "reported": True, "value": "residences",
           "quote": "living in three residences", "page": 2},
}  # fmt: skip
ASKED: list[list[str]] = []


def second_answer(item: TaskInput) -> dict[str, Any]:
    assert isinstance(item, ExtractFieldsInput)
    codes = [f.code for f in item.fields]
    ASKED.append(codes)
    return {"values": [ANSWERS[code] for code in codes]}


def _changed(tmp_path: Path) -> Any:  # noqa: ANN401 - the demonstration
    """Version 1 pre-filled, D2 validated and D3 corrected by the person; version 2
    defines D2, removes D3 and adds D4."""
    demo = _with_grid(tmp_path)
    ref = demo.ids()["loneliness"]
    kwargs: dict[str, Any] = {"now": demo.clock, "tool_version": TOOL_VERSION}
    prefill.run_ai(demo.folder, batch_limit=Decimal(1), factory=factory(answer), **kwargs)
    validation.validate_value(demo.folder, ref, "D2", **kwargs)
    validation.record_value(demo.folder, ref, "D3", reported=True, value="Quantitatif", **kwargs)
    grid.update_field(
        demo.folder, "D2", label="Taille de l'échantillon", type=FieldType.NUMBER,
        definition="Participants analysed", **kwargs,
    )  # fmt: skip
    grid.remove_field(demo.folder, "D3", **kwargs)
    grid.add_field(demo.folder, label="Milieu", type=FieldType.TEXT, **kwargs)
    grid.activate_draft(demo.folder, rationale="Taille définie; devis retiré", **kwargs)
    return demo


def test_impact_recorded_then_followed(tmp_path: Path) -> None:
    demo = _changed(tmp_path)
    ref = demo.ids()["loneliness"]
    folder = demo.folder
    kwargs: dict[str, Any] = {"now": demo.clock, "tool_version": TOOL_VERSION}
    try:
        with folder.engine.connect() as connection:
            entries = [
                e
                for e in journal.list_entries(connection)
                if e.entry_type == EntryType.GRID_IMPACT_ASSESSED
            ]
        before = impact.impact_state(folder)
        state = prefill.extraction_state(folder)
        study = state.studies[0]
        rows = {r.field.code: r for r in validation.synthesis_rows(folder)}
        archived = validation.archived_values(folder)

        ASKED.clear()
        prefill.run_ai(folder, batch_limit=Decimal(1), factory=factory(second_answer), **kwargs)
        assert prefill.extraction_state(folder).waiting == []
        with pytest.raises(validation.NothingToConfirmError):  # the AI's value is in force
            validation.confirm_value(folder, ref, "D2", **kwargs)
        middle = impact.impact_state(folder)
        validation.validate_value(folder, ref, "D2", **kwargs)
        validation.record_value(folder, ref, "D4", reported=False, **kwargs)
        after = impact.impact_state(folder)
        path, written = validation.export_extraction(folder)
    finally:
        folder.close()
    assert len(entries) == 1
    assert entries[0].summary_fr == (
        "Impact de la version 2 de la grille : études à compléter : 1; valeurs à "
        "revoir : 1; valeurs archivées : 1"
    )
    assert entries[0].payload["from_version"] == 1
    assert before is not None
    assert (before.from_number, before.to_number) == (1, 2)
    assert [(c.change.kind, c.change.code, c.remaining) for c in before.changes] == [
        (ChangeKind.ADDED, "D4", (ref,)),
        (ChangeKind.MODIFIED, "D2", (ref,)),
        (ChangeKind.REMOVED, "D3", ()),
    ]
    # the AI is asked only D2 (modified) and D4 (added); D1 keeps its answer
    assert (study.due, study.to_review) == (("D2", "D4"), ("D2",))
    assert ASKED == [["D2", "D4"]]
    # the person's D2 stays in the synthesis, flagged; D3 is archived, out of it
    assert rows["D2"].to_review
    assert rows["D2"].value is not None
    assert rows["D2"].value.value == 24
    assert "D3" not in rows
    assert [(a.label, a.value.value) for a in archived] == [("Devis", "Quantitatif")]
    # the AI's new D2 is still to check: the study remains to review
    assert middle is not None
    assert [c.remaining for c in middle.changes] == [(ref,), (ref,), ()]
    assert after is not None
    assert [c.remaining for c in after.changes] == [(), (), ()]
    assert written == 2  # D1: proposed by the AI only, never checked
    text = path.read_text(encoding="utf-8")
    assert ",D2,Taille de l'échantillon,oui,22,2,validated,\n" in text
    assert ",D4,Milieu,non,,,corrected,\n" in text
    archive = (path.parent / "donnees-archivees.csv").read_text(encoding="utf-8")
    assert ",D3,Devis,oui,Quantitatif,,corrected" in archive


def test_value_confirmed_under_the_new_definition(tmp_path: Path) -> None:
    demo = _changed(tmp_path)
    ref = demo.ids()["loneliness"]
    kwargs: dict[str, Any] = {"now": demo.clock, "tool_version": TOOL_VERSION}
    try:
        confirmed = validation.confirm_value(demo.folder, ref, "D2", note="même sens", **kwargs)
        study = prefill.extraction_state(demo.folder).studies[0]
        followed = impact.impact_state(demo.folder)
        with pytest.raises(validation.NothingToConfirmError):  # no longer to review
            validation.confirm_value(demo.folder, ref, "D2", **kwargs)
        with pytest.raises(validation.NothingToConfirmError):  # the AI's value
            validation.confirm_value(demo.folder, ref, "D1", **kwargs)
    finally:
        demo.folder.close()
    assert confirmed.status is ValueStatus.VALIDATED
    assert confirmed.value == 24
    assert confirmed.note == "même sens"
    assert (study.due, study.to_review) == (("D4",), ())
    assert followed is not None
    assert [c.remaining for c in followed.changes] == [(ref,), (), ()]


def test_no_impact_for_the_first_version(tmp_path: Path) -> None:
    demo = _with_grid(tmp_path)
    try:
        assert impact.impact_state(demo.folder) is None
    finally:
        demo.folder.close()
