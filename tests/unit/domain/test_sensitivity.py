"""Sensitivity assessment, on a case worked out by hand."""

from decimal import Decimal

from revue_portee.domain.search import KeyArticle, KeyArticleKind
from revue_portee.domain.sensitivity import LIMITS, assess_sensitivity


def _pmid(value: str) -> KeyArticle:
    return KeyArticle(kind=KeyArticleKind.PMID, value=value)


def test_eight_of_ten_with_the_responsible_blocks() -> None:
    articles = [_pmid(str(n)) for n in range(1, 11)]
    ids = {a: f"R{a.value}" for a in articles}
    found = {f"R{n}" for n in range(1, 9)}
    result = assess_sensitivity(
        articles,
        ids,
        found,
        # Among the missed R9 and R10: B1 retrieves both, B2 only R10; B3 (NOT) has R10.
        included_hits={"B1": {"R9", "R10"}, "B2": {"R10"}},
        excluded_hits={"B3": {"R10"}},
    )
    assert (result.found, result.indexed) == (8, 10)
    assert result.recall == Decimal("0.800")
    assert [(o.article.value, o.responsible) for o in result.missed] == [
        ("9", ("B2",)),
        ("10", ("B3",)),
    ]
    assert result.not_indexed == ()


def test_unindexed_articles_and_limits() -> None:
    a, b, c = _pmid("1"), _pmid("2"), KeyArticle(kind=KeyArticleKind.TITLE, value="A long title")
    result = assess_sensitivity(
        [a, b, c],
        {a: "R1", b: "R2", c: None},
        {"R1"},
        included_hits={"B1": {"R2"}},
        excluded_hits={},
        limits_hits=set(),
    )
    assert result.indexed == 2
    assert result.recall == Decimal("0.500")
    assert result.missed[0].responsible == (LIMITS,)
    assert result.not_indexed[0].article == c
    assert not result.not_indexed[0].found


def test_no_indexed_article_has_no_recall() -> None:
    a = _pmid("1")
    result = assess_sensitivity([a], {}, set(), included_hits={}, excluded_hits={})
    assert result.recall is None
    assert result.outcomes[0].record_id is None
