"""SQLite schema (SQLAlchemy Core) and engine for a project's ``revue.sqlite``.

The schema itself is created and evolved by Alembic (``storage/migrations``); the
table objects below are what the repositories query. A test checks that both agree.
Append-only rules (ENF-TRA-02) are enforced by SQLite triggers, so that they hold even
for code that bypasses the repositories.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    Connection,
    Date,
    Dialect,
    Engine,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    TypeDecorator,
    create_engine,
    event,
    text,
)
from sqlalchemy.pool import ConnectionPoolEntry

__all__ = [
    "DecimalText",
    "UTCDateTime",
    "ai_call",
    "ai_config",
    "ai_suggestion",
    "collection_end",
    "collection_page",
    "collection_run",
    "create_project_engine",
    "criteria_version",
    "criterion",
    "criterion_change",
    "criterion_code",
    "descriptor_check",
    "enrichment",
    "framing_version",
    "import_file",
    "journal_entry",
    "key_article_set_version",
    "metadata",
    "project",
    "protocol_registration",
    "protocol_text_version",
    "provenance",
    "qualification_proposal",
    "query",
    "reference",
    "reviewer",
    "search_run",
    "search_strategy_version",
    "sensitivity_check",
    "suggestion_review",
    "term_suggestion",
    "term_suggestion_review",
    "write_transaction",
]


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware datetime stored as ISO 8601 text in UTC, with microseconds."""

    impl = String(32)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("datetimes must be timezone-aware")
        return value.astimezone(UTC).isoformat(timespec="microseconds")

    def process_result_value(self, value: str | None, dialect: Dialect) -> datetime | None:
        return None if value is None else datetime.fromisoformat(value)


class DecimalText(TypeDecorator[Decimal]):
    """Exact decimal amount (costs) stored as text."""

    impl = String(32)
    cache_ok = True

    def process_bind_param(self, value: Decimal | None, dialect: Dialect) -> str | None:
        return None if value is None else str(value)

    def process_result_value(self, value: str | None, dialect: Dialect) -> Decimal | None:
        return None if value is None else Decimal(value)


metadata = MetaData()

project = Table(
    "project",
    metadata,
    Column("id", String(26), primary_key=True),
    Column("title", Text, nullable=False),
    Column("language", String(2), nullable=False),
    Column("description", Text, nullable=False, server_default=""),
    Column("created_at", UTCDateTime, nullable=False),
    Column("format_version", String(16), nullable=False),
)

reviewer = Table(
    "reviewer",
    metadata,
    Column("id", String(26), primary_key=True),
    Column("kind", String(8), nullable=False),
    Column("display_name", Text, nullable=False),
    Column("role", Text, nullable=False, server_default=""),
    Column("ai_config_id", String(26), nullable=True),
    Column("active", Boolean, nullable=False, server_default=text("1")),
    Column("created_at", UTCDateTime, nullable=False),
)

journal_entry = Table(
    "journal_entry",
    metadata,
    Column("id", String(26), primary_key=True),
    # Storage order of the hash chain (0, 1, 2…), local to the project.
    Column("position", Integer, nullable=False, unique=True),
    Column("created_at", UTCDateTime, nullable=False),
    Column("actor_reviewer_id", String(26), ForeignKey("reviewer.id"), nullable=True),
    Column("entry_type", String(64), nullable=False),
    Column("subject_type", String(64), nullable=True),
    Column("subject_id", String(26), nullable=True),
    Column("payload_json", Text, nullable=False),
    Column("summary_fr", Text, nullable=False),
    Column("tool_version", Text, nullable=False),
    Column("prev_hash", String(64), nullable=False),
    Column("hash", String(64), nullable=False, unique=True),
)

