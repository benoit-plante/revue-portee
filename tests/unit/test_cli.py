from pathlib import Path

from typer.testing import CliRunner

from revue_portee import __version__
from revue_portee.cli.main import app
from revue_portee.domain.journal import EntryType
from revue_portee.protocol import notes
from revue_portee.storage.project_folder import open_project_folder
from support import raw_sqlite

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == f"revue-portee {__version__}"


def test_no_arguments_shows_french_help() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Afficher la version et quitter." in result.output
    assert "nouveau" in result.output
    assert "verifier-journal" in result.output


def test_new_project_then_verify_journal(tmp_path: Path) -> None:
    created = runner.invoke(
        app, ["nouveau", str(tmp_path / "demo"), "--titre", "Démo", "--reviseur", "Benoit"]
    )
    assert created.exit_code == 0, created.output
    assert "Projet créé" in created.output
    folder = tmp_path / "demo.revue"

    checked = runner.invoke(app, ["verifier-journal", str(folder)])
    assert checked.exit_code == 0, checked.output
    assert "Journal intègre : 1 entrée" in checked.output

    # The check is read-only: it does not record an opening.
    from revue_portee.clock import utc_now

    project = open_project_folder(folder, now=utc_now, tool_version="t", record_opening=False)
    assert [e.entry_type for e in notes.journal_entries(project)] == [EntryType.PROJECT_CREATED]
    project.close()


def test_new_project_refuses_non_empty_folder(tmp_path: Path) -> None:
    target = tmp_path / "demo.revue"
    target.mkdir()
    (target / "x").write_text("x")
    result = runner.invoke(app, ["nouveau", str(target), "--titre", "T", "--reviseur", "R"])
    assert result.exit_code == 1
    assert "n'est pas vide" in result.output


def test_verify_journal_reports_alteration(tmp_path: Path) -> None:
    runner.invoke(app, ["nouveau", str(tmp_path / "demo"), "--titre", "T", "--reviseur", "R"])
    database = tmp_path / "demo.revue" / "revue.sqlite"
    with raw_sqlite(database) as connection:
        connection.execute("DROP TRIGGER journal_entry_no_update")
        connection.execute("UPDATE journal_entry SET summary_fr = 'falsifié'")
    result = runner.invoke(app, ["verifier-journal", str(tmp_path / "demo.revue")])
    assert result.exit_code == 1
    assert "rompue à l'entrée 1" in result.output


def test_verify_journal_on_a_non_project(tmp_path: Path) -> None:
    result = runner.invoke(app, ["verifier-journal", str(tmp_path)])
    assert result.exit_code == 1
    assert "n'est pas un dossier de projet" in result.output


def test_new_project_reports_invalid_input_in_french(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["nouveau", str(tmp_path / "demo"), "--titre", " ", "--reviseur", "R"]
    )
    assert result.exit_code == 1
    assert "Le titre de la revue est obligatoire." in result.output
    assert "Traceback" not in result.output


def test_commands_accept_the_name_given_at_creation(tmp_path: Path) -> None:
    runner.invoke(app, ["nouveau", str(tmp_path / "demo"), "--titre", "T", "--reviseur", "R"])
    result = runner.invoke(app, ["verifier-journal", str(tmp_path / "demo")])
    assert result.exit_code == 0, result.output


def test_protocol_export(tmp_path: Path) -> None:
    runner.invoke(app, ["nouveau", str(tmp_path / "demo"), "--titre", "Démo", "--reviseur", "B"])
    folder = tmp_path / "demo.revue"
    for language in ("fr", "en"):
        result = runner.invoke(app, ["protocole", str(folder), "--langue", language])
        assert result.exit_code == 0, result.output
        assert "Protocole écrit" in result.output
        assert (folder / "exports" / f"protocole-{language}.md").is_file()
        assert (folder / "exports" / f"protocole-{language}.docx").is_file()
    french = (folder / "exports" / "protocole-fr.md").read_text(encoding="utf-8")
    assert french.startswith("# Démo : protocole de revue de portée")
    refused = runner.invoke(app, ["protocole", str(folder), "--langue", "de"])
    assert refused.exit_code == 1
    assert "Langue non prise en charge" in refused.output
    missing = runner.invoke(app, ["protocole", str(tmp_path / "absent")])
    assert missing.exit_code == 1


