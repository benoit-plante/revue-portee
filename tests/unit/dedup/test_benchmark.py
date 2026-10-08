"""Deduplication on the annotated set of tranche 1.5 (tests/fixtures/dedup/README.md).

Acceptance criterion: recall of duplicates ≥ 0.98 and precision ≥ 0.99 for the
automatic grouping plus the pairs left to a person (simulated by the annotation).
"""

import json
from collections import Counter
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from revue_portee.dedup.evaluation import Evaluation, evaluate
from revue_portee.dedup.matching import find_candidates
from revue_portee.domain.dedup import DedupSettings, Proposal
from revue_portee.domain.references import Reference

FIXTURES = Path(__file__).parents[2] / "fixtures" / "dedup"
NOW = datetime(2026, 10, 8, tzinfo=UTC)


@cache
def annotated() -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    with (FIXTURES / "references.jsonl").open(encoding="utf-8") as lines:
        rows = [json.loads(line) for line in lines]
    versions = [(a, b) for a, b, _kind in json.loads((FIXTURES / "versions.json").read_text())]
    return rows, versions


def references(*, identifiers: bool = True) -> list[Reference]:
    rows, _versions = annotated()
    return [
        Reference(
            id=r["id"],
            title=r["title"],
            authors=tuple(r["authors"]),
            year=r["year"],
            container_title=r["container_title"],
            volume=r["volume"],
            issue=r["issue"],
            pages=r["pages"],
            doi=r["doi"] if identifiers else "",
            pmid=r["pmid"] if identifiers else "",
            openalex_id=r["openalex_id"] if identifiers else "",
            language=r["language"],
            doc_type=r["doc_type"],
            created_at=NOW,
        )
        for r in rows
    ]


def run(settings: DedupSettings, *, identifiers: bool = True) -> Evaluation:
    rows, versions = annotated()
    candidates = find_candidates(references(identifiers=identifiers), settings)
    return evaluate(candidates, {r["id"]: r["cluster"] for r in rows}, versions)


def test_the_annotated_set_is_as_described() -> None:
    rows, versions = annotated()
    groups = Counter(r["cluster"] for r in rows)
    assert len(rows) == 4486
    assert len(groups) == 2642
    assert sum(n * (n - 1) // 2 for n in groups.values()) == 2670
    assert len(versions) == 30
    assert all("abstract" not in r for r in rows)  # no abstract is published (D-060)
    assert Counter(r["database"] for r in rows)["Variante construite"] == 103


def test_recall_and_precision_with_default_thresholds() -> None:
    result = run(DedupSettings())
    assert result.recall >= 0.98
    assert result.precision >= 0.99
    assert result.automatic_errors == 0
    assert result.versions_flagged == result.versions == 30
    assert result.review_pairs <= 100  # the person's work stays small


@pytest.mark.parametrize(("review_from", "auto_from"), [(0.6, 0.85), (0.8, 0.97)])
def test_results_hold_for_other_thresholds(review_from: float, auto_from: float) -> None:
    result = run(DedupSettings(review_from=review_from, auto_from=auto_from))
    assert result.recall >= 0.98
    assert result.precision >= 0.99


def test_without_any_identifier_approximate_matching_still_finds_duplicates() -> None:
    result = run(DedupSettings(), identifiers=False)
    assert result.recall >= 0.98
    assert result.precision >= 0.99


def test_every_constructed_variant_is_grouped_with_its_original() -> None:
    rows, _versions = annotated()
    cluster = {r["id"]: r["cluster"] for r in rows}
    variants = {r["id"]: r["variant"] for r in rows if "variant" in r}
    grouped: set[str] = set()
    reviewed: set[str] = set()
    for c in find_candidates(references(), DedupSettings()):
        if cluster[c.reference_a] == cluster[c.reference_b]:
            found = grouped if c.proposal is Proposal.DUPLICATE else reviewed
            found |= {c.reference_a, c.reference_b}
    assert all(v in grouped | reviewed for v in variants)
    # Without its subtitle, one title keeps a single word: a person decides.
    assert sorted(v for v in variants if v not in grouped) == [
        "variant-003-no_subtitle",
        "variant-018-no_subtitle",
    ]
    assert set(variants.values()) == {
        "accents",
        "upper_case",
        "no_subtitle",
        "punctuation",
        "no_doi_journal_case",
        "author_initials",
        "online_first",
        "html_markup",
        "typo",
    }
