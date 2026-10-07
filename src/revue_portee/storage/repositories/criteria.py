"""Criteria versions and their criteria.

Writes that the database refuses (immutable version) surface as
:class:`~revue_portee.domain.criteria.ImmutableVersionError`.
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Connection, select
from sqlalchemy.exc import IntegrityError

from revue_portee.domain.criteria import (
    CriteriaVersion,
    Criterion,
    ImmutableVersionError,
    VersionStatus,
    code_sort_key,
)
from revue_portee.storage.db import criteria_version, criterion

__all__ = [
    "delete_draft",
    "get_active_version",
    "get_draft_version",
    "get_version",
    "get_version_by_number",
    "insert_version",
    "list_versions",
    "replace_draft_criteria",
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


def _criterion_rows(version: CriteriaVersion) -> list[dict[str, object]]:
    return [
        {
            "version_id": version.id,
            "code": c.code,
            "pcc_element": c.pcc_element.value,
            "kind": c.kind.value,
            "text": c.text,
            "guidance": c.guidance,
            "examples_json": json.dumps(list(c.examples), ensure_ascii=False),
            "counterexamples_json": json.dumps(list(c.counterexamples), ensure_ascii=False),
        }
        for c in version.criteria
    ]


def insert_version(
    connection: Connection, version: CriteriaVersion, *, journal_entry_id: str | None = None
) -> None:
    """Store a new version (normally a draft) and its criteria."""
    with _immutability_errors():
        connection.execute(
            criteria_version.insert().values(
                id=version.id,
                number=version.number,
                parent_id=version.parent_id,
                status=version.status.value,
                created_at=version.created_at,
                activated_at=version.activated_at,
                author_id=version.author_id,
                rationale=version.rationale,
                journal_entry_id=journal_entry_id,
                after_protocol_registration=version.after_protocol_registration,
            )
        )
        rows = _criterion_rows(version)
        if rows:
            connection.execute(criterion.insert(), rows)


def replace_draft_criteria(connection: Connection, version: CriteriaVersion) -> None:
    """Store the new criteria of a draft (the database refuses it for other statuses)."""
    with _immutability_errors():
        connection.execute(criterion.delete().where(criterion.c.version_id == version.id))
        rows = _criterion_rows(version)
        if rows:
            connection.execute(criterion.insert(), rows)


def delete_draft(connection: Connection, version: CriteriaVersion) -> None:
    """Remove a draft and its criteria (the database refuses it for other statuses)."""
    with _immutability_errors():
        connection.execute(criterion.delete().where(criterion.c.version_id == version.id))
        connection.execute(criteria_version.delete().where(criteria_version.c.id == version.id))


def update_version_status(
    connection: Connection, version: CriteriaVersion, *, journal_entry_id: str | None = None
) -> None:
    """Persist an activation (draft -> active) or a supersession (active -> superseded)."""
    values: dict[str, object] = {
        "status": version.status.value,
        "activated_at": version.activated_at,
        "rationale": version.rationale,
    }
    if journal_entry_id is not None:
        values["journal_entry_id"] = journal_entry_id
    with _immutability_errors():
        connection.execute(
            criteria_version.update().where(criteria_version.c.id == version.id).values(**values)
        )


def _load(connection: Connection, row: dict[str, object]) -> CriteriaVersion:
    rows = connection.execute(
        select(criterion).where(criterion.c.version_id == row["id"])
    ).mappings()
    criteria = sorted(
        (
            Criterion(
                code=r["code"],
                pcc_element=r["pcc_element"],
                kind=r["kind"],
                text=r["text"],
                guidance=r["guidance"],
                examples=tuple(json.loads(r["examples_json"])),
                counterexamples=tuple(json.loads(r["counterexamples_json"])),
            )
            for r in rows
        ),
        key=lambda c: code_sort_key(c.code),
    )
    data = {key: value for key, value in row.items() if key != "journal_entry_id"}
    return CriteriaVersion.model_validate(data | {"criteria": tuple(criteria)})


def _one(connection: Connection, *conditions: object) -> CriteriaVersion | None:
    row = connection.execute(select(criteria_version).where(*conditions)).mappings()  # type: ignore[arg-type]
    found = row.one_or_none()
    return None if found is None else _load(connection, dict(found))


def get_version(connection: Connection, version_id: str) -> CriteriaVersion | None:
    return _one(connection, criteria_version.c.id == version_id)


def get_version_by_number(connection: Connection, number: int) -> CriteriaVersion | None:
    return _one(connection, criteria_version.c.number == number)


def get_active_version(connection: Connection) -> CriteriaVersion | None:
    return _one(connection, criteria_version.c.status == VersionStatus.ACTIVE.value)


def get_draft_version(connection: Connection) -> CriteriaVersion | None:
    return _one(connection, criteria_version.c.status == VersionStatus.DRAFT.value)


def list_versions(connection: Connection) -> list[CriteriaVersion]:
    rows = connection.execute(select(criteria_version).order_by(criteria_version.c.number))
    return [_load(connection, dict(row)) for row in rows.mappings()]


def used_codes(connection: Connection) -> set[str]:
    """Every code present in any stored version (codes are never reused)."""
    return set(connection.execute(select(criterion.c.code).distinct()).scalars())
