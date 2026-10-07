"""Project row and reviewers."""

from datetime import datetime

from sqlalchemy import Connection, select

from revue_portee.domain.project import Project, Reviewer, ReviewerKind
from revue_portee.storage.db import project, reviewer

__all__ = ["get_project", "get_reviewer", "insert_project", "insert_reviewer", "list_reviewers"]


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
