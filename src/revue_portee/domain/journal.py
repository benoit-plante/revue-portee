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
    CRITERIA_CHANGE_PROPOSED = "criteria.change_proposed"
    CRITERIA_CHANGE_QUALIFIED = "criteria.change_qualified"
    AI_CONFIG_RECORDED = "ai.config_recorded"
    AI_CALL_FAILED = "ai.call_failed"
    AI_RESULT_UNUSABLE = "ai.result_unusable"
    FRAMING_SUGGESTIONS_RECEIVED = "framing.suggestions_received"
    FRAMING_SUGGESTION_REVIEWED = "framing.suggestion_reviewed"
    PROTOCOL_TEXT_UPDATED = "protocol.text_updated"
    PROTOCOL_REGISTERED = "protocol.registered"
    SEARCH_QUERY_VERSIONED = "search.query_versioned"
    SEARCH_RUN_COMPLETED = "search.run_completed"
    SEARCH_KEY_ARTICLES_UPDATED = "search.key_articles_updated"
    SEARCH_SENSITIVITY_CHECKED = "search.sensitivity_checked"
    SEARCH_DESCRIPTORS_CHECKED = "search.descriptors_checked"
    SEARCH_TERMS_SUGGESTED = "search.terms_suggested"
    SEARCH_TERM_SUGGESTION_REVIEWED = "search.term_suggestion_reviewed"
    COLLECT_STARTED = "collect.started"
    COLLECT_PAGE_STORED = "collect.page_stored"
    COLLECT_COMPLETED = "collect.completed"
    COLLECT_FAILED = "collect.failed"
    IMPORT_COMPLETED = "import.completed"
    ENRICH_COMPLETED = "enrich.completed"
    DEDUP_COMPLETED = "dedup.completed"
    DEDUP_PAIR_DECIDED = "dedup.pair_decided"
    PILOT_STARTED = "pilot.started"
    SCREENING_HUMAN_DECIDED = "screening.human_decided"
    SCREENING_AI_DECIDED = "screening.ai_decided"
    SCREENING_AI_FAILED = "screening.ai_failed"
    SCREENING_AI_BATCH_ENDED = "screening.ai_batch_ended"
    REVIEWER_AI_RECORDED = "reviewer.ai_recorded"
    CALIBRATION_FITTED = "calibration.fitted"
    THRESHOLDS_SET = "thresholds.set"
    BUDGET_SET = "budget.set"
    BUDGET_REACHED = "budget.reached"
    SCREENING_STARTED = "screening.started"
    SCREENING_MEMBERS_ADDED = "screening.members_added"
    SCREENING_AI_BATCH_SUBMITTED = "screening.ai_batch_submitted"
    SCREENING_RECONCILED = "screening.reconciled"
    IMPACT_ASSESSED = "impact.assessed"
    REASSESSMENT_STARTED = "reassessment.started"
    REASSESSMENT_DECIDED = "reassessment.decided"
    REASSESSMENT_COMPLETED = "reassessment.completed"
    ARCHIVE_EXPORTED = "archive.exported"
    FULLTEXT_OBTAINED = "fulltext.obtained"
    FULLTEXT_UPLOADED = "fulltext.uploaded"
    FULLTEXT_NOT_FOUND = "fulltext.not_found"
    FULLTEXT_NOT_RETRIEVABLE = "fulltext.not_retrievable"
    FULLTEXT_CONVERTED = "fulltext.converted"
    STUDY_LINK_ASSESSED = "study.link_assessed"
    STUDY_LINK_DECIDED = "study.link_decided"
    STUDY_PRIMARY_CHOSEN = "study.primary_chosen"
    GRID_DRAFT_STARTED = "grid.draft_started"
    GRID_DRAFT_EDITED = "grid.draft_edited"
    GRID_DRAFT_DISCARDED = "grid.draft_discarded"
    GRID_VERSION_CREATED = "grid.version_created"
    GRID_IMPACT_ASSESSED = "grid.impact_assessed"
    EXTRACTION_AI_PROPOSED = "extraction.ai_proposed"
    EXTRACTION_AI_FAILED = "extraction.ai_failed"
    EXTRACTION_VALUE_DECIDED = "extraction.value_decided"
    EXTRACTION_PILOT_STARTED = "extraction.pilot_started"


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
