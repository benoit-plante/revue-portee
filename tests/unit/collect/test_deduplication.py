"""Deduplication of a project (EF-COL-06 to EF-COL-08) on the demonstration set.

The demonstration set (tests/fixtures/dedup/demo-*.ris) holds 9 fictitious records,
computed by hand: PsycInfo 4, CINAHL 3, PubMed 2; one article in the three databases
(same DOI, written three ways), one in two (title without its subtitle, initials),
two records of the same title by different first authors (left to a person), and a
correction that must stay apart.
"""

import sqlite3
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

import pytest

from revue_portee.collect import deduplication, imports
from revue_portee.domain.dedup import DedupSettings, PairKind, PairOutcome, Proposal
from revue_portee.domain.journal import EntryType
from revue_portee.protocol import notes
from revue_portee.storage.project_folder import DATABASE_FILE, ProjectFolder
from revue_portee.storage.repositories import references as references_repo
from support import TOOL_VERSION, make_clock, new_project, raw_sqlite

Clock = Callable[[], datetime]
DEMO = Path(__file__).parents[2] / "fixtures" / "dedup"
FILES = (
    ("demo-psycinfo.ris", "APA PsycInfo (EBSCOhost)"),
    ("demo-cinahl.ris", "CINAHL (EBSCOhost)"),
    ("demo-pubmed.ris", "PubMed"),
)


def load_demo(folder: ProjectFolder, clock: Clock) -> dict[str, str]:
    """Import the demonstration set; ids by source and first word, e.g. "APA:housing"."""
    for name, database in FILES:
        content = (DEMO / name).read_bytes()
        imports.import_ris(
            folder, name, content, database=database, now=clock, tool_version=TOOL_VERSION
        )
    with folder.engine.connect() as connection:
        sources = references_repo.source_names(connection)
        refs = references_repo.list_references(connection)
    return {f"{sources[r.id][:3]}:{r.title.split()[0].lower().rstrip(':')}": r.id for r in refs}


@pytest.fixture
def setup(tmp_path: Path) -> Iterator[tuple[ProjectFolder, Clock, dict[str, str]]]:
    clock = make_clock()
    folder = new_project(tmp_path, clock)
    ids = load_demo(folder, clock)
    yield folder, clock, ids
    folder.close()


def run(folder: ProjectFolder, clock: Clock) -> None:
    deduplication.run_deduplication(folder, DedupSettings(), now=clock, tool_version=TOOL_VERSION)


def decide(folder: ProjectFolder, clock: Clock, a: str, b: str, outcome: PairOutcome) -> None:
    deduplication.decide_pair(folder, a, b, outcome, now=clock, tool_version=TOOL_VERSION)


def test_flow_numbers_of_the_demonstration_set(
    setup: tuple[ProjectFolder, Clock, dict[str, str]],
) -> None:
    folder, clock, ids = setup
    before = deduplication.dedup_state(folder)
    assert before.run is None
    assert (before.counts.identified, before.counts.duplicates_removed) == (9, 0)
    run(folder, clock)
    state = deduplication.dedup_state(folder)
    assert state.counts.identified_by_source == {
        "APA PsycInfo (EBSCOhost)": 4,
        "CINAHL (EBSCOhost)": 3,
        "PubMed": 2,
    }
    assert (state.counts.identified, state.counts.duplicates_removed) == (9, 3)
    assert (state.counts.after_deduplication, state.counts.pending_pairs) == (6, 1)
    assert sorted(len(g.members) for g in state.groups) == [2, 3]
    (pending,) = state.pending
    assert {pending.reference_a_id, pending.reference_b_id} == {
        ids["APA:loneliness"],
        ids["Pub:loneliness"],
    }
    assert pending.details["not_automatic"] == "first_author"
    # the person decides: they are duplicates
    decide(folder, clock, ids["Pub:loneliness"], ids["APA:loneliness"], PairOutcome.DUPLICATE)
    after = deduplication.dedup_state(folder)
    assert (after.counts.duplicates_removed, after.counts.after_deduplication) == (4, 5)
    assert after.counts.pending_pairs == 0
    # the correction stays apart, and the primary is the most complete record
    grouped = {ref_id for g in after.groups for ref_id in g.members}
    assert ids["APA:correction"] not in grouped
    article = next(g for g in after.groups if len(g.members) == 3)
    assert article.primary == ids["APA:housing"]  # complete, then the oldest import


