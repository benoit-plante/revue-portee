"""Frequency tables, cross tables, evidence maps and gaps (EF-SYN-01 to EF-SYN-03),
counted by hand on five studies built for the purpose."""

import csv
import io
from datetime import UTC, datetime

import openpyxl

from revue_portee.domain.grid import FieldType, GridField
from revue_portee.reporting import synthesis_export as export
from revue_portee.reporting.synthesis import (
    CategoryLabels,
    GapKind,
    StudyData,
    categories,
    cross_table,
    frequency_table,
    gaps,
)

NOW = datetime(2026, 10, 9, 12, tzinfo=UTC)
DESIGN = GridField(
    code="D1", label="Devis", type=FieldType.SINGLE_CHOICE,
    choices=("Qualitatif", "Quantitatif", "Mixte"),
)  # fmt: skip
SETTING = GridField(
    code="D2", label="Milieu", type=FieldType.MULTIPLE_CHOICE,
    choices=("Domicile", "Résidence", "Hôpital"),
)  # fmt: skip
COUNTRY = GridField(code="D3", label="Pays", type=FieldType.TEXT)
CARERS = GridField(code="D4", label="Proches aidants", type=FieldType.BOOLEAN)
DATE = GridField(code="D5", label="Collecte", type=FieldType.DATE)
SIZE = GridField(code="D6", label="Taille", type=FieldType.NUMBER)

STUDIES = [
    StudyData(id="S1", label="Roy et al. 2019", values={
        "D1": "Qualitatif", "D2": ["Domicile", "Résidence"], "D3": "Canada", "D4": True,
        "D5": "2019-05", "D6": 24,
    }),
    StudyData(id="S2", label="Martin 2021", values={
        "D1": "Quantitatif", "D2": ["Résidence"], "D3": "France", "D4": False, "D5": "2021",
        "D6": 120.0,
    }),
    StudyData(id="S3", label="Tremblay 2019", values={
        "D1": "Qualitatif", "D2": ["Domicile"], "D3": "Canada ", "D5": "2019", "D6": 8,
    }, not_reported=frozenset({"D4"})),
    StudyData(id="S4", label="Gagnon 2020", values={"D2": ["Résidence"]},
              not_reported=frozenset({"D1"})),
    StudyData(id="S5", label="Côté 2022"),  # nothing decided yet
]  # fmt: skip


def _counts(field: GridField) -> list[tuple[str, int]]:
    return [(r.category, r.count) for r in frequency_table(field, STUDIES).rows]


def test_frequencies_counted_by_hand() -> None:
    design = frequency_table(DESIGN, STUDIES)
    assert [(r.category, r.studies) for r in design.rows] == [
        ("Qualitatif", ("S1", "S3")), ("Quantitatif", ("S2",)), ("Mixte", ()),
    ]  # fmt: skip
    assert (design.not_reported, design.not_extracted, design.total) == (("S4",), ("S5",), 5)
    assert design.share(design.rows[0]) == 0.4
    # a study counts once in each of its choices
    assert _counts(SETTING) == [("Domicile", 2), ("Résidence", 3), ("Hôpital", 0)]
    assert _counts(COUNTRY) == [("Canada", 2), ("France", 1)]
    assert _counts(CARERS) == [("oui", 1), ("non", 1)]
    assert frequency_table(CARERS, STUDIES).not_reported == ("S3",)
    assert _counts(DATE) == [("2019", 2), ("2021", 1)]
    assert _counts(SIZE) == [("8", 1), ("24", 1), ("120", 1)]  # numeric order
    assert frequency_table(DESIGN, []).share(design.rows[0]) is None


def test_categories() -> None:
    english = CategoryLabels(yes="yes", no="no")
    assert categories(CARERS, STUDIES[0], english) == ("yes",)
    assert categories(CARERS, STUDIES[2]) == ()  # not reported
    assert categories(CARERS, STUDIES[4]) is None  # not extracted
    odd = StudyData(id="S9", label="", values={"D1": "Autre", "D2": "Domicile"})
    assert categories(SETTING, odd) == ("Domicile",)
    # a value outside the choices (a former choice) is kept, after them
    table = frequency_table(DESIGN, [*STUDIES, odd])
    assert [r.category for r in table.rows][-1] == "Autre"


