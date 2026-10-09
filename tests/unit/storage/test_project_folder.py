import shutil
import tomllib
from pathlib import Path

import pytest
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, text

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


# SQLite cannot reflect the expression index ix_decision_priority (migration 0007): it is
# left out of the comparison, and its creation is checked by the migration itself.
@pytest.mark.filterwarnings("ignore:Skipped unsupported reflection of expression-based index")
@pytest.mark.filterwarnings("ignore:autogenerate skipping metadata-specified expression-based")
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


@pytest.mark.parametrize(
    ("title", "language", "reviewer", "message"),
    [
        (" ", "fr", "R", "titre de la revue est obligatoire"),
        ("T", "fr", "  ", "nom du réviseur est obligatoire"),
        ("T", "fra", "R", "code ISO 639-1"),
        ("T", "f1", "R", "code ISO 639-1"),
    ],
)
def test_invalid_input_is_refused_in_french_before_writing(
    tmp_path: Path, title: str, language: str, reviewer: str, message: str
) -> None:
    with pytest.raises(ProjectFolderError, match=message):
        create_project_folder(
            tmp_path / "demo",
            title=title,
            language=language,
            reviewer_name=reviewer,
            now=make_clock(),
            tool_version=TOOL_VERSION,
        )
    assert not (tmp_path / "demo.revue").exists()


def test_language_is_normalized(tmp_path: Path) -> None:
    folder = create_project_folder(
        tmp_path / "demo", title="T", language=" FR ", reviewer_name="R",
        now=make_clock(), tool_version=TOOL_VERSION,
    )  # fmt: skip
    with folder.engine.connect() as connection:
        assert projects.get_project(connection).language == "fr"
    folder.close()


@pytest.mark.parametrize("pre_existing_empty_folder", [False, True])
def test_failed_creation_leaves_nothing_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pre_existing_empty_folder: bool
) -> None:
    target = tmp_path / "demo.revue"
    if pre_existing_empty_folder:
        target.mkdir()

    def broken_upgrade(engine: object) -> None:
        raise OSError("disque plein")

    monkeypatch.setattr(migrate, "upgrade", broken_upgrade)
    with pytest.raises(OSError, match="disque plein"):
        new_project(tmp_path)
    if pre_existing_empty_folder:
        assert list(target.iterdir()) == []
    else:
        assert not target.exists()
    monkeypatch.undo()
    new_project(tmp_path).close()  # the same name can be used again


def test_open_accepts_the_name_given_at_creation(tmp_path: Path) -> None:
    folder = new_project(tmp_path)
    folder.close()
    reopened = open_project_folder(tmp_path / "demo", now=make_clock(), tool_version=TOOL_VERSION)
    assert reopened.path == tmp_path / "demo.revue"
    reopened.close()


def test_concurrent_writers_keep_a_valid_chain(tmp_path: Path) -> None:
    import threading

    from revue_portee.clock import utc_now

    folder = new_project(tmp_path)
    failures: list[BaseException] = []

    def write_notes() -> None:
        for index in range(8):
            try:
                notes.add_note(folder, f"note {index}", now=utc_now, tool_version=TOOL_VERSION)
            except BaseException as error:  # collected and asserted below
                failures.append(error)

    threads = [threading.Thread(target=write_notes) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert failures == []
    assert len(notes.journal_entries(folder)) == 1 + 6 * 8
    assert notes.verify_journal(folder).valid
    folder.close()


def test_project_of_tranche_1_1_is_migrated_after_a_backup(tmp_path: Path) -> None:
    folder = new_project(tmp_path)
    folder.close()
    new_tables = (
        # tranche 3.3 (0013)
        "extraction_pilot",
        # tranche 3.2 (0012)
        "extraction_value",
        # tranche 3.1 (0011)
        "grid_field_code",
        "grid_field",
        "grid_version",
        # tranche 2.3 (0010)
        "primary_report_choice",
        "study_link_decision",
        "study_link_assessment",
        # tranche 2.1 (0008)
        "retrieval_note",
        "fulltext_document",
        # tranche 1.7 (0007), dependent tables first
        "impact_assessment",
        "ai_batch_end",
        "ai_batch",
        # tranche 1.6 (0006), dependent tables first
        "budget_setting",
        "threshold_setting",
        "calibration_model",
        "decision",
        "round_member",
        "screening_round",
        # tranche 1.5 (0005)
        "pair_decision",
        "duplicate_pair",
        "dedup_run",
        # tranche 1.4 (0004)
        "enrichment",
        "provenance",
        "import_file",
        "collection_end",
        "collection_page",
        "collection_run",
        "reference",
        # tranche 1.3 (0003)
        "term_suggestion_review",
        "term_suggestion",
        "descriptor_check",
        "sensitivity_check",
        "key_article_set_version",
        "search_run",
        "query",
        "search_strategy_version",
        # tranche 1.2 (0002)
        "protocol_registration",
        "protocol_text_version",
        "criterion_change",
        "qualification_proposal",
        "suggestion_review",
        "ai_suggestion",
        "ai_call",
        "ai_config",
    )
    with raw_sqlite(folder.path / DATABASE_FILE) as connection:
        for table in new_tables:
            connection.execute(f"DROP TABLE {table}")
        connection.execute("UPDATE alembic_version SET version_num = '0001'")
    reopened = open_project_folder(folder.path, now=make_clock(), tool_version=TOOL_VERSION)
    try:
        backups = list(folder.path.glob(f"{DATABASE_FILE}.sauvegarde-*"))
        assert len(backups) == 1
        with reopened.engine.connect() as connection:
            assert (
                MigrationContext.configure(connection).get_current_revision()
                == migrate.head_revision()
            )
            tables = set(inspect(connection).get_table_names())
        assert set(new_tables) <= tables
        entry = notes.journal_entries(reopened)[-1]
        assert entry.payload == {"migrated_from": "0001"}
    finally:
        reopened.close()
