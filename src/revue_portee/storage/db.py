"""SQLite schema (SQLAlchemy Core) and engine for a project's ``revue.sqlite``.

The schema itself is created and evolved by Alembic (``storage/migrations``); the
table objects below are what the repositories query. A test checks that both agree.
Append-only rules (ENF-TRA-02) are enforced by SQLite triggers, so that they hold even
for code that bypasses the repositories.
"""

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    Dialect,
    Engine,
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
    "UTCDateTime",
    "create_project_engine",
    "criteria_version",
    "criterion",
    "framing_version",
    "journal_entry",
    "metadata",
    "project",
    "reviewer",
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


def _enable_foreign_keys(dbapi_connection: object, _record: ConnectionPoolEntry) -> None:
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()


def create_project_engine(database: Path) -> Engine:
    """Engine for one project database, with foreign keys enforced."""
    engine = create_engine(f"sqlite:///{database}")
    event.listen(engine, "connect", _enable_foreign_keys)
    return engine
