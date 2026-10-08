"""References, provenance, collection runs, RIS imports and enrichments (tranche 1.4)."""

import json
from typing import Any

from sqlalchemy import Connection, func, select

from revue_portee.domain.references import (
    CollectionEnd,
    CollectionPage,
    CollectionRun,
    Enrichment,
    ImportFile,
    ImportIssue,
    Provenance,
    Reference,
    SourceKind,
)
from revue_portee.domain.search import Database
from revue_portee.storage.db import (
    collection_end,
    collection_page,
    collection_run,
    enrichment,
    import_file,
    provenance,
    reference,
)

__all__ = [
    "count_by_source",
    "count_enrichment_candidates",
    "count_references",
    "find_by_source_id",
    "get_import_by_sha256",
    "get_reference",
    "get_run",
    "insert_end",
    "insert_enrichment",
    "insert_import",
    "insert_page",
    "insert_provenance",
    "insert_reference",
    "insert_run",
    "list_ends",
    "list_enrichments",
    "list_imports",
    "list_pages",
    "list_provenance",
    "list_references",
    "list_runs",
    "run_original_ids",
    "run_summaries",
    "source_names",
]


def _dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _plain(row: Any) -> dict[str, Any]:  # noqa: ANN401 - SQLAlchemy row mapping
    return {k: v for k, v in dict(row).items() if k != "journal_entry_id"}


# --- References and provenance ------------------------------------------------------


def insert_reference(connection: Connection, value: Reference) -> None:
    data = value.model_dump(mode="python")
    data["authors_json"] = _dumps(list(data.pop("authors")))
    connection.execute(reference.insert().values(**data))


def _to_reference(row: Any) -> Reference:  # noqa: ANN401
    data = dict(row)
    data["authors"] = tuple(json.loads(data.pop("authors_json")))
    return Reference.model_validate(data)


def get_reference(connection: Connection, reference_id: str) -> Reference | None:
    row = (
        connection.execute(select(reference).where(reference.c.id == reference_id))
        .mappings()
        .one_or_none()
    )
    return None if row is None else _to_reference(row)


def list_references(connection: Connection) -> list[Reference]:
    rows = connection.execute(select(reference).order_by(reference.c.id)).mappings()
    return [_to_reference(row) for row in rows]


def count_references(connection: Connection) -> int:
    return int(connection.execute(select(func.count()).select_from(reference)).scalar_one())


def find_by_source_id(
    connection: Connection, source: SourceKind, original_ids: list[str]
) -> dict[str, str]:
    """Reference id of each original id already given by ``source``."""
    found: dict[str, str] = {}
    for start in range(0, len(original_ids), 500):
        part = original_ids[start : start + 500]
        rows = connection.execute(
            select(provenance.c.original_id, provenance.c.reference_id).where(
                provenance.c.source == source.value, provenance.c.original_id.in_(part)
            )
        )
        for original_id, reference_id in rows:
            found.setdefault(str(original_id), str(reference_id))
    return found


def insert_provenance(connection: Connection, value: Provenance) -> None:
    connection.execute(provenance.insert().values(**value.model_dump(mode="python")))


def list_provenance(connection: Connection, *, reference_id: str | None = None) -> list[Provenance]:
    statement = select(provenance).order_by(provenance.c.created_at, provenance.c.id)
    if reference_id is not None:
        statement = statement.where(provenance.c.reference_id == reference_id)
    return [
        Provenance.model_validate(dict(row)) for row in connection.execute(statement).mappings()
    ]


def count_by_source(connection: Connection) -> dict[str, int]:
    """Distinct references given by each source (a reference may come from several)."""
    rows = connection.execute(
        select(provenance.c.source, func.count(func.distinct(provenance.c.reference_id))).group_by(
            provenance.c.source
        )
    )
    return {str(source): int(count) for source, count in rows}


def source_names(connection: Connection) -> dict[str, str]:
    """Name of the source of each reference: the database of its collection, or the
    database declared for its RIS file (its first provenance when it has several)."""
    rows = connection.execute(
        select(
            provenance.c.reference_id,
            collection_run.c.database,
            import_file.c.database_declared,
        )
        .select_from(
            provenance.outerjoin(
                collection_run, provenance.c.collection_run_id == collection_run.c.id
            ).outerjoin(import_file, provenance.c.import_file_id == import_file.c.id)
        )
        .order_by(provenance.c.created_at, provenance.c.id)
    )
    names: dict[str, str] = {}
    for reference_id, database, declared in rows:
        if str(reference_id) in names:
            continue
        if database is not None:
            names[str(reference_id)] = Database(database).display_name
        else:
            names[str(reference_id)] = str(declared or "")
    return names


def run_summaries(connection: Connection) -> dict[str, tuple[int, int | None, int]]:
    """For each collection: pages stored, number announced by its last page, distinct
    records collected (SQL counts, without loading the records)."""
    pages = {
        str(run_id): (int(count), int(last))
        for run_id, count, last in connection.execute(
            select(
                collection_page.c.run_id,
                func.count(),
                func.max(collection_page.c.number),
            ).group_by(collection_page.c.run_id)
        )
    }
    announced = {
        str(run_id): int(value)
        for run_id, number, value in connection.execute(
            select(collection_page.c.run_id, collection_page.c.number, collection_page.c.announced)
        )
        if pages.get(str(run_id), (0, -1))[1] == number
    }
    collected = {
        str(run_id): int(count)
        for run_id, count in connection.execute(
            select(provenance.c.collection_run_id, func.count())
            .where(provenance.c.collection_run_id.is_not(None))
            .group_by(provenance.c.collection_run_id)
        )
    }
    return {
        run_id: (count, announced.get(run_id), collected.get(run_id, 0))
        for run_id, (count, _last) in pages.items()
    }


