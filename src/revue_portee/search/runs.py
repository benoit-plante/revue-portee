"""Executions against the database APIs: result counts (EF-REC-04), key articles and
sensitivity test (EF-REC-05), descriptor checks (EF-REC-02).

The APIs are called outside any transaction; their raw answers are then written in
``brut/sources/<id>/`` and the result recorded with its journal entry in one
transaction. If recording fails, the raw answers are removed (no orphan folder).
"""

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import JsonValue
from sqlalchemy import Connection

from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.domain.search import (
    Database,
    DescriptorCheck,
    KeyArticle,
    KeyArticleSetVersion,
    QueryVersion,
    RunKind,
    SearchRun,
    TermKind,
    TermSuggestionKind,
    Vocabulary,
    parse_key_article,
)
from revue_portee.domain.sensitivity import SensitivityCheck, assess_sensitivity
from revue_portee.i18n import french
from revue_portee.i18n import gettext as _
from revue_portee.search.strategies import current_queries
from revue_portee.sources import SearchSource, SourceFactory, default_source_factory
from revue_portee.sources.pubmed import MeshCheck
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.raw import remove_source_pages, write_source_pages
from revue_portee.storage.repositories import journal
from revue_portee.storage.repositories import search as search_repo

__all__ = [
    "DescriptorSource",
    "InvalidKeyArticlesError",
    "NoKeyArticlesError",
    "NoQueryError",
    "check_descriptors",
    "check_sensitivity",
    "count_results",
    "current_key_articles",
    "default_descriptor_source",
    "descriptor_checks",
    "headings_to_check",
    "latest_runs",
    "save_key_articles",
    "sensitivity_checks",
]

Clock = Callable[[], datetime]


@runtime_checkable
class DescriptorSource(Protocol):
    def mesh(self, heading: str) -> MeshCheck: ...


def default_descriptor_source() -> DescriptorSource:
    source = default_source_factory(Database.PUBMED)
    assert isinstance(source, DescriptorSource)  # noqa: S101 - the PubMed connector
    return source


class NoQueryError(LookupError):
    def __init__(self) -> None:
        super().__init__(_("Save the search strategy first."))


class NoKeyArticlesError(LookupError):
    def __init__(self) -> None:
        super().__init__(_("Enter the key articles first."))


class InvalidKeyArticlesError(ValueError):
    def __init__(self, lines: Sequence[str]) -> None:
        self.lines = tuple(lines)
        super().__init__(
            _("Neither a DOI, a PMID nor a title (10 characters or more): {lines}").format(
                lines=" ; ".join(f"« {line} »" for line in lines)
            )
        )


def _query(folder: ProjectFolder, database: Database) -> QueryVersion:
    query = current_queries(folder).get(database)
    if query is None or not query.translation.text:
        raise NoQueryError
    return query


@contextmanager
def _recording(folder: ProjectFolder, run_id: str, pages: list[JsonValue]) -> Iterator[str]:
    """Write the raw answers, then yield their folder to the recording transaction."""
    raw_dir = write_source_pages(folder.path, run_id, pages)
    try:
        yield raw_dir
    except BaseException:
        remove_source_pages(folder.path, raw_dir)
        raise


def _record_run(
    connection: Connection,
    folder: ProjectFolder,
    run: SearchRun,
    *,
    database: Database,
    summary: str,
    tool_version: str,
    payload: dict[str, JsonValue],
) -> None:
    entry = journal.append_entry(
        connection,
        now=run.executed_at,
        actor_reviewer_id=folder.reviewer_id,
        entry_type=EntryType.SEARCH_RUN_COMPLETED
        if run.kind is RunKind.COUNT
        else EntryType.SEARCH_SENSITIVITY_CHECKED,
        subject_type="search_run",
        subject_id=run.id,
        summary_fr=summary,
        tool_version=tool_version,
        payload={"database": database.value, "query_id": run.query_id, "raw_dir": run.raw_dir}
        | payload,
    )
    search_repo.insert_run(connection, run, journal_entry_id=entry.id)


# --- Counts -------------------------------------------------------------------------


def count_results(
    folder: ProjectFolder,
    database: Database,
    *,
    now: Clock,
    tool_version: str,
    factory: SourceFactory = default_source_factory,
) -> SearchRun:
    """Number of results of the complete query and of each block alone (EF-REC-04)."""
    query = _query(folder, database)
    source = factory(database)
    total = source.count(query.translation.text)
    pages: list[JsonValue] = [total.raw]
    blocks: dict[str, int] = {}
    for code, text in query.translation.blocks.items():
        answer = source.count(text)
        blocks[code] = answer.count
        pages.append(answer.raw)
    moment = now()
    run = SearchRun(
        id=new_ulid(moment),
        query_id=query.id,
        kind=RunKind.COUNT,
        executed_at=moment,
        result_count=total.count,
        block_counts=blocks,
        raw_dir="",
        reviewer_id=folder.reviewer_id,
    )
    with _recording(folder, run.id, pages) as raw_dir, folder.write() as connection:
        run = run.model_copy(update={"raw_dir": raw_dir})
        _record_run(
            connection,
            folder,
            run,
            database=database,
            summary=french("{database}: {count} results").format(
                database=database.display_name, count=total.count
            ),
            tool_version=tool_version,
            payload={
                "query": query.translation.text,
                "total": total.count,
                "blocks": dict[str, JsonValue](blocks),
            },
        )
    return run


