"""Free notes added to the project journal (EF-PRJ-03)."""

from collections.abc import Callable
from datetime import datetime

from revue_portee.domain.journal import ChainCheck, EntryType, JournalEntry
from revue_portee.i18n import french
from revue_portee.i18n import gettext as _
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import journal

__all__ = ["EmptyNoteError", "add_note", "journal_entries", "verify_journal"]


class EmptyNoteError(ValueError):
    def __init__(self) -> None:
        super().__init__(_("A note cannot be empty."))


def add_note(
    folder: ProjectFolder, text: str, *, now: Callable[[], datetime], tool_version: str
) -> JournalEntry:
    text = text.strip()
    if not text:
        raise EmptyNoteError
    with folder.engine.begin() as connection:
        return journal.append_entry(
            connection,
            now=now(),
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.NOTE_ADDED,
            summary_fr=french("Note added to the journal"),
            tool_version=tool_version,
            payload={"text": text},
        )


def journal_entries(folder: ProjectFolder) -> list[JournalEntry]:
    with folder.engine.connect() as connection:
        return journal.list_entries(connection)


def verify_journal(folder: ProjectFolder) -> ChainCheck:
    with folder.engine.connect() as connection:
        return journal.verify(connection)
