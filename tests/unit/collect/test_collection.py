"""Paginated collection: resumption without duplicate or loss, counts (EF-COL-01)."""

import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pytest

from revue_portee.collect import collection
from revue_portee.domain.journal import EntryType
from revue_portee.domain.references import CollectionStatus
from revue_portee.domain.search import ConceptBlock, Database, SearchStrategy, parse_term
from revue_portee.protocol import notes
from revue_portee.search import strategies
from revue_portee.sources.http import SourceUnreachableError
from revue_portee.sources.openalex import OpenAlexKeyError
from revue_portee.sources.records import FetchedPage, FetchedRecord
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.raw import source_raw_dir
from revue_portee.storage.repositories import references as references_repo
from support import TOOL_VERSION, make_clock, new_project

Clock = Callable[[], datetime]


def record(n: int) -> FetchedRecord:
    return FetchedRecord(
        original_id=f"W{n}", fields={"title": f"Record {n}", "year": 2020, "openalex_id": f"W{n}"}
    )


@dataclass
class Pages:
    """A source giving ``pages`` (lists of record numbers) for ``announced`` records."""

    pages: list[list[int]]
    announced: int
    database: Database = Database.OPENALEX
    fail_at: dict[int, Exception] = field(default_factory=dict)  # page index -> error
    calls: list[str | None] = field(default_factory=list)

    def fetch(self, query: str, cursor: str | None) -> FetchedPage:
        self.calls.append(cursor)
        index = int(cursor or 0)
        if index in self.fail_at:
            raise self.fail_at.pop(index)
        following = str(index + 1) if index + 1 < len(self.pages) else None
        return FetchedPage(
            records=tuple(record(n) for n in self.pages[index]),
            announced=self.announced,
            next_cursor=following,
            raw={"page": index},
        )


@pytest.fixture
def setup(tmp_path: Path) -> Iterator[tuple[ProjectFolder, Clock]]:
    clock = make_clock()
    folder = new_project(tmp_path, clock)
    strategy = SearchStrategy(
        blocks=(ConceptBlock(code="B1", label="P", terms=(parse_term("parent*"),)),)
    )
    strategies.save_strategy(folder, strategy, now=clock, tool_version=TOOL_VERSION)
    yield folder, clock
    folder.close()


def run_all(folder: ProjectFolder, clock: Clock, source: Pages, **kwargs: object) -> str:
    run = collection.start_collection(folder, source.database, now=clock, tool_version=TOOL_VERSION)
    collection.collect(
        folder,
        run.id,
        now=clock,
        tool_version=TOOL_VERSION,
        factory=lambda _: source,
        **kwargs,  # type: ignore[arg-type]
    )
    return run.id


def test_complete_collection_matches_the_announced_count(
    setup: tuple[ProjectFolder, Clock],
) -> None:
    folder, clock = setup
    source = Pages([[1, 2, 3], [4, 5, 6], [7]], announced=7)
    run_id = run_all(folder, clock, source)
    state = collection.collection_states(folder)[run_id]
    assert state.end is not None
    assert (state.end.status, state.end.collected, state.end.announced) == (
        CollectionStatus.COMPLETED,
        7,
        7,
    )
    assert state.end.discrepancy == ""
    assert source.calls == [None, "1", "2"]
    raw = folder.path / source_raw_dir(run_id)
    assert sorted(p.name for p in raw.iterdir()) == [
        "page-0001.json.gz",
        "page-0002.json.gz",
        "page-0003.json.gz",
    ]
    types = [e.entry_type for e in notes.journal_entries(folder)]
    assert types.count(EntryType.COLLECT_PAGE_STORED) == 3
    assert types[-1] == EntryType.COLLECT_COMPLETED
    with folder.engine.connect() as connection:
        assert references_repo.count_references(connection) == 7
        assert references_repo.count_by_source(connection) == {"openalex": 7}
    with pytest.raises(collection.AlreadyEndedError):
        collection.collect(
            folder, run_id, now=clock, tool_version=TOOL_VERSION, factory=lambda _: source
        )


