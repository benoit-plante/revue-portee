"""Project row and reviewers."""

from datetime import datetime

from sqlalchemy import Connection, select

from revue_portee.domain.project import (
    Project,
    ReplicationMarker,
    ReplicationMode,
    Reviewer,
    ReviewerKind,
)
from revue_portee.storage.db import project, replication_marker, reviewer

__all__ = [
    "get_project",
    "get_replication_marker",
    "get_reviewer",
    "insert_project",
    "insert_replication_marker",
    "insert_reviewer",
    "list_reviewers",
]


def insert_project(connection: Connection, value: Project) -> None:
    connection.execute(project.insert().values(**value.model_dump()))


def get_project(connection: Connection) -> Project:
    row = connection.execute(select(project)).mappings().one()
    return Project.model_validate(dict(row))


def insert_reviewer(connection: Connection, value: Reviewer, *, now: datetime) -> None:
    connection.execute(reviewer.insert().values(**value.model_dump(), created_at=now))


def _to_reviewer(row: dict[str, object]) -> Reviewer:
    data = {key: value for key, value in row.items() if key != "created_at"}
    return Reviewer.model_validate(data | {"kind": ReviewerKind(str(row["kind"]))})


def get_reviewer(connection: Connection, reviewer_id: str) -> Reviewer | None:
    row = connection.execute(select(reviewer).where(reviewer.c.id == reviewer_id)).mappings()
    found = row.one_or_none()
    return None if found is None else _to_reviewer(dict(found))


def list_reviewers(connection: Connection) -> list[Reviewer]:
    rows = connection.execute(select(reviewer).order_by(reviewer.c.id)).mappings()
    return [_to_reviewer(dict(row)) for row in rows]


def insert_replication_marker(
    connection: Connection,
    project_id: str,
    marker: ReplicationMarker,
    *,
    now: datetime,
    journal_entry_id: str,
) -> None:
    """Mark the project as a replication project (refused by the base unless the
    project is being created, D-104)."""
    connection.execute(
        replication_marker.insert().values(
            project_id=project_id,
            review_id=marker.review_id,
            mode=marker.mode.value,
            created_at=now,
            journal_entry_id=journal_entry_id,
        )
    )


def get_replication_marker(connection: Connection) -> ReplicationMarker | None:
    row = connection.execute(select(replication_marker)).mappings().one_or_none()
    if row is None:
        return None
    return ReplicationMarker(review_id=str(row["review_id"]), mode=ReplicationMode(row["mode"]))
