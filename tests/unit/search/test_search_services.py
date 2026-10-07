"""Search services with fake connectors and FakeProvider (EF-REC-01 to 06)."""

import sqlite3
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from revue_portee.domain.criteria import PccElement
from revue_portee.domain.framing import Framing
from revue_portee.domain.journal import EntryType
from revue_portee.domain.search import (
    BlockRole,
    ConceptBlock,
    Database,
    KeyArticle,
    KeyArticleKind,
    Limits,
    SearchStrategy,
    TermSuggestionKind,
    parse_term,
)
from revue_portee.domain.sensitivity import LIMITS
from revue_portee.domain.suggestions import SuggestionOutcome
from revue_portee.protocol import framing, notes
from revue_portee.search import runs, strategies, suggestions
from revue_portee.sources import SourceAnswer, UnsupportedDatabaseError, default_source_factory
from revue_portee.sources.pubmed import MeshCheck
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.raw import read_source_pages
from support import TOOL_VERSION, fake_factory, make_clock, new_project, raw_sqlite

Clock = Callable[[], datetime]


def block(code: str, *lines: str, role: BlockRole = BlockRole.INCLUDE) -> ConceptBlock:
    return ConceptBlock(code=code, label=code, role=role, terms=tuple(parse_term(x) for x in lines))


STRATEGY = SearchStrategy(
    blocks=(
        block("B1", "parent*", "mesh:Parenting"),
        block("B2", '"scoping review"'),
        block("B3", "rat*", role=BlockRole.EXCLUDE),
    ),
    limits=Limits(year_from=2010, languages=("en",)),
)


@dataclass
class FakeSource:
    """Each query retrieves the records listed for it; records resolve by value."""

    database: Database
    hits: dict[str, set[str]]
    counts: dict[str, int] = field(default_factory=dict)
    calls: list[tuple[str, str]] = field(default_factory=list)

    def count(self, query: str) -> SourceAnswer:
        self.calls.append(("count", query))
        return SourceAnswer(count=self.counts.get(query, 0), ids=(), raw={"q": query})

    def among(self, query: str, ids: Sequence[str]) -> SourceAnswer:
        self.calls.append(("among", query))
        found = tuple(i for i in ids if i in self.hits.get(query, set()))
        return SourceAnswer(count=len(found), ids=found, raw={"q": query, "ids": list(ids)})

    def resolve(self, article: KeyArticle) -> tuple[str | None, dict[str, Any]]:
        record = None if article.value.startswith("absent") else f"R-{article.value}"
        return record, {"resolve": article.value}


@pytest.fixture
def setup(tmp_path: Path) -> Iterator[tuple[ProjectFolder, Clock]]:
    clock = make_clock()
    folder = new_project(tmp_path, clock)
    yield folder, clock
    folder.close()


def types(folder: ProjectFolder) -> list[str]:
    return [e.entry_type for e in notes.journal_entries(folder)]


