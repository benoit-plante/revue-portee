"""AI batches, impact assessments and screening indexes (tranche 1.7).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-08
"""

import sqlalchemy as sa
from alembic import op

from revue_portee.storage.db import DecimalText, UTCDateTime

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

# Every table of this migration is append-only (ENF-TRA-02).
_APPEND_ONLY = ("ai_batch", "ai_batch_end", "impact_assessment")


def _triggers(table: str) -> tuple[str, str]:
    return (
        f"""CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table}
    BEGIN SELECT RAISE(ABORT, 'append-only: {table}'); END""",
        f"""CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table}
    BEGIN SELECT RAISE(ABORT, 'append-only: {table}'); END""",
    )


def _journal() -> sa.Column[str]:
    return sa.Column(
        "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "ai_batch",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("round_id", sa.String(26), sa.ForeignKey("screening_round.id"), nullable=False),
        sa.Column("task", sa.String(64), nullable=False),
        sa.Column(
            "criteria_version_id",
            sa.String(26),
            sa.ForeignKey("criteria_version.id"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_batch_id", sa.Text, nullable=False),
        sa.Column("item_ids_json", sa.Text, nullable=False),
        sa.Column("estimate", DecimalText, nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column("reviewer_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        _journal(),
    )
    op.create_table(
        "ai_batch_end",
        sa.Column("batch_id", sa.String(26), sa.ForeignKey("ai_batch.id"), primary_key=True),
        sa.Column("screened", sa.Integer, nullable=False),
        sa.Column("failed_json", sa.Text, nullable=False),
        sa.Column("spent", DecimalText, nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        _journal(),
    )
    op.create_table(
        "impact_assessment",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "from_version_id", sa.String(26), sa.ForeignKey("criteria_version.id"), nullable=False
        ),
        sa.Column(
            "to_version_id", sa.String(26), sa.ForeignKey("criteria_version.id"), nullable=False
        ),
        sa.Column(
            "main_round_id", sa.String(26), sa.ForeignKey("screening_round.id"), nullable=False
        ),
        sa.Column("changes_json", sa.Text, nullable=False),
        sa.Column("touched_count", sa.Integer, nullable=False),
        sa.Column(
            "reassessment_round_id",
            sa.String(26),
            sa.ForeignKey("screening_round.id"),
            nullable=True,
        ),
        sa.Column("seed", sa.Integer, nullable=False),
        sa.Column("sampled", sa.Boolean, nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column("reviewer_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        _journal(),
    )
    # Next reference to screen among tens of thousands (ENF-PER-01): whether a reference
    # has a human decision is read from the index alone, and the references are taken in
    # the order of the AI's probability by walking an index.
    op.create_index(
        "ix_decision_reference_kind",
        "decision",
        ["reference_id", "reviewer_kind", "context", "round_id"],
    )
    op.create_index(
        "ix_decision_round_kind",
        "decision",
        ["round_id", "reviewer_kind", "context", "reference_id"],
    )
    op.execute(
        "CREATE INDEX ix_decision_priority ON decision "
        "(round_id, reviewer_kind, coalesce(confidence_calibrated, confidence_raw))"
    )
    op.create_index("ix_ai_call_batch", "ai_call", ["batch_id", "item_id"])
    for table in _APPEND_ONLY:
        for statement in _triggers(table):
            op.execute(statement)


def downgrade() -> None:  # pragma: no cover - project data is never downgraded
    raise NotImplementedError("revue-portee projects are only migrated forward")
