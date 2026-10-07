"""Concept blocks, term syntax, limits and key articles (EF-REC-01, EF-REC-05)."""

import pytest

from revue_portee.domain.search import (
    BlockRole,
    ConceptBlock,
    Database,
    KeyArticleKind,
    Limits,
    SearchStrategy,
    Term,
    TermField,
    TermKind,
    TermSyntaxError,
    Vocabulary,
    format_term,
    next_block_code,
    parse_key_article,
    parse_term,
)


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("parent*", Term(kind=TermKind.FREE, text="parent*")),
        ('"parenting program"', Term(kind=TermKind.FREE, text="parenting program", phrase=True)),
        (
            "« programme parental »",
            Term(kind=TermKind.FREE, text="programme parental", phrase=True),
        ),
        ("parenting  program", Term(kind=TermKind.FREE, text="parenting program", phrase=True)),
        ("TI: father*", Term(kind=TermKind.FREE, text="father*", field=TermField.TI)),
        ("pt:Review", Term(kind=TermKind.FREE, text="Review", field=TermField.PT)),
        (
            'mesh: "Parenting"',
            Term(kind=TermKind.DESCRIPTOR, text="Parenting", vocabulary=Vocabulary.MESH),
        ),
        (
            "mesh-noexp:Fathers",
            Term(
                kind=TermKind.DESCRIPTOR, text="Fathers", vocabulary=Vocabulary.MESH, explode=False
            ),
        ),
        (
            "apa:Parenting",
            Term(
                kind=TermKind.DESCRIPTOR, text="Parenting", vocabulary=Vocabulary.APA, explode=False
            ),
        ),
        (
            "apa+:Parenting",
            Term(kind=TermKind.DESCRIPTOR, text="Parenting", vocabulary=Vocabulary.APA),
        ),
        (
            "pubmed: (a[ti] OR b[ti])",
            Term(kind=TermKind.RAW, text="(a[ti] OR b[ti])", database=Database.PUBMED),
        ),
        ("covid-19: impact", Term(kind=TermKind.FREE, text="covid-19: impact", phrase=True)),
    ],
)
def test_parse_and_format_round_trip(line: str, expected: Term) -> None:
    term = parse_term(line)
    assert term == expected
    assert parse_term(format_term(term)) == term


@pytest.mark.parametrize(
    "line",
    [
        "",
        "   ",
        "ti:",
        "a AND b",
        "x NOT y",
        '"open',
        "(a)",
        "a[tiab]",
        'mesh: ""',
        'mesh: a"b',
        "pubmed: (a",
    ],
)
def test_invalid_lines(line: str) -> None:
    with pytest.raises(TermSyntaxError):
        parse_term(line)


def test_operators_inside_words_are_allowed() -> None:
    assert parse_term("ANDROGEN").text == "ANDROGEN"
    assert parse_term("candor").truncated is False
    assert parse_term("cand*").truncated is True


def test_inconsistent_terms_are_refused() -> None:
    with pytest.raises(ValueError, match="vocabulary"):
        Term(kind=TermKind.FREE, text="a", vocabulary=Vocabulary.MESH)
    with pytest.raises(ValueError, match="database"):
        Term(kind=TermKind.FREE, text="a", database=Database.PUBMED)


def test_blocks_and_strategy() -> None:
    terms = (parse_term("a"), parse_term("pubmed: b[ti]"), parse_term("openalex: type:review"))
    b1 = ConceptBlock(code="B1", label="A", terms=terms)
    b2 = ConceptBlock(code="B2", label="Empty")
    b3 = ConceptBlock(code="B3", label="NOT", role=BlockRole.EXCLUDE, terms=(parse_term("x"),))
    assert [t.text for t in b1.terms_for(Database.PUBMED)] == ["a", "b[ti]"]
    strategy = SearchStrategy(blocks=(b1, b2, b3))
    assert strategy.included == (b1,)
    assert strategy.excluded == (b3,)
    assert strategy.block("B2") == b2
    assert strategy.block("B9") is None
    with pytest.raises(ValueError, match="unique"):
        SearchStrategy(blocks=(b1, b1))
    with pytest.raises(ValueError):  # noqa: PT011
        ConceptBlock(code="A1", label="x")


def test_block_codes_are_never_reused() -> None:
    assert next_block_code([]) == "B1"
    assert next_block_code(["B1", "B3", "x"]) == "B4"


def test_limits() -> None:
    assert Limits().empty
    assert not Limits(languages=("fr",)).empty
    with pytest.raises(ValueError, match="first year"):
        Limits(year_from=2020, year_to=2010)
    with pytest.raises(ValueError, match="unknown languages"):
        Limits(languages=("xx",))


def test_database_names() -> None:
    assert [d.display_name for d in Database] == ["PubMed", "OpenAlex", "PsycINFO (EBSCOhost)"]


@pytest.mark.parametrize(
    ("line", "kind", "value"),
    [
        ("12345678", KeyArticleKind.PMID, "12345678"),
        ("PMID: 42", KeyArticleKind.PMID, "42"),
        ("pmid 42", KeyArticleKind.PMID, "42"),
        ("https://doi.org/10.1186/abc", KeyArticleKind.DOI, "10.1186/ABC"),
        ("A scoping review of things", KeyArticleKind.TITLE, "A scoping review of things"),
    ],
)
def test_key_articles(line: str, kind: KeyArticleKind, value: str) -> None:
    article = parse_key_article(line)
    assert (article.kind, article.value) == (kind, value)
    assert article.label == f"{kind.value.upper()} {value}"


def test_short_key_article_is_refused() -> None:
    with pytest.raises(ValueError, match="DOI"):
        parse_key_article("too short")