framing_version = Table(
    "framing_version",
    metadata,
    Column("id", String(26), primary_key=True),
    Column("number", Integer, nullable=False, unique=True),
    Column("created_at", UTCDateTime, nullable=False),
    Column("author_id", String(26), ForeignKey("reviewer.id"), nullable=False),
    Column("question", Text, nullable=False),
    Column("population", Text, nullable=False),
    Column("concept", Text, nullable=False),
    Column("context", Text, nullable=False),
    Column("secondary_questions_json", Text, nullable=False),
    Column("journal_entry_id", String(26), ForeignKey("journal_entry.id"), nullable=False),
)

criteria_version = Table(
    "criteria_version",
    metadata,
    Column("id", String(26), primary_key=True),
    Column("number", Integer, nullable=False, unique=True),
    Column("parent_id", String(26), ForeignKey("criteria_version.id"), nullable=True),
    Column("status", String(16), nullable=False),
    Column("created_at", UTCDateTime, nullable=False),
    Column("activated_at", UTCDateTime, nullable=True),
    Column("author_id", String(26), ForeignKey("reviewer.id"), nullable=False),
    Column("rationale", Text, nullable=False, server_default=""),
    Column("journal_entry_id", String(26), ForeignKey("journal_entry.id"), nullable=True),
    Column("after_protocol_registration", Boolean, nullable=False, server_default=text("0")),
    # At most one active version and one draft at a time.
    Index(
        "uq_criteria_version_one_active",
        "status",
        unique=True,
        sqlite_where=text("status = 'active'"),
    ),
    Index(
        "uq_criteria_version_one_draft",
        "status",
        unique=True,
        sqlite_where=text("status = 'draft'"),
    ),
)

criterion = Table(
    "criterion",
    metadata,
    Column("version_id", String(26), ForeignKey("criteria_version.id"), nullable=False),
    Column("code", String(16), nullable=False),
    Column("pcc_element", String(16), nullable=False),
    Column("kind", String(16), nullable=False),
    Column("text", Text, nullable=False),
    Column("guidance", Text, nullable=False, server_default=""),
    Column("examples_json", Text, nullable=False, server_default="[]"),
    Column("counterexamples_json", Text, nullable=False, server_default="[]"),
    PrimaryKeyConstraint("version_id", "code"),
)


# Registry of every criterion code ever assigned, append-only (D-026, option A).
# No foreign key: a code first assigned in a discarded draft keeps its row.
criterion_code = Table(
    "criterion_code",
    metadata,
    Column("code", String(16), primary_key=True),
    Column("pcc_element", String(16), nullable=False),
    Column("first_version_id", String(26), nullable=False),
    Column("created_at", UTCDateTime, nullable=False),
)


# --- AI configuration and calls (docs/03-architecture.md §5.1, §5.6) -------------------

ai_config = Table(
    "ai_config",
    metadata,
    Column("id", String(26), primary_key=True),
    Column("task", String(64), nullable=False),
    Column("provider", String(32), nullable=False),
    Column("model_requested", Text, nullable=False),
    Column("prompt_template_id", String(64), nullable=False),
    Column("prompt_template_version", String(16), nullable=False),
    Column("params_json", Text, nullable=False),
    Column("created_at", UTCDateTime, nullable=False),
)

ai_call = Table(
    "ai_call",
    metadata,
    Column("id", String(26), primary_key=True),
    Column("ai_config_id", String(26), ForeignKey("ai_config.id"), nullable=False),
    Column("task", String(64), nullable=False),
    Column("item_id", Text, nullable=False),
    Column("provider", String(32), nullable=False),
    Column("model_requested", Text, nullable=False),
    Column("model_returned", Text, nullable=True),
    Column("provider_request_id", Text, nullable=True),
    Column("prompt_template_id", String(64), nullable=False),
    Column("prompt_template_version", String(16), nullable=False),
    Column("prompt_sha256", String(64), nullable=False),
    Column("params_json", Text, nullable=False),
    Column("input_tokens", Integer, nullable=False),
    Column("output_tokens", Integer, nullable=False),
    Column("cache_read_tokens", Integer, nullable=False),
    Column("cache_write_tokens", Integer, nullable=False),
    Column("cost_estimate", DecimalText, nullable=False),
    Column("currency", String(3), nullable=False),
    Column("latency_ms", Integer, nullable=False),
    Column("batch_id", Text, nullable=True),
    Column("response_path", Text, nullable=True),
    Column("status", String(8), nullable=False),
    Column("error_code", Text, nullable=True),
    Column("created_at", UTCDateTime, nullable=False),
)

