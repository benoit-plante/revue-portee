"""Paginated collection of the records of a query (EF-COL-01, EF-COL-05, ENF-PER-04).

Each page is stored in one transaction with its references, their provenance and
its journal entry, after its raw answer is written in ``brut/sources/<run_id>/``.
A collection interrupted at any point therefore resumes after its last stored page,
without duplicate (an identifier already given in this collection is never stored
again) and without loss. At the end, the number of distinct records collected is
compared with the number announced by the API; any difference is explained and
recorded.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from pydantic import JsonValue, ValidationError

from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.domain.references import (
    CollectionEnd,
    CollectionPage,
    CollectionRun,
    CollectionStatus,
    Provenance,
    Reference,
    SourceKind,
)
from revue_portee.domain.search import Database
from revue_portee.i18n import french
from revue_portee.i18n import gettext as _
from revue_portee.search.strategies import current_queries
from revue_portee.sources import close_source, default_source_factory
from revue_portee.sources.http import SourceAccessError, SourceError
from revue_portee.sources.openalex import OpenAlexKeyError
from revue_portee.sources.pubmed import TooManyRecordsError
from revue_portee.sources.records import FetchedPage, FetchedRecord
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.raw import write_source_page
from revue_portee.storage.repositories import journal
from revue_portee.storage.repositories import references as references_repo

__all__ = [
    "AlreadyEndedError",
    "CollectionOpenError",
    "Collector",
    "CollectorFactory",
    "NoCollectableQueryError",
    "RunState",
    "collect",
    "collection_states",
    "start_collection",
]

Clock = Callable[[], datetime]
_SOURCES = {Database.PUBMED: SourceKind.PUBMED, Database.OPENALEX: SourceKind.OPENALEX}


def _permanent(error: SourceError) -> bool:
    """Errors that collecting again cannot fix: the collection is ended as failed.

    A refused key, too many PubMed records, or a request the API refuses (4xx other
    than 408 and 429, which are retried): an invalid query stays invalid."""
    if isinstance(error, OpenAlexKeyError | TooManyRecordsError):
        return True
    return (
        isinstance(error, SourceAccessError)
        and 400 <= error.status < 500
        and error.status not in (408, 429)
    )


class Collector(Protocol):
    @property
    def database(self) -> Database: ...

    def fetch(self, query: str, cursor: str | None) -> FetchedPage: ...


CollectorFactory = Callable[[Database], Collector]


def _default_collector(database: Database) -> Collector:
    source = default_source_factory(database)
    assert hasattr(source, "fetch")  # noqa: S101 - PubMed and OpenAlex connectors
    return source  # type: ignore[return-value]


class NoCollectableQueryError(LookupError):
    def __init__(self, database: Database) -> None:
        super().__init__(
            _("There is no query to collect in {database}: save the search strategy.").format(
                database=database.display_name
            )
        )


class CollectionOpenError(ValueError):
    def __init__(self, database: Database) -> None:
        super().__init__(
            _(
                "A collection in {database} is not finished: resume it (or wait for its end) "
                "before starting another one."
            ).format(database=database.display_name)
        )


class AlreadyEndedError(ValueError):
    def __init__(self) -> None:
        super().__init__(_("This collection is already finished."))


@dataclass(frozen=True, slots=True)
class RunState:
    run: CollectionRun
    pages: int
    collected: int  # distinct records stored so far
    announced: int | None
    end: CollectionEnd | None

    @property
    def finished(self) -> bool:
        return self.end is not None


def start_collection(
    folder: ProjectFolder, database: Database, *, now: Clock, tool_version: str
) -> CollectionRun:
    """Record the start of the collection of the current query of ``database``."""
    if database not in _SOURCES:
        raise NoCollectableQueryError(database)
    query = current_queries(folder).get(database)
    if query is None or not query.translation.text:
        raise NoCollectableQueryError(database)
    with folder.write() as connection:
        ends = references_repo.list_ends(connection)
        if any(
            r.database is database and r.id not in ends
            for r in references_repo.list_runs(connection)
        ):
            raise CollectionOpenError(database)
        moment = now()
        run = CollectionRun(
            id=new_ulid(moment),
            query_id=query.id,
            database=database,
            query_text=query.translation.text,
            started_at=moment,
            reviewer_id=folder.reviewer_id,
        )
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.COLLECT_STARTED,
            subject_type="collection_run",
            subject_id=run.id,
            summary_fr=french("Collection started in {database}").format(
                database=database.display_name
            ),
            tool_version=tool_version,
            payload={"database": database.value, "query_id": query.id, "query": run.query_text},
        )
        references_repo.insert_run(connection, run, journal_entry_id=entry.id)
    return run


def _reference(record: FetchedRecord, moment: datetime) -> tuple[Reference, list[str]]:
    """The reference of a record, and the fields left out because they are invalid."""
    fields = dict(record.fields)
    fields["authors"] = tuple(fields.get("authors") or ())
    year = fields.get("year")
    if not isinstance(year, int) or not 1000 <= year <= 2100:
        fields["year"] = None
    data = {"id": new_ulid(moment), "created_at": moment}
    dropped: list[str] = []
    while True:
        try:
            return Reference.model_validate(data | fields), dropped
        except ValidationError as error:
            bad = {str(e["loc"][0]) for e in error.errors() if e["loc"]} & set(fields)
            if not bad:  # pragma: no cover - only record fields can be invalid
                raise
            dropped += sorted(bad)
            for name in bad:
                fields.pop(name)


def _store_page(
    folder: ProjectFolder,
    run: CollectionRun,
    number: int,
    page: FetchedPage,
    *,
    now: Clock,
    tool_version: str,
) -> CollectionPage:
    raw: JsonValue = page.raw
    raw_path = write_source_page(folder.path, run.id, number, raw)
    source = _SOURCES[run.database]
    with folder.write() as connection:
        moment = now()
        seen = references_repo.run_original_ids(connection, run.id)
        records: dict[str, FetchedRecord] = {}
        for record in page.records:
            if record.original_id not in seen:
                records.setdefault(record.original_id, record)
        known = references_repo.find_by_source_id(connection, source, list(records))
        new = 0
        dropped: dict[str, list[str]] = {}
        for original_id, record in records.items():
            reference_id = known.get(original_id)
            if reference_id is None:
                reference, left_out = _reference(record, moment)
                if left_out:
                    dropped[original_id] = left_out
                references_repo.insert_reference(connection, reference)
                reference_id = reference.id
                new += 1
            references_repo.insert_provenance(
                connection,
                Provenance(
                    id=new_ulid(moment),
                    reference_id=reference_id,
                    source=source,
                    original_id=original_id,
                    collection_run_id=run.id,
                    query_id=run.query_id,
                    page=number,
                    created_at=moment,
                ),
            )
        stored = CollectionPage(
            run_id=run.id,
            number=number,
            announced=page.announced,
            record_count=len(page.records),
            new_references=new,
            next_cursor=page.next_cursor,
            raw_path=raw_path,
            created_at=moment,
        )
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.COLLECT_PAGE_STORED,
            subject_type="collection_run",
            subject_id=run.id,
            summary_fr=french("{database}: page {number} stored (records: {count})").format(
                database=run.database.display_name, number=number, count=len(page.records)
            ),
            tool_version=tool_version,
            payload={
                "page": number,
                "records": len(page.records),
                "new_in_collection": len(records),
                "new_references": new,
                "announced": page.announced,
                "raw_path": raw_path,
                "invalid_fields_left_out": {k: list[JsonValue](v) for k, v in dropped.items()},
            },
        )
        references_repo.insert_page(connection, stored, journal_entry_id=entry.id)
    return stored


def _discrepancy(announced: int, collected: int, received: int) -> str:
    if announced == collected:
        return ""
    reasons = []
    if received > collected:
        reasons.append(
            french("records given more than once by the API: {count}").format(
                count=received - collected
            )
        )
    if received < announced:
        reasons.append(
            french(
                "the API gave {received} records for {announced} announced (records without "
                "identifier, or results changed during the collection)"
            ).format(received=received, announced=announced)
        )
    elif received > announced:
        reasons.append(
            french("the results grew during the collection (records given: {received})").format(
                received=received
            )
        )
    return "; ".join(reasons)


def _end(
    folder: ProjectFolder,
    run: CollectionRun,
    *,
    status: CollectionStatus,
    error: str = "",
    now: Clock,
    tool_version: str,
) -> CollectionEnd:
    with folder.write() as connection:
        moment = now()
        pages = references_repo.list_pages(connection, run.id)
        collected = len(references_repo.run_original_ids(connection, run.id))
        announced = pages[-1].announced if pages else None
        received = sum(p.record_count for p in pages)
        discrepancy = (
            _discrepancy(announced, collected, received)
            if status is CollectionStatus.COMPLETED and announced is not None
            else ""
        )
        end = CollectionEnd(
            run_id=run.id,
            status=status,
            announced=announced,
            collected=collected,
            discrepancy=discrepancy,
            error=error,
            ended_at=moment,
        )
        if status is CollectionStatus.COMPLETED:
            summary = french("{database}: records collected: {collected} of {announced} announced")
            entry_type = EntryType.COLLECT_COMPLETED
        else:
            summary = french("{database}: collection stopped (records collected: {collected})")
            entry_type = EntryType.COLLECT_FAILED
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=entry_type,
            subject_type="collection_run",
            subject_id=run.id,
            summary_fr=summary.format(
                database=run.database.display_name, collected=collected, announced=announced
            ),
            tool_version=tool_version,
            payload={
                "pages": len(pages),
                "announced": announced,
                "received": received,
                "collected": collected,
                "discrepancy": discrepancy,
                "error": error,
            },
        )
        references_repo.insert_end(connection, end, journal_entry_id=entry.id)
    return end


def collect(
    folder: ProjectFolder,
    run_id: str,
    *,
    now: Clock,
    tool_version: str,
    factory: CollectorFactory = _default_collector,
    max_pages: int | None = None,
) -> RunState:
    """Collect (or resume collecting) the pages of a run, up to its end.

    ``max_pages`` stops after that many new pages (progress in steps; tests). A network
    error leaves the run open, to be resumed; an error that collecting again cannot fix
    (OpenAlex key refused, too many PubMed records) ends it as failed."""
    with folder.engine.connect() as connection:
        run = references_repo.get_run(connection, run_id)
        if run is None:
            raise LookupError(run_id)
        if run_id in references_repo.list_ends(connection):
            raise AlreadyEndedError
        pages = references_repo.list_pages(connection, run_id)
    number = len(pages)
    cursor = pages[-1].next_cursor if pages else None
    done = bool(pages) and cursor is None
    source = factory(run.database)
    fetched = 0
    try:
        while not done and (max_pages is None or fetched < max_pages):
            try:
                page = source.fetch(run.query_text, cursor)
            except SourceError as error:
                if not _permanent(error):
                    raise
                _end(
                    folder,
                    run,
                    status=CollectionStatus.FAILED,
                    error=str(error),
                    now=now,
                    tool_version=tool_version,
                )
                raise
            number += 1
            stored = _store_page(folder, run, number, page, now=now, tool_version=tool_version)
            fetched += 1
            cursor = stored.next_cursor
            done = cursor is None
    finally:
        close_source(source)
    if done:
        _end(folder, run, status=CollectionStatus.COMPLETED, now=now, tool_version=tool_version)
    return collection_states(folder)[run_id]


def collection_states(folder: ProjectFolder) -> dict[str, RunState]:
    """State of every collection, oldest first (counted in SQL: cheap to poll)."""
    with folder.engine.connect() as connection:
        ends = references_repo.list_ends(connection)
        summaries = references_repo.run_summaries(connection)
        states = {}
        for run in references_repo.list_runs(connection):
            pages, announced, collected = summaries.get(run.id, (0, None, 0))
            states[run.id] = RunState(
                run=run,
                pages=pages,
                collected=collected,
                announced=announced,
                end=ends.get(run.id),
            )
    return states
