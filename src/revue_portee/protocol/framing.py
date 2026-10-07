"""Record the PCC framing of the review question (EF-CAD-01)."""

from collections.abc import Callable
from datetime import datetime

from pydantic import JsonValue
from sqlalchemy import Connection

from revue_portee.domain.framing import Framing, FramingVersion
from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.i18n import french
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import framing as framing_repo
from revue_portee.storage.repositories import journal

__all__ = ["current_framing", "framing_history", "save_framing", "save_framing_in"]


def current_framing(folder: ProjectFolder) -> FramingVersion | None:
    with folder.engine.connect() as connection:
        return framing_repo.latest_framing_version(connection)


def framing_history(folder: ProjectFolder) -> list[FramingVersion]:
    with folder.engine.connect() as connection:
        return framing_repo.list_framing_versions(connection)


def save_framing_in(
    connection: Connection,
    folder: ProjectFolder,
    framing: Framing,
    *,
    moment: datetime,
    tool_version: str,
    payload: dict[str, JsonValue] | None = None,
) -> FramingVersion:
    """Store a new framing version within the caller's transaction, unless it is
    identical to the current one (then the current version is returned)."""
    latest = framing_repo.latest_framing_version(connection)
    if latest is not None and latest.framing == framing:
        return latest
    version = FramingVersion(
        id=new_ulid(moment),
        number=1 if latest is None else latest.number + 1,
        created_at=moment,
        author_id=folder.reviewer_id,
        framing=framing,
    )
    details: dict[str, JsonValue] = {
        "number": version.number,
        "framing": framing.model_dump(mode="json"),
    }
    entry = journal.append_entry(
        connection,
        now=moment,
        actor_reviewer_id=folder.reviewer_id,
        entry_type=EntryType.FRAMING_UPDATED,
        subject_type="framing_version",
        subject_id=version.id,
        summary_fr=french("Review question framed (version {number})").format(
            number=version.number
        ),
        tool_version=tool_version,
        payload=details | (payload or {}),
    )
    framing_repo.insert_framing_version(connection, version, journal_entry_id=entry.id)
    return version


def save_framing(
    folder: ProjectFolder, framing: Framing, *, now: Callable[[], datetime], tool_version: str
) -> FramingVersion:
    """Store a new framing version, unless it is identical to the current one."""
    with folder.write() as connection:
        return save_framing_in(connection, folder, framing, moment=now(), tool_version=tool_version)