def test_run_and_decisions_are_recorded_in_the_journal(
    setup: tuple[ProjectFolder, Clock, dict[str, str]],
) -> None:
    folder, clock, ids = setup
    run(folder, clock)
    entry = notes.journal_entries(folder)[-1]
    assert entry.entry_type == EntryType.DEDUP_COMPLETED
    assert entry.payload["references"] == 9
    assert entry.payload["automatic_pairs"] == 4
    assert entry.payload["review_pairs"] == 1
    assert entry.payload["pairs_by_kind"] == {"identifier": 3, "fuzzy": 2, "version": 0}
    assert entry.payload["settings"] == DedupSettings().model_dump(mode="json")
    a, b = sorted((ids["APA:loneliness"], ids["Pub:loneliness"]))
    decide(folder, clock, a, b, PairOutcome.NOT_DUPLICATE)
    entry = notes.journal_entries(folder)[-1]
    assert entry.entry_type == EntryType.DEDUP_PAIR_DECIDED
    assert entry.summary_fr == "Dédoublonnage : deux références gardées séparées"
    assert entry.payload["outcome"] == "not_duplicate"
    assert entry.payload["grouped_before"] is False
    assert entry.payload["rule"] == "similarity"
    assert notes.verify_journal(folder).valid


def test_every_grouping_can_be_undone_and_nothing_is_deleted(
    setup: tuple[ProjectFolder, Clock, dict[str, str]],
) -> None:
    folder, clock, ids = setup
    run(folder, clock)
    apa, cin, pub = ids["APA:housing"], ids["CIN:housing"], ids["Pub:housing"]
    decide(folder, clock, apa, cin, PairOutcome.NOT_DUPLICATE)
    state = deduplication.dedup_state(folder)
    # still one group: the CINAHL record is linked to PubMed, PubMed to PsycInfo
    assert any({apa, cin, pub} == set(g.members) for g in state.groups)
    decide(folder, clock, cin, pub, PairOutcome.NOT_DUPLICATE)
    state = deduplication.dedup_state(folder)
    assert any({apa, pub} == set(g.members) for g in state.groups)
    assert all(cin not in g.members for g in state.groups)
    assert state.counts.duplicates_removed == 2
    # undone, then redone
    decide(folder, clock, cin, pub, PairOutcome.DUPLICATE)
    state = deduplication.dedup_state(folder)
    assert any({apa, cin, pub} == set(g.members) for g in state.groups)
    # a new run keeps the decisions taken
    run(folder, clock)
    again = deduplication.dedup_state(folder)
    assert again.links == state.links
    with folder.engine.connect() as connection:
        assert references_repo.count_references(connection) == 9
    with raw_sqlite(folder.path / DATABASE_FILE) as connection:
        counts = {
            table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]  # noqa: S608
            for table in ("dedup_run", "duplicate_pair", "pair_decision")
        }
        assert counts == {"dedup_run": 2, "duplicate_pair": 10, "pair_decision": 3}
        for table in ("dedup_run", "duplicate_pair", "pair_decision"):
            with pytest.raises(sqlite3.DatabaseError, match="append-only"):
                connection.execute(f"DELETE FROM {table}")  # noqa: S608
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            connection.execute("UPDATE pair_decision SET outcome = 'duplicate'")


def test_errors(tmp_path: Path) -> None:
    clock = make_clock()
    folder = new_project(tmp_path, clock)
    try:
        with pytest.raises(deduplication.NoReferencesError):
            run(folder, clock)
        ids = load_demo(folder, clock)
        with pytest.raises(deduplication.UnknownPairError):
            decide(folder, clock, ids["APA:housing"], ids["CIN:housing"], PairOutcome.DUPLICATE)
        run(folder, clock)
        with pytest.raises(deduplication.UnknownPairError):  # never paired
            decide(folder, clock, ids["APA:housing"], ids["CIN:community"], PairOutcome.DUPLICATE)
    finally:
        folder.close()


def test_kinds_of_the_pairs(setup: tuple[ProjectFolder, Clock, dict[str, str]]) -> None:
    folder, clock, _ids = setup
    run(folder, clock)
    state = deduplication.dedup_state(folder)
    kinds = sorted((p.kind, p.rule, p.proposal) for p in state.pairs.values())
    assert kinds == sorted(
        [(PairKind.IDENTIFIER, "doi", Proposal.DUPLICATE)] * 3
        + [(PairKind.FUZZY, "similarity", Proposal.DUPLICATE)]
        + [(PairKind.FUZZY, "similarity", Proposal.REVIEW)]
    )
    assert state.new_references == 0
