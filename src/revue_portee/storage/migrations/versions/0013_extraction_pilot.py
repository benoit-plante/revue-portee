"""Extraction pilots (tranche 3.3), append-only.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-09
"""

import sqlalchemy as sa
from alembic import op

from revue_portee.storage.db import UTCDateTime

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "extraction_pilot",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("number", sa.Integer, nullable=False, unique=True),
        sa.Column("seed", sa.Integer, nullable=False),
        sa.Column(
            "grid_version_id", sa.String(26), sa.ForeignKey("grid_version.id"), nullable=False
        ),
        sa.Column("reference_ids_json", sa.Text, nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column("reviewer_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
        ),
    )
    for event in ("UPDATE", "DELETE"):
        op.execute(
            f"""CREATE TRIGGER extraction_pilot_no_{event.lower()} BEFORE {event}
    ON extraction_pilot BEGIN SELECT RAISE(ABORT, 'append-only: extraction_pilot'); END"""
        )


def downgrade() -> None:  # pragma: no cover - project data is never downgraded
    raise NotImplementedError("revue-portee projects are only migrated forward")
