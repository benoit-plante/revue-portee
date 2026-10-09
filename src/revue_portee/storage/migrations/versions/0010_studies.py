"""Reports of a same study (tranche 2.3): the AI's examinations, the person's decisions
and the primary report chosen.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-09
"""

from typing import Any

import sqlalchemy as sa
from alembic import op

from revue_portee.storage.db import UTCDateTime

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

# Every table of this migration is append-only (ENF-TRA-02).
_APPEND_ONLY = ("study_link_assessment", "study_link_decision", "primary_report_choice")


def _triggers(table: str) -> tuple[str, str]:
    return (
        f"""CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table}
    BEGIN SELECT RAISE(ABORT, 'append-only: {table}'); END""",
        f"""CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table}
    BEGIN SELECT RAISE(ABORT, 'append-only: {table}'); END""",
    )


def _pair() -> list[sa.Column[Any]]:
    return [
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("reference_a_id", sa.String(26), sa.ForeignKey("reference.id"), nullable=False),
        sa.Column("reference_b_id", sa.String(26), sa.ForeignKey("reference.id"), nullable=False),
    ]


def _common() -> list[sa.Column[Any]]:
    return [
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column("reviewer_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "study_link_assessment",
        *_pair(),
        sa.Column("rule", sa.String(16), nullable=False),
        sa.Column("verdict", sa.String(16), nullable=False),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("evidence_json", sa.Text, nullable=False),
        sa.Column("ai_call_id", sa.String(26), sa.ForeignKey("ai_call.id"), nullable=False),
        *_common(),
    )
    op.create_index(
        "ix_study_link_assessment_pair",
        "study_link_assessment",
        ["reference_a_id", "reference_b_id"],
    )
    op.create_table(
        "study_link_decision",
        *_pair(),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("note", sa.Text, nullable=False),
        *_common(),
        sa.CheckConstraint("outcome IN ('same', 'different')", name="ck_study_link_outcome"),
    )
    op.create_index(
        "ix_study_link_decision_pair", "study_link_decision", ["reference_a_id", "reference_b_id"]
    )
    op.create_table(
        "primary_report_choice",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("reference_id", sa.String(26), sa.ForeignKey("reference.id"), nullable=False),
        *_common(),
    )
    for table in _APPEND_ONLY:
        for statement in _triggers(table):
            op.execute(statement)


def downgrade() -> None:  # pragma: no cover - project data is never downgraded
    raise NotImplementedError("revue-portee projects are only migrated forward")
