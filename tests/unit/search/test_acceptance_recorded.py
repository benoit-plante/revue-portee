"""Acceptance tests of tranche 1.3 against recorded PubMed and OpenAlex answers.

- Counts per block and in total, for PubMed and OpenAlex (EF-REC-04).
- Sensitivity test: of 10 real key articles, 2 are scoping reviews on dementia that
  the population block (parents) cannot retrieve; the tool reports 8/10, names the 2
  missed articles and the responsible block (EF-REC-05).
"""

from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

import httpx2
import pytest
from pydantic import SecretStr

from revue_portee.domain.criteria import PccElement
from revue_portee.domain.search import ConceptBlock, Database, SearchStrategy, parse_term
from revue_portee.search import runs, strategies
from revue_portee.sources import SearchSource
from revue_portee.sources.http import RateLimiter
from revue_portee.sources.openalex import OpenAlex
from revue_portee.sources.pubmed import PubMed
from revue_portee.storage.project_folder import ProjectFolder
from support import TOOL_VERSION, make_clock, new_project

pytestmark = pytest.mark.cassette

Clock = Callable[[], datetime]

STRATEGY = SearchStrategy(
    blocks=(
        ConceptBlock(
            code="B1",
            label="Parents",
            pcc_element=PccElement.POPULATION,
            terms=tuple(parse_term(x) for x in ("parent*", "father*", "mother*")),
        ),
        ConceptBlock(
            code="B2",
            label="Scoping reviews",
            terms=(parse_term('"scoping review"'),),
        ),
    )
)

# Eight scoping reviews on parents (PubMed, 2024-2025), as DOI or PMID...
IN_SCOPE = [
    "10.1080/03036758.2024.2399359",
    "39938532",
    "10.3389/phrs.2024.1607651",
    "39757795",
    "PMID: 39713846",
    "https://doi.org/10.1186/s13643-024-02690-2",
    "39696198",
    "10.2196/60352",
]
# ... and two on dementia, outside the population block.
OUT_OF_SCOPE = ["10.12688/openresafrica.14092.4", "39086663"]


@pytest.fixture
def setup(tmp_path: Path) -> Iterator[tuple[ProjectFolder, Clock]]:
    clock = make_clock()
    folder = new_project(tmp_path, clock)
    strategies.save_strategy(folder, STRATEGY, now=clock, tool_version=TOOL_VERSION)
    runs.save_key_articles(folder, IN_SCOPE + OUT_OF_SCOPE, now=clock, tool_version=TOOL_VERSION)
    yield folder, clock
    folder.close()


@pytest.fixture
def factory(
    request: pytest.FixtureRequest, http_cassette: httpx2.Client, contact_email: SecretStr
) -> Callable[[Database], SearchSource]:
    recording = str(request.config.getoption("--record-mode")) != "none"

    def make(database: Database) -> SearchSource:
        if database is Database.PUBMED:
            limiter = RateLimiter(0.4 if recording else 0.0)
            return PubMed(http_cassette, email=contact_email, limiter=limiter)
        return OpenAlex(http_cassette, limiter=RateLimiter(0.2 if recording else 0.0))

    return make


@pytest.mark.parametrize("database", [Database.PUBMED, Database.OPENALEX])
def test_counts_per_block_and_total(
    setup: tuple[ProjectFolder, Clock],
    factory: Callable[[Database], SearchSource],
    database: Database,
) -> None:
    folder, clock = setup
    run = runs.count_results(
        folder, database, now=clock, tool_version=TOOL_VERSION, factory=factory
    )
    assert run.result_count is not None
    assert set(run.block_counts) == {"B1", "B2"}
    # AND can only narrow: the total is below each block alone.
    assert 0 < run.result_count < min(run.block_counts.values())


@pytest.mark.parametrize("database", [Database.PUBMED, Database.OPENALEX])
def test_sensitivity_reports_eight_of_ten(
    setup: tuple[ProjectFolder, Clock],
    factory: Callable[[Database], SearchSource],
    database: Database,
) -> None:
    folder, clock = setup
    check = runs.check_sensitivity(
        folder, database, now=clock, tool_version=TOOL_VERSION, factory=factory
    )
    result = check.result
    assert (result.found, result.indexed) == (8, 10)
    assert [o.article.label for o in result.missed] == [
        "DOI 10.12688/OPENRESAFRICA.14092.4",  # DOIs are stored in upper case
        "PMID 39086663",
    ]
    assert [o.responsible for o in result.missed] == [("B1",), ("B1",)]
