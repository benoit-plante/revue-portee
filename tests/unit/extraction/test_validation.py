"""The person's check of the extracted values, the extraction pilot and the data kept
for the synthesis (EF-EXT-04, EF-EXT-05): no value the person did not decide goes into
the synthesis."""

import csv
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from revue_portee.domain.extraction import InvalidValueError, ValueStatus
from revue_portee.domain.fulltext import QuoteCheck
from revue_portee.domain.journal import EntryType
from revue_portee.domain.project import ReviewerKind
from revue_portee.extraction import prefill, validation
from revue_portee.storage.repositories import journal
from support import TOOL_VERSION
from unit.extraction.test_prefill import _with_grid, answer, factory


def _prefilled(tmp_path: Path) -> Any:  # noqa: ANN401 - the demonstration
    demo = _with_grid(tmp_path)
    prefill.run_ai(
        demo.folder, batch_limit=Decimal(1), factory=factory(answer), now=demo.clock,
        tool_version=TOOL_VERSION,
    )  # fmt: skip
    return demo


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_only_values_decided_by_the_person_go_into_the_synthesis(tmp_path: Path) -> None:
    demo = _prefilled(tmp_path)
    ref = demo.ids()["loneliness"]
    folder = demo.folder
    kwargs: dict[str, Any] = {"now": demo.clock, "tool_version": TOOL_VERSION}
    try:
        # the AI proposed three values: none goes into the synthesis yet
        path, written = validation.export_extraction(folder)
        assert written == 0
        rows = _rows(path)
        assert [(r["field"], r["value"], r["status"]) for r in rows] == [
            ("D1", "", ""), ("D2", "", ""), ("D3", "", ""),
        ]  # fmt: skip
        assert all(row.value is None for row in validation.synthesis_rows(folder))

        validated = validation.validate_value(folder, ref, "D2", note="ok", **kwargs)
        corrected = validation.record_value(
            folder, ref, "D3", reported=True, value="Quantitatif",
            quote="living in three residences", page=5, **kwargs,
        )  # fmt: skip
        rejected = validation.reject_value(folder, ref, "D1", **kwargs)
        state = prefill.extraction_state(folder)
        assert state.waiting == []  # checked by the person, never pre-filled again

        path, written = validation.export_extraction(folder)
        rows = _rows(path)
    finally:
        folder.close()
    assert validated.status is ValueStatus.VALIDATED
    assert validated.reviewer_kind is ReviewerKind.HUMAN
    assert validated.value == 24
    assert validated.ai_call_id is None
    assert validated.note == "ok"
    assert corrected.status is ValueStatus.CORRECTED
    assert (corrected.page, corrected.quote_check) == (2, QuoteCheck.OTHER_PAGE)
    assert rejected.status is ValueStatus.REJECTED
    assert not rejected.reported
    assert validated.supersedes_id
    assert corrected.supersedes_id
    assert rejected.supersedes_id
    # D1 rejected: no value; D2 validated: 24; D3 corrected: « Quantitatif »
    assert written == 2
    assert [(r["field"], r["reported"], r["value"], r["page"], r["status"]) for r in rows] == [
        ("D1", "", "", "", ""),
        ("D2", "oui", "24", "2", "validated"),
        ("D3", "oui", "Quantitatif", "2", "corrected"),
    ]
    assert "Qualitatif" not in path.read_text(encoding="utf-8")  # the AI's value, corrected


