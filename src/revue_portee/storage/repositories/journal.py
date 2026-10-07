"""Append-only journal: each new entry is chained to the last stored one."""

import json
from collections.abc import Mapping
from datetime import datetime

from pydantic import JsonValue
from sqlalchemy import Connection, func, select

from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import (
    GENESIS_HASH,
    ChainCheck,
    JournalEntry,
    canonical_json,
    seal,
    verify_chain,
)
from revue_portee.storage.db import journal_entry

__all__ = ["append_entry", "count_entries", "list_entries", "verify"]


def append_entry(
    connection: Connection,
    *,
    now: datetime,
    actor_reviewer_id: str | None,
    entry_type: str,
    summary_fr: str,
    tool_version: str,
    subject_type: str | None = None,
    subject_id: str | None = None,
    payload: Mapping[str, JsonValue] | None = None,
) -> JournalEntry:
    """Seal and store the next entry. Call inside the transaction of the action it records."""
    last = connection.execute(
        select(journal_entry.c.position, journal_entry.c.hash)
        .order_by(journal_entry.c.position.desc())
        .limit(1)
    ).one_or_none()
    position, prev_hash = (0, GENESIS_HASH) if last is None else (last.position + 1, last.hash)
    entry = seal(
        entry_id=new_ulid(now),
        created_at=now,
        actor_reviewer_id=actor_reviewer_id,
        entry_type=entry_type,
        summary_fr=summary_fr,
        tool_version=tool_version,
        prev_hash=prev_hash,
        subject_type=subject_type,
        subject_id=subject_id,
        payload=payload,
    )
    data = entry.model_dump(exclude={"payload"})
    connection.execute(
        journal_entry.insert().values(
            **data, position=position, payload_json=canonical_json(entry.payload)
        )
    )
    return entry


def list_entries(connection: Connection) -> list[JournalEntry]:
    rows = connection.execute(select(journal_entry).order_by(journal_entry.c.position)).mappings()
    entries = []
    for row in rows:
        data = {k: v for k, v in row.items() if k not in {"position", "payload_json"}}
        entries.append(
            JournalEntry.model_validate(data | {"payload": json.loads(row["payload_json"])})
        )
    return entries


def count_entries(connection: Connection) -> int:
    return int(connection.execute(select(func.count()).select_from(journal_entry)).scalar_one())


def verify(connection: Connection) -> ChainCheck:
    """Recompute the whole chain from the stored entries."""
    return verify_chain(list_entries(connection))
