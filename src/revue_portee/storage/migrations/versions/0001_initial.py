"""Initial schema: project, reviewers, journal, framing and criteria versions.

Revision ID: 0001
Revises:
Create Date: 2026-10-07
"""

import sqlalchemy as sa
from alembic import op

from revue_portee.storage.db import UTCDateTime

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Append-only rules (ENF-TRA-02), enforced by the database itself.
_TRIGGERS = (
    # The journal is never changed nor shortened.
    """CREATE TRIGGER journal_entry_no_update BEFORE UPDATE ON journal_entry
    BEGIN SELECT RAISE(ABORT, 'append-only: journal_entry'); END""",
    """CREATE TRIGGER journal_entry_no_delete BEFORE DELETE ON journal_entry
    BEGIN SELECT RAISE(ABORT, 'append-only: journal_entry'); END""",
    # Framing versions are never changed nor removed.
    """CREATE TRIGGER framing_version_no_update BEFORE UPDATE ON framing_version
    BEGIN SELECT RAISE(ABORT, 'append-only: framing_version'); END""",
    """CREATE TRIGGER framing_version_no_delete BEFORE DELETE ON framing_version
    BEGIN SELECT RAISE(ABORT, 'append-only: framing_version'); END""",
    # A criteria version that left draft never changes, except active -> superseded.
    """CREATE TRIGGER criteria_version_immutable BEFORE UPDATE ON criteria_version
    WHEN OLD.status != 'draft' AND NOT (
        OLD.status = 'active' AND NEW.status = 'superseded'
        AND NEW.id = OLD.id AND NEW.number = OLD.number
        AND NEW.parent_id IS OLD.parent_id AND NEW.created_at = OLD.created_at
        AND NEW.activated_at IS OLD.activated_at AND NEW.author_id = OLD.author_id
        AND NEW.rationale = OLD.rationale AND NEW.journal_entry_id IS OLD.journal_entry_id
        AND NEW.after_protocol_registration = OLD.after_protocol_registration
    )
    BEGIN SELECT RAISE(ABORT, 'immutable: criteria_version'); END""",
    """CREATE TRIGGER criteria_version_no_delete BEFORE DELETE ON criteria_version
    WHEN OLD.status != 'draft'
    BEGIN SELECT RAISE(ABORT, 'immutable: criteria_version'); END""",
    # Criteria of a version that left draft never change.
    """CREATE TRIGGER criterion_no_insert BEFORE INSERT ON criterion
    WHEN (SELECT status FROM criteria_version WHERE id = NEW.version_id) != 'draft'
    BEGIN SELECT RAISE(ABORT, 'immutable: criterion'); END""",
    """CREATE TRIGGER criterion_no_update BEFORE UPDATE ON criterion
    WHEN (SELECT status FROM criteria_version WHERE id = OLD.version_id) != 'draft'
    BEGIN SELECT RAISE(ABORT, 'immutable: criterion'); END""",
    """CREATE TRIGGER criterion_no_delete BEFORE DELETE ON criterion
    WHEN (SELECT status FROM criteria_version WHERE id = OLD.version_id) != 'draft'
    BEGIN SELECT RAISE(ABORT, 'immutable: criterion'); END""",
    # The project row is never removed.
    """CREATE TRIGGER project_no_delete BEFORE DELETE ON project
    BEGIN SELECT RAISE(ABORT, 'append-only: project'); END""",
)


def upgrade() -> None:
    op.create_table(
        "project",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column("format_version", sa.String(16), nullable=False),
    )
    op.create_table(
        "reviewer",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("role", sa.Text, nullable=False, server_default=""),
        sa.Column("ai_config_id", sa.String(26), nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", UTCDateTime, nullable=False),
    )
    op.create_table(
        "journal_entry",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("position", sa.Integer, nullable=False, unique=True),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column("actor_reviewer_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=True),
        sa.Column("entry_type", sa.String(64), nullable=False),
        sa.Column("subject_type", sa.String(64), nullable=True),
        sa.Column("subject_id", sa.String(26), nullable=True),
        sa.Column("payload_json", sa.Text, nullable=False),
        sa.Column("summary_fr", sa.Text, nullable=False),
        sa.Column("tool_version", sa.Text, nullable=False),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False, unique=True),
    )
    op.create_table(
        "framing_version",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("number", sa.Integer, nullable=False, unique=True),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column("author_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("population", sa.Text, nullable=False),
        sa.Column("concept", sa.Text, nullable=False),
        sa.Column("context", sa.Text, nullable=False),
        sa.Column("secondary_questions_json", sa.Text, nullable=False),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
        ),
    )
    op.create_table(
        "criteria_version",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("number", sa.Integer, nullable=False, unique=True),
        sa.Column("parent_id", sa.String(26), sa.ForeignKey("criteria_version.id"), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column("activated_at", UTCDateTime, nullable=True),
        sa.Column("author_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        sa.Column("rationale", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=True
        ),
        sa.Column(
            "after_protocol_registration",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_index(
        "uq_criteria_version_one_active",
        "criteria_version",
        ["status"],
        unique=True,
        sqlite_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "uq_criteria_version_one_draft",
        "criteria_version",
        ["status"],
        unique=True,
        sqlite_where=sa.text("status = 'draft'"),
    )
    op.create_table(
        "criterion",
        sa.Column(
            "version_id", sa.String(26), sa.ForeignKey("criteria_version.id"), nullable=False
        ),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("pcc_element", sa.String(16), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("guidance", sa.Text, nullable=False, server_default=""),
        sa.Column("examples_json", sa.Text, nullable=False, server_default="[]"),
        sa.Column("counterexamples_json", sa.Text, nullable=False, server_default="[]"),
        sa.PrimaryKeyConstraint("version_id", "code"),
    )
    for statement in _TRIGGERS:
        op.execute(statement)


def downgrade() -> None:  # pragma: no cover - project data is never downgraded
    raise NotImplementedError("revue-portee projects are only migrated forward")