def test_each_decision_is_journaled(tmp_path: Path) -> None:
    demo = _prefilled(tmp_path)
    ref = demo.ids()["loneliness"]
    try:
        validation.validate_value(demo.folder, ref, "D2", now=demo.clock, tool_version=TOOL_VERSION)
        validation.record_value(
            demo.folder, ref, "D1", reported=True, value="Canada", now=demo.clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
        with demo.folder.engine.connect() as connection:
            entries = [
                e
                for e in journal.list_entries(connection)
                if e.entry_type == EntryType.EXTRACTION_VALUE_DECIDED
            ]
    finally:
        demo.folder.close()
    assert [e.summary_fr for e in entries] == [
        "Extraction : valeur de D2 validée",
        "Extraction : valeur de D1 corrigée",
    ]
    assert entries[1].payload["value"] == "Canada"


def test_refused_decisions(tmp_path: Path) -> None:
    demo = _with_grid(tmp_path)
    ref = demo.ids()["loneliness"]
    kwargs: dict[str, Any] = {"now": demo.clock, "tool_version": TOOL_VERSION}
    try:
        with pytest.raises(validation.NoAIValueError):
            validation.validate_value(demo.folder, ref, "D2", **kwargs)
        with pytest.raises(validation.NoAIValueError):
            validation.reject_value(demo.folder, ref, "D2", **kwargs)
        with pytest.raises(validation.NotAStudyError):
            validation.record_value(demo.folder, ref, "D9", reported=False, **kwargs)
        with pytest.raises(validation.NotAStudyError):
            validation.record_value(demo.folder, "UNKNOWN", "D1", reported=False, **kwargs)
        with pytest.raises(InvalidValueError):
            validation.record_value(demo.folder, ref, "D2", reported=True, value="many", **kwargs)
        extracted = validation.record_value(
            demo.folder, ref, "D2", reported=True, value="12", quote="absent words", **kwargs
        )
        not_reported = validation.record_value(
            demo.folder, ref, "D1", reported=False, value="ignored", quote="x", **kwargs
        )
    finally:
        demo.folder.close()
    # no AI value: the person's own extraction; a quote not found is kept, without page
    assert extracted.status is ValueStatus.EXTRACTED
    assert extracted.value == 12
    assert (extracted.page, extracted.quote_check) == (None, QuoteCheck.NOT_FOUND)
    assert not_reported.value is None
    assert not_reported.quote == ""


def test_pilot_blind_then_agreement_counted_by_hand(tmp_path: Path) -> None:
    demo = _prefilled(tmp_path)
    ref = demo.ids()["loneliness"]
    folder = demo.folder
    kwargs: dict[str, Any] = {"now": demo.clock, "tool_version": TOOL_VERSION}
    try:
        assert validation.pilot_state(folder) is None
        pilot = validation.start_pilot(folder, seed=7, **kwargs)
        again = validation.start_pilot(folder, size=3, seed=8, **kwargs)
        assert validation.blind(folder, ref)
        with pytest.raises(validation.NoAIValueError):  # its values are hidden
            validation.validate_value(folder, ref, "D1", **kwargs)
        validation.record_value(folder, ref, "D1", reported=False, **kwargs)
        validation.record_value(folder, ref, "D2", reported=True, value=24, **kwargs)
        partial = validation.pilot_state(folder)
        third = validation.record_value(
            folder, ref, "D3", reported=True, value="Quantitatif", **kwargs
        )
        state = validation.pilot_state(folder)
        with folder.engine.connect() as connection:
            entries = [
                e
                for e in journal.list_entries(connection)
                if e.entry_type == EntryType.EXTRACTION_PILOT_STARTED
            ]
    finally:
        folder.close()
    # one study only: every pilot draws it
    assert pilot.reference_ids == (ref,)
    assert (pilot.number, again.number) == (1, 2)
    assert entries[0].summary_fr == ("Pilote d'extraction 1 : études tirées : 1 sur 1 (graine 7)")
    assert partial is not None
    assert partial.visible_ai(ref) == {}
    assert partial.done == 0
    # in the pilot, the person's values are extractions, not corrections
    assert third.status is ValueStatus.EXTRACTED
    assert state is not None
    assert state.pilot.number == 2
    assert state.done == 1
    assert set(state.visible_ai(ref)) == {"D1", "D2", "D3"}
    # D1 not reported by both, D2 24 by both, D3 « Quantitatif » against « Qualitatif »
    assert [(a.code, a.compared, a.agreed) for a in state.agreement] == [
        ("D1", 1, 1), ("D2", 1, 1), ("D3", 1, 0),
    ]  # fmt: skip
    assert state.agreement[2].share == 0.0
    assert validation.FieldAgreement("D9", "x").share is None


def test_pilot_needs_a_grid_and_studies(tmp_path: Path) -> None:
    from demo import build

    demo = build(tmp_path)
    try:
        with pytest.raises(prefill.NoGridError):
            validation.start_pilot(demo.folder, now=demo.clock, tool_version=TOOL_VERSION)
        assert validation.synthesis_rows(demo.folder) == []
    finally:
        demo.folder.close()
