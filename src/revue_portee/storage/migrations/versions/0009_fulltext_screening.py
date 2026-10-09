"""Mode of a screening round (tranche 2.2, D-102): blind or assisted.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-09
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Adding a column with a default changes no existing row: the append-only
    # triggers of the table stay as they are. Every round before is blind.
    op.add_column(
        "screening_round",
        sa.Column("mode", sa.String(16), nullable=False, server_default="blind"),
    )


def downgrade() -> None:  # pragma: no cover - project data is never downgraded
    raise NotImplementedError("revue-portee projects are only migrated forward")
