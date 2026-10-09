"""Plain-language summaries (tranche 4.1), append-only.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-09
"""

import sqlalchemy as sa
from alembic import op

from revue_portee.storage.db import UTCDateTime

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lay_summary",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reviewer_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        sa.Column("reviewer_kind", sa.String(8), nullable=False),
        sa.Column("ai_call_id", sa.String(26), sa.ForeignKey("ai_call.id")),
        sa.Column("supersedes_id", sa.String(26), sa.ForeignKey("lay_summary.id")),
        sa.Column("narrative_ids_json", sa.Text, nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
        ),
    )
    for event in ("UPDATE", "DELETE"):
        op.execute(
            f"""CREATE TRIGGER lay_summary_no_{event.lower()} BEFORE {event}
    ON lay_summary BEGIN SELECT RAISE(ABORT, 'append-only: lay_summary'); END"""
        )


def downgrade() -> None:  # pragma: no cover - project data is never downgraded
    raise NotImplementedError("revue-portee projects are only migrated forward")