# --- Framing suggestions (EF-CAD-02) ------------------------------------------------

ai_suggestion = Table(
    "ai_suggestion",
    metadata,
    Column("id", String(26), primary_key=True),
    Column("ai_call_id", String(26), ForeignKey("ai_call.id"), nullable=False),
    Column("position", Integer, nullable=False),
    Column("kind", String(32), nullable=False),
    Column("text", Text, nullable=False),
    Column("rationale", Text, nullable=False),
    Column("created_at", UTCDateTime, nullable=False),
)

suggestion_review = Table(
    "suggestion_review",
    metadata,
    Column("id", String(26), primary_key=True),
    # One human decision per suggestion, never changed.
    Column(
        "suggestion_id", String(26), ForeignKey("ai_suggestion.id"), nullable=False, unique=True
    ),
    Column("outcome", String(16), nullable=False),
    Column("final_text", Text, nullable=False),
    Column("reviewer_id", String(26), ForeignKey("reviewer.id"), nullable=False),
    Column("created_at", UTCDateTime, nullable=False),
    Column("framing_version_id", String(26), ForeignKey("framing_version.id"), nullable=True),
    Column("journal_entry_id", String(26), ForeignKey("journal_entry.id"), nullable=False),
)

# --- Qualification of criteria changes (EF-VER-03) ----------------------------------

# No foreign key to the draft: a discarded draft is deleted, its proposals stay.
qualification_proposal = Table(
    "qualification_proposal",
    metadata,
    Column("id", String(26), primary_key=True),
    Column("draft_version_id", String(26), nullable=False),
    Column("code", String(16), nullable=False),
    Column("ai_call_id", String(26), ForeignKey("ai_call.id"), nullable=False),
    Column("change_type", String(16), nullable=False),
    Column("confidence", Float, nullable=True),
    Column("rationale", Text, nullable=False),
    Column("after_json", Text, nullable=False),
    Column("created_at", UTCDateTime, nullable=False),
)

criterion_change = Table(
    "criterion_change",
    metadata,
    Column("id", String(26), primary_key=True),
    Column("from_version_id", String(26), ForeignKey("criteria_version.id"), nullable=False),
    Column("to_version_id", String(26), ForeignKey("criteria_version.id"), nullable=False),
    Column("code", String(16), nullable=False),
    Column("change_type", String(16), nullable=False),
    Column("proposed_by", String(8), nullable=False),
    Column("proposal_id", String(26), ForeignKey("qualification_proposal.id"), nullable=True),
    Column("confirmed_by", String(26), ForeignKey("reviewer.id"), nullable=False),
    Column("created_at", UTCDateTime, nullable=False),
    Column("journal_entry_id", String(26), ForeignKey("journal_entry.id"), nullable=False),
)

# --- Protocol (EF-CAD-06 to 08) -----------------------------------------------------

protocol_text_version = Table(
    "protocol_text_version",
    metadata,
    Column("id", String(26), primary_key=True),
    Column("number", Integer, nullable=False, unique=True),
    Column("created_at", UTCDateTime, nullable=False),
    Column("author_id", String(26), ForeignKey("reviewer.id"), nullable=False),
    Column("sections_json", Text, nullable=False),
    Column("journal_entry_id", String(26), ForeignKey("journal_entry.id"), nullable=False),
)

