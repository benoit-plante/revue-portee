"""Full-text commands: textes-ajouter, texte-introuvable, textes-manquants, textes-libres
(without a contact address it stops cleanly, before any request) and banc-pages."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from demo import broaden_and_reassess, build, create, deduplicate, reconcile, screen
from revue_portee.cli.main import app
from support import make_pdf

runner = CliRunner()
CAREGIVERS = "Family caregivers of older adults living in rural areas: A qualitative study"


def _built(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    demo = build(tmp_path)
    ids = demo.ids()
    demo.folder.close()
    return demo.folder.path, ids


def test_add_declare_and_list(tmp_path: Path) -> None:
    folder, ids = _built(tmp_path)
    files = tmp_path / "pdf"
    files.mkdir()
    (files / "aidants.pdf").write_bytes(make_pdf([CAREGIVERS]))
    (files / "autre.pdf").write_bytes(make_pdf(["Something else"]))
    (files / "casse.pdf").write_bytes(b"%PDF-1.4 broken")
    (files / "notes.txt").write_text("not a PDF", encoding="utf-8")
    added = runner.invoke(app, ["textes-ajouter", str(folder), str(files)])
    assert added.exit_code == 0, added.output
    assert f"Ajouté : aidants.pdf → {ids['caregivers']}" in added.output
    assert "Aucune référence trouvée (l'ajouter avec --reference) : autre.pdf" in added.output
    assert "casse.pdf : Le fichier n'est pas un PDF lisible." in added.output
    assert "Textes intégraux : 3 obtenus sur 3 recherchés" in added.output
    again = runner.invoke(app, ["textes-ajouter", str(folder), str(files / "aidants.pdf")])
    assert "Déjà dans le projet : aidants.pdf" in again.output
    one = runner.invoke(
        app,
        ["textes-ajouter", str(folder), str(files / "autre.pdf"), "--reference", ids["housing"]],
    )
    assert one.exit_code == 0, one.output
    assert "Texte ajouté : autre.pdf" in one.output
    two = runner.invoke(
        app, ["textes-ajouter", str(folder), str(files), "--reference", ids["housing"]]
    )
    assert two.exit_code == 1
    excluded = runner.invoke(
        app,
        ["textes-ajouter", str(folder), str(files / "autre.pdf"), "--reference", ids["gardens"]],
    )
    assert excluded.exit_code == 1
    assert "n'est pas recherchée" in excluded.output
    absent = runner.invoke(app, ["textes-ajouter", str(folder), str(files / "absent.pdf")])
    assert absent.exit_code == 1
    declared = runner.invoke(
        app, ["texte-introuvable", str(folder), ids["loneliness"], "--raison", "x"]
    )
    assert declared.exit_code == 1
    assert "déjà obtenu" in declared.output
    listed = runner.invoke(app, ["textes-manquants", str(folder)])
    assert listed.exit_code == 0, listed.output
    assert "0 référence sans texte intégral, écrite" in listed.output
    assert (folder / "exports" / "textes-manquants.csv").is_file()
    assert runner.invoke(app, ["textes-manquants", str(tmp_path / "absent")]).exit_code == 1


def test_declare_not_retrievable(tmp_path: Path) -> None:
    demo = create(tmp_path)
    deduplicate(demo)
    screen(demo)
    reconcile(demo)
    broaden_and_reassess(demo)
    ids = demo.ids()
    demo.folder.close()
    folder = demo.folder.path
    declared = runner.invoke(
        app, ["texte-introuvable", str(folder), ids["caregivers"], "--raison", "Hors bibliothèque"]
    )
    assert declared.exit_code == 0, declared.output
    assert "introuvables : 1" in declared.output
    listed = runner.invoke(app, ["textes-manquants", str(folder)])
    assert "3 références sans texte intégral, écrites" in listed.output


def test_open_access_needs_the_contact_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    demo = create(tmp_path)
    deduplicate(demo)
    screen(demo)
    reconcile(demo)
    broaden_and_reassess(demo)
    demo.folder.close()
    monkeypatch.delenv("CONTACT_EMAIL", raising=False)
    result = runner.invoke(app, ["textes-libres", str(demo.folder.path), "--limite", "1"])
    assert result.exit_code == 1
    assert "CONTACT_EMAIL" in result.output
    assert "jamais cherchés : 3" in result.output
    assert runner.invoke(app, ["textes-libres", str(tmp_path / "absent")]).exit_code == 1


def test_page_benchmark(tmp_path: Path) -> None:
    pdfs = tmp_path / "pdf"
    pdfs.mkdir()
    words = " ".join(f"word{i}" for i in range(40))
    lines = "\n".join(words[i : i + 60] for i in range(0, len(words), 60))
    (pdfs / "a.pdf").write_bytes(make_pdf([lines, lines.replace("word", "term")]))
    out = tmp_path / "rapports"
    result = runner.invoke(app, ["banc-pages", str(pdfs), "--sortie", str(out)])
    assert result.exit_code == 0, result.output
    assert "pymupdf : bonne page pour" in result.output
    assert (out / "extraction-pages.md").is_file()
    empty = tmp_path / "vide"
    empty.mkdir()
    assert runner.invoke(app, ["banc-pages", str(empty)]).exit_code == 1
    assert runner.invoke(app, ["banc-pages", str(tmp_path / "absent")]).exit_code == 1