def test_strategy_versions_keep_each_query(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    first = strategies.save_strategy(folder, STRATEGY, now=clock, tool_version=TOOL_VERSION)
    again = strategies.save_strategy(folder, STRATEGY, now=clock, tool_version=TOOL_VERSION)
    assert again.id == first.id  # unchanged: no new version
    changed = STRATEGY.model_copy(update={"limits": Limits()})
    second = strategies.save_strategy(
        folder, changed, rationale=" No limits ", now=clock, tool_version=TOOL_VERSION
    )
    assert (first.number, second.number, second.rationale) == (1, 2, "No limits")
    history = strategies.strategy_history(folder)
    assert [len(queries) for _, queries in history] == [3, 3]
    queries = strategies.current_queries(folder)
    assert set(queries) == set(Database)
    pubmed = queries[Database.PUBMED].translation
    assert pubmed.text == (
        '(parent*[tiab] OR "Parenting"[mh]) AND ("scoping review"[tiab]) NOT (rat*[tiab])'
    )
    old = {q.database: q for q in history[0][1]}[Database.PUBMED]
    assert "english[la]" in old.translation.text  # the exact text of version 1 is kept
    assert types(folder).count(EntryType.SEARCH_QUERY_VERSIONED) == 2
    assert strategies.current_strategy(folder) == second


def test_empty_first_strategy_is_refused(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    with pytest.raises(strategies.EmptyStrategyError):
        strategies.save_strategy(folder, SearchStrategy(), now=clock, tool_version=TOOL_VERSION)
    assert strategies.current_queries(folder) == {}


def test_counts_total_and_per_block(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    with pytest.raises(runs.NoQueryError):
        runs.count_results(folder, Database.PUBMED, now=clock, tool_version=TOOL_VERSION)
    strategies.save_strategy(folder, STRATEGY, now=clock, tool_version=TOOL_VERSION)
    query = strategies.current_queries(folder)[Database.PUBMED].translation
    source = FakeSource(
        Database.PUBMED,
        hits={},
        counts={query.text: 42, query.blocks["B1"]: 9000, query.blocks["B2"]: 700},
    )
    run = runs.count_results(
        folder, Database.PUBMED, now=clock, tool_version=TOOL_VERSION, factory=lambda _: source
    )
    assert run.result_count == 42
    assert run.block_counts == {"B1": 9000, "B2": 700, "B3": 0}
    assert len(read_source_pages(folder.path, run.raw_dir)) == 4
    assert runs.latest_runs(folder)[run.query_id] == run
    entry = notes.journal_entries(folder)[-1]
    assert entry.entry_type == EntryType.SEARCH_RUN_COMPLETED
    assert entry.payload["total"] == 42


def test_failed_recording_leaves_no_raw_folder(
    setup: tuple[ProjectFolder, Clock], monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, clock = setup
    strategies.save_strategy(folder, STRATEGY, now=clock, tool_version=TOOL_VERSION)

    def broken(*_args: object, **_kwargs: object) -> None:
        raise sqlite3.OperationalError("disk full")

    monkeypatch.setattr(runs.search_repo, "insert_run", broken)
    source = FakeSource(Database.OPENALEX, hits={})
    with pytest.raises(sqlite3.OperationalError):
        runs.count_results(
            folder,
            Database.OPENALEX,
            now=clock,
            tool_version=TOOL_VERSION,
            factory=lambda _: source,
        )
    assert not any((folder.path / "brut" / "sources").iterdir())


def test_key_articles(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    with pytest.raises(runs.InvalidKeyArticlesError) as raised:
        runs.save_key_articles(folder, ["12345", "court"], now=clock, tool_version=TOOL_VERSION)
    assert raised.value.lines == ("court",)
    assert runs.save_key_articles(folder, ["", " "], now=clock, tool_version=TOOL_VERSION) is None
    lines = ["PMID: 12345", "https://doi.org/10.1000/ABC", "12345", "A title long enough"]
    first = runs.save_key_articles(folder, lines, now=clock, tool_version=TOOL_VERSION)
    assert first is not None
    assert [a.kind for a in first.articles] == [
        KeyArticleKind.PMID,
        KeyArticleKind.DOI,
        KeyArticleKind.TITLE,
    ]
    same = runs.save_key_articles(folder, lines, now=clock, tool_version=TOOL_VERSION)
    assert same == first
    assert runs.current_key_articles(folder) == first
    assert types(folder).count(EntryType.SEARCH_KEY_ARTICLES_UPDATED) == 1


def test_sensitivity_names_missed_articles_and_blocks(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    strategies.save_strategy(folder, STRATEGY, now=clock, tool_version=TOOL_VERSION)
    with pytest.raises(runs.NoKeyArticlesError):
        runs.check_sensitivity(folder, Database.PUBMED, now=clock, tool_version=TOOL_VERSION)
    pmids = [str(n) for n in range(1, 11)]
    runs.save_key_articles(
        folder, [*pmids, "absent from PubMed title"], now=clock, tool_version=TOOL_VERSION
    )
    query = strategies.current_queries(folder)[Database.PUBMED].translation
    records = {f"R-{p}" for p in pmids}
    source = FakeSource(
        Database.PUBMED,
        hits={
            query.text: records - {"R-9", "R-10"},
            query.blocks["B1"]: records - {"R-9"},  # B1 loses article 9
            query.blocks["B2"]: records,
            query.blocks["B3"]: {"R-10"},  # NOT B3 removes article 10
            query.limits: records,
        },
    )
    check = runs.check_sensitivity(
        folder, Database.PUBMED, now=clock, tool_version=TOOL_VERSION, factory=lambda _: source
    )
    result = check.result
    assert (result.found, result.indexed) == (8, 10)
    assert [(o.article.value, o.responsible) for o in result.missed] == [
        ("9", ("B1",)),
        ("10", ("B3",)),
    ]
    assert [o.article.value for o in result.not_indexed] == ["absent from PubMed title"]
    entry = notes.journal_entries(folder)[-1]
    assert entry.entry_type == EntryType.SEARCH_SENSITIVITY_CHECKED
    assert entry.payload["missed"] == [
        {"article": "PMID 9", "responsible": ["B1"]},
        {"article": "PMID 10", "responsible": ["B3"]},
    ]
    assert entry.payload["recall"] == "0.800"
    [(run, stored)] = runs.sensitivity_checks(folder)
    assert stored == check
    assert run.result_count is None


def test_sensitivity_blames_limits_and_skips_blocks_when_all_found(
    setup: tuple[ProjectFolder, Clock],
) -> None:
    folder, clock = setup
    strategies.save_strategy(folder, STRATEGY, now=clock, tool_version=TOOL_VERSION)
    runs.save_key_articles(folder, ["1", "2"], now=clock, tool_version=TOOL_VERSION)
    query = strategies.current_queries(folder)[Database.OPENALEX].translation
    every = {"R-1", "R-2"}
    source = FakeSource(
        Database.OPENALEX,
        hits={query.text: {"R-1"}, query.blocks["B1"]: every, query.blocks["B2"]: every},
    )
    check = runs.check_sensitivity(
        folder, Database.OPENALEX, now=clock, tool_version=TOOL_VERSION, factory=lambda _: source
    )
    assert check.result.missed[0].responsible == (LIMITS,)
    complete = FakeSource(Database.OPENALEX, hits={query.text: every})
    runs.check_sensitivity(
        folder, Database.OPENALEX, now=clock, tool_version=TOOL_VERSION, factory=lambda _: complete
    )
    assert [kind for kind, _ in complete.calls] == ["among"]  # no block query needed


@dataclass
class FakeMesh:
    known: dict[str, str]
    asked: list[str] = field(default_factory=list)

    def mesh(self, heading: str) -> MeshCheck:
        self.asked.append(heading)
        official = next((h for h in self.known if h.casefold() == heading.casefold()), None)
        if official is None:
            return MeshCheck(found=False, heading=None, ui=None, raw=({"term": heading},))
        return MeshCheck(found=True, heading=official, ui=self.known[official], raw=({},))


def terms_answer(_item: object) -> dict[str, Any]:
    return {
        "suggestions": [
            {"block_code": "B1", "kind": "free_term", "line": "father*", "rationale": "Pères"},
            {
                "block_code": "B1",
                "kind": "descriptor",
                "line": "mesh:Parenting Programs",
                "rationale": "M",
            },
            {"block_code": "B1", "kind": "free_term", "line": "parent*", "rationale": "déjà là"},
            {
                "block_code": "B9",
                "kind": "free_term",
                "line": "mother*",
                "rationale": "bloc inconnu",
            },
            {"block_code": "B2", "kind": "free_term", "line": "a AND b", "rationale": "invalide"},
            {"block_code": "B2", "kind": "free_term", "line": '"scoping study"', "rationale": "V"},
        ]
    }


FACTORY = fake_factory({"SuggestTermsInput": terms_answer})


def test_term_suggestions_are_reviewed_into_new_versions(
    setup: tuple[ProjectFolder, Clock],
) -> None:
    folder, clock = setup
    with pytest.raises(suggestions.NoStrategyError):
        suggestions.request_term_suggestions(
            folder, now=clock, tool_version=TOOL_VERSION, factory=FACTORY
        )
    framing.save_framing(
        folder,
        Framing(question="Quels programmes ?", population="Parents"),
        now=clock,
        tool_version=TOOL_VERSION,
    )
    strategies.save_strategy(folder, STRATEGY, now=clock, tool_version=TOOL_VERSION)
    preview = suggestions.preview_term_suggestions(folder, factory=FACTORY)
    assert preview.items == 1
    received = suggestions.request_term_suggestions(
        folder, now=clock, tool_version=TOOL_VERSION, factory=FACTORY
    )
    assert [(s.block_code, s.line) for s in received] == [
        ("B1", "father*"),
        ("B1", "mesh: Parenting Programs"),
        ("B2", '"scoping study"'),
    ]
    entry = notes.journal_entries(folder)[-1]
    assert entry.entry_type == EntryType.SEARCH_TERMS_SUGGESTED
    assert entry.payload["left_out"] == 3

    # MeSH headings of the strategy and of pending suggestions are checked.
    assert runs.headings_to_check(folder) == ["Parenting", "Parenting Programs"]
    mesh = FakeMesh({"Parenting": "D016487"})
    checks = runs.check_descriptors(
        folder, now=clock, tool_version=TOOL_VERSION, source=lambda: mesh
    )
    assert [(c.heading, c.found, c.descriptor_ui) for c in checks] == [
        ("Parenting", True, "D016487"),
        ("Parenting Programs", False, None),
    ]
    assert runs.descriptor_checks(folder)[("mesh", "parenting programs")].found is False
    assert notes.journal_entries(folder)[-1].payload["checks"][1]["found"] is False

    father, programs, scoping = received
    accepted = suggestions.review_term_suggestion(
        folder, father.id, SuggestionOutcome.ACCEPTED, now=clock, tool_version=TOOL_VERSION
    )
    assert accepted.strategy_version_id is not None
    version = strategies.current_strategy(folder)
    assert version is not None
    assert version.number == 2
    b1 = version.strategy.block("B1")
    assert b1 is not None
    assert parse_term("father*") in b1.terms
    with pytest.raises(suggestions.AlreadyReviewedError):
        suggestions.review_term_suggestion(
            folder, father.id, SuggestionOutcome.REJECTED, now=clock, tool_version=TOOL_VERSION
        )
    rejected = suggestions.review_term_suggestion(
        folder, programs.id, SuggestionOutcome.REJECTED, now=clock, tool_version=TOOL_VERSION
    )
    assert (rejected.final_line, rejected.strategy_version_id) == ("", None)
    with pytest.raises(suggestions.InvalidTermError):
        suggestions.review_term_suggestion(
            folder,
            scoping.id,
            SuggestionOutcome.MODIFIED,
            line="(x",
            now=clock,
            tool_version=TOOL_VERSION,
        )
    modified = suggestions.review_term_suggestion(
        folder,
        scoping.id,
        SuggestionOutcome.MODIFIED,
        line="scoping stud*",
        now=clock,
        tool_version=TOOL_VERSION,
    )
    assert modified.final_line == '"scoping stud*"'
    assert modified.outcome is SuggestionOutcome.MODIFIED
    views = suggestions.list_term_suggestions(folder)
    assert [v.review is not None for v in views] == [True, True, True]
    assert views[0].model_returned == "fake-model-2026-10-07"
    assert runs.headings_to_check(folder) == ["Parenting"]  # the rejected one is no longer pending
    with pytest.raises(suggestions.UnknownSuggestionError):
        suggestions.review_term_suggestion(
            folder, "nope", SuggestionOutcome.ACCEPTED, now=clock, tool_version=TOOL_VERSION
        )


def test_accepting_into_a_removed_block_fails(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    strategies.save_strategy(folder, STRATEGY, now=clock, tool_version=TOOL_VERSION)
    [first, *_] = suggestions.request_term_suggestions(
        folder, now=clock, tool_version=TOOL_VERSION, factory=FACTORY
    )
    without_b1 = STRATEGY.model_copy(update={"blocks": STRATEGY.blocks[1:]})
    strategies.save_strategy(folder, without_b1, now=clock, tool_version=TOOL_VERSION)
    with pytest.raises(suggestions.BlockGoneError):
        suggestions.review_term_suggestion(
            folder, first.id, SuggestionOutcome.ACCEPTED, now=clock, tool_version=TOOL_VERSION
        )
    assert (
        runs.check_descriptors(
            folder, now=clock, tool_version=TOOL_VERSION, source=lambda: FakeMesh({})
        )
        != []
    )


def test_tables_are_append_only(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    strategies.save_strategy(folder, STRATEGY, now=clock, tool_version=TOOL_VERSION)
    with (
        raw_sqlite(folder.path / "revue.sqlite") as connection,
        pytest.raises(sqlite3.IntegrityError, match="append-only"),
    ):
        connection.execute("UPDATE query SET syntax_text = 'x'")


def test_psycinfo_has_no_api() -> None:
    with pytest.raises(UnsupportedDatabaseError, match="PsycINFO"):
        default_source_factory(Database.PSYCINFO_EBSCO)


def test_pcc_element_is_kept_in_blocks() -> None:
    b = ConceptBlock(code="B1", label="Parents", pcc_element=PccElement.POPULATION)
    assert TermSuggestionKind.DESCRIPTOR.value == "descriptor"
    assert b.pcc_element is PccElement.POPULATION