protocol_registration = Table(
    "protocol_registration",
    metadata,
    Column("id", String(26), primary_key=True),
    Column("doi", Text, nullable=False),
    Column("registered_on", Date, nullable=False),
    Column("criteria_version_id", String(26), ForeignKey("criteria_version.id"), nullable=True),
    Column("created_at", UTCDateTime, nullable=False),
    Column("reviewer_id", String(26), ForeignKey("reviewer.id"), nullable=False),
    Column("journal_entry_id", String(26), ForeignKey("journal_entry.id"), nullable=False),
)


# --- Search (EF-REC-01 to 06) ---------------------------------------------------

search_strategy_version = Table(
    "search_strategy_version",
    metadata,
    Column("id", String(26), primary_key=True),
    Column("number", Integer, unique=True, nullable=False),
    Column("created_at", UTCDateTime, nullable=False),
    Column("author_id", String(26), ForeignKey("reviewer.id"), nullable=False),
    Column("rationale", Text, nullable=False),
    Column("strategy_json", Text, nullable=False),
    Column("journal_entry_id", String(26), ForeignKey("journal_entry.id"), nullable=False),
)


query = Table(
    "query",
    metadata,
    Column("id", String(26), primary_key=True),
    Column(
        "strategy_version_id", String(26), ForeignKey("search_strategy_version.id"), nullable=False
    ),
    Column("database", String(32), nullable=False),
    Column("syntax_text", Text, nullable=False),
    Column("blocks_json", Text, nullable=False),
    Column("limits_text", Text, nullable=False),
    Column("warnings_json", Text, nullable=False),
    Column("generated_by", String(32), nullable=False),
    Column("edited", Boolean, nullable=False),
    Column("created_at", UTCDateTime, nullable=False),
    Index("ix_query_strategy_version", "strategy_version_id", "database", unique=True),
)


search_run = Table(
    "search_run",
    metadata,
    Column("id", String(26), primary_key=True),
    Column("query_id", String(26), ForeignKey("query.id"), nullable=False),
    Column("kind", String(16), nullable=False),
    Column("executed_at", UTCDateTime, nullable=False),
    Column("result_count", Integer, nullable=True),
    Column("blocks_json", Text, nullable=False),
    Column("status", String(16), nullable=False),
    Column("raw_dir", Text, nullable=False),
    Column("reviewer_id", String(26), ForeignKey("reviewer.id"), nullable=False),
    Column("journal_entry_id", String(26), ForeignKey("journal_entry.id"), nullable=False),
    Index("ix_search_run_query", "query_id"),
)


key_article_set_version = Table(
    "key_article_set_version",
    metadata,
    Column("id", String(26), primary_key=True),
    Column("number", Integer, unique=True, nullable=False),
    Column("created_at", UTCDateTime, nullable=False),
    Column("author_id", String(26), ForeignKey("reviewer.id"), nullable=False),
    Column("articles_json", Text, nullable=False),
    Column("journal_entry_id", String(26), ForeignKey("journal_entry.id"), nullable=False),
)


sensitivity_check = Table(
    "sensitivity_check",
    metadata,
    Column("id", String(26), primary_key=True),
    Column("search_run_id", String(26), ForeignKey("search_run.id"), nullable=False),
    Column(
        "key_article_set_version_id",
        String(26),
        ForeignKey("key_article_set_version.id"),
        nullable=False,
    ),
    Column("found", Integer, nullable=False),
    Column("indexed", Integer, nullable=False),
    Column("outcomes_json", Text, nullable=False),
)


descriptor_check = Table(
    "descriptor_check",
    metadata,
    Column("id", String(26), primary_key=True),
    Column("created_at", UTCDateTime, nullable=False),
    Column("vocabulary", String(16), nullable=False),
    Column("heading", Text, nullable=False),
    Column("found", Boolean, nullable=False),
    Column("official_heading", Text, nullable=True),
    Column("descriptor_ui", Text, nullable=True),
    Column("raw_dir", Text, nullable=False),
    Column("reviewer_id", String(26), ForeignKey("reviewer.id"), nullable=False),
    Column("journal_entry_id", String(26), ForeignKey("journal_entry.id"), nullable=False),
    Index("ix_descriptor_check_heading", "vocabulary", "heading"),
)


