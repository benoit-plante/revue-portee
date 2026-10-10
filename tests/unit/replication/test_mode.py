"""Guards of the replication mode (D-104): never in an ordinary project, never removed,
and a mention on every export."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from revue_portee.domain.criteria import CriterionKind, PccElement
from revue_portee.domain.project import ReplicationMarker, ReplicationMode
from revue_portee.domain.screening import Decision, DecisionContext, DecisionValue, Stage
from revue_portee.domain.screening import ReviewerKind as Kind
from revue_portee.protocol import criteria
from revue_portee.reporting.flow_svg import simulation_mention
from revue_portee.reporting.methods import build_methods
from revue_portee.screening.archive import ArchiveKind, archive_files
from revue_portee.screening.methods import methods_data
from revue_portee.screening.report import flow_report
from revue_portee.storage.project_folder import (
    PROJECT_FILE,
    ProjectFolder,
    ProjectFolderError,
    create_project_folder,
    open_project_folder,
)
from revue_portee.storage.repositories import journal, projects
from revue_portee.storage.repositories import screening as screening_repo
from support import TOOL_VERSION, make_clock, new_project, raw_sqlite

MARKER = ReplicationMarker(review_id="Fictive", mode=ReplicationMode.CHAINED)
MENTION = "Simulation de réplication — ne constitue pas une revue"


def _replication(tmp_path: Path) -> ProjectFolder:
    return create_project_folder(
        tmp_path / "replication", title="Réplication fictive", language="fr",
        reviewer_name="banc-replication", now=make_clock(), tool_version=TOOL_VERSION,
        replication=MARKER,
    )  # fmt: skip


def test_replication_project_carries_its_marker(tmp_path: Path) -> None:
    folder = _replication(tmp_path)
    assert folder.replication == MARKER
    folder.close()
    text = (tmp_path / "replication.revue" / PROJECT_FILE).read_text(encoding="utf-8")
    assert "[replication]" in text
    reopened = open_project_folder(tmp_path / "replication", now=make_clock(),
                                   tool_version=TOOL_VERSION)  # fmt: skip
    assert reopened.replication == MARKER
    reopened.close()


def test_ordinary_project_has_no_marker(tmp_path: Path) -> None:
    folder = new_project(tmp_path)
    assert folder.replication is None
    folder.close()


def test_mode_cannot_be_activated_in_an_ordinary_project(tmp_path: Path) -> None:
    folder = new_project(tmp_path)
    # Not through the database: the marker is refused once the project exists…
    with (
        pytest.raises(IntegrityError, match="only when the project is created"),
        folder.write() as connection,
    ):
        projects.insert_replication_marker(
            connection, folder.project_id, MARKER, now=datetime(2026, 10, 9, tzinfo=UTC),
            journal_entry_id=journal.list_entries(connection)[0].id,
        )  # fmt: skip
    folder.close()
    # …nor by writing the marker in projet.toml: the folder is no longer opened.
    path = tmp_path / "demo.revue" / PROJECT_FILE
    path.write_text(
        path.read_text(encoding="utf-8")
        + '\n[replication]\nreview_id = "Fictive"\nmode = "chained"\n',
        encoding="utf-8",
    )
    with pytest.raises(ProjectFolderError, match="replication"):
        open_project_folder(tmp_path / "demo", now=make_clock(), tool_version=TOOL_VERSION)


def test_replication_project_cannot_be_converted(tmp_path: Path) -> None:
    _replication(tmp_path).close()
    database = tmp_path / "replication.revue" / "revue.sqlite"
    for statement in ("DELETE FROM replication_marker", "UPDATE replication_marker SET mode='x'"):
        with (
            pytest.raises(sqlite3.IntegrityError, match="append-only"),
            raw_sqlite(database) as connection,
        ):
            connection.execute(statement)
    path = tmp_path / "replication.revue" / PROJECT_FILE
    text = path.read_text(encoding="utf-8")
    path.write_text(text.split("[replication]")[0], encoding="utf-8")
    with pytest.raises(ProjectFolderError, match="replication"):
        open_project_folder(tmp_path / "replication", now=make_clock(), tool_version=TOOL_VERSION)
    path.write_text(text.replace('mode = "chained"', 'mode = "stepwise"'), encoding="utf-8")
    with pytest.raises(ProjectFolderError, match="replication"):
        open_project_folder(tmp_path / "replication", now=make_clock(), tool_version=TOOL_VERSION)
    path.write_text(text.replace('mode = "chained"', 'mode = "other"'), encoding="utf-8")
    with pytest.raises(ProjectFolderError, match=r"\[replication\]"):
        open_project_folder(tmp_path / "replication", now=make_clock(), tool_version=TOOL_VERSION)


def _decision(folder: ProjectFolder, reference_id: str, version_id: str) -> Decision:
    return Decision(
        id="d" * 26, reference_id=reference_id, stage=Stage.TITLE_ABSTRACT, round_id=None,
        reviewer_id=folder.reviewer_id, reviewer_kind=Kind.HUMAN,
        value=DecisionValue.UNCERTAIN, criteria_version_id=version_id,
        context=DecisionContext.REPLICATION, tool_version=TOOL_VERSION,
        created_at=datetime(2026, 10, 9, tzinfo=UTC),
    )  # fmt: skip


def test_ordinary_project_refuses_a_replication_decision(tmp_path: Path) -> None:
    from revue_portee.domain.references import Reference
    from revue_portee.storage.repositories import references as references_repo

    clock = make_clock()
    folder = new_project(tmp_path, clock)
    criteria.add_criterion(folder, pcc_element=PccElement.POPULATION, kind=CriterionKind.INCLUSION,
                           text="Adultes.", now=clock, tool_version=TOOL_VERSION)  # fmt: skip
    version = criteria.activate_draft(folder, rationale="", now=clock, tool_version=TOOL_VERSION)
    reference = Reference(id="r" * 26, title="Une référence", created_at=clock())
    with folder.write() as connection:
        references_repo.insert_reference(connection, reference)
    with folder.write() as connection:
        entry = journal.append_entry(
            connection, now=clock(), actor_reviewer_id=folder.reviewer_id,
            entry_type="note.added", subject_type="decision", subject_id="d" * 26,
            summary_fr="test", tool_version=TOOL_VERSION, payload={},
        )  # fmt: skip
        decision = _decision(folder, reference.id, version.id)
        with pytest.raises(IntegrityError, match="replication decisions only"):
            screening_repo.insert_decision(connection, decision, journal_entry_id=entry.id)
    folder.close()


def test_exports_carry_the_simulation_mention(tmp_path: Path) -> None:
    from revue_portee.reporting.flow_svg import render_flow_svg
    from revue_portee.resources import flow_template

    clock = make_clock()
    folder = _replication(tmp_path)
    assert simulation_mention(lambda text: text) == "Replication simulation — not a review"
    report = flow_report(folder, now=clock, tool_version=TOOL_VERSION)
    assert report.context.simulation
    svg = render_flow_svg(report.numbers, flow_template(), report.context, language="fr")
    assert MENTION in svg
    methods = build_methods(
        methods_data(folder, now=clock, tool_version=TOOL_VERSION), language="fr"
    )
    assert any(getattr(block, "text", "") == MENTION for block in methods.blocks)
    files = archive_files(folder, ArchiveKind.PUBLIC, now=clock, tool_version=TOOL_VERSION)
    readme = files["LISEZMOI.md"].decode()
    assert MENTION in readme
    assert "Replication simulation — not a review" in readme
    assert MENTION in files["exports/diagramme-fr.svg"].decode()
    folder.close()


def test_ordinary_exports_have_no_mention(tmp_path: Path) -> None:

    clock = make_clock()
    folder = new_project(tmp_path, clock)
    files = archive_files(folder, ArchiveKind.PUBLIC, now=clock, tool_version=TOOL_VERSION)
    assert MENTION not in files["LISEZMOI.md"].decode()
    assert MENTION not in files["exports/diagramme-fr.svg"].decode()
    folder.close()
