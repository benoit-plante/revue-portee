"""Comments on the gaps of an evidence map (tranche 3.5), append-only.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-09
"""

import sqlalchemy as sa
from alembic import op

from revue_portee.storage.db import UTCDateTime

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gap_comment",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("rows_field", sa.String(16), nullable=False),
        sa.Column("columns_field", sa.String(16), nullable=False),
        sa.Column("row", sa.Text, nullable=False),
        sa.Column("column", sa.Text, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column("reviewer_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
        ),
    )
    for event in ("UPDATE", "DELETE"):
        op.execute(
            f"""CREATE TRIGGER gap_comment_no_{event.lower()} BEFORE {event}
    ON gap_comment BEGIN SELECT RAISE(ABORT, 'append-only: gap_comment'); END"""
        )


def downgrade() -> None:  # pragma: no cover - project data is never downgraded
    raise NotImplementedError("revue-portee projects are only migrated forward")