term_suggestion = Table(
    "term_suggestion",
    metadata,
    Column("id", String(26), primary_key=True),
    Column("ai_call_id", String(26), ForeignKey("ai_call.id"), nullable=False),
    Column(
        "strategy_version_id", String(26), ForeignKey("search_strategy_version.id"), nullable=False
    ),
    Column("position", Integer, nullable=False),
    Column("block_code", String(16), nullable=False),
    Column("kind", String(32), nullable=False),
    Column("line", Text, nullable=False),
    Column("rationale", Text, nullable=False),
    Column("created_at", UTCDateTime, nullable=False),
)


term_suggestion_review = Table(
    "term_suggestion_review",
    metadata,
    Column("id", String(26), primary_key=True),
    Column(
        "suggestion_id", String(26), ForeignKey("term_suggestion.id"), unique=True, nullable=False
    ),
    Column("outcome", String(16), nullable=False),
    Column("final_line", Text, nullable=False),
    Column("reviewer_id", String(26), ForeignKey("reviewer.id"), nullable=False),
    Column("created_at", UTCDateTime, nullable=False),
    Column(
        "strategy_version_id", String(26), ForeignKey("search_strategy_version.id"), nullable=True
    ),
    Column("journal_entry_id", String(26), ForeignKey("journal_entry.id"), nullable=False),
)


# --- References and collection (EF-COL-01 to 05) ---------------------------------

reference = Table(
    "reference",
    metadata,
    Column("id", String(26), primary_key=True),
    Column("title", Text, nullable=False),
    Column("abstract", Text, nullable=False),
    Column("authors_json", Text, nullable=False),
    Column("year", Integer, nullable=True),
    Column("container_title", Text, nullable=False),
    Column("volume", Text, nullable=False),
    Column("issue", Text, nullable=False),
    Column("pages", Text, nullable=False),
    Column("doi", Text, nullable=False),
    Column("pmid", Text, nullable=False),
    Column("openalex_id", Text, nullable=False),
    Column("language", Text, nullable=False),
    Column("doc_type", Text, nullable=False),
    Column("url", Text, nullable=False),
    Column("created_at", UTCDateTime, nullable=False),
    Index("ix_reference_doi", "doi"),
    Index("ix_reference_pmid", "pmid"),
    Index("ix_reference_openalex", "openalex_id"),
)


collection_run = Table(
    "collection_run",
    metadata,
    Column("id", String(26), primary_key=True),
    Column("query_id", String(26), ForeignKey("query.id"), nullable=False),
    Column("database", String(32), nullable=False),
    Column("query_text", Text, nullable=False),
    Column("started_at", UTCDateTime, nullable=False),
    Column("reviewer_id", String(26), ForeignKey("reviewer.id"), nullable=False),
    Column("journal_entry_id", String(26), ForeignKey("journal_entry.id"), nullable=False),
)


collection_page = Table(
    "collection_page",
    metadata,
    Column("run_id", String(26), ForeignKey("collection_run.id"), nullable=False),
    Column("number", Integer, nullable=False),
    Column("announced", Integer, nullable=False),
    Column("record_count", Integer, nullable=False),
    Column("new_references", Integer, nullable=False),
    Column("next_cursor", Text, nullable=True),
    Column("raw_path", Text, nullable=False),
    Column("created_at", UTCDateTime, nullable=False),
    Column("journal_entry_id", String(26), ForeignKey("journal_entry.id"), nullable=False),
    PrimaryKeyConstraint("run_id", "number"),
)