def test_cross_table_and_gaps_counted_by_hand() -> None:
    table = cross_table(DESIGN, SETTING, STUDIES)
    assert table.rows == ("Qualitatif", "Quantitatif", "Mixte")
    assert table.columns == ("Domicile", "Résidence", "Hôpital")
    assert (table.placed, table.unplaced) == (("S1", "S2", "S3"), ("S4", "S5"))
    assert table.studies("Qualitatif", "Domicile") == ("S1", "S3")
    assert table.count("Qualitatif", "Résidence") == 1
    assert table.count("Quantitatif", "Résidence") == 1
    assert table.count("Mixte", "Hôpital") == 0
    assert table.largest == 2
    found = gaps(table)
    assert [(g.row, g.column) for g in found if g.kind is GapKind.SPARSE] == [
        ("Qualitatif", "Résidence"), ("Quantitatif", "Résidence"),
    ]  # fmt: skip
    assert sum(g.kind is GapKind.EMPTY for g in found) == 6  # 9 cells, 3 occupied
    assert [g.kind for g in gaps(table, sparse_max=0)].count(GapKind.SPARSE) == 0
    assert len(gaps(table, sparse_max=2)) == 9


def _rows(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text)))


def test_table_exports() -> None:
    design = frequency_table(DESIGN, STUDIES)
    rows = _rows(export.frequency_csv(design, "fr"))
    assert rows[0] == ["Catégorie", "Études", "Part des études incluses"]
    assert rows[1] == ["Qualitatif", "2", "40,0 %"]
    assert rows[-3:] == [["Non rapporté", "1", ""], ["Pas encore extrait", "1", ""],
                         ["Études incluses", "5", ""]]  # fmt: skip
    english = _rows(export.frequency_csv(design, "en"))
    assert english[0] == ["Category", "Studies", "Share of the included studies"]
    assert english[1] == ["Qualitatif", "2", "40.0%"]
    crossed = cross_table(DESIGN, SETTING, STUDIES)
    grid = _rows(export.cross_csv(crossed, "fr"))
    assert grid[0] == ["Devis \\ Milieu", "Domicile", "Résidence", "Hôpital", "Total"]
    assert grid[1] == ["Qualitatif", "2", "1", "0", "2"]
    assert grid[3] == ["Mixte", "0", "0", "0", "0"]
    assert grid[4] == ["Total", "2", "2", "0", "3"]
    markdown = export.frequency_markdown(design, "fr")
    assert "## D1 — Devis" in markdown
    assert "| Qualitatif | 2 | 40,0 % |" in markdown
    crossed_md = export.cross_markdown(crossed, "fr")
    assert "| Qualitatif | 2 | 1 | 0 | 2 |" in crossed_md
    assert "Études sans valeur sur l'un des deux champs : 2." in crossed_md
    book = openpyxl.load_workbook(
        io.BytesIO(export.tables_xlsx([design], [crossed], language="fr", generated_at=NOW))
    )
    assert book.sheetnames == ["D1", "D1 x D2"]
    sheet = book["D1 x D2"]
    assert sheet["A1"].value == f"Devis {export.TIMES} Milieu"
    assert [c.value for c in sheet[3]] == ["Qualitatif", 2, 1, 0, 2]
    assert book.properties.created == NOW.replace(tzinfo=None)


def test_map_exports() -> None:
    crossed = cross_table(DESIGN, SETTING, STUDIES)
    found = gaps(crossed)
    context = export.MapContext(
        project_title="Démo", language="fr", tool_version="0.0.0-test", generated_at=NOW
    )
    svg = export.map_svg(crossed, found, context)
    assert svg.startswith("<svg ")
    assert svg.count("<circle ") == 3  # three cells hold studies
    assert svg.count('stroke-dasharray="4 3"') == 6  # empty cells
    assert svg.count('stroke="#c0392b"') == 2  # sparse cells
    assert "Lignes : D1 Devis; colonnes : D2 Milieu" in svg
    assert "Études placées : 3; sans valeur sur l'un des deux champs : 2." in svg
    page = export.map_html(
        crossed, found, {s.id: s.label for s in STUDIES},
        {("Mixte", "Hôpital"): "Aucune étude mixte <en milieu hospitalier>"}, context,
    )  # fmt: skip
    assert page.startswith("<!doctype html>")
    assert '<html lang="fr">' in page
    assert (
        "<td>Qualitatif</td><td>Domicile</td><td>2</td><td>Roy et al. 2019; Tremblay 2019</td>"
        in page
    )
    assert "Aucune étude mixte &lt;en milieu hospitalier&gt;" in page
    assert "<td>peu d'études (1)</td>" in page
    english = export.map_svg(
        crossed, found,
        export.MapContext(project_title="Demo", language="en", tool_version="t", generated_at=NOW),
    )  # fmt: skip
    assert "Rows: D1 Devis; columns: D2 Milieu" in english
