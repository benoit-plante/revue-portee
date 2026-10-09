"""Full texts obtained and references left without one (tranche 2.1).

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-09
"""

from typing import Any

import sqlalchemy as sa
from alembic import op

from revue_portee.storage.db import UTCDateTime

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

# Every table of this migration is append-only (ENF-TRA-02).
_APPEND_ONLY = ("fulltext_document", "retrieval_note")


def _triggers(table: str) -> tuple[str, str]:
    return (
        f"""CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table}
    BEGIN SELECT RAISE(ABORT, 'append-only: {table}'); END""",
        f"""CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table}
    BEGIN SELECT RAISE(ABORT, 'append-only: {table}'); END""",
    )


def _reference() -> sa.Column[str]:
    return sa.Column("reference_id", sa.String(26), sa.ForeignKey("reference.id"), nullable=False)


def _common() -> list[sa.Column[Any]]:
    return [
        sa.Column("raw_dir", sa.Text, nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column("reviewer_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "fulltext_document",
        sa.Column("id", sa.String(26), primary_key=True),
        _reference(),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("license", sa.Text, nullable=False),
        sa.Column("version", sa.Text, nullable=False),
        sa.Column("host_type", sa.Text, nullable=False),
        sa.Column("filename", sa.Text, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("page_count", sa.Integer, nullable=False),
        sa.Column("text_chars", sa.Integer, nullable=False),
        sa.Column("needs_ocr", sa.Boolean, nullable=False),
        sa.Column("references_page", sa.Integer, nullable=True),
        sa.Column("converter", sa.Text, nullable=False),
        *_common(),
    )
    op.create_index("ix_fulltext_document_reference", "fulltext_document", ["reference_id"])
    op.create_table(
        "retrieval_note",
        sa.Column("id", sa.String(26), primary_key=True),
        _reference(),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        *_common(),
        sa.CheckConstraint(
            "status IN ('not_found', 'not_retrievable')", name="ck_retrieval_status"
        ),
    )
    op.create_index("ix_retrieval_note_reference", "retrieval_note", ["reference_id"])
    for table in _APPEND_ONLY:
        for statement in _triggers(table):
            op.execute(statement)


def downgrade() -> None:  # pragma: no cover - project data is never downgraded
    raise NotImplementedError("revue-portee projects are only migrated forward")
