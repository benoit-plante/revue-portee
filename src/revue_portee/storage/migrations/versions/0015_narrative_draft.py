"""Drafts of the narrative synthesis (tranche 3.6), append-only.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-09
"""

import sqlalchemy as sa
from alembic import op

from revue_portee.storage.db import UTCDateTime

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "narrative_draft",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("field_code", sa.String(16), nullable=False),
        sa.Column(
            "grid_version_id", sa.String(26), sa.ForeignKey("grid_version.id"), nullable=False
        ),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("sentences_json", sa.Text, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reviewer_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        sa.Column("reviewer_kind", sa.String(8), nullable=False),
        sa.Column("ai_call_id", sa.String(26), sa.ForeignKey("ai_call.id")),
        sa.Column("supersedes_id", sa.String(26), sa.ForeignKey("narrative_draft.id")),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
        ),
    )
    for event in ("UPDATE", "DELETE"):
        op.execute(
            f"""CREATE TRIGGER narrative_draft_no_{event.lower()} BEFORE {event}
    ON narrative_draft BEGIN SELECT RAISE(ABORT, 'append-only: narrative_draft'); END"""
        )


def downgrade() -> None:  # pragma: no cover - project data is never downgraded
    raise NotImplementedError("revue-portee projects are only migrated forward")
