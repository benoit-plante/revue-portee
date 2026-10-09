"""Synthesis tables, evidence map and gaps on the demonstration (tests/fixtures/demo/
README.md, « Extraction et synthèse »): numbers counted by hand; only the values a
person decided count."""

import csv
from decimal import Decimal
from pathlib import Path
from typing import Any

import openpyxl
import pytest

from demo import build_extracted
from revue_portee.domain.journal import EntryType
from revue_portee.domain.references import Reference
from revue_portee.extraction import prefill
from revue_portee.reporting.synthesis import GapKind, gaps
from revue_portee.storage.repositories import journal
from revue_portee.synthesis import maps
from support import TOOL_VERSION
from unit.extraction.test_prefill import _with_grid, answer, factory


def test_tables_and_map_counted_by_hand(tmp_path: Path) -> None:
    demo = build_extracted(tmp_path)
    folder = demo.folder
    study = demo.ids()["loneliness"]
    try:
        tables = {t.field.code: t for t in maps.frequencies(folder)}
        crossed, studies = maps.cross(folder, "D1", "D2")
        with pytest.raises(maps.UnknownFieldError):
            maps.cross(folder, "D1", "D9")
    finally:
        folder.close()
    assert [(r.category, r.count) for r in tables["D1"].rows] == [
        ("Qualitatif", 1), ("Quantitatif", 0), ("Mixte", 0),
    ]  # fmt: skip
    assert tables["D1"].share(tables["D1"].rows[0]) == 1.0
    assert [(r.category, r.count) for r in tables["D2"].rows] == [
        ("Domicile", 0), ("Résidence", 1), ("Hôpital", 0),
    ]  # fmt: skip
    assert (tables["D3"].rows, tables["D3"].not_reported) == ((), (study,))
    assert [s.label for s in studies] == [studies[0].label]
    assert crossed.studies("Qualitatif", "Résidence") == (study,)
    found = gaps(crossed)
    assert [g.kind for g in found].count(GapKind.SPARSE) == 1
    assert [g.kind for g in found].count(GapKind.EMPTY) == 8
    assert (len(crossed.placed), len(crossed.unplaced)) == (1, 0)


def test_values_of_the_ai_not_checked_never_count(tmp_path: Path) -> None:
    demo = _with_grid(tmp_path)
    try:
        prefill.run_ai(
            demo.folder, batch_limit=Decimal(1), factory=factory(answer), now=demo.clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
        tables = maps.frequencies(demo.folder)
    finally:
        demo.folder.close()
    # the AI proposed a value for each field; no one checked them
    assert all(not any(r.count for r in t.rows) for t in tables)
    assert all(len(t.not_extracted) == 1 for t in tables)


def test_gap_commented_and_exported(tmp_path: Path) -> None:
    demo = build_extracted(tmp_path)
    folder = demo.folder
    kwargs: dict[str, Any] = {"now": demo.clock, "tool_version": TOOL_VERSION}
    try:
        maps.comment_gap(folder, "D1", "D2", "Mixte", "Hôpital", "Aucune étude mixte", **kwargs)
        maps.comment_gap(folder, "D1", "D2", "Mixte", "Domicile", "à revoir", **kwargs)
        maps.comment_gap(folder, "D1", "D2", "Mixte", "Domicile", "", **kwargs)  # withdrawn
        with pytest.raises(maps.UnknownFieldError):
            maps.comment_gap(folder, "D1", "D2", "Autre", "Hôpital", "x", **kwargs)
        in_force = maps.comments(folder, "D1", "D2")
        other_map = maps.comments(folder, "D2", "D1")
        with folder.engine.connect() as connection:
            entries = [
                e
                for e in journal.list_entries(connection)
                if e.entry_type == EntryType.SYNTHESIS_GAP_COMMENTED
            ]
        tables = maps.export_tables(folder, language="fr", crosses=[("D1", "D2")], now=demo.clock)
        drawn = maps.export_map(
            folder, "D1", "D2", language="en", now=demo.clock, tool_version=TOOL_VERSION
        )
    finally:
        folder.close()
    assert in_force == {("Mixte", "Hôpital"): "Aucune étude mixte"}
    assert other_map == {}
    assert len(entries) == 3
    assert entries[0].summary_fr == "Carte D1 par D2 : lacune commentée"
    names = [p.name for p in tables]
    assert names == [
        "frequences-D1-fr.csv", "frequences-D2-fr.csv", "frequences-D3-fr.csv",
        "croise-D1-D2-fr.csv", "tableaux-fr.md", "tableaux-fr.xlsx",
    ]  # fmt: skip
    with tables[0].open(encoding="utf-8", newline="") as stream:
        assert list(csv.reader(stream))[1] == ["Qualitatif", "1", "100,0 %"]
    markdown = tables[4].read_text(encoding="utf-8")
    assert markdown.startswith("# Tableaux de synthèse — ")
    assert "| Résidence | 1 | 100,0 % |" in markdown
    assert openpyxl.load_workbook(tables[5]).sheetnames == ["D1", "D2", "D3", "D1 x D2"]
    assert [p.name for p in drawn] == ["carte-D1-D2-en.svg", "carte-D1-D2-en.html",
                                       "croise-D1-D2-en.csv"]  # fmt: skip
    page = drawn[1].read_text(encoding="utf-8")
    assert "Aucune étude mixte" in page
    assert "<td>no study (0)</td>" in page
    assert drawn[0].read_text(encoding="utf-8").count("<circle ") == 1


def test_study_label() -> None:
    def ref(**kwargs: object) -> Reference:
        return Reference.model_validate(
            {"id": "R", "created_at": "2026-10-09T00:00:00+00:00"} | kwargs
        )

    assert maps.study_label(ref(authors=("Roy, A.", "Côté, B."), year=2019)) == "Roy et al. 2019"
    assert maps.study_label(ref(authors=("Roy, A.",))) == "Roy s. d."
    assert maps.study_label(ref(title="Loneliness")) == "Loneliness"
    assert maps.study_label(ref()) == "R"
