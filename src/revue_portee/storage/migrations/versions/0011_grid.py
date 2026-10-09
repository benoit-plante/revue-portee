"""Versioned data extraction grid (tranche 3.1): versions, fields, field codes.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-09
"""

import sqlalchemy as sa
from alembic import op

from revue_portee.storage.db import UTCDateTime

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

# The same rules as for the criteria (0001): a version that left draft never changes,
# except active -> superseded; its fields never change; field codes are never reused.
_TRIGGERS = (
    """CREATE TRIGGER grid_version_immutable BEFORE UPDATE ON grid_version
    WHEN OLD.status != 'draft' AND NOT (
        OLD.status = 'active' AND NEW.status = 'superseded'
        AND NEW.id = OLD.id AND NEW.number = OLD.number
        AND NEW.parent_id IS OLD.parent_id AND NEW.created_at = OLD.created_at
        AND NEW.activated_at IS OLD.activated_at AND NEW.author_id = OLD.author_id
        AND NEW.rationale = OLD.rationale AND NEW.journal_entry_id IS OLD.journal_entry_id
    )
    BEGIN SELECT RAISE(ABORT, 'immutable: grid_version'); END""",
    """CREATE TRIGGER grid_version_no_delete BEFORE DELETE ON grid_version
    WHEN OLD.status != 'draft'
    BEGIN SELECT RAISE(ABORT, 'immutable: grid_version'); END""",
    """CREATE TRIGGER grid_field_no_insert BEFORE INSERT ON grid_field
    WHEN (SELECT status FROM grid_version WHERE id = NEW.version_id) != 'draft'
    BEGIN SELECT RAISE(ABORT, 'immutable: grid_field'); END""",
    """CREATE TRIGGER grid_field_no_update BEFORE UPDATE ON grid_field
    WHEN (SELECT status FROM grid_version WHERE id = OLD.version_id) != 'draft'
    BEGIN SELECT RAISE(ABORT, 'immutable: grid_field'); END""",
    """CREATE TRIGGER grid_field_no_delete BEFORE DELETE ON grid_field
    WHEN (SELECT status FROM grid_version WHERE id = OLD.version_id) != 'draft'
    BEGIN SELECT RAISE(ABORT, 'immutable: grid_field'); END""",
    """CREATE TRIGGER grid_field_code_no_update BEFORE UPDATE ON grid_field_code
    BEGIN SELECT RAISE(ABORT, 'append-only: grid_field_code'); END""",
    """CREATE TRIGGER grid_field_code_no_delete BEFORE DELETE ON grid_field_code
    BEGIN SELECT RAISE(ABORT, 'append-only: grid_field_code'); END""",
)


def upgrade() -> None:
    op.create_table(
        "grid_version",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("number", sa.Integer, nullable=False, unique=True),
        sa.Column("parent_id", sa.String(26), sa.ForeignKey("grid_version.id"), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column("activated_at", UTCDateTime, nullable=True),
        sa.Column("author_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=True
        ),
    )
    for status in ("active", "draft"):
        op.create_index(
            f"uq_grid_version_one_{status}",
            "grid_version",
            ["status"],
            unique=True,
            sqlite_where=sa.text(f"status = '{status}'"),
        )
    op.create_table(
        "grid_field",
        sa.Column("version_id", sa.String(26), sa.ForeignKey("grid_version.id"), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("definition", sa.Text, nullable=False),
        sa.Column("guidance", sa.Text, nullable=False),
        sa.Column("examples_json", sa.Text, nullable=False),
        sa.Column("choices_json", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("version_id", "code"),
    )
    op.create_table(
        "grid_field_code",
        sa.Column("code", sa.String(16), primary_key=True),
        sa.Column("first_version_id", sa.String(26), nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
    )
    for statement in _TRIGGERS:
        op.execute(statement)


def downgrade() -> None:  # pragma: no cover - project data is never downgraded
    raise NotImplementedError("revue-portee projects are only migrated forward")
