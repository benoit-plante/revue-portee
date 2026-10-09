"""Stakeholders, their comments and the responses (tranche 4.2), append-only."""

from typing import Any

from pydantic import BaseModel
from sqlalchemy import Connection, Table, select

from revue_portee.domain.stakeholders import Comment, CommentResponse, Stakeholder
from revue_portee.storage.db import comment_response, stakeholder, stakeholder_comment

__all__ = [
    "insert_comment",
    "insert_response",
    "insert_stakeholder",
    "list_comments",
    "list_responses",
    "list_stakeholders",
]


def _insert(connection: Connection, table: Table, item: BaseModel, journal_entry_id: str) -> None:
    data: dict[str, Any] = item.model_dump(mode="python")
    for key, value in data.items():
        if hasattr(value, "value") and isinstance(value.value, str):
            data[key] = value.value
    connection.execute(table.insert().values(**data, journal_entry_id=journal_entry_id))


def _rows(connection: Connection, table: Table) -> list[dict[str, Any]]:
    rows = connection.execute(select(table).order_by(table.c.created_at, table.c.id))
    return [
        {k: v for k, v in dict(row).items() if k != "journal_entry_id"} for row in rows.mappings()
    ]


def insert_stakeholder(connection: Connection, item: Stakeholder, *, journal_entry_id: str) -> None:
    _insert(connection, stakeholder, item, journal_entry_id)


def insert_comment(connection: Connection, item: Comment, *, journal_entry_id: str) -> None:
    _insert(connection, stakeholder_comment, item, journal_entry_id)


def insert_response(
    connection: Connection, item: CommentResponse, *, journal_entry_id: str
) -> None:
    _insert(connection, comment_response, item, journal_entry_id)


def list_stakeholders(connection: Connection) -> list[Stakeholder]:
    return [Stakeholder.model_validate(r) for r in _rows(connection, stakeholder)]


def list_comments(connection: Connection) -> list[Comment]:
    return [Comment.model_validate(r) for r in _rows(connection, stakeholder_comment)]


def list_responses(connection: Connection) -> list[CommentResponse]:
    return [CommentResponse.model_validate(r) for r in _rows(connection, comment_response)]
