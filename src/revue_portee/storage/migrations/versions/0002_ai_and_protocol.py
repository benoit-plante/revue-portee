"""AI configurations and calls, framing suggestions, qualification of criteria changes,
protocol text and registration (tranche 1.2).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-07
"""

import sqlalchemy as sa
from alembic import op

from revue_portee.storage.db import DecimalText, UTCDateTime

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# Every table of this migration is append-only (ENF-TRA-02).
_APPEND_ONLY = (
    "ai_config",
    "ai_call",
    "ai_suggestion",
    "suggestion_review",
    "qualification_proposal",
    "criterion_change",
    "protocol_text_version",
    "protocol_registration",
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
        "ai_config",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("task", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model_requested", sa.Text, nullable=False),
        sa.Column("prompt_template_id", sa.String(64), nullable=False),
        sa.Column("prompt_template_version", sa.String(16), nullable=False),
        sa.Column("params_json", sa.Text, nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
    )
    op.create_table(
        "ai_call",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("ai_config_id", sa.String(26), sa.ForeignKey("ai_config.id"), nullable=False),
        sa.Column("task", sa.String(64), nullable=False),
        sa.Column("item_id", sa.Text, nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model_requested", sa.Text, nullable=False),
        sa.Column("model_returned", sa.Text, nullable=False),
        sa.Column("provider_request_id", sa.Text, nullable=True),
        sa.Column("prompt_template_id", sa.String(64), nullable=False),
        sa.Column("prompt_template_version", sa.String(16), nullable=False),
        sa.Column("prompt_sha256", sa.String(64), nullable=False),
        sa.Column("params_json", sa.Text, nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=False),
        sa.Column("output_tokens", sa.Integer, nullable=False),
        sa.Column("cache_read_tokens", sa.Integer, nullable=False),
        sa.Column("cache_write_tokens", sa.Integer, nullable=False),
        sa.Column("cost_estimate", DecimalText, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("batch_id", sa.Text, nullable=True),
        sa.Column("response_path", sa.Text, nullable=True),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("error_code", sa.Text, nullable=True),
        sa.Column("created_at", UTCDateTime, nullable=False),
    )
    op.create_table(
        "ai_suggestion",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("ai_call_id", sa.String(26), sa.ForeignKey("ai_call.id"), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
    )
    op.create_table(
        "suggestion_review",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "suggestion_id",
            sa.String(26),
            sa.ForeignKey("ai_suggestion.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("final_text", sa.Text, nullable=False),
        sa.Column("reviewer_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column(
            "framing_version_id", sa.String(26), sa.ForeignKey("framing_version.id"), nullable=True
        ),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
        ),
    )
    op.create_table(
        "qualification_proposal",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("draft_version_id", sa.String(26), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("ai_call_id", sa.String(26), sa.ForeignKey("ai_call.id"), nullable=False),
        sa.Column("change_type", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("after_json", sa.Text, nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
    )
    op.create_table(
        "criterion_change",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "from_version_id", sa.String(26), sa.ForeignKey("criteria_version.id"), nullable=False
        ),
        sa.Column(
            "to_version_id", sa.String(26), sa.ForeignKey("criteria_version.id"), nullable=False
        ),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("change_type", sa.String(16), nullable=False),
        sa.Column("proposed_by", sa.String(8), nullable=False),
        sa.Column(
            "proposal_id", sa.String(26), sa.ForeignKey("qualification_proposal.id"), nullable=True
        ),
        sa.Column("confirmed_by", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
        ),
    )
    op.create_table(
        "protocol_text_version",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("number", sa.Integer, nullable=False, unique=True),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column("author_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        sa.Column("sections_json", sa.Text, nullable=False),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
        ),
    )
    op.create_table(
        "protocol_registration",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("doi", sa.Text, nullable=False),
        sa.Column("registered_on", sa.Date, nullable=False),
        sa.Column(
            "criteria_version_id",
            sa.String(26),
            sa.ForeignKey("criteria_version.id"),
            nullable=True,
        ),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column("reviewer_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
        ),
    )
    for table in _APPEND_ONLY:
        for statement in _triggers(table):
            op.execute(statement)


def downgrade() -> None:  # pragma: no cover - project data is never downgraded
    raise NotImplementedError("revue-portee projects are only migrated forward")