def count_enrichment_candidates(connection: Connection) -> int:
    """References with a DOI, a missing enrichable field, and no Crossref check yet."""
    missing = (
        (reference.c.title == "")
        | (reference.c.abstract == "")
        | (reference.c.authors_json == "[]")
        | reference.c.year.is_(None)
        | (reference.c.container_title == "")
        | (reference.c.volume == "")
        | (reference.c.issue == "")
        | (reference.c.pages == "")
    )
    checked = select(enrichment.c.reference_id)
    statement = (
        select(func.count())
        .select_from(reference)
        .where(reference.c.doi != "", missing, reference.c.id.not_in(checked))
    )
    return int(connection.execute(statement).scalar_one())


def run_original_ids(connection: Connection, run_id: str) -> set[str]:
    rows = connection.execute(
        select(provenance.c.original_id).where(provenance.c.collection_run_id == run_id)
    )
    return {str(value) for (value,) in rows}


# --- Collection runs ----------------------------------------------------------------


def insert_run(connection: Connection, value: CollectionRun, *, journal_entry_id: str) -> None:
    connection.execute(
        collection_run.insert().values(
            **value.model_dump(mode="python"), journal_entry_id=journal_entry_id
        )
    )


def get_run(connection: Connection, run_id: str) -> CollectionRun | None:
    row = (
        connection.execute(select(collection_run).where(collection_run.c.id == run_id))
        .mappings()
        .one_or_none()
    )
    return None if row is None else CollectionRun.model_validate(_plain(row))


def list_runs(connection: Connection) -> list[CollectionRun]:
    rows = connection.execute(
        select(collection_run).order_by(collection_run.c.started_at, collection_run.c.id)
    ).mappings()
    return [CollectionRun.model_validate(_plain(row)) for row in rows]


def insert_page(connection: Connection, value: CollectionPage, *, journal_entry_id: str) -> None:
    connection.execute(
        collection_page.insert().values(
            **value.model_dump(mode="python"), journal_entry_id=journal_entry_id
        )
    )


def list_pages(connection: Connection, run_id: str) -> list[CollectionPage]:
    rows = connection.execute(
        select(collection_page)
        .where(collection_page.c.run_id == run_id)
        .order_by(collection_page.c.number)
    ).mappings()
    return [CollectionPage.model_validate(_plain(row)) for row in rows]


def insert_end(connection: Connection, value: CollectionEnd, *, journal_entry_id: str) -> None:
    connection.execute(
        collection_end.insert().values(
            **value.model_dump(mode="python"), journal_entry_id=journal_entry_id
        )
    )


def list_ends(connection: Connection) -> dict[str, CollectionEnd]:
    rows = connection.execute(select(collection_end)).mappings()
    ends = (CollectionEnd.model_validate(_plain(row)) for row in rows)
    return {end.run_id: end for end in ends}


# --- Imports and enrichments --------------------------------------------------------


def insert_import(connection: Connection, value: ImportFile, *, journal_entry_id: str) -> None:
    data = value.model_dump(mode="json")
    data["imported_at"] = value.imported_at
    data["issues_json"] = _dumps(data.pop("issues"))
    connection.execute(import_file.insert().values(**data, journal_entry_id=journal_entry_id))


def _to_import(row: Any) -> ImportFile:  # noqa: ANN401
    data = _plain(row)
    data["issues"] = tuple(
        ImportIssue.model_validate(i) for i in json.loads(data.pop("issues_json"))
    )
    return ImportFile.model_validate(data)


def get_import_by_sha256(connection: Connection, sha256: str) -> ImportFile | None:
    row = (
        connection.execute(select(import_file).where(import_file.c.sha256 == sha256))
        .mappings()
        .one_or_none()
    )
    return None if row is None else _to_import(row)


def list_imports(connection: Connection) -> list[ImportFile]:
    rows = connection.execute(
        select(import_file).order_by(import_file.c.imported_at, import_file.c.id)
    ).mappings()
    return [_to_import(row) for row in rows]


def insert_enrichment(connection: Connection, value: Enrichment, *, journal_entry_id: str) -> None:
    connection.execute(
        enrichment.insert().values(
            id=value.id,
            reference_id=value.reference_id,
            source=value.source,
            fields_json=_dumps(value.fields),
            raw_dir=value.raw_dir,
            created_at=value.created_at,
            journal_entry_id=journal_entry_id,
        )
    )


def list_enrichments(connection: Connection) -> dict[str, list[Enrichment]]:
    """Enrichments of each reference, oldest first."""
    rows = connection.execute(
        select(enrichment).order_by(enrichment.c.created_at, enrichment.c.id)
    ).mappings()
    result: dict[str, list[Enrichment]] = {}
    for row in rows:
        data = _plain(row)
        data["fields"] = json.loads(data.pop("fields_json"))
        item = Enrichment.model_validate(data)
        result.setdefault(item.reference_id, []).append(item)
    return result
