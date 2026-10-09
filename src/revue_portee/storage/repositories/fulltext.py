"""Full-text documents and retrieval notes (tranche 2.1), append-only."""

from typing import Any

from sqlalchemy import Connection, select

from revue_portee.domain.fulltext import FulltextDocument, RetrievalNote
from revue_portee.storage.db import fulltext_document, retrieval_note

__all__ = [
    "insert_document",
    "insert_note",
    "list_documents",
    "list_notes",
]


def _plain(row: Any) -> dict[str, Any]:  # noqa: ANN401 - SQLAlchemy row mapping
    return {k: v for k, v in dict(row).items() if k != "journal_entry_id"}


def insert_document(
    connection: Connection, value: FulltextDocument, *, journal_entry_id: str
) -> None:
    connection.execute(
        fulltext_document.insert().values(
            **value.model_dump(mode="python"), journal_entry_id=journal_entry_id
        )
    )


def insert_note(connection: Connection, value: RetrievalNote, *, journal_entry_id: str) -> None:
    connection.execute(
        retrieval_note.insert().values(
            **value.model_dump(mode="python"), journal_entry_id=journal_entry_id
        )
    )


def list_documents(connection: Connection) -> list[FulltextDocument]:
    """Every document, oldest first."""
    rows = connection.execute(
        select(fulltext_document).order_by(fulltext_document.c.created_at, fulltext_document.c.id)
    ).mappings()
    return [FulltextDocument.model_validate(_plain(row)) for row in rows]


def list_notes(connection: Connection) -> list[RetrievalNote]:
    """Every retrieval note, oldest first."""
    rows = connection.execute(
        select(retrieval_note).order_by(retrieval_note.c.created_at, retrieval_note.c.id)
    ).mappings()
    return [RetrievalNote.model_validate(_plain(row)) for row in rows]
