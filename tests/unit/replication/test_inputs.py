"""The folder of a review to replay: freeze, inputs and reference standard."""

from pathlib import Path

import pytest

from replication_support import copy_review
from revue_portee.domain.search import Database
from revue_portee.replication.inputs import (
    ReplicationInputError,
    read_inputs,
    read_standard,
)


def test_reads_the_fictitious_review(tmp_path: Path) -> None:
    review = copy_review(tmp_path)
    inputs = read_inputs(review)
    assert inputs.sheet.id == "Fictive_2026_marche_anxiete"
    assert inputs.sheet.search_end == 2025
    assert [c.code for c in inputs.criteria.criteria] == ["P1", "C1", "O1"]
    assert [f.type for f in inputs.grid.fields] == ["single_choice", "single_choice", "boolean"]
    assert [p.name for p in inputs.ris_files] == ["export-base-fictive.ris"]
    assert inputs.search is None
    assert len(inputs.texts) == 9


def test_reads_the_reference_standard(tmp_path: Path) -> None:
    standard = read_standard(copy_review(tmp_path, texts=False))
    assert [s.study_id for s in standard.studies] == ["S1", "S2", "S3", "S4", "S5", "S6"]
    assert [s.in_search for s in standard.studies] == [True] * 5 + [False]
    assert standard.studies[0].doi == "10.5555/FICT.0001"
    assert len(standard.values) == 18
    assert standard.flow.identified == 30
    assert standard.flow.included_studies == 6
    assert [d.field for d in standard.distributions] == ["D1", "Milieu"]
    assert standard.distributions[0].total == 6
    assert standard.distributions[1].total == 6


def test_a_changed_input_is_refused(tmp_path: Path) -> None:
    review = copy_review(tmp_path, texts=False)
    criteria = review / "criteres.yaml"
    # The hashes only count: the same content written again (a newer date) is accepted.
    criteria.write_bytes(criteria.read_bytes())
    read_inputs(review)
    criteria.write_text(criteria.read_text(encoding="utf-8") + "\n# reformulé\n", "utf-8")
    with pytest.raises(ReplicationInputError, match=r"criteres.yaml a changé depuis le gel"):
        read_inputs(review)


def test_an_input_not_frozen_is_refused(tmp_path: Path) -> None:
    review = copy_review(tmp_path, texts=False)
    (review / "recherche" / "autre-base.ris").write_text("TY  - JOUR\nTI  - X\nER  - \n", "utf-8")
    with pytest.raises(ReplicationInputError, match=r"recherche/autre-base.ris n.est pas gelé"):
        read_inputs(review)
    (review / "GEL.sha256").unlink()
    with pytest.raises(ReplicationInputError, match=r"GEL.sha256 manque"):
        read_inputs(review)


def test_folder_without_search_or_sheet(tmp_path: Path) -> None:
    with pytest.raises(ReplicationInputError, match="Dossier introuvable"):
        read_inputs(tmp_path / "absent")
    review = copy_review(tmp_path, texts=False)
    for path in (review / "recherche").iterdir():
        path.unlink()
    with pytest.raises(ReplicationInputError, match="ni export RIS ni stratégie"):
        read_inputs(review)


def test_invalid_sheet_and_grid(tmp_path: Path) -> None:
    review = copy_review(tmp_path, texts=False)
    sheet = review / "fiche.yaml"
    sheet.write_text("id: deux mots\n", "utf-8")
    with pytest.raises(ReplicationInputError, match="id fait de lettres"):
        read_inputs(review)
    sheet.write_text("- une liste\n", "utf-8")
    with pytest.raises(ReplicationInputError, match="illisible"):
        read_inputs(review)
    sheet.write_text("id: [non fermé\n", "utf-8")
    with pytest.raises(ReplicationInputError, match="illisible"):
        read_inputs(review)


def _refreeze(review: Path) -> None:
    import hashlib

    names = ["criteres.yaml", "grille.yaml"] + [
        p.relative_to(review).as_posix() for p in sorted((review / "recherche").iterdir())
    ]
    (review / "GEL.sha256").write_text(
        "".join(f"{hashlib.sha256((review / n).read_bytes()).hexdigest()}  {n}\n" for n in names),
        "utf-8",
    )


def test_grid_in_another_format_is_refused(tmp_path: Path) -> None:
    review = copy_review(tmp_path, texts=False)
    (review / "grille.yaml").write_text("fields: []\n", "utf-8")
    _refreeze(review)
    with pytest.raises(ReplicationInputError, match="format des grilles de départ"):
        read_inputs(review)


def test_search_strategy(tmp_path: Path) -> None:
    review = copy_review(tmp_path, texts=False)
    (review / "recherche" / "strategie.yaml").write_text(
        "bases: [pubmed]\n"
        "limites: {annee_min: 2010, annee_max: 2025}\n"
        "blocs:\n"
        "  - libelle: Marche\n"
        "    element: concept\n"
        "    termes: ['walking', 'mesh: Walking']\n"
        "  - libelle: Animaux\n"
        "    exclure: oui\n"
        "    termes: ['mice']\n",
        "utf-8",
    )
    _refreeze(review)
    plan = read_inputs(review).search
    assert plan is not None
    assert plan.databases == (Database.PUBMED,)
    assert plan.strategy.limits.year_to == 2025
    assert [b.code for b in plan.strategy.blocks] == ["B1", "B2"]
    assert plan.strategy.excluded[0].label == "Animaux"
    (review / "recherche" / "strategie.yaml").write_text("blocs: []\n", "utf-8")
    _refreeze(review)
    with pytest.raises(ReplicationInputError, match="aucune base"):
        read_inputs(review)
    (review / "recherche" / "strategie.yaml").write_text(
        "bases: [pubmed]\nblocs:\n  - libelle: X\n    termes: ['a AND b']\n", "utf-8"
    )
    _refreeze(review)
    with pytest.raises(ReplicationInputError, match="invalide"):
        read_inputs(review)


def test_invalid_reference_standard(tmp_path: Path) -> None:
    review = copy_review(tmp_path, texts=False)
    included = review / "norme" / "incluses.csv"
    text = included.read_text(encoding="utf-8")
    included.write_text(text.replace("hors_recherche", "peut-être"), "utf-8")
    with pytest.raises(ReplicationInputError, match=r"ligne 7.: retrievable"):
        read_standard(review)
    included.write_text("study_id,retrievable\nS1,oui\nS1,oui\n", "utf-8")
    with pytest.raises(ReplicationInputError, match="propre study_id"):
        read_standard(review)
    included.write_text("doi\n10.1/x\n", "utf-8")
    with pytest.raises(ReplicationInputError, match="colonnes retrievable, study_id"):
        read_standard(review)
    included.write_text(text, "utf-8")
    (review / "norme" / "resultats-publies.yaml").write_text("diagramme: {inconnu: 3}\n", "utf-8")
    with pytest.raises(ReplicationInputError, match="illisible"):
        read_standard(review)
    included.unlink()
    with pytest.raises(ReplicationInputError, match="introuvable"):
        read_standard(review)


def test_standard_without_extraction_nor_results(tmp_path: Path) -> None:
    review = copy_review(tmp_path, texts=False)
    (review / "norme" / "extraction-publiee.csv").unlink()
    (review / "norme" / "resultats-publies.yaml").unlink()
    standard = read_standard(review)
    assert standard.values == ()
    assert standard.distributions == ()
    assert standard.flow.identified is None
