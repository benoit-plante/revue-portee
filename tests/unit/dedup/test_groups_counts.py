"""Links in force, groups, primary reference, flow numbers and evaluation, by hand."""

from datetime import UTC, datetime, timedelta

import pytest

from revue_portee.dedup.counts import flow_counts
from revue_portee.dedup.evaluation import evaluate
from revue_portee.dedup.groups import (
    Group,
    choose_primary,
    group_references,
    links_in_force,
    pending_pairs,
)
from revue_portee.dedup.matching import Candidate
from revue_portee.domain.dedup import (
    DuplicatePair,
    PairDecision,
    PairKind,
    PairOutcome,
    Proposal,
)
from revue_portee.domain.references import Reference

NOW = datetime(2026, 10, 8, tzinfo=UTC)


def ref(ref_id: str, minutes: int = 0, **fields: object) -> Reference:
    return Reference(id=ref_id, created_at=NOW + timedelta(minutes=minutes), **fields)  # type: ignore[arg-type]


def pair(a: str, b: str, proposal: Proposal = Proposal.DUPLICATE) -> DuplicatePair:
    return DuplicatePair(
        id=f"P{a}{b}",
        run_id="R",
        reference_a_id=a,
        reference_b_id=b,
        kind=PairKind.FUZZY,
        rule="similarity",
        score=0.9,
        proposal=proposal,
    )


def decision(a: str, b: str, outcome: PairOutcome, n: int = 0) -> PairDecision:
    return PairDecision(
        id=f"D{n}",
        reference_a_id=a,
        reference_b_id=b,
        pair_id=None,
        outcome=outcome,
        reviewer_id="H",
        created_at=NOW + timedelta(minutes=n),
    )


def test_links_follow_the_latest_decision() -> None:
    pairs = [pair("A", "B"), pair("B", "C", Proposal.REVIEW), pair("D", "E")]
    assert links_in_force(pairs, []) == {("A", "B"), ("D", "E")}
    decisions = [
        decision("B", "C", PairOutcome.DUPLICATE, 1),
        decision("D", "E", PairOutcome.NOT_DUPLICATE, 2),  # undo an automatic grouping
        decision("A", "B", PairOutcome.NOT_DUPLICATE, 3),
        decision("A", "B", PairOutcome.DUPLICATE, 4),  # and redo it
    ]
    assert links_in_force(pairs, decisions) == {("A", "B"), ("B", "C")}
    assert pending_pairs(pairs, decisions) == []
    assert pending_pairs(pairs, decisions[1:]) == [pairs[1]]


def test_a_pair_already_joined_by_other_links_is_not_pending() -> None:
    pairs = [pair("A", "B"), pair("B", "C"), pair("A", "C", Proposal.REVIEW)]
    pairs.append(pair("D", "E", Proposal.REVIEW))
    references = {k: ref(k, title="T") for k in "ABCDE"}
    groups = group_references(references, links_in_force(pairs, []))
    assert pending_pairs(pairs, [], groups) == [pairs[3]]
    assert pending_pairs(pairs, []) == [pairs[2], pairs[3]]


def test_groups_join_linked_references_under_the_most_complete() -> None:
    references = {
        "A": ref("A", title="T"),
        "B": ref("B", 1, title="T", doi="10.1/X"),
        "C": ref("C", 2, title="T", doi="10.1/X", abstract="Résumé"),
        "D": ref("D", title="U"),
        "E": ref("E", title="U"),
        "F": ref("F", title="V"),
    }
    groups = group_references(references, [("A", "B"), ("B", "C"), ("D", "E"), ("E", "Z")])
    assert groups == [Group("C", ("C", "A", "B")), Group("D", ("D", "E"))]
    assert groups[0].duplicates == ("A", "B")


def test_primary_is_the_oldest_when_records_are_as_complete() -> None:
    late, early = ref("A", 5, title="T"), ref("B", 1, title="T")
    assert choose_primary([late, early]) is early
    assert choose_primary([ref("B", title="T"), ref("A", title="T")]).id == "A"


def test_flow_numbers_of_the_demonstration_set() -> None:
    # Computed by hand: 4 PsycInfo records, 3 CINAHL, 2 PubMed (9 identified);
    # one group of three (2 duplicates) and one group of two (1 duplicate).
    source_of = {
        "p1": "PsycInfo",
        "p2": "PsycInfo",
        "p3": "PsycInfo",
        "p4": "PsycInfo",
        "c1": "CINAHL",
        "c2": "CINAHL",
        "c3": "CINAHL",
        "m1": "PubMed",
        "m2": "PubMed",
    }
    groups = [Group("p1", ("p1", "c1", "m1")), Group("p2", ("p2", "c2"))]
    counts = flow_counts(source_of, groups, pending_pairs=1)
    assert counts.identified_by_source == {"CINAHL": 3, "PsycInfo": 4, "PubMed": 2}
    assert (counts.identified, counts.duplicates_removed, counts.after_deduplication) == (9, 3, 6)
    assert counts.pending_pairs == 1


def candidate(a: str, b: str, proposal: Proposal, kind: PairKind = PairKind.FUZZY) -> Candidate:
    return Candidate(a, b, kind, "similarity", 0.9, proposal)


def test_evaluation_by_hand() -> None:
    # Annotated: {a, b, c} duplicates, {d, e} duplicates, f and g alone (4 true pairs);
    # groups g1 and g4 are two versions of one work.
    truth = {"a": "g1", "b": "g1", "c": "g1", "d": "g2", "e": "g2", "f": "g3", "g": "g4"}
    candidates = [
        candidate("a", "b", Proposal.DUPLICATE),
        candidate("b", "c", Proposal.REVIEW),  # the person groups it: a true pair
        candidate("d", "f", Proposal.DUPLICATE),  # an automatic error
        candidate("e", "f", Proposal.REVIEW),  # the person keeps it apart
        candidate("a", "g", Proposal.REVIEW, PairKind.VERSION),
    ]
    result = evaluate(candidates, truth, [("g4", "g1")])
    # found groups {a, b, c} and {d, f}: 4 pairs, of which 3 true; d-e is missed
    assert (result.true_pairs, result.found_pairs, result.correct_pairs) == (4, 4, 3)
    assert result.recall == pytest.approx(0.75)
    assert result.precision == pytest.approx(0.75)
    assert (result.automatic_pairs, result.automatic_errors, result.review_pairs) == (2, 1, 3)
    assert (result.versions, result.versions_flagged) == (1, 1)


def test_evaluation_without_pairs() -> None:
    result = evaluate([], {"a": "g1", "b": "g2"})
    assert (result.recall, result.precision) == (1.0, 1.0)


def test_pairs_and_decisions_are_ordered() -> None:
    with pytest.raises(ValueError, match="sort before"):
        pair("B", "A")
    with pytest.raises(ValueError, match="sort before"):
        decision("B", "A", PairOutcome.DUPLICATE)
