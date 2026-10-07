"""Translation of published strategies and syntactic equivalence (EF-REC-03).

Each reference strategy was published in an open-access scoping review; it is entered
as concept blocks, translated, and compared with the published text.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

from revue_portee.domain.search import (
    BlockRole,
    ConceptBlock,
    Database,
    Limits,
    SearchStrategy,
    next_block_code,
    parse_term,
)
from revue_portee.search.equivalence import Syntax, equivalent, normalize, parse
from revue_portee.search.translate import translate

FIXTURE = Path(__file__).parents[2] / "fixtures" / "search" / "reference_strategies.yaml"
REFERENCES: list[dict[str, Any]] = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def strategy_of(reference: dict[str, Any]) -> SearchStrategy:
    blocks: list[ConceptBlock] = []
    for entry in reference["blocks"]:
        blocks.append(
            ConceptBlock(
                code=next_block_code(b.code for b in blocks),
                label=entry["label"],
                role=BlockRole(entry["role"]),
                terms=tuple(parse_term(line) for line in entry["terms"]),
            )
        )
    return SearchStrategy(blocks=tuple(blocks), limits=Limits(**reference.get("limits", {})))


def test_at_least_ten_published_strategies() -> None:
    assert len(REFERENCES) >= 10
    assert all(r["doi"].startswith("10.") for r in REFERENCES)
    assert len({r["id"] for r in REFERENCES}) == len(REFERENCES)


@pytest.mark.parametrize("reference", REFERENCES, ids=[r["id"] for r in REFERENCES])
def test_published_strategy_is_reproduced(reference: dict[str, Any]) -> None:
    database = Database(reference["database"])
    translation = translate(strategy_of(reference), database)
    syntax = Syntax.PUBMED if database is Database.PUBMED else Syntax.EBSCO
    assert translation.warnings == ()
    assert equivalent(translation.text, reference["published"], syntax)


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ('a[tiab] OR "b c"[tiab]', "“b c”[Title/Abstract] OR a[tiab]"),
        ("(a[ti] OR a[ab]) AND b[mh]", "b[MeSH Terms] AND a[tiab]"),
        ("a[tiab] AND b[tiab] NOT c[tiab]", "b[tiab] NOT c[tiab] AND a[tiab]"),
        ("((a[tiab]))", "a[tiab]"),
        ('"2014"[pdat] : "2026"[pdat]', '"2014"[dp]:"2026"[dp]'),
        ("x[Mesh:NoExp]", "x[mh:noexp]"),
    ],
)
def test_equivalent_pubmed_forms(first: str, second: str) -> None:
    assert equivalent(first, second, Syntax.PUBMED)


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("a[tiab] OR b[tiab]", "a[tiab] AND b[tiab]"),  # operator
        ("a[tiab]", "a[ti]"),  # field
        ("a*[tiab]", "a[tiab]"),  # truncation
        ('"a b"[tiab]', '"a c"[tiab]'),  # phrase
        ("a[tiab] NOT b[tiab]", "b[tiab] NOT a[tiab]"),  # NOT is not commutative
        ("a[mh]", "a[mh:noexp]"),  # explosion
        ("(a[tiab] OR b[tiab]) AND c[tiab]", "a[tiab] OR (b[tiab] AND c[tiab])"),  # grouping
    ],
)
def test_different_pubmed_queries_are_told_apart(first: str, second: str) -> None:
    assert not equivalent(first, second, Syntax.PUBMED)


def test_ebsco_field_codes() -> None:
    assert equivalent(
        "TI ( a OR b ) OR AB ( a OR b )", "TI a OR AB a OR TI b OR AB b", Syntax.EBSCO
    )
    assert equivalent('DE "X+" or TI y', 'TI y OR DE "X +"', Syntax.EBSCO)
    assert not equivalent("TI a", "AB a", Syntax.EBSCO)
    assert not equivalent('DE "X+"', 'DE "X"', Syntax.EBSCO)


@pytest.mark.parametrize("text", ["(a[tiab]", "a[tiab])", "a AND", '"2014"[dp] : (b)', ""])
def test_unreadable_queries(text: str) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 - every reading error
        parse(text, Syntax.PUBMED)


def test_normalize_keeps_single_operands() -> None:
    assert normalize(parse("(a[tiab] OR a[tiab])", Syntax.PUBMED)) == parse(
        "a[tiab]", Syntax.PUBMED
    )
