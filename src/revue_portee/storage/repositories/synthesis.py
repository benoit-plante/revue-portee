"""Comments on the gaps of an evidence map (tranche 3.5), append-only."""

from sqlalchemy import Connection, select

from revue_portee.domain.synthesis import GapComment
from revue_portee.storage.db import gap_comment

__all__ = ["insert_comment", "list_comments"]


def insert_comment(connection: Connection, comment: GapComment, *, journal_entry_id: str) -> None:
    connection.execute(
        gap_comment.insert().values(
            **comment.model_dump(mode="python"), journal_entry_id=journal_entry_id
        )
    )


def list_comments(connection: Connection) -> list[GapComment]:
    rows = connection.execute(select(gap_comment).order_by(gap_comment.c.created_at))
    return [
        GapComment.model_validate({k: v for k, v in dict(row).items() if k != "journal_entry_id"})
        for row in rows.mappings()
    ]
