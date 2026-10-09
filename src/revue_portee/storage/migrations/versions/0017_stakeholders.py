"""Stakeholders, their comments and the responses (tranche 4.2), append-only.

A stakeholder holds a name, a role and an organisation, nothing else (EF-CON-03).

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-09
"""

import sqlalchemy as sa
from alembic import op

from revue_portee.storage.db import UTCDateTime

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def _journal() -> sa.Column[str]:
    return sa.Column(
        "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "stakeholder",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("organisation", sa.Text, nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column("reviewer_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        _journal(),
    )
    op.create_table(
        "stakeholder_comment",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("stakeholder_id", sa.String(26), sa.ForeignKey("stakeholder.id"), nullable=False),
        sa.Column("target", sa.String(16), nullable=False),
        sa.Column("target_detail", sa.Text, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("received_on", sa.Date, nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column("reviewer_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        _journal(),
    )
    op.create_table(
        "comment_response",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "comment_id", sa.String(26), sa.ForeignKey("stakeholder_comment.id"), nullable=False
        ),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("supersedes_id", sa.String(26), sa.ForeignKey("comment_response.id")),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column("reviewer_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        _journal(),
    )
    for table in ("stakeholder", "stakeholder_comment", "comment_response"):
        for event in ("UPDATE", "DELETE"):
            op.execute(
                f"""CREATE TRIGGER {table}_no_{event.lower()} BEFORE {event}
    ON {table} BEGIN SELECT RAISE(ABORT, 'append-only: {table}'); END"""
            )


def downgrade() -> None:  # pragma: no cover - project data is never downgraded
    raise NotImplementedError("revue-portee projects are only migrated forward")
