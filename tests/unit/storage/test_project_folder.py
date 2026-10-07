import shutil
import tomllib
from pathlib import Path

import pytest
from sqlalchemy import text

from revue_portee.domain.criteria import CriterionKind, PccElement
from revue_portee.domain.framing import Framing
from revue_portee.domain.journal import EntryType
from revue_portee.protocol import criteria, framing, notes
from revue_portee.storage import migrate
from revue_portee.storage.db import metadata
from revue_portee.storage.project_folder import (
    DATABASE_FILE,
    PROJECT_FILE,
    SUBDIRECTORIES,
    ProjectFolderError,
    create_project_folder,
    open_project_folder,
)
from revue_portee.storage.repositories import projects
from support import TOOL_VERSION, make_clock, new_project, raw_sqlite


def test_create_project_folder(tmp_path: Path) -> None:
    folder = new_project(tmp_path)
    assert folder.path == tmp_path / "demo.revue"
    for sub in SUBDIRECTORIES:
        assert (folder.path / sub).is_dir()
    meta = tomllib.loads((folder.path / PROJECT_FILE).read_text(encoding="utf-8"))
    assert meta["format_version"] == "1.0"
    assert meta["project"]["id"] == folder.project_id
    assert meta["project"]["main_reviewer_id"] == folder.reviewer_id
    with folder.engine.connect() as connection:
        project = projects.get_project(connection)
        assert project.title.startswith("Soutien")
        assert [r.display_name for r in projects.list_reviewers(connection)] == ["Benoit Plante"]
    [entry] = notes.journal_entries(folder)
    assert entry.entry_type == EntryType.PROJECT_CREATED
    assert entry.tool_version == TOOL_VERSION
    folder.close()


def test_existing_non_empty_folder_is_refused(tmp_path: Path) -> None:
    (tmp_path / "demo.revue").mkdir()
    (tmp_path / "demo.revue" / "file.txt").write_text("x")
    with pytest.raises(ProjectFolderError, match="n'est pas vide"):
        new_project(tmp_path)


def test_folder_reopens_identically_elsewhere(tmp_path: Path) -> None:
    clock = make_clock()
    folder = new_project(tmp_path, clock)
    framing.save_framing(
        folder,
        Framing(question="Quels programmes ?", population="Parents", concept="Soutien"),
        now=clock,
        tool_version=TOOL_VERSION,
    )
    for text_ in ("Parents d'enfants de 0 à 12 ans", "Familles d'accueil"):
        criteria.add_criterion(
            folder,
            pcc_element=PccElement.POPULATION,
            kind=CriterionKind.INCLUSION,
            text=text_,
            examples=["Mères adolescentes"],
            now=clock,
            tool_version=TOOL_VERSION,
        )
    criteria.activate_draft(folder, rationale="", now=clock, tool_version=TOOL_VERSION)
    before = (
        criteria.criteria_state(folder),
        framing.framing_history(folder),
        notes.journal_entries(folder),
    )
    folder.close()

    copy = tmp_path / "ailleurs" / "copie.revue"
    shutil.copytree(tmp_path / "demo.revue", copy)
    reopened = open_project_folder(copy, now=clock, tool_version="9.9.9 (fedcba)")
    after_state = criteria.criteria_state(reopened)
    entries = notes.journal_entries(reopened)
    assert after_state == before[0]
    assert framing.framing_history(reopened) == before[1]
    assert entries[:-1] == before[2]
    assert entries[-1].entry_type == EntryType.PROJECT_OPENED
    assert entries[-1].tool_version == "9.9.9 (fedcba)"  # ENF-REP-05
    assert notes.verify_journal(reopened).valid
    assert reopened.project_id == folder.project_id
    reopened.close()


