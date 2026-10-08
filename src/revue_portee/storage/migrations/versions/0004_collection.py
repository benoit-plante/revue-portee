"""References, provenance, paginated collections, RIS imports and Crossref enrichment
(tranche 1.4).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-08
"""

import sqlalchemy as sa
from alembic import op

from revue_portee.storage.db import UTCDateTime

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

# Every table of this migration is append-only (ENF-TRA-02).
_APPEND_ONLY = (
    "reference",
    "collection_run",
    "collection_page",
    "collection_end",
    "import_file",
    "provenance",
    "enrichment",
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
        "reference",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("abstract", sa.Text, nullable=False),
        sa.Column("authors_json", sa.Text, nullable=False),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("container_title", sa.Text, nullable=False),
        sa.Column("volume", sa.Text, nullable=False),
        sa.Column("issue", sa.Text, nullable=False),
        sa.Column("pages", sa.Text, nullable=False),
        sa.Column("doi", sa.Text, nullable=False),
        sa.Column("pmid", sa.Text, nullable=False),
        sa.Column("openalex_id", sa.Text, nullable=False),
        sa.Column("language", sa.Text, nullable=False),
        sa.Column("doc_type", sa.Text, nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
    )
    op.create_table(
        "collection_run",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("query_id", sa.String(26), sa.ForeignKey("query.id"), nullable=False),
        sa.Column("database", sa.String(32), nullable=False),
        sa.Column("query_text", sa.Text, nullable=False),
        sa.Column("started_at", UTCDateTime, nullable=False),
        sa.Column("reviewer_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
        ),
    )
    op.create_table(
        "collection_page",
        sa.Column("run_id", sa.String(26), sa.ForeignKey("collection_run.id"), nullable=False),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("announced", sa.Integer, nullable=False),
        sa.Column("record_count", sa.Integer, nullable=False),
        sa.Column("new_references", sa.Integer, nullable=False),
        sa.Column("next_cursor", sa.Text, nullable=True),
        sa.Column("raw_path", sa.Text, nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
        ),
        sa.PrimaryKeyConstraint("run_id", "number"),
    )
    op.create_table(
        "collection_end",
        sa.Column(
            "run_id", sa.String(26), sa.ForeignKey("collection_run.id"), unique=True, nullable=False
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("announced", sa.Integer, nullable=True),
        sa.Column("collected", sa.Integer, nullable=False),
        sa.Column("discrepancy", sa.Text, nullable=False),
        sa.Column("error", sa.Text, nullable=False),
        sa.Column("ended_at", UTCDateTime, nullable=False),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
        ),
    )
    op.create_table(
        "import_file",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("filename", sa.Text, nullable=False),
        sa.Column("sha256", sa.String(64), unique=True, nullable=False),
        sa.Column("format", sa.String(16), nullable=False),
        sa.Column("database_declared", sa.Text, nullable=False),
        sa.Column("imported_at", UTCDateTime, nullable=False),
        sa.Column("record_count", sa.Integer, nullable=False),
        sa.Column("issues_json", sa.Text, nullable=False),
        sa.Column("reviewer_id", sa.String(26), sa.ForeignKey("reviewer.id"), nullable=False),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
        ),
    )
    op.create_table(
        "provenance",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("reference_id", sa.String(26), sa.ForeignKey("reference.id"), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("original_id", sa.Text, nullable=False),
        sa.Column(
            "collection_run_id", sa.String(26), sa.ForeignKey("collection_run.id"), nullable=True
        ),
        sa.Column("import_file_id", sa.String(26), sa.ForeignKey("import_file.id"), nullable=True),
        sa.Column("query_id", sa.String(26), sa.ForeignKey("query.id"), nullable=True),
        sa.Column("page", sa.Integer, nullable=True),
        sa.Column("created_at", UTCDateTime, nullable=False),
    )
    op.create_table(
        "enrichment",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("reference_id", sa.String(26), sa.ForeignKey("reference.id"), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("fields_json", sa.Text, nullable=False),
        sa.Column("raw_dir", sa.Text, nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column(
            "journal_entry_id", sa.String(26), sa.ForeignKey("journal_entry.id"), nullable=False
        ),
    )
    op.create_index("ix_reference_doi", "reference", ["doi"])
    op.create_index("ix_reference_pmid", "reference", ["pmid"])
    op.create_index("ix_reference_openalex", "reference", ["openalex_id"])
    op.create_index("ix_provenance_source_id", "provenance", ["source", "original_id"])
    op.create_index("ix_provenance_reference", "provenance", ["reference_id"])
    op.create_index(
        "uq_provenance_run_record",
        "provenance",
        ["collection_run_id", "original_id"],
        unique=True,
        sqlite_where=sa.text("collection_run_id IS NOT NULL"),
    )
    op.create_index("ix_enrichment_reference", "enrichment", ["reference_id"])
    for table in _APPEND_ONLY:
        for statement in _triggers(table):
            op.execute(statement)


def downgrade() -> None:  # pragma: no cover - project data is never downgraded
    raise NotImplementedError("revue-portee projects are only migrated forward")
