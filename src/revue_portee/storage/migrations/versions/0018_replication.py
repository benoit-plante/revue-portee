"""Replication mode, reserved for benchmarks (tranche 3.8, D-104).

A project created by ``banc-replication`` holds one ``replication_marker`` row, written
in the transaction that creates the project. The base itself keeps the mode out of
ordinary projects: the marker can only be inserted while the journal holds nothing but
the creation of the project, it is never changed nor deleted (so a replication project
cannot become an ordinary one), and a decision of context ``replication`` is refused
in a project without a marker.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-09
"""

import sqlalchemy as sa
from alembic import op

from revue_portee.storage.db import UTCDateTime

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

_TRIGGERS = (
    """CREATE TRIGGER replication_marker_no_update BEFORE UPDATE ON replication_marker
    BEGIN SELECT RAISE(ABORT, 'append-only: replication_marker'); END""",
    """CREATE TRIGGER replication_marker_no_delete BEFORE DELETE ON replication_marker
    BEGIN SELECT RAISE(ABORT, 'append-only: replication_marker'); END""",
    # The marker points to the creation of the project, the only entry of the journal,
    # whose payload (sealed in the hash chain) declares the same mode.
    """CREATE TRIGGER replication_marker_at_creation BEFORE INSERT ON replication_marker
    WHEN (SELECT count(*) FROM journal_entry) <> 1 OR NOT EXISTS (
        SELECT 1 FROM journal_entry
        WHERE id = NEW.journal_entry_id
        AND entry_type = 'project.created'
        AND json_extract(payload_json, '$.replication.review_id') = NEW.review_id
        AND json_extract(payload_json, '$.replication.mode') = NEW.mode
    )
    BEGIN SELECT RAISE(ABORT, 'replication mode is set only when the project is created');
    END""",
    """CREATE TRIGGER decision_replication_only BEFORE INSERT ON decision
    WHEN NEW.context = 'replication' AND NOT EXISTS (SELECT 1 FROM replication_marker)
    BEGIN SELECT RAISE(ABORT, 'replication decisions only in a replication project'); END""",
)


def upgrade() -> None:
    op.create_table(
        "replication_marker",
        sa.Column("project_id", sa.String(26), sa.ForeignKey("project.id"), primary_key=True),
        sa.Column("review_id", sa.Text, nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
        ),
    )
    for statement in _TRIGGERS:
        op.execute(statement)


def downgrade() -> None:  # pragma: no cover - project data is never downgraded
    raise NotImplementedError("revue-portee projects are only migrated forward")