def latest_runs(folder: ProjectFolder) -> dict[str, SearchRun]:
    """Latest count of each query, keyed by query id."""
    with folder.engine.connect() as connection:
        runs = search_repo.list_runs(connection)
    return {run.query_id: run for run in runs if run.kind is RunKind.COUNT}


# --- Key articles and sensitivity ---------------------------------------------------


def current_key_articles(folder: ProjectFolder) -> KeyArticleSetVersion | None:
    with folder.engine.connect() as connection:
        return search_repo.latest_key_article_set(connection)


def save_key_articles(
    folder: ProjectFolder, lines: Sequence[str], *, now: Clock, tool_version: str
) -> KeyArticleSetVersion | None:
    """Store the key articles (one DOI, PMID or title per line), unless unchanged."""
    articles: list[KeyArticle] = []
    invalid: list[str] = []
    for line in (line.strip() for line in lines):
        if not line:
            continue
        try:
            article = parse_key_article(line)
        except ValueError:
            invalid.append(line)
            continue
        if article not in articles:
            articles.append(article)
    if invalid:
        raise InvalidKeyArticlesError(invalid)
    with folder.write() as connection:
        latest = search_repo.latest_key_article_set(connection)
        if (latest is None and not articles) or (
            latest is not None and latest.articles == tuple(articles)
        ):
            return latest
        moment = now()
        version = KeyArticleSetVersion(
            id=new_ulid(moment),
            number=1 if latest is None else latest.number + 1,
            created_at=moment,
            author_id=folder.reviewer_id,
            articles=tuple(articles),
        )
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.SEARCH_KEY_ARTICLES_UPDATED,
            subject_type="key_article_set_version",
            subject_id=version.id,
            summary_fr=french("Key articles updated ({count})").format(count=len(articles)),
            tool_version=tool_version,
            payload={
                "number": version.number,
                "articles": [a.model_dump(mode="json") for a in articles],
            },
        )
        search_repo.insert_key_article_set(connection, version, journal_entry_id=entry.id)
        return version


def _hits(source: SearchSource, text: str, ids: Sequence[str], pages: list[JsonValue]) -> set[str]:
    answer = source.among(text, ids)
    pages.append(answer.raw)
    return set(answer.ids)


def check_sensitivity(
    folder: ProjectFolder,
    database: Database,
    *,
    now: Clock,
    tool_version: str,
    factory: SourceFactory = default_source_factory,
) -> SensitivityCheck:
    """Which key articles the query retrieves and, for the others, which block loses
    them (EF-REC-05)."""
    query = _query(folder, database)
    key_articles = current_key_articles(folder)
    if key_articles is None or not key_articles.articles:
        raise NoKeyArticlesError
    with folder.engine.connect() as connection:
        version = search_repo.latest_strategy_version(connection)
    assert version is not None  # noqa: S101 - a query implies a strategy version
    source = factory(database)
    pages: list[JsonValue] = []
    record_ids: dict[KeyArticle, str | None] = {}
    for article in key_articles.articles:
        record_id, raw = source.resolve(article)
        record_ids[article] = record_id
        pages.append(raw)
    indexed = sorted({r for r in record_ids.values() if r is not None})
    translation = query.translation
    found = _hits(source, translation.text, indexed, pages) if indexed else set()
    missed = [r for r in indexed if r not in found]
    included: dict[str, set[str]] = {}
    excluded: dict[str, set[str]] = {}
    limits: set[str] | None = None
    if missed:
        for block in version.strategy.included:
            if block.code in translation.blocks:
                included[block.code] = _hits(source, translation.blocks[block.code], missed, pages)
        for block in version.strategy.excluded:
            if block.code in translation.blocks:
                excluded[block.code] = _hits(source, translation.blocks[block.code], missed, pages)
        if translation.limits:
            limits = _hits(source, translation.limits, missed, pages)
    result = assess_sensitivity(
        key_articles.articles,
        record_ids,
        found,
        included_hits=included,
        excluded_hits=excluded,
        limits_hits=limits,
    )
    moment = now()
    run = SearchRun(
        id=new_ulid(moment),
        query_id=query.id,
        kind=RunKind.SENSITIVITY,
        executed_at=moment,
        result_count=None,
        raw_dir="",
        reviewer_id=folder.reviewer_id,
    )
    check = SensitivityCheck(
        id=new_ulid(moment),
        search_run_id=run.id,
        key_article_set_version_id=key_articles.id,
        result=result,
    )
    with _recording(folder, run.id, pages) as raw_dir, folder.write() as connection:
        run = run.model_copy(update={"raw_dir": raw_dir})
        _record_run(
            connection,
            folder,
            run,
            database=database,
            summary=french("{database}: {found} of {indexed} key articles retrieved").format(
                database=database.display_name, found=result.found, indexed=result.indexed
            ),
            tool_version=tool_version,
            payload={
                "key_article_set_version_id": key_articles.id,
                "found": result.found,
                "indexed": result.indexed,
                "recall": None if result.recall is None else str(result.recall),
                "missed": [
                    {"article": o.article.label, "responsible": list(o.responsible)}
                    for o in result.missed
                ],
                "not_indexed": [o.article.label for o in result.not_indexed],
            },
        )
        search_repo.insert_sensitivity_check(connection, check)
    return check


