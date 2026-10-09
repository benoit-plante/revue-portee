"""Versions of the extraction grid and their fields (tranche 3.1).

Writes that the database refuses (a version that left draft) surface as
:class:`~revue_portee.domain.criteria.ImmutableVersionError`.
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import Connection, select
from sqlalchemy.exc import IntegrityError

from revue_portee.domain.criteria import ImmutableVersionError, VersionStatus
from revue_portee.domain.grid import GridField, GridVersion, field_sort_key
from revue_portee.storage.db import grid_field, grid_field_code, grid_version

__all__ = [
    "delete_draft",
    "get_active_version",
    "get_draft_version",
    "get_version",
    "get_version_by_number",
    "insert_version",
    "list_versions",
    "register_code",
    "replace_draft_fields",
    "update_version_status",
    "used_codes",
]


@contextmanager
def _immutability_errors() -> Iterator[None]:
    try:
        yield
    except IntegrityError as error:
        if "immutable" in str(error.orig):
            raise ImmutableVersionError(str(error.orig)) from error
        raise


def _rows(version: GridVersion) -> list[dict[str, object]]:
    return [
        {
            "version_id": version.id,
            "code": f.code,
            "label": f.label,
            "type": f.type.value,
            "definition": f.definition,
            "guidance": f.guidance,
            "examples_json": json.dumps(list(f.examples), ensure_ascii=False),
            "choices_json": json.dumps(list(f.choices), ensure_ascii=False),
        }
        for f in version.fields
    ]


def insert_version(
    connection: Connection, version: GridVersion, *, journal_entry_id: str | None = None
) -> None:
    with _immutability_errors():
        connection.execute(
            grid_version.insert().values(
                id=version.id,
                number=version.number,
                parent_id=version.parent_id,
                status=version.status.value,
                created_at=version.created_at,
                activated_at=version.activated_at,
                author_id=version.author_id,
                rationale=version.rationale,
                journal_entry_id=journal_entry_id,
            )
        )
        rows = _rows(version)
        if rows:
            connection.execute(grid_field.insert(), rows)


def replace_draft_fields(connection: Connection, version: GridVersion) -> None:
    with _immutability_errors():
        connection.execute(grid_field.delete().where(grid_field.c.version_id == version.id))
        rows = _rows(version)
        if rows:
            connection.execute(grid_field.insert(), rows)


def delete_draft(connection: Connection, version: GridVersion) -> None:
    with _immutability_errors():
        connection.execute(grid_field.delete().where(grid_field.c.version_id == version.id))
        connection.execute(grid_version.delete().where(grid_version.c.id == version.id))


def update_version_status(
    connection: Connection, version: GridVersion, *, journal_entry_id: str | None = None
) -> None:
    values: dict[str, object] = {
        "status": version.status.value,
        "activated_at": version.activated_at,
        "rationale": version.rationale,
    }
    if journal_entry_id is not None:
        values["journal_entry_id"] = journal_entry_id
    with _immutability_errors():
        connection.execute(
            grid_version.update().where(grid_version.c.id == version.id).values(**values)
        )


def _load(connection: Connection, row: dict[str, object]) -> GridVersion:
    rows = connection.execute(
        select(grid_field).where(grid_field.c.version_id == row["id"])
    ).mappings()
    fields = sorted(
        (
            GridField(
                code=r["code"],
                label=r["label"],
                type=r["type"],
                definition=r["definition"],
                guidance=r["guidance"],
                examples=tuple(json.loads(r["examples_json"])),
                choices=tuple(json.loads(r["choices_json"])),
            )
            for r in rows
        ),
        key=lambda f: field_sort_key(f.code),
    )
    data = {key: value for key, value in row.items() if key != "journal_entry_id"}
    return GridVersion.model_validate(data | {"fields": tuple(fields)})


def _one(connection: Connection, *conditions: object) -> GridVersion | None:
    rows = connection.execute(select(grid_version).where(*conditions)).mappings()  # type: ignore[arg-type]
    found = rows.one_or_none()
    return None if found is None else _load(connection, dict(found))


def get_version(connection: Connection, version_id: str) -> GridVersion | None:
    return _one(connection, grid_version.c.id == version_id)


def get_version_by_number(connection: Connection, number: int) -> GridVersion | None:
    return _one(connection, grid_version.c.number == number)


def get_active_version(connection: Connection) -> GridVersion | None:
    return _one(connection, grid_version.c.status == VersionStatus.ACTIVE.value)


def get_draft_version(connection: Connection) -> GridVersion | None:
    return _one(connection, grid_version.c.status == VersionStatus.DRAFT.value)


def list_versions(connection: Connection) -> list[GridVersion]:
    rows = connection.execute(select(grid_version).order_by(grid_version.c.number))
    return [_load(connection, dict(row)) for row in rows.mappings()]


def register_code(connection: Connection, code: str, *, version_id: str, now: datetime) -> None:
    """Record a newly given code, so that it is never given to another field."""
    connection.execute(
        grid_field_code.insert().values(code=code, first_version_id=version_id, created_at=now)
    )


def used_codes(connection: Connection) -> set[str]:
    return set(connection.execute(select(grid_field_code.c.code)).scalars())
