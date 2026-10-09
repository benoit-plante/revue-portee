"""Use cases of the versioned extraction grid (tranche 3.1): draft, fields, starting
grid, activation, history and diff, journal; versions in force never change."""

import sqlite3
from pathlib import Path

import pytest

from revue_portee.domain.criteria import MissingRationaleError, VersionStatus
from revue_portee.domain.grid import FieldType
from revue_portee.domain.journal import EntryType
from revue_portee.extraction import grid
from revue_portee.protocol import notes
from revue_portee.protocol.document import protocol_document
from revue_portee.reporting.document import Document, Heading, Paragraph, Table
from support import TOOL_VERSION, make_clock, new_project, raw_sqlite


def test_grid_versions(tmp_path: Path) -> None:
    clock = make_clock()
    folder = new_project(tmp_path, clock)
    try:
        assert grid.grid_state(folder).active is None
        template = grid.add_template(folder, now=clock, tool_version=TOOL_VERSION)
        assert [f.code for f in template][:2] == ["D1", "D2"]
        assert template[0].label == "Pays"  # the project is in French
        age = grid.add_field(
            folder, label="  Âge   moyen ", type=FieldType.NUMBER, definition=" En années. ",
            examples=["42,5", " "], now=clock, tool_version=TOOL_VERSION,
        )  # fmt: skip
        assert (age.code, age.label, age.definition, age.examples) == (
            "D12",
            "Âge moyen",
            "En années.",
            ("42,5",),
        )
        grid.remove_field(folder, "D11", now=clock, tool_version=TOOL_VERSION)
        v1 = grid.activate_draft(folder, rationale="", now=clock, tool_version=TOOL_VERSION)
        assert (v1.number, len(v1.fields)) == (1, 11)
        # nothing changed: no draft is started
        same = grid.update_field(
            folder, "D12", label="Âge moyen", type=FieldType.NUMBER, definition="En années.",
            examples=["42,5"], now=clock, tool_version=TOOL_VERSION,
        )  # fmt: skip
        assert same == age
        assert grid.grid_state(folder).draft is None
        grid.update_field(
            folder, "D3", label="Type de source", type=FieldType.MULTIPLE_CHOICE,
            choices=["Étude", "Revue", "Étude"], now=clock, tool_version=TOOL_VERSION,
        )  # fmt: skip
        with pytest.raises(MissingRationaleError):
            grid.activate_draft(folder, rationale="", now=clock, tool_version=TOOL_VERSION)
        grid.discard_draft(folder, now=clock, tool_version=TOOL_VERSION)
        with pytest.raises(grid.NoDraftError):
            grid.discard_draft(folder, now=clock, tool_version=TOOL_VERSION)
        with pytest.raises(grid.NoDraftError):
            grid.activate_draft(folder, rationale="x", now=clock, tool_version=TOOL_VERSION)
        # the discarded field codes are never given again
        sex = grid.add_field(
            folder, label="Sexe", type=FieldType.TEXT, now=clock, tool_version=TOOL_VERSION
        )
        assert sex.code == "D13"
        v2 = grid.activate_draft(
            folder, rationale="Sexe des participants.", now=clock, tool_version=TOOL_VERSION
        )
        state = grid.grid_state(folder)
        delta = grid.diff(folder, 1, 2)
        with pytest.raises(grid.UnknownVersionError):
            grid.version(folder, 9)
        with pytest.raises(grid.UnknownFieldError):
            grid.remove_field(folder, "D99", now=clock, tool_version=TOOL_VERSION)
        with pytest.raises(grid.UnknownFieldError):
            grid.update_field(folder, "D99", label="x", type=FieldType.TEXT, now=clock,
                              tool_version=TOOL_VERSION)  # fmt: skip
        entries = notes.journal_entries(folder)
    finally:
        folder.close()
    assert state.active == v2
    assert [v.status for v in state.versions] == [VersionStatus.SUPERSEDED, VersionStatus.ACTIVE]
    assert [f.code for f in delta.added] == ["D13"]
    kinds = [e.entry_type for e in entries if e.entry_type.startswith("grid.")]
    assert kinds.count(EntryType.GRID_VERSION_CREATED) == 2
    assert EntryType.GRID_DRAFT_DISCARDED in kinds
    last = next(e for e in reversed(entries) if e.entry_type == EntryType.GRID_VERSION_CREATED)
    assert last.payload["changes"] == {"added": ["D13"], "removed": [], "modified": {}}
    with (
        pytest.raises(sqlite3.IntegrityError, match="immutable"),
        raw_sqlite(folder.path / "revue.sqlite") as connection,
    ):
        connection.execute("UPDATE grid_field SET label = 'x' WHERE code = 'D1'")


def test_grid_in_the_protocol(tmp_path: Path) -> None:
    clock = make_clock()
    folder = new_project(tmp_path, clock)
    try:
        before = protocol_document(folder, language="fr", now=clock, tool_version=TOOL_VERSION)
        grid.add_template(folder, now=clock, tool_version=TOOL_VERSION)
        draft = protocol_document(folder, language="fr", now=clock, tool_version=TOOL_VERSION)
        grid.activate_draft(folder, rationale="", now=clock, tool_version=TOOL_VERSION)
        english = protocol_document(folder, language="en", now=clock, tool_version=TOOL_VERSION)
    finally:
        folder.close()

    def appendix(document: Document) -> tuple[Paragraph, Table | None]:
        blocks = list(document.blocks)
        start = next(
            i
            for i, b in enumerate(blocks)
            if isinstance(b, Heading) and b.text.startswith(("Annexe III", "Appendix III"))
        )
        intro, table = blocks[start + 1], blocks[start + 2]
        assert isinstance(intro, Paragraph)
        return intro, table if isinstance(table, Table) else None

    assert appendix(before)[0].placeholder
    intro, table = appendix(draft)
    assert intro.text.startswith("Brouillon de la version 1 de la grille")
    assert table is not None
    assert table.rows[2][:3] == ("D3", "Type de source", "choix unique")
    assert "[Étude empirique quantitative | " in table.rows[2][3]
    english_intro, _table = appendix(english)
    assert english_intro.text.startswith("Version 1 of the extraction grid")
