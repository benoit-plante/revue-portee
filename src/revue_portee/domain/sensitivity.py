"""Sensitivity test of a search strategy against key articles (EF-REC-05).

Pure function: the database answers are collected by ``search/sensitivity.py``.
An article that the complete query misses is blamed on

- each inclusion block that, alone, does not retrieve it;
- each exclusion block that, alone, retrieves it (``NOT`` removes it);
- the limits (years, languages), when they alone do not retrieve it.

An article the database does not index is reported apart and left out of the recall.
"""

from collections.abc import Mapping, Sequence, Set
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from revue_portee.domain.search import KeyArticle

__all__ = [
    "LIMITS",
    "ArticleOutcome",
    "SensitivityCheck",
    "SensitivityResult",
    "assess_sensitivity",
]

LIMITS = "limits"  # pseudo block code for the limits


class ArticleOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    article: KeyArticle
    record_id: str | None  # identifier in the database, None when not indexed
    found: bool
    responsible: tuple[str, ...] = ()  # block codes (and LIMITS) that lose the article

    @property
    def indexed(self) -> bool:
        return self.record_id is not None


class SensitivityResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    outcomes: tuple[ArticleOutcome, ...]

    @property
    def indexed(self) -> int:
        return sum(1 for o in self.outcomes if o.indexed)

    @property
    def found(self) -> int:
        return sum(1 for o in self.outcomes if o.found)

    @property
    def missed(self) -> tuple[ArticleOutcome, ...]:
        return tuple(o for o in self.outcomes if o.indexed and not o.found)

    @property
    def not_indexed(self) -> tuple[ArticleOutcome, ...]:
        return tuple(o for o in self.outcomes if not o.indexed)

    @property
    def recall(self) -> Decimal | None:
        """Found among indexed articles, rounded to 3 decimals (None if none indexed)."""
        if not self.indexed:
            return None
        return (Decimal(self.found) / Decimal(self.indexed)).quantize(Decimal("0.001"))


class SensitivityCheck(BaseModel):
    """A sensitivity test as stored: the run that queried the database and its result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    search_run_id: str
    key_article_set_version_id: str
    result: SensitivityResult


def assess_sensitivity(
    articles: Sequence[KeyArticle],
    record_ids: Mapping[KeyArticle, str | None],
    found: Set[str],
    *,
    included_hits: Mapping[str, Set[str]],
    excluded_hits: Mapping[str, Set[str]],
    limits_hits: Set[str] | None = None,
) -> SensitivityResult:
    """Outcome of each key article.

    ``found`` holds the record identifiers that the complete query retrieves;
    ``included_hits`` and ``excluded_hits`` those that each block alone retrieves
    among the missed articles; ``limits_hits`` those that the limits alone retrieve
    (None when the strategy has no limits).
    """
    outcomes = []
    for article in articles:
        record = record_ids.get(article)
        hit = record is not None and record in found
        responsible: list[str] = []
        if record is not None and not hit:
            responsible += [code for code, ids in included_hits.items() if record not in ids]
            responsible += [code for code, ids in excluded_hits.items() if record in ids]
            if limits_hits is not None and record not in limits_hits:
                responsible.append(LIMITS)
        outcomes.append(
            ArticleOutcome(
                article=article, record_id=record, found=hit, responsible=tuple(responsible)
            )
        )
    return SensitivityResult(outcomes=tuple(outcomes))
