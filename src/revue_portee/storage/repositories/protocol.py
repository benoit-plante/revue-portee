"""Protocol text versions, protocol registration and confirmed criterion changes."""

import json

from sqlalchemy import Connection, select

from revue_portee.domain.changes import ChangeType, CriterionChange
from revue_portee.domain.project import ReviewerKind
from revue_portee.domain.protocol import ProtocolRegistration, ProtocolText, ProtocolTextVersion
from revue_portee.storage.db import criterion_change, protocol_registration, protocol_text_version

__all__ = [
    "insert_change",
    "insert_registration",
    "insert_text_version",
    "latest_registration",
    "latest_text_version",
    "list_changes",
    "list_registrations",
    "list_text_versions",
]


def insert_text_version(
    connection: Connection, value: ProtocolTextVersion, *, journal_entry_id: str
) -> None:
    connection.execute(
        protocol_text_version.insert().values(
            id=value.id,
            number=value.number,
            created_at=value.created_at,
            author_id=value.author_id,
            sections_json=json.dumps(
                {key.value: text for key, text in value.text.sections.items()},
                ensure_ascii=False,
                sort_keys=True,
            ),
            journal_entry_id=journal_entry_id,
        )
    )


def _to_text_version(row: dict[str, object]) -> ProtocolTextVersion:
    return ProtocolTextVersion(
        id=str(row["id"]),
        number=int(str(row["number"])),
        created_at=row["created_at"],  # type: ignore[arg-type]
        author_id=str(row["author_id"]),
        text=ProtocolText.model_validate({"sections": json.loads(str(row["sections_json"]))}),
    )


def latest_text_version(connection: Connection) -> ProtocolTextVersion | None:
    row = (
        connection.execute(
            select(protocol_text_version).order_by(protocol_text_version.c.number.desc()).limit(1)
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else _to_text_version(dict(row))


def list_text_versions(connection: Connection) -> list[ProtocolTextVersion]:
    rows = connection.execute(
        select(protocol_text_version).order_by(protocol_text_version.c.number)
    ).mappings()
    return [_to_text_version(dict(row)) for row in rows]


def insert_registration(
    connection: Connection, value: ProtocolRegistration, *, journal_entry_id: str
) -> None:
    connection.execute(
        protocol_registration.insert().values(
            **value.model_dump(mode="python"), journal_entry_id=journal_entry_id
        )
    )


def _to_registration(row: dict[str, object]) -> ProtocolRegistration:
    return ProtocolRegistration.model_validate(
        {key: value for key, value in row.items() if key != "journal_entry_id"}
    )


def list_registrations(connection: Connection) -> list[ProtocolRegistration]:
    rows = connection.execute(
        select(protocol_registration).order_by(
            protocol_registration.c.created_at, protocol_registration.c.id
        )
    ).mappings()
    return [_to_registration(dict(row)) for row in rows]


def latest_registration(connection: Connection) -> ProtocolRegistration | None:
    registrations = list_registrations(connection)
    return registrations[-1] if registrations else None


def insert_change(connection: Connection, value: CriterionChange, *, journal_entry_id: str) -> None:
    connection.execute(
        criterion_change.insert().values(
            **value.model_dump(mode="python"), journal_entry_id=journal_entry_id
        )
    )


def list_changes(
    connection: Connection, *, to_version_id: str | None = None
) -> list[CriterionChange]:
    query = select(criterion_change).order_by(criterion_change.c.created_at, criterion_change.c.id)
    if to_version_id is not None:
        query = query.where(criterion_change.c.to_version_id == to_version_id)
    return [
        CriterionChange.model_validate(
            {k: v for k, v in row.items() if k != "journal_entry_id"}
            | {
                "change_type": ChangeType(str(row["change_type"])),
                "proposed_by": ReviewerKind(str(row["proposed_by"])),
            }
        )
        for row in connection.execute(query).mappings()
    ]
