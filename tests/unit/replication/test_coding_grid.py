"""Tranche 3.9 on the fictitious review: the coding grid of the reference standard
(D-112), the references of the standard completed by Crossref (stepwise), and the
measures of the multiple choice and number fields. Counts by hand in
tests/fixtures/replication/README.md (section « Tranche 3.9 »)."""

from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest

from replication_support import Crossref, Finder, copy_review, factory
from revue_portee.domain.grid import FieldType
from revue_portee.domain.project import ReplicationMode
from revue_portee.extraction import grid as grid_uc
from revue_portee.protocol.ai_assist import CostPreview
from revue_portee.replication import bench, report
from revue_portee.replication.inputs import read_inputs, read_standard
from revue_portee.storage.project_folder import ProjectFolder, open_project_folder
from revue_portee.storage.repositories import ai as ai_repo
from support import TOOL_VERSION, make_clock

STEPWISE = ReplicationMode.STEPWISE

CODING_GRID = """\
# Coding grid of the fictitious review (D-112): the grid of the protocol, D2 defined
# more precisely, with two fields whose categories the authors publish (D4, D5).
id: fictive-marche-anxiete-codage
version: "1"
date: 2026-10-11
source: Grille de codage d'une revue fictive (jeu de test, tranche 3.9).
fields:
  - type: single_choice
    label: {fr: Devis}
    definition: {fr: Devis de l'étude.}
    choices: {fr: [Essai randomisé, Quasi expérimental, Qualitatif]}
  - type: single_choice
    label: {fr: Milieu}
    definition: {fr: Milieu principal où le programme a lieu (Tableau 1).}
    choices: {fr: [Communauté, Résidence, Hôpital]}
  - type: boolean
    label: {fr: Suivi après le programme}
    definition: {fr: Les participants sont revus après la fin du programme.}
  - type: multiple_choice
    label: {fr: Activités}
    definition: {fr: Activités du programme (Tableau 2).}
    choices: {fr: [Marche, Danse, Natation]}
  - type: number
    label: {fr: Participants}
    definition: {fr: Nombre de participants (Tableau 1).}
"""
# Published values of D4 and D5 (S3 has no text: not compared).
CODED_VALUES = """\
S1,D4,Marche
S1,D5,40
S2,D4,Marche | Danse
S2,D5,25
S3,D4,Marche
S3,D5,18
S4,D4,Marche
S4,D5,12
S5,D4,Natation
S5,D5,
S6,D4,
S6,D5,30
"""


def _run(review: Path, *, go_on: bool) -> bench.BenchOutcome:
    def answer(_step: str, _preview: CostPreview) -> bool:
        return True

    return bench.run_bench(
        read_inputs(review),
        bench.BenchSettings(mode=STEPWISE, ceiling=Decimal(5), go_on_without_texts=go_on),
        standard=read_standard(review), factory=factory(), finder=Finder, crossref=Crossref,
        confirm=answer, now=make_clock(), tool_version=TOOL_VERSION, wait=lambda _s: None,
    )  # fmt: skip


