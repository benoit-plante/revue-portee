"""Collection and enrichment against recorded answers of the real services.

- PubMed: 218 records announced, two pages; OpenAlex: 268 records, two pages. The
  number collected equals the number announced (EF-COL-01).
- Crossref completes a real PubMed record exported without title (EF-COL-02).
"""

from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

import httpx2
import pytest
from pydantic import SecretStr

from revue_portee.collect import collection, enrichment, imports
from revue_portee.collect.collection import Collector
from revue_portee.domain.references import CollectionStatus
from revue_portee.domain.search import (
    ConceptBlock,
    Database,
    Limits,
    SearchStrategy,
    parse_term,
)
from revue_portee.search import strategies
from revue_portee.sources.crossref import Crossref
from revue_portee.sources.http import RateLimiter
from revue_portee.sources.openalex import OpenAlex
from revue_portee.sources.pubmed import PubMed
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import references as references_repo
from support import TOOL_VERSION, make_clock, new_project

pytestmark = pytest.mark.cassette

Clock = Callable[[], datetime]


def strategy(*blocks: tuple[str, ...], limits: Limits = Limits()) -> SearchStrategy:
    return SearchStrategy(
        blocks=tuple(
            ConceptBlock(code=f"B{n}", label=f"B{n}", terms=tuple(parse_term(t) for t in terms))
            for n, terms in enumerate(blocks, start=1)
        ),
        limits=limits,
    )


@pytest.fixture
def folder(tmp_path: Path) -> Iterator[ProjectFolder]:
    project = new_project(tmp_path, make_clock())
    yield project
    project.close()


@pytest.fixture
def recording(request: pytest.FixtureRequest) -> bool:
    return str(request.config.getoption("--record-mode")) != "none"


def collect_all(
    folder: ProjectFolder, database: Database, source: Collector
) -> collection.RunState:
    clock = make_clock()
    run = collection.start_collection(folder, database, now=clock, tool_version=TOOL_VERSION)
    return collection.collect(
        folder, run.id, now=clock, tool_version=TOOL_VERSION, factory=lambda _: source
    )


def test_pubmed_collection_matches_the_announced_count(
    folder: ProjectFolder, http_cassette: httpx2.Client, contact_email: SecretStr, recording: bool
) -> None:
    years = Limits(year_from=2022, year_to=2024)
    strategies.save_strategy(
        folder,
        strategy(('ti: "scoping review"',), ("ti:parent*",), limits=years),
        now=make_clock(),
        tool_version=TOOL_VERSION,
    )
    source = PubMed(
        http_cassette, email=contact_email, limiter=RateLimiter(0.4 if recording else 0.0)
    )
    state = collect_all(folder, Database.PUBMED, source)
    assert state.end is not None
    assert state.end.status is CollectionStatus.COMPLETED
    assert (state.pages, state.end.announced, state.end.collected) == (2, 218, 218)
    assert state.end.discrepancy == ""
    with folder.engine.connect() as connection:
        references = references_repo.list_references(connection)
    assert len(references) == 218
    assert all(r.pmid and r.title for r in references)
    assert sum(1 for r in references if r.doi) > 200
    assert sum(1 for r in references if r.abstract) > 200


def test_openalex_collection_matches_the_announced_count(
    folder: ProjectFolder, http_cassette: httpx2.Client, recording: bool
) -> None:
    strategies.save_strategy(
        folder,
        strategy(('"scoping review"',), ("fathers",)),
        now=make_clock(),
        tool_version=TOOL_VERSION,
    )
    source = OpenAlex(http_cassette, limiter=RateLimiter(0.2 if recording else 0.0))
    state = collect_all(folder, Database.OPENALEX, source)
    assert state.end is not None
    assert (state.pages, state.end.announced, state.end.collected) == (2, 268, 268)
    with folder.engine.connect() as connection:
        references = references_repo.list_references(connection)
    assert all(r.openalex_id.startswith("W") for r in references)
    assert sum(1 for r in references if r.abstract) > 100


def test_crossref_completes_a_pubmed_record_without_title(
    folder: ProjectFolder, http_cassette: httpx2.Client, contact_email: SecretStr, recording: bool
) -> None:
    clock = make_clock()
    content = (
        "TY  - JOUR\nPY  - 2018\nLA  - eng\nDO  - 10.3310/phr06130\nAN  - 30475559\n"
        "ID  - 30475559\nDB  - PubMed\nER  -\n"
        "TY  - JOUR\nTI  - DOI inconnu\nDO  - 10.9999/revue-portee.test.inexistant\nER  -\n"
    ).encode()
    imports.import_ris(folder, "pubmed.ris", content, now=clock, tool_version=TOOL_VERSION)

    def crossref() -> Crossref:
        return Crossref(
            http_cassette, email=contact_email, limiter=RateLimiter(0.2 if recording else 0.0)
        )

    summary = enrichment.enrich_references(
        folder, now=clock, tool_version=TOOL_VERSION, source=crossref, max_workers=1
    )
    assert (summary.checked, summary.enriched, summary.not_found) == (2, 1, 1)
    report = next(r for r in enrichment.references_with_enrichment(folder) if r.pmid)
    assert report.title
    assert report.container_title
    assert report.authors