@pytest.mark.parametrize("missing", [PROJECT_FILE, DATABASE_FILE])
def test_not_a_project_folder(tmp_path: Path, missing: str) -> None:
    folder = new_project(tmp_path)
    folder.close()
    (folder.path / missing).unlink()
    with pytest.raises(ProjectFolderError, match="n'est pas un dossier de projet"):
        open_project_folder(folder.path, now=make_clock(), tool_version=TOOL_VERSION)


def test_unsupported_format_and_mismatched_project(tmp_path: Path) -> None:
    folder = new_project(tmp_path)
    folder.close()
    project_file = folder.path / PROJECT_FILE
    original = project_file.read_text(encoding="utf-8")
    project_file.write_text(original.replace('"1.0"', '"9.0"'), encoding="utf-8")
    with pytest.raises(ProjectFolderError, match=r"Format de projet non pris en charge"):
        open_project_folder(folder.path, now=make_clock(), tool_version=TOOL_VERSION)
    project_file.write_text(original.replace(folder.project_id, "0" * 26), encoding="utf-8")
    with pytest.raises(ProjectFolderError, match="projets différents"):
        open_project_folder(folder.path, now=make_clock(), tool_version=TOOL_VERSION)
    project_file.write_text("not = [toml", encoding="utf-8")
    with pytest.raises(ProjectFolderError, match="illisible"):
        open_project_folder(folder.path, now=make_clock(), tool_version=TOOL_VERSION)


def test_unknown_schema_revision_is_backed_up_and_refused(tmp_path: Path) -> None:
    folder = new_project(tmp_path)
    folder.close()
    with raw_sqlite(folder.path / DATABASE_FILE) as connection:
        connection.execute("UPDATE alembic_version SET version_num = 'inconnue'")
    with pytest.raises(ProjectFolderError, match="schéma de base de données inconnu"):
        open_project_folder(folder.path, now=make_clock(), tool_version=TOOL_VERSION)
    assert list(folder.path.glob(f"{DATABASE_FILE}.sauvegarde-*"))


def test_migrated_schema_matches_table_definitions(tmp_path: Path) -> None:
    from alembic.autogenerate import compare_metadata
    from alembic.runtime.migration import MigrationContext

    folder = new_project(tmp_path)
    assert migrate.current_revision(folder.engine) == migrate.head_revision()
    with folder.engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), metadata)
    assert differences == []
    folder.close()


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE journal_entry SET summary_fr = 'falsifié'",
        "DELETE FROM journal_entry",
        "DELETE FROM project",
    ],
)
def test_append_only_tables_refuse_changes(tmp_path: Path, statement: str) -> None:
    folder = new_project(tmp_path)
    with pytest.raises(Exception, match="append-only"), folder.engine.begin() as connection:
        connection.execute(text(statement))
    folder.close()


def test_altered_database_breaks_the_journal_chain(tmp_path: Path) -> None:
    clock = make_clock()
    folder = new_project(tmp_path, clock)
    notes.add_note(folder, "Réunion du 7 octobre", now=clock, tool_version=TOOL_VERSION)
    notes.add_note(folder, "Deuxième note", now=clock, tool_version=TOOL_VERSION)
    folder.close()
    # Someone edits the file directly, dropping the trigger first.
    with raw_sqlite(folder.path / DATABASE_FILE) as connection:
        connection.execute("DROP TRIGGER journal_entry_no_update")
        connection.execute(
            'UPDATE journal_entry SET payload_json = \'{"text":"Réunion du 8 octobre"}\' '
            "WHERE position = 1"
        )
    reopened = open_project_folder(folder.path, now=clock, tool_version=TOOL_VERSION)
    check = notes.verify_journal(reopened)
    assert not check.valid
    assert check.first_invalid_index == 1
    reopened.close()


def test_create_appends_suffix_only_once(tmp_path: Path) -> None:
    folder = create_project_folder(
        tmp_path / "deja.revue",
        title="T",
        language="fr",
        reviewer_name="R",
        now=make_clock(),
        tool_version=TOOL_VERSION,
    )
    assert folder.path.name == "deja.revue"
    folder.close()