def test_resumption_after_interruptions_without_duplicate_or_loss(
    setup: tuple[ProjectFolder, Clock], monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, clock = setup
    source = Pages(
        [[1, 2], [3, 4], [5, 6], [7, 8]],
        announced=8,
        fail_at={2: SourceUnreachableError("OpenAlex", "api.openalex.org")},
    )
    run = collection.start_collection(
        folder, Database.OPENALEX, now=clock, tool_version=TOOL_VERSION
    )
    with pytest.raises(SourceUnreachableError):  # network lost while fetching page 3
        collection.collect(
            folder, run.id, now=clock, tool_version=TOOL_VERSION, factory=lambda _: source
        )
    state = collection.collection_states(folder)[run.id]
    assert (state.pages, state.collected, state.finished) == (2, 4, False)

    # Crash after page 3 is written on disk but before it is recorded.
    original = references_repo.insert_page

    def crash(*args: object, **kwargs: object) -> None:
        raise sqlite3.OperationalError("power cut")

    monkeypatch.setattr(references_repo, "insert_page", crash)
    with pytest.raises(sqlite3.OperationalError):
        collection.collect(
            folder, run.id, now=clock, tool_version=TOOL_VERSION, factory=lambda _: source
        )
    assert collection.collection_states(folder)[run.id].collected == 4  # rolled back
    monkeypatch.setattr(references_repo, "insert_page", original)

    collection.collect(
        folder, run.id, now=clock, tool_version=TOOL_VERSION, factory=lambda _: source
    )
    state = collection.collection_states(folder)[run.id]
    assert state.end is not None
    assert (state.end.collected, state.end.announced, state.end.discrepancy) == (8, 8, "")
    with folder.engine.connect() as connection:
        assert references_repo.count_references(connection) == 8
        assert len(references_repo.list_provenance(connection)) == 8
        assert [p.number for p in references_repo.list_pages(connection, run.id)] == [1, 2, 3, 4]


def test_steps_and_duplicates_are_explained(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    source = Pages([[1, 2, 2], [2, 3]], announced=5)  # W2 given three times
    run = collection.start_collection(
        folder, Database.OPENALEX, now=clock, tool_version=TOOL_VERSION
    )
    first = collection.collect(
        folder, run.id, now=clock, tool_version=TOOL_VERSION, factory=lambda _: source, max_pages=1
    )
    assert (first.pages, first.collected, first.finished) == (1, 2, False)
    final = collection.collect(
        folder, run.id, now=clock, tool_version=TOOL_VERSION, factory=lambda _: source
    )
    assert final.end is not None
    assert (final.end.collected, final.end.announced) == (3, 5)
    assert "notices données plus d'une fois par l'API : 2" in final.end.discrepancy.replace(
        " ", " "
    )
    assert notes.journal_entries(folder)[-1].payload["received"] == 5


def test_second_collection_adds_provenance_not_references(
    setup: tuple[ProjectFolder, Clock],
) -> None:
    folder, clock = setup
    run_all(folder, clock, Pages([[1, 2]], announced=2))
    run_all(folder, clock, Pages([[2, 3]], announced=2))
    with folder.engine.connect() as connection:
        assert references_repo.count_references(connection) == 3
        assert len(references_repo.list_provenance(connection)) == 4


def test_refused_openalex_key_stops_the_collection(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    source = Pages([[1], [2]], announced=2, fail_at={1: OpenAlexKeyError(403)})
    run = collection.start_collection(
        folder, Database.OPENALEX, now=clock, tool_version=TOOL_VERSION
    )
    with pytest.raises(OpenAlexKeyError, match="OPENALEX_API_KEY"):
        collection.collect(
            folder, run.id, now=clock, tool_version=TOOL_VERSION, factory=lambda _: source
        )
    end = collection.collection_states(folder)[run.id].end
    assert end is not None
    assert end.status is CollectionStatus.FAILED
    assert "OPENALEX_API_KEY" in end.error
    assert end.collected == 1
    assert notes.journal_entries(folder)[-1].entry_type == EntryType.COLLECT_FAILED


def test_no_query_to_collect(setup: tuple[ProjectFolder, Clock], tmp_path: Path) -> None:
    folder, clock = setup
    with pytest.raises(collection.NoCollectableQueryError):
        collection.start_collection(
            folder, Database.PSYCINFO_EBSCO, now=clock, tool_version=TOOL_VERSION
        )
    empty = new_project(tmp_path / "vide", clock)
    try:
        with pytest.raises(collection.NoCollectableQueryError):
            collection.start_collection(
                empty, Database.PUBMED, now=clock, tool_version=TOOL_VERSION
            )
    finally:
        empty.close()
