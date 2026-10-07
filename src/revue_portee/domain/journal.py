"""Append-only project journal with a hash chain (EF-PRJ-02, ENF-TRA-02).

Each entry stores the SHA-256 digest of its own canonical content, which includes the
digest of the previous entry. Altering, removing or reordering any entry breaks the
chain from that point on, which :func:`verify_chain` detects.
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue

__all__ = [
    "GENESIS_HASH",
    "ChainCheck",
    "EntryType",
    "JournalEntry",
    "canonical_json",
    "entry_digest",
    "seal",
    "verify_chain",
]

GENESIS_HASH = "0" * 64


class EntryType:
    """Journal entry types used so far (docs/03-architecture.md §5.1)."""

    PROJECT_CREATED = "project.created"
    PROJECT_OPENED = "project.opened"
    NOTE_ADDED = "note.added"
    FRAMING_UPDATED = "framing.updated"
    CRITERIA_DRAFT_STARTED = "criteria.draft_started"
    CRITERIA_DRAFT_EDITED = "criteria.draft_edited"
    CRITERIA_DRAFT_DISCARDED = "criteria.draft_discarded"
    CRITERIA_VERSION_CREATED = "criteria.version_created"


class JournalEntry(BaseModel):
    """One sealed journal entry (table ``journal_entry``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    created_at: AwareDatetime
    actor_reviewer_id: str | None
    entry_type: str = Field(pattern=r"^[a-z_]+\.[a-z_]+$")
    subject_type: str | None = None
    subject_id: str | None = None
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    summary_fr: str
    tool_version: str
    prev_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    hash: str = Field(pattern=r"^[0-9a-f]{64}$")


def canonical_json(value: object) -> str:
    """Deterministic JSON: sorted keys, no spaces, UTF-8 kept as is."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _timestamp(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def entry_digest(fields: Mapping[str, object], prev_hash: str) -> str:
    """SHA-256 of the canonical content of an entry and of the previous digest."""
    content = {
        "id": fields["id"],
        "created_at": _timestamp(fields["created_at"]),  # type: ignore[arg-type]
        "actor_reviewer_id": fields["actor_reviewer_id"],
        "entry_type": fields["entry_type"],
        "subject_type": fields.get("subject_type"),
        "subject_id": fields.get("subject_id"),
        "payload": fields.get("payload", {}),
        "summary_fr": fields["summary_fr"],
        "tool_version": fields["tool_version"],
        "prev_hash": prev_hash,
    }
    return hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest()


def seal(
    *,
    entry_id: str,
    created_at: datetime,
    actor_reviewer_id: str | None,
    entry_type: str,
    summary_fr: str,
    tool_version: str,
    prev_hash: str,
    subject_type: str | None = None,
    subject_id: str | None = None,
    payload: Mapping[str, JsonValue] | None = None,
) -> JournalEntry:
    """Build the next entry of the chain, whose predecessor has digest ``prev_hash``."""
    fields: dict[str, object] = {
        "id": entry_id,
        "created_at": created_at,
        "actor_reviewer_id": actor_reviewer_id,
        "entry_type": entry_type,
        "subject_type": subject_type,
        "subject_id": subject_id,
        # Round-trip through canonical JSON: the stored payload is exactly what is hashed.
        "payload": json.loads(canonical_json(dict(payload or {}))),
        "summary_fr": summary_fr,
        "tool_version": tool_version,
    }
    return JournalEntry.model_validate(
        fields | {"prev_hash": prev_hash, "hash": entry_digest(fields, prev_hash)}
    )


class ChainCheck(BaseModel):
    """Result of a chain verification."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    valid: bool
    checked: int
    first_invalid_index: int | None = None
    first_invalid_id: str | None = None
    reason: str | None = None


def verify_chain(entries: Sequence[JournalEntry]) -> ChainCheck:
    """Check every digest and link, in storage order, from the genesis value."""
    expected_prev = GENESIS_HASH
    for index, entry in enumerate(entries):
        if entry.prev_hash != expected_prev:
            return ChainCheck(
                valid=False,
                checked=index,
                first_invalid_index=index,
                first_invalid_id=entry.id,
                reason="broken_link",
            )
        if entry_digest(entry.model_dump(), entry.prev_hash) != entry.hash:
            return ChainCheck(
                valid=False,
                checked=index,
                first_invalid_index=index,
                first_invalid_id=entry.id,
                reason="content_altered",
            )
        expected_prev = entry.hash
    return ChainCheck(valid=True, checked=len(entries))
