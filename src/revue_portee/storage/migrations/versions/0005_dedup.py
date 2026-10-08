"""Deduplication runs, candidate pairs and people's decisions (tranche 1.5).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-08
"""

import sqlalchemy as sa
from alembic import op

from revue_portee.storage.db import UTCDateTime

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

# Every table of this migration is append-only (ENF-TRA-02, EF-COL-07).
_APPEND_ONLY = ("dedup_run", "duplicate_pair", "pair_decision")


def _triggers(table: str) -> tuple[str, str]:
    return (
        f"""CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table}
    BEGIN SELECT RAISE(ABORT, 'append-only: {table}'); END""",
        f"""CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table}
    BEGIN SELECT RAISE(ABORT, 'append-only: {table}'); END""",
    )


def upgrade() -> None:
    op.create_table(
        "dedup_run",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column("reviewer_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        sa.Column("settings_json", sa.Text, nullable=False),
        sa.Column("reference_count", sa.Integer, nullable=False),
        sa.Column("automatic_pairs", sa.Integer, nullable=False),
        sa.Column("review_pairs", sa.Integer, nullable=False),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
        ),
    )
    op.create_table(
        "duplicate_pair",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("run_id", sa.String(26), sa.ForeignKey("dedup_run.id"), nullable=False),
        sa.Column("reference_a_id", sa.String(26), sa.ForeignKey("reference.id"), nullable=False),
        sa.Column("reference_b_id", sa.String(26), sa.ForeignKey("reference.id"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("rule", sa.String(32), nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("proposal", sa.String(16), nullable=False),
        sa.Column("details_json", sa.Text, nullable=False),
        sa.UniqueConstraint("run_id", "reference_a_id", "reference_b_id", name="uq_pair_run"),
    )
    op.create_table(
        "pair_decision",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("reference_a_id", sa.String(26), sa.ForeignKey("reference.id"), nullable=False),
        sa.Column("reference_b_id", sa.String(26), sa.ForeignKey("reference.id"), nullable=False),
        sa.Column("pair_id", sa.String(26), sa.ForeignKey("duplicate_pair.id"), nullable=True),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("reviewer_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        sa.Column("note", sa.Text, nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
        ),
    )
    op.create_index("ix_duplicate_pair_run", "duplicate_pair", ["run_id"])
    op.create_index("ix_pair_decision_pair", "pair_decision", ["reference_a_id", "reference_b_id"])
    for table in _APPEND_ONLY:
        for statement in _triggers(table):
            op.execute(statement)


def downgrade() -> None:  # pragma: no cover - project data is never downgraded
    raise NotImplementedError("revue-portee projects are only migrated forward")
