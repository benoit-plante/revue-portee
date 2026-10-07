"""Create and open a project folder ``<name>.revue`` (docs/03-architecture.md §4).

``projet.toml`` holds the metadata and the folder format version; ``revue.sqlite`` is
the source of truth. No secret is ever written in the folder (ENF-SEC-01).
"""

import shutil
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import tomli_w
from alembic.util.exc import CommandError
from sqlalchemy import Engine

from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.domain.project import FORMAT_VERSION, Project, Reviewer, ReviewerKind
from revue_portee.i18n import french
from revue_portee.i18n import gettext as _
from revue_portee.storage import migrate
from revue_portee.storage.db import create_project_engine
from revue_portee.storage.repositories import journal, projects

__all__ = [
    "DATABASE_FILE",
    "FOLDER_SUFFIX",
    "PROJECT_FILE",
    "SUBDIRECTORIES",
    "ProjectFolder",
    "ProjectFolderError",
    "create_project_folder",
    "open_project_folder",
]

FOLDER_SUFFIX = ".revue"
PROJECT_FILE = "projet.toml"
DATABASE_FILE = "revue.sqlite"
SUBDIRECTORIES = ("brut/ia", "brut/sources", "imports", "textes", "etalonnage", "exports")
SUPPORTED_FORMATS = {FORMAT_VERSION}


class ProjectFolderError(Exception):
    """A folder that cannot be created or opened as a project (French message)."""


@dataclass(frozen=True, slots=True)
class ProjectFolder:
    """An open project: its folder, its database engine and its main human reviewer."""

    path: Path
    engine: Engine
    project_id: str
    reviewer_id: str

    def close(self) -> None:
        self.engine.dispose()


def _with_suffix(path: Path) -> Path:
    return path if path.name.endswith(FOLDER_SUFFIX) else path.with_name(path.name + FOLDER_SUFFIX)


def create_project_folder(
    path: Path,
    *,
    title: str,
    language: str,
    reviewer_name: str,
    now: Callable[[], datetime],
    tool_version: str,
    description: str = "",
) -> ProjectFolder:
    """Create a new project folder (``.revue`` is appended to the name if missing)."""
    folder = _with_suffix(path)
    if folder.exists() and any(folder.iterdir()):
        raise ProjectFolderError(
            _("The folder {folder} already exists and is not empty.").format(folder=folder)
        )
    created_at = now()
    project = Project(
        id=new_ulid(created_at),
        title=title.strip(),
        language=language,
        description=description.strip(),
        created_at=created_at,
    )
    reviewer = Reviewer(
        id=new_ulid(created_at),
        kind=ReviewerKind.HUMAN,
        display_name=reviewer_name.strip(),
        role="reviewer",
    )
    folder.mkdir(parents=True, exist_ok=True)
    for sub in SUBDIRECTORIES:
        (folder / sub).mkdir(parents=True, exist_ok=True)
    (folder / PROJECT_FILE).write_text(
        tomli_w.dumps(
            {
                "format_version": FORMAT_VERSION,
                "project": {
                    "id": project.id,
                    "title": project.title,
                    "language": project.language,
                    "created_at": project.created_at.isoformat(),
                    "main_reviewer_id": reviewer.id,
                },
            }
        ),
        encoding="utf-8",
    )
    engine = create_project_engine(folder / DATABASE_FILE)
    migrate.upgrade(engine)
    with engine.begin() as connection:
        projects.insert_project(connection, project)
        projects.insert_reviewer(connection, reviewer, now=created_at)
        journal.append_entry(
            connection,
            now=created_at,
            actor_reviewer_id=reviewer.id,
            entry_type=EntryType.PROJECT_CREATED,
            subject_type="project",
            subject_id=project.id,
            summary_fr=french("Project created: {title}").format(title=project.title),
            tool_version=tool_version,
            payload={
                "title": project.title,
                "language": project.language,
                "format_version": FORMAT_VERSION,
                "reviewer": {"id": reviewer.id, "display_name": reviewer.display_name},
            },
        )
    return ProjectFolder(path=folder, engine=engine, project_id=project.id, reviewer_id=reviewer.id)


def _read_metadata(folder: Path) -> dict[str, object]:
    project_file = folder / PROJECT_FILE
    if not project_file.is_file() or not (folder / DATABASE_FILE).is_file():
        raise ProjectFolderError(
            _("{folder} is not a revue-portee project folder.").format(folder=folder)
        )
    try:
        return tomllib.loads(project_file.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ProjectFolderError(
            _("The file {file} is unreadable.").format(file=project_file)
        ) from error


def _open(
    folder: Path,
    engine: Engine,
    project_meta: dict[str, object],
    *,
    now: Callable[[], datetime],
    tool_version: str,
    record_opening: bool,
) -> tuple[str, str]:
    """Migrate if needed, check consistency and record the opening; return the ids."""
    current = migrate.current_revision(engine)
    if current != migrate.head_revision():
        moment = now().strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(folder / DATABASE_FILE, folder / f"{DATABASE_FILE}.sauvegarde-{moment}")
        try:
            migrate.upgrade(engine)
        except CommandError as error:
            raise ProjectFolderError(
                _(
                    "The project has an unknown database schema ({revision}); "
                    "a backup copy was made before any change."
                ).format(revision=current)
            ) from error
    with engine.begin() as connection:
        project = projects.get_project(connection)
        if project.id != project_meta.get("id"):
            raise ProjectFolderError(
                _("{file} and the database describe different projects.").format(file=PROJECT_FILE)
            )
        reviewer_id = str(project_meta.get("main_reviewer_id", ""))
        if projects.get_reviewer(connection, reviewer_id) is None:
            raise ProjectFolderError(_("The main reviewer of the project is missing."))
        if not record_opening:
            return project.id, reviewer_id
        journal.append_entry(
            connection,
            now=now(),
            actor_reviewer_id=reviewer_id,
            entry_type=EntryType.PROJECT_OPENED,
            subject_type="project",
            subject_id=project.id,
            summary_fr=french("Project opened with revue-portee {version}").format(
                version=tool_version
            ),
            tool_version=tool_version,
            payload={"migrated_from": current} if current != migrate.head_revision() else {},
        )
    return project.id, reviewer_id


def open_project_folder(
    path: Path, *, now: Callable[[], datetime], tool_version: str, record_opening: bool = True
) -> ProjectFolder:
    """Open an existing project, migrating its database (after a backup) if needed.

    Each opening is recorded in the journal with the tool version (ENF-REP-05), except
    for read-only checks (``record_opening=False``), which must not change the project.
    """
    folder = path
    metadata = _read_metadata(folder)
    format_version = str(metadata.get("format_version", ""))
    if format_version not in SUPPORTED_FORMATS:
        raise ProjectFolderError(
            _("Unsupported project format: {version}.").format(version=format_version or "?")
        )
    project_meta = metadata.get("project")
    if not isinstance(project_meta, dict):
        raise ProjectFolderError(
            _("The file {file} is unreadable.").format(file=folder / PROJECT_FILE)
        )
    engine = create_project_engine(folder / DATABASE_FILE)
    try:
        project_id, reviewer_id = _open(
            folder, engine, project_meta, now=now, tool_version=tool_version,
            record_opening=record_opening,
        )  # fmt: skip
    except BaseException:
        engine.dispose()
        raise
    return ProjectFolder(path=folder, engine=engine, project_id=project_id, reviewer_id=reviewer_id)