collection_end = Table(
    "collection_end",
    metadata,
    Column("run_id", String(26), ForeignKey("collection_run.id"), unique=True, nullable=False),
    Column("status", String(16), nullable=False),
    Column("announced", Integer, nullable=True),
    Column("collected", Integer, nullable=False),
    Column("discrepancy", Text, nullable=False),
    Column("error", Text, nullable=False),
    Column("ended_at", UTCDateTime, nullable=False),
    Column("journal_entry_id", String(26), ForeignKey("journal_entry.id"), nullable=False),
)


import_file = Table(
    "import_file",
    metadata,
    Column("id", String(26), primary_key=True),
    Column("filename", Text, nullable=False),
    Column("sha256", String(64), unique=True, nullable=False),
    Column("format", String(16), nullable=False),
    Column("database_declared", Text, nullable=False),
    Column("imported_at", UTCDateTime, nullable=False),
    Column("record_count", Integer, nullable=False),
    Column("issues_json", Text, nullable=False),
    Column("reviewer_id", String(26), ForeignKey("reviewer.id"), nullable=False),
    Column("journal_entry_id", String(26), ForeignKey("journal_entry.id"), nullable=False),
)


provenance = Table(
    "provenance",
    metadata,
    Column("id", String(26), primary_key=True),
    Column("reference_id", String(26), ForeignKey("reference.id"), nullable=False),
    Column("source", String(16), nullable=False),
    Column("original_id", Text, nullable=False),
    Column("collection_run_id", String(26), ForeignKey("collection_run.id"), nullable=True),
    Column("import_file_id", String(26), ForeignKey("import_file.id"), nullable=True),
    Column("query_id", String(26), ForeignKey("query.id"), nullable=True),
    Column("page", Integer, nullable=True),
    Column("created_at", UTCDateTime, nullable=False),
    Index("ix_provenance_source_id", "source", "original_id"),
    Index("ix_provenance_reference", "reference_id"),
    Index(
        "uq_provenance_run_record",
        "collection_run_id",
        "original_id",
        unique=True,
        sqlite_where=text("collection_run_id IS NOT NULL"),
    ),
)


enrichment = Table(
    "enrichment",
    metadata,
    Column("id", String(26), primary_key=True),
    Column("reference_id", String(26), ForeignKey("reference.id"), nullable=False),
    Column("source", String(16), nullable=False),
    Column("fields_json", Text, nullable=False),
    Column("raw_dir", Text, nullable=False),
    Column("created_at", UTCDateTime, nullable=False),
    Column("journal_entry_id", String(26), ForeignKey("journal_entry.id"), nullable=False),
    Index("ix_enrichment_reference", "reference_id"),
)


def _on_connect(dbapi_connection: object, _record: ConnectionPoolEntry) -> None:
    # Let SQLAlchemy emit BEGIN itself (see _on_begin) instead of the sqlite3 module.
    dbapi_connection.isolation_level = None  # type: ignore[attr-defined]
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()


def _on_begin(connection: Connection) -> None:
    # Writes take the database lock as soon as the transaction starts: a use case
    # that reads (e.g. the last journal entry) before writing cannot then collide
    # with a concurrent writer (concurrent web requests, two browser tabs).
    mode = "IMMEDIATE" if connection.get_execution_options().get(WRITE_OPTION) else "DEFERRED"
    connection.exec_driver_sql(f"BEGIN {mode}")


WRITE_OPTION = "revue_portee_write"


def create_project_engine(database: Path) -> Engine:
    """Engine for one project database, with foreign keys enforced.

    Use :func:`write_transaction` for every transaction that writes.
    """
    engine = create_engine(f"sqlite:///{database}", connect_args={"timeout": 30})
    event.listen(engine, "connect", _on_connect)
    event.listen(engine, "begin", _on_begin)
    return engine


@contextmanager
def write_transaction(engine: Engine) -> Iterator[Connection]:
    """Transaction that holds the write lock from its first statement (BEGIN IMMEDIATE)."""
    with engine.connect() as connection:
        connection.execution_options(**{WRITE_OPTION: True})
        with connection.begin():
            yield connection