def test_flow_diagram_export(tmp_path: Path) -> None:
    runner.invoke(app, ["nouveau", str(tmp_path / "demo"), "--titre", "Démo", "--reviseur", "B"])
    folder = tmp_path / "demo.revue"
    result = runner.invoke(app, ["diagramme", str(folder)])
    assert result.exit_code == 0, result.output
    assert result.output.count("Diagramme de flux écrit") == 2
    french = (folder / "exports" / "diagramme-fr.svg").read_text(encoding="utf-8")
    assert "PROVISOIRE" in french  # nothing collected nor screened yet
    assert (folder / "exports" / "diagramme-en.svg").is_file()
    missing = runner.invoke(app, ["diagramme", str(tmp_path / "absent")])
    assert missing.exit_code == 1


def test_methods_export(tmp_path: Path) -> None:
    runner.invoke(app, ["nouveau", str(tmp_path / "demo"), "--titre", "Démo", "--reviseur", "B"])
    folder = tmp_path / "demo.revue"
    result = runner.invoke(app, ["methode", str(folder)])
    assert result.exit_code == 0, result.output
    assert result.output.count("Section méthode écrite") == 4
    french = (folder / "exports" / "methode-fr.md").read_text(encoding="utf-8")
    assert "Aucune IA n'a servi au tri des titres et résumés." in french
    assert (folder / "exports" / "methode-en.docx").is_file()
    missing = runner.invoke(app, ["methode", str(tmp_path / "absent")])
    assert missing.exit_code == 1


def test_archive_export(tmp_path: Path) -> None:
    runner.invoke(app, ["nouveau", str(tmp_path / "demo"), "--titre", "Démo", "--reviseur", "B"])
    folder = tmp_path / "demo.revue"
    public = runner.invoke(app, ["archive", str(folder)])
    assert public.exit_code == 0, public.output
    assert "Archive écrite" in public.output
    assert "ne pas la déposer" not in public.output
    complete = runner.invoke(app, ["archive", str(folder), "--complete"])
    assert complete.exit_code == 0, complete.output
    assert "ne pas la déposer publiquement" in complete.output
    assert len(list((folder / "exports").glob("archive-*.zip"))) == 2
    missing = runner.invoke(app, ["archive", str(tmp_path / "absent")])
    assert missing.exit_code == 1


def test_retained_export(tmp_path: Path) -> None:
    runner.invoke(app, ["nouveau", str(tmp_path / "demo"), "--titre", "Démo", "--reviseur", "B"])
    folder = tmp_path / "demo.revue"
    result = runner.invoke(app, ["retenues", str(folder)])
    assert result.exit_code == 0, result.output
    assert result.output.count("0 référence retenue, écrite") == 2
    assert "Le tri n'est pas terminé" in result.output
    assert (folder / "exports" / "references-retenues.ris").read_text(encoding="utf-8") == ""
    assert (folder / "exports" / "references-retenues.csv").is_file()
    missing = runner.invoke(app, ["retenues", str(tmp_path / "absent")])
    assert missing.exit_code == 1


def test_extracted_values_export(tmp_path: Path) -> None:
    runner.invoke(app, ["nouveau", str(tmp_path / "demo"), "--titre", "Démo", "--reviseur", "B"])
    folder = tmp_path / "demo.revue"
    result = runner.invoke(app, ["donnees-extraites", str(folder)])
    assert result.exit_code == 0, result.output
    assert "Valeurs écrites dans" in result.output
    assert result.output.rstrip().endswith(": 0.")
    written = (folder / "exports" / "donnees-extraites.csv").read_text(encoding="utf-8")
    assert written == "study,title,year,field,label,reported,value,page,status,to_review\n"
    missing = runner.invoke(app, ["donnees-extraites", str(tmp_path / "absent")])
    assert missing.exit_code == 1
