"""Versioned search strategies and their queries (EF-REC-01, EF-REC-03, EF-REC-06).

Saving a changed strategy creates a new immutable version and, in the same transaction,
the query of each database generated from it: the exact text is kept with its version,
and the date and number of results of each execution are kept with the runs.
"""

from collections.abc import Callable
from datetime import datetime

from pydantic import JsonValue
from sqlalchemy import Connection

from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.domain.search import Database, QueryVersion, SearchStrategy, StrategyVersion
from revue_portee.i18n import french
from revue_portee.i18n import gettext as _
from revue_portee.search.translate import translate
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import journal
from revue_portee.storage.repositories import search as search_repo

__all__ = [
    "EmptyStrategyError",
    "current_queries",
    "current_strategy",
    "save_strategy",
    "save_strategy_in",
    "strategy_history",
    "used_block_codes",
]

Clock = Callable[[], datetime]


class EmptyStrategyError(ValueError):
    def __init__(self) -> None:
        super().__init__(_("Add at least one concept block before saving the strategy."))


def current_strategy(folder: ProjectFolder) -> StrategyVersion | None:
    with folder.engine.connect() as connection:
        return search_repo.latest_strategy_version(connection)


def strategy_history(folder: ProjectFolder) -> list[tuple[StrategyVersion, list[QueryVersion]]]:
    """Every strategy version, oldest first, with its queries."""
    with folder.engine.connect() as connection:
        queries = search_repo.list_queries(connection)
        return [
            (version, [q for q in queries if q.strategy_version_id == version.id])
            for version in search_repo.list_strategy_versions(connection)
        ]


def used_block_codes(folder: ProjectFolder) -> set[str]:
    """Codes of every block of every version: never given to a new block again."""
    with folder.engine.connect() as connection:
        versions = search_repo.list_strategy_versions(connection)
    return {b.code for v in versions for b in v.strategy.blocks}


def current_queries(folder: ProjectFolder) -> dict[Database, QueryVersion]:
    """The query of each database for the current strategy version."""
    with folder.engine.connect() as connection:
        latest = search_repo.latest_strategy_version(connection)
        if latest is None:
            return {}
        queries = search_repo.list_queries(connection, strategy_version_id=latest.id)
    return {q.database: q for q in queries}


def save_strategy_in(
    connection: Connection,
    folder: ProjectFolder,
    strategy: SearchStrategy,
    *,
    rationale: str,
    moment: datetime,
    tool_version: str,
    payload: dict[str, JsonValue] | None = None,
) -> StrategyVersion:
    """Store a new strategy version and its queries within the caller's transaction,
    unless the strategy is unchanged (then the current version is returned)."""
    latest = search_repo.latest_strategy_version(connection)
    if latest is not None and latest.strategy == strategy:
        return latest
    if latest is None and not strategy.blocks and strategy.limits.empty:
        raise EmptyStrategyError
    version = StrategyVersion(
        id=new_ulid(moment),
        number=1 if latest is None else latest.number + 1,
        created_at=moment,
        author_id=folder.reviewer_id,
        rationale=rationale.strip(),
        strategy=strategy,
    )
    queries = [
        QueryVersion(
            id=new_ulid(moment),
            strategy_version_id=version.id,
            created_at=moment,
            translation=translate(strategy, database),
        )
        for database in Database
    ]
    details: dict[str, JsonValue] = {
        "number": version.number,
        "rationale": version.rationale,
        "strategy": strategy.model_dump(mode="json"),
        "queries": {
            q.database.value: {
                "id": q.id,
                "text": q.translation.text,
                "warnings": len(q.translation.warnings),
            }
            for q in queries
        },
    }
    entry = journal.append_entry(
        connection,
        now=moment,
        actor_reviewer_id=folder.reviewer_id,
        entry_type=EntryType.SEARCH_QUERY_VERSIONED,
        subject_type="search_strategy_version",
        subject_id=version.id,
        summary_fr=french("Search strategy saved (version {number})").format(number=version.number),
        tool_version=tool_version,
        payload=details | (payload or {}),
    )
    search_repo.insert_strategy_version(connection, version, journal_entry_id=entry.id)
    search_repo.insert_queries(connection, queries)
    return version


def save_strategy(
    folder: ProjectFolder,
    strategy: SearchStrategy,
    *,
    rationale: str = "",
    now: Clock,
    tool_version: str,
) -> StrategyVersion:
    with folder.write() as connection:
        return save_strategy_in(
            connection,
            folder,
            strategy,
            rationale=rationale,
            moment=now(),
            tool_version=tool_version,
        )