@pytest.fixture(scope="module")
def coded(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The fictitious review with a coding grid, replayed stepwise (stopped for S3,
    then resumed), then run once more."""
    review = copy_review(tmp_path_factory.mktemp("coded"))
    (review / "norme" / "grille-codage.yaml").write_text(CODING_GRID, encoding="utf-8")
    values = review / "norme" / "extraction-publiee.csv"
    values.write_bytes(values.read_bytes() + CODED_VALUES.encode("utf-8"))
    assert _run(review, go_on=False).stopped is bench.Stop.TEXTS
    assert _run(review, go_on=True).stopped is bench.Stop.NONE
    assert _run(review, go_on=True).stopped is bench.Stop.NONE  # nothing left to do
    return review


def _open(review: Path) -> ProjectFolder:
    return open_project_folder(bench.project_path(review, STEPWISE), now=make_clock(),
                               tool_version=TOOL_VERSION, record_opening=False)  # fmt: skip


def test_the_standard_reads_the_coding_grid(coded: Path) -> None:
    standard = read_standard(coded)
    assert standard.coding_grid is not None
    assert len(standard.coding_grid.fields) == 5
    assert len(standard.coding_grid_sha256) == 64
    plain = copy_review(coded.parent / "plain", texts=False)
    assert read_standard(plain).coding_grid is None
    assert read_standard(plain).coding_grid_sha256 == ""


def test_the_coding_grid_is_in_force_before_the_extraction(coded: Path) -> None:
    folder = _open(coded)
    try:
        state = grid_uc.grid_state(folder)
        with folder.engine.connect() as connection:
            calls = Counter(c.task for c in ai_repo.list_calls(connection))
    finally:
        folder.close()
    # Version 1: the transcribed grid; version 2: the coding grid, once (third run).
    assert [v.number for v in state.versions] == [1, 2]
    active = state.active
    assert active is not None
    assert [f.code for f in active.fields] == ["D1", "D2", "D3", "D4", "D5"]
    assert active.fields[1].definition == "Milieu principal où le programme a lieu (Tableau 1)."
    assert active.fields[3].type is FieldType.MULTIPLE_CHOICE
    assert active.fields[4].type is FieldType.NUMBER
    assert "D-112" in active.rationale
    # Extracted once, with the coding grid: one call per study with a text.
    assert calls["extract_fields"] == 5


def test_the_references_of_the_standard_are_completed_by_crossref(coded: Path) -> None:
    measures = report.measure_review(coded, read_inputs(coded).sheet, read_standard(coded),
                                     now=make_clock(), tool_version=TOOL_VERSION)  # fmt: skip
    (stepwise,) = measures
    # S5 completed (authors, year, journal); S6 has no DOI: one bare reference.
    assert stepwise.bare_standard == 1


def test_multiple_choice_and_number_fields_are_measured(coded: Path) -> None:
    (m,) = report.measure_review(coded, read_inputs(coded).sheet, read_standard(coded),
                                 now=make_clock(), tool_version=TOOL_VERSION)  # fmt: skip
    exact = {a.field: a for a in m.agreement}
    assert (exact["D4"].compared, exact["D4"].agreed) == (5, 1)
    assert (exact["D1"].agreed, exact["D2"].agreed, exact["D3"].agreed) == (4, 4, 4)
    (d4,) = m.multiple
    assert [(c.choice, c.agreed) for c in d4.choices] == [
        ("Marche", 2), ("Danse", 4), ("Natation", 5),
    ]  # fmt: skip
    assert d4.jaccard == pytest.approx(2 / 3)
    assert d4.jaccard_n == 3
    (d5,) = m.numeric
    assert (d5.field, d5.compared, d5.agreed) == ("D5", 5, 3)
    assert (d5.not_reported_published, d5.not_reported_tool) == (1, 2)


def test_report_shows_the_new_measures(coded: Path) -> None:
    standard = read_standard(coded)
    measures = report.measure_review(coded, read_inputs(coded).sheet, standard,
                                     now=make_clock(), tool_version=TOOL_VERSION)  # fmt: skip
    text = report.report_markdown(
        read_inputs(coded).sheet, standard, measures, generated_at=make_clock()(),
        tool_version=TOOL_VERSION,
    )  # fmt: skip
    assert f"SHA-256 de grille-codage.yaml : {standard.coding_grid_sha256[:16]}…" in text
    assert "- Références de la norme sans auteurs ni résumé, après Crossref : 1" in text
    assert "**D4** (choix multiple)" in text
    assert "études rapportées des deux côtés : 0,67" in text
    assert "| Marche | 5 | 2/5 (40,0%)" in text
    assert "| D5 | 5 | 3/5 (60,0%)" in text
    assert "elle reprend ces valeurs telles quelles" in text
    assert "erreur" not in text.lower()
