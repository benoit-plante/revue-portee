"""Pilot rounds, screening decisions, calibrations, thresholds and budget (tranche 1.6).

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-08
"""

import sqlalchemy as sa
from alembic import op

from revue_portee.storage.db import DecimalText, UTCDateTime

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

# Every table of this migration is append-only (ENF-TRA-02).
_APPEND_ONLY = (
    "screening_round",
    "round_member",
    "decision",
    "calibration_model",
    "threshold_setting",
    "budget_setting",
)


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
        "screening_round",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column(
            "criteria_version_id",
            sa.String(26),
            sa.ForeignKey("criteria_version.id"),
            nullable=False,
        ),
        sa.Column("seed", sa.Integer, nullable=False),
        sa.Column("sample_size", sa.Integer, nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column("reviewer_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        _journal(),
        sa.UniqueConstraint("stage", "kind", "number", name="uq_round_number"),
    )
    op.create_table(
        "round_member",
        sa.Column("round_id", sa.String(26), sa.ForeignKey("screening_round.id"), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("reference_id", sa.String(26), sa.ForeignKey("reference.id"), nullable=False),
        sa.PrimaryKeyConstraint("round_id", "position"),
        sa.UniqueConstraint("round_id", "reference_id", name="uq_round_member"),
    )
    op.create_table(
        "decision",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("reference_id", sa.String(26), sa.ForeignKey("reference.id"), nullable=False),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("round_id", sa.String(26), sa.ForeignKey("screening_round.id"), nullable=True),
        sa.Column("reviewer_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        sa.Column("reviewer_kind", sa.String(8), nullable=False),
        sa.Column("value", sa.String(16), nullable=False),
        sa.Column("confidence_raw", sa.Float, nullable=True),
        sa.Column("confidence_calibrated", sa.Float, nullable=True),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("criteria_cited_json", sa.Text, nullable=False),
        sa.Column("per_criterion_json", sa.Text, nullable=False),
        sa.Column("model_decision", sa.String(16), nullable=True),
        sa.Column("thresholds_json", sa.Text, nullable=True),
        sa.Column("calibration_id", sa.String(26), nullable=True),
        sa.Column(
            "criteria_version_id",
            sa.String(26),
            sa.ForeignKey("criteria_version.id"),
            nullable=False,
        ),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("context", sa.String(16), nullable=False),
        sa.Column("blinded", sa.Boolean, nullable=False),
        sa.Column(
            "supersedes_decision_id", sa.String(26), sa.ForeignKey("decision.id"), nullable=True
        ),
        sa.Column("ai_call_id", sa.String(26), sa.ForeignKey("ai_call.id"), nullable=True),
        sa.Column("tool_version", sa.Text, nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        _journal(),
        # ENF-TRA-05: the base refuses an AI decision without its call and confidence.
        sa.CheckConstraint(
            "reviewer_kind <> 'ai' OR (ai_call_id IS NOT NULL AND confidence_raw IS NOT NULL "
            "AND thresholds_json IS NOT NULL AND model_decision IS NOT NULL)",
            name="ck_decision_ai_traceable",
        ),
        sa.CheckConstraint(
            "reviewer_kind <> 'human' OR ai_call_id IS NULL", name="ck_decision_human"
        ),
    )
    op.create_table(
        "calibration_model",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("round_id", sa.String(26), sa.ForeignKey("screening_round.id"), nullable=False),
        sa.Column("ai_config_id", sa.String(26), sa.ForeignKey("ai_config.id"), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("calibration_json", sa.Text, nullable=False),
        sa.Column("artifact_path", sa.Text, nullable=False),
        sa.Column("fitted_on_n", sa.Integer, nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        _journal(),
    )
    op.create_table(
        "threshold_setting",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("exclude_below", sa.Float, nullable=False),
        sa.Column("include_above", sa.Float, nullable=False),
        sa.Column("target_sensitivity", DecimalText, nullable=False),
        sa.Column("justification", sa.Text, nullable=False),
        sa.Column(
            "based_on_round_id", sa.String(26), sa.ForeignKey("screening_round.id"), nullable=True
        ),
        sa.Column(
            "calibration_id", sa.String(26), sa.ForeignKey("calibration_model.id"), nullable=True
        ),
        sa.Column("reviewer_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        _journal(),
    )
    op.create_table(
        "budget_setting",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("limit_amount", DecimalText, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("reviewer_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        _journal(),
    )
    op.create_index("ix_decision_reference", "decision", ["reference_id", "stage"])
    op.create_index("ix_decision_round", "decision", ["round_id"])
    for table in _APPEND_ONLY:
        for statement in _triggers(table):
            op.execute(statement)


def downgrade() -> None:  # pragma: no cover - project data is never downgraded
    raise NotImplementedError("revue-portee projects are only migrated forward")
