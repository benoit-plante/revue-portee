"""Search strategies, queries, counts, key articles, sensitivity tests, descriptor checks
and AI term suggestions (tranche 1.3).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-07
"""

import sqlalchemy as sa
from alembic import op

from revue_portee.storage.db import UTCDateTime

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

# Every table of this migration is append-only (ENF-TRA-02).
_APPEND_ONLY = (
    "search_strategy_version",
    "query",
    "search_run",
    "key_article_set_version",
    "sensitivity_check",
    "descriptor_check",
    "term_suggestion",
    "term_suggestion_review",
)


def _triggers(table: str) -> tuple[str, str]:
    return (
        f"""CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table}
    BEGIN SELECT RAISE(ABORT, 'append-only: {table}'); END""",
        f"""CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table}
    BEGIN SELECT RAISE(ABORT, 'append-only: {table}'); END""",
    )


def upgrade() -> None:
    op.create_table(
        "search_strategy_version",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("number", sa.Integer, unique=True, nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column("author_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("strategy_json", sa.Text, nullable=False),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
        ),
    )
    op.create_table(
        "query",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "strategy_version_id",
            sa.String(26),
            sa.ForeignKey("search_strategy_version.id"),
            nullable=False,
        ),
        sa.Column("database", sa.String(32), nullable=False),
        sa.Column("syntax_text", sa.Text, nullable=False),
        sa.Column("blocks_json", sa.Text, nullable=False),
        sa.Column("limits_text", sa.Text, nullable=False),
        sa.Column("warnings_json", sa.Text, nullable=False),
        sa.Column("generated_by", sa.String(32), nullable=False),
        sa.Column("edited", sa.Boolean, nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
    )
    op.create_table(
        "search_run",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("query_id", sa.String(26), sa.ForeignKey("query.id"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("executed_at", UTCDateTime, nullable=False),
        sa.Column("result_count", sa.Integer, nullable=True),
        sa.Column("blocks_json", sa.Text, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("raw_dir", sa.Text, nullable=False),
        sa.Column("reviewer_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
        ),
    )
    op.create_table(
        "key_article_set_version",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("number", sa.Integer, unique=True, nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column("author_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        sa.Column("articles_json", sa.Text, nullable=False),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
        ),
    )
    op.create_table(
        "sensitivity_check",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("search_run_id", sa.String(26), sa.ForeignKey("search_run.id"), nullable=False),
        sa.Column(
            "key_article_set_version_id",
            sa.String(26),
            sa.ForeignKey("key_article_set_version.id"),
            nullable=False,
        ),
        sa.Column("found", sa.Integer, nullable=False),
        sa.Column("indexed", sa.Integer, nullable=False),
        sa.Column("outcomes_json", sa.Text, nullable=False),
    )
    op.create_table(
        "descriptor_check",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column("vocabulary", sa.String(16), nullable=False),
        sa.Column("heading", sa.Text, nullable=False),
        sa.Column("found", sa.Boolean, nullable=False),
        sa.Column("official_heading", sa.Text, nullable=True),
        sa.Column("descriptor_ui", sa.Text, nullable=True),
        sa.Column("raw_dir", sa.Text, nullable=False),
        sa.Column("reviewer_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
        ),
    )
    op.create_table(
        "term_suggestion",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("ai_call_id", sa.String(26), sa.ForeignKey("ai_call.id"), nullable=False),
        sa.Column(
            "strategy_version_id",
            sa.String(26),
            sa.ForeignKey("search_strategy_version.id"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("block_code", sa.String(16), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("line", sa.Text, nullable=False),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
    )
    op.create_table(
        "term_suggestion_review",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "suggestion_id",
            sa.String(26),
            sa.ForeignKey("term_suggestion.id"),
            unique=True,
            nullable=False,
        ),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("final_line", sa.Text, nullable=False),
        sa.Column("reviewer_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column(
            "strategy_version_id",
            sa.String(26),
            sa.ForeignKey("search_strategy_version.id"),
            nullable=True,
        ),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
        ),
    )
    op.create_index(
        "ix_query_strategy_version", "query", ["strategy_version_id", "database"], unique=True
    )
    op.create_index("ix_search_run_query", "search_run", ["query_id"])
    op.create_index("ix_descriptor_check_heading", "descriptor_check", ["vocabulary", "heading"])
    for table in _APPEND_ONLY:
        for statement in _triggers(table):
            op.execute(statement)


def downgrade() -> None:  # pragma: no cover - project data is never downgraded
    raise NotImplementedError("revue-portee projects are only migrated forward")
