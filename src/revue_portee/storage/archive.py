"""Readable copies of the project data, and the archive file (EF-PRJ-04, ENF-REP-06).

The tables are written as CSV (and the journal as JSON lines) that a third party can
read without the tool: one row per record, identifiers kept, lists joined with
``"; "``. Abstracts, URLs and raw responses are never written here: they belong to
the publishers or to the provider, and only the complete archive (a copy of the
folder) holds them. The archive is a ZIP file whose content and dates are fixed by the
data, so the same project gives the same file.
"""

import csv
import io
import sqlite3
import tempfile
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from sqlalchemy import Connection, select

from revue_portee.domain.journal import canonical_json
from revue_portee.domain.references import Reference
from revue_portee.domain.screening import RoundKind, Stage
from revue_portee.storage.db import round_member
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import ai as ai_repo
from revue_portee.storage.repositories import criteria as criteria_repo
from revue_portee.storage.repositories import journal
from revue_portee.storage.repositories import screening as screening_repo

__all__ = [
    "csv_text",
    "database_copy",
    "readable_tables",
    "reference_rows",
    "write_zip",
]

type Row = Sequence[object]


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple | list):
        return "; ".join(str(v) for v in value)
    return str(value)


def csv_text(header: Sequence[str], rows: Iterable[Row]) -> str:
    """CSV with a header, comma-separated, quoted when needed, ``\\n`` line ends."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows([_cell(v) for v in row] for row in rows)
    return buffer.getvalue()


def reference_rows(references: Iterable[Reference]) -> str:
    """Bibliographic data of the references, without abstract nor URL."""
    header = (
        "id",
        "title",
        "authors",
        "year",
        "container_title",
        "volume",
        "issue",
        "pages",
        "doi",
        "pmid",
        "openalex_id",
        "language",
        "doc_type",
    )
    rows = (
        (
            r.id,
            r.title,
            r.authors,
            r.year,
            r.container_title,
            r.volume,
            r.issue,
            r.pages,
            r.doi,
            r.pmid,
            r.openalex_id,
            r.language,
            r.doc_type,
        )
        for r in sorted(references, key=lambda r: r.id)
    )
    return csv_text(header, rows)


def _rounds(connection: Connection) -> tuple[str, str]:
    rounds = [
        r
        for stage in Stage
        for kind in RoundKind
        for r in screening_repo.list_screening_rounds(connection, stage, kind)
    ]
    versions = {v.id: v.number for v in criteria_repo.list_versions(connection)}
    header = (
        "id",
        "stage",
        "kind",
        "number",
        "criteria_version",
        "seed",
        "sample_size",
        "created_at",
        "mode",
    )
    table = csv_text(
        header,
        (
            (
                r.id,
                r.stage.value,
                r.kind.value,
                r.number,
                versions[r.criteria_version_id],
                r.seed,
                r.sample_size,
                r.created_at,
                r.mode.value,
            )
            for r in sorted(rounds, key=lambda r: r.created_at)
        ),
    )
    members = connection.execute(
        select(
            round_member.c.round_id, round_member.c.position, round_member.c.reference_id
        ).order_by(round_member.c.round_id, round_member.c.position)
    ).all()
    return table, csv_text(("round_id", "position", "reference_id"), members)


def _decisions(connection: Connection) -> str:
    versions = {v.id: v.number for v in criteria_repo.list_versions(connection)}
    header = (
        "order",
        "id",
        "reference_id",
        "stage",
        "round_id",
        "reviewer_kind",
        "value",
        "criteria_cited",
        "criteria_version",
        "context",
        "blinded",
        "supersedes_decision_id",
        "ai_call_id",
        "confidence_raw",
        "confidence_calibrated",
        "model_decision",
        "rationale",
        "language",
        "created_at",
    )
    rows = (
        (
            order,
            d.id,
            d.reference_id,
            d.stage.value,
            d.round_id,
            d.reviewer_kind.value,
            d.value.value,
            d.criteria_cited,
            versions[d.criteria_version_id],
            d.context.value,
            d.blinded,
            d.supersedes_decision_id,
            d.ai_call_id,
            d.confidence_raw,
            d.confidence_calibrated,
            None if d.model_decision is None else d.model_decision.value,
            d.rationale,
            d.language,
            d.created_at,
        )
        for order, d in enumerate(screening_repo.list_decisions(connection), start=1)
    )
    return csv_text(header, rows)


def _calls(connection: Connection) -> str:
    header = (
        "id",
        "task",
        "item_id",
        "provider",
        "model_requested",
        "model_returned",
        "prompt_template_id",
        "prompt_template_version",
        "prompt_sha256",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "cost_estimate",
        "currency",
        "batch_id",
        "status",
        "error_code",
        "created_at",
    )
    rows = (
        (
            c.id,
            c.task,
            c.item_id,
            r.provider,
            r.model_requested,
            r.model_returned,
            r.prompt_template_id,
            r.prompt_template_version,
            r.prompt_sha256,
            r.input_tokens,
            r.output_tokens,
            r.cache_read_tokens,
            r.cache_write_tokens,
            r.cost_estimate,
            r.currency,
            r.batch_id,
            r.status,
            r.error_code,
            r.created_at,
        )
        for c in ai_repo.list_calls(connection)
        for r in (c.record,)
    )
    return csv_text(header, rows)


def _criteria(connection: Connection) -> str:
    header = (
        "version",
        "status",
        "activated_at",
        "rationale",
        "code",
        "kind",
        "pcc_element",
        "text",
        "guidance",
    )
    rows = (
        (
            v.number,
            v.status.value,
            v.activated_at,
            v.rationale,
            c.code,
            c.kind.value,
            c.pcc_element.value,
            c.text,
            c.guidance,
        )
        for v in criteria_repo.list_versions(connection)
        for c in v.criteria
    )
    return csv_text(header, rows)


def _journal(connection: Connection) -> str:
    """One entry per line; ``created_at`` written as it is hashed (UTC, microseconds), so
    that the chain can be checked from the file alone."""
    lines = []
    for entry in journal.list_entries(connection):
        fields = entry.model_dump(mode="json")
        fields["created_at"] = entry.created_at.astimezone(UTC).isoformat(timespec="microseconds")
        lines.append(canonical_json(fields) + "\n")
    return "".join(lines)


def readable_tables(folder: ProjectFolder) -> dict[str, str]:
    """The tables a third party needs, by file name (``donnees/``)."""
    with folder.engine.connect() as connection:
        rounds, members = _rounds(connection)
        return {
            "decisions.csv": _decisions(connection),
            "tours.csv": rounds,
            "membres-des-tours.csv": members,
            "appels-ia.csv": _calls(connection),
            "criteres.csv": _criteria(connection),
            "journal.jsonl": _journal(connection),
        }


def database_copy(folder: ProjectFolder) -> bytes:
    """A consistent copy of the project database (SQLite online backup)."""
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "copie.sqlite"
        with folder.engine.connect() as connection:
            source = cast(sqlite3.Connection, connection.connection.driver_connection)
            copy = sqlite3.connect(target)
            try:
                source.backup(copy)
            finally:
                copy.close()
        return target.read_bytes()


def write_zip(target: Path, files: Mapping[str, bytes], moment: datetime) -> None:
    """A ZIP of ``files`` (path in the archive: content), sorted, all dated ``moment``."""
    stamp = (moment.year, moment.month, moment.day, moment.hour, moment.minute, moment.second)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=stamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, files[name])