def sensitivity_checks(folder: ProjectFolder) -> list[tuple[SearchRun, SensitivityCheck]]:
    """Every sensitivity test, oldest first, with its run."""
    with folder.engine.connect() as connection:
        runs = {run.id: run for run in search_repo.list_runs(connection)}
        checks = search_repo.list_sensitivity_checks(connection)
    return [(runs[c.search_run_id], c) for c in checks]


# --- Descriptors --------------------------------------------------------------------


def headings_to_check(folder: ProjectFolder) -> list[str]:
    """MeSH headings of the current strategy and of the pending AI suggestions."""
    with folder.engine.connect() as connection:
        version = search_repo.latest_strategy_version(connection)
        reviews = search_repo.list_term_reviews(connection)
        suggestions = [
            s for s in search_repo.list_term_suggestions(connection) if s.id not in reviews
        ]
    terms = [] if version is None else [t for b in version.strategy.blocks for t in b.terms]
    for suggestion in suggestions:
        if suggestion.kind is TermSuggestionKind.DESCRIPTOR:
            try:
                terms.append(suggestion.term)
            except ValueError:
                continue
    headings: dict[str, str] = {}
    for term in terms:
        if term.kind is TermKind.DESCRIPTOR and term.vocabulary is Vocabulary.MESH:
            headings.setdefault(term.text.casefold(), term.text)
    return list(headings.values())


def check_descriptors(
    folder: ProjectFolder,
    *,
    now: Clock,
    tool_version: str,
    source: Callable[[], DescriptorSource] = default_descriptor_source,
) -> list[DescriptorCheck]:
    """Look every MeSH heading up with the E-utilities; absent ones are reported.

    APA Thesaurus headings cannot be checked (no public API)."""
    headings = headings_to_check(folder)
    if not headings:
        return []
    mesh = source()
    answers = [(heading, mesh.mesh(heading)) for heading in headings]
    pages: list[JsonValue] = [list(answer.raw) for _heading, answer in answers]
    moment = now()
    batch_id = new_ulid(moment)
    with _recording(folder, batch_id, pages) as raw_dir, folder.write() as connection:
        checks = [
            DescriptorCheck(
                id=new_ulid(moment),
                created_at=moment,
                vocabulary=Vocabulary.MESH,
                heading=heading,
                found=answer.found,
                official_heading=answer.heading,
                descriptor_ui=answer.ui,
                raw_dir=raw_dir,
                reviewer_id=folder.reviewer_id,
            )
            for heading, answer in answers
        ]
        absent = [c.heading for c in checks if not c.found]
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.SEARCH_DESCRIPTORS_CHECKED,
            subject_type="descriptor_check",
            subject_id=batch_id,
            summary_fr=french("{count} MeSH descriptors checked, {absent} not found").format(
                count=len(checks), absent=len(absent)
            ),
            tool_version=tool_version,
            payload={
                "raw_dir": raw_dir,
                "checks": [
                    {
                        "heading": c.heading,
                        "found": c.found,
                        "official_heading": c.official_heading,
                        "descriptor_ui": c.descriptor_ui,
                    }
                    for c in checks
                ],
            },
        )
        search_repo.insert_descriptor_checks(connection, checks, journal_entry_id=entry.id)
    return checks


def descriptor_checks(folder: ProjectFolder) -> dict[tuple[str, str], DescriptorCheck]:
    """Latest check of each heading, keyed by (vocabulary, heading in lower case)."""
    with folder.engine.connect() as connection:
        return search_repo.latest_descriptor_checks(connection)
