"""Extracted values (tranche 3.2), append-only.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-09
"""

import sqlalchemy as sa
from alembic import op

from revue_portee.storage.db import UTCDateTime

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "extraction_value",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("reference_id", sa.String(26), sa.ForeignKey("reference.id"), nullable=False),
        sa.Column("field_code", sa.String(16), nullable=False),
        sa.Column(
            "grid_version_id", sa.String(26), sa.ForeignKey("grid_version.id"), nullable=False
        ),
        sa.Column("reported", sa.Boolean, nullable=False),
        sa.Column("value_json", sa.Text, nullable=False),
        sa.Column("quote", sa.Text, nullable=False),
        sa.Column("page", sa.Integer, nullable=True),
        sa.Column("model_page", sa.Integer, nullable=True),
        sa.Column("quote_check", sa.String(16), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reviewer_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        sa.Column("reviewer_kind", sa.String(8), nullable=False),
        sa.Column(
            "supersedes_id", sa.String(26), sa.ForeignKey("extraction_value.id"), nullable=True
        ),
        sa.Column("ai_call_id", sa.String(26), sa.ForeignKey("ai_call.id"), nullable=True),
        sa.Column("note", sa.Text, nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
        ),
        sa.CheckConstraint(
            "reviewer_kind <> 'ai' OR (ai_call_id IS NOT NULL AND status = 'proposed')",
            name="ck_extraction_ai_traceable",
        ),
    )
    op.create_index(
        "ix_extraction_value_reference", "extraction_value", ["reference_id", "field_code"]
    )
    for event in ("UPDATE", "DELETE"):
        op.execute(
            f"""CREATE TRIGGER extraction_value_no_{event.lower()} BEFORE {event}
    ON extraction_value BEGIN SELECT RAISE(ABORT, 'append-only: extraction_value'); END"""
        )


def downgrade() -> None:  # pragma: no cover - project data is never downgraded
    raise NotImplementedError("revue-portee projects are only migrated forward")
