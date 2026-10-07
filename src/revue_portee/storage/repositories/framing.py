"""Framing (PCC question) versions."""

import json

from sqlalchemy import Connection, select

from revue_portee.domain.framing import Framing, FramingVersion
from revue_portee.storage.db import framing_version

__all__ = ["insert_framing_version", "latest_framing_version", "list_framing_versions"]


def insert_framing_version(
    connection: Connection, value: FramingVersion, *, journal_entry_id: str
) -> None:
    framing = value.framing
    connection.execute(
        framing_version.insert().values(
            id=value.id,
            number=value.number,
            created_at=value.created_at,
            author_id=value.author_id,
            question=framing.question,
            population=framing.population,
            concept=framing.concept,
            context=framing.context,
            secondary_questions_json=json.dumps(
                list(framing.secondary_questions), ensure_ascii=False
            ),
            journal_entry_id=journal_entry_id,
        )
    )


def _to_version(row: dict[str, object]) -> FramingVersion:
    return FramingVersion(
        id=str(row["id"]),
        number=int(str(row["number"])),
        created_at=row["created_at"],  # type: ignore[arg-type]
        author_id=str(row["author_id"]),
        framing=Framing(
            question=str(row["question"]),
            population=str(row["population"]),
            concept=str(row["concept"]),
            context=str(row["context"]),
            secondary_questions=tuple(json.loads(str(row["secondary_questions_json"]))),
        ),
    )


def latest_framing_version(connection: Connection) -> FramingVersion | None:
    row = (
        connection.execute(
            select(framing_version).order_by(framing_version.c.number.desc()).limit(1)
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else _to_version(dict(row))


def list_framing_versions(connection: Connection) -> list[FramingVersion]:
    rows = connection.execute(select(framing_version).order_by(framing_version.c.number))
    return [_to_version(dict(row)) for row in rows.mappings()]
