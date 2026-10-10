"""Concordance of a replayed review with the published review (tranche 3.8, D-103).

The published review is the reference standard by definition: every measure is a
**concordance** with it, never a measure of who is right (docs/11-plan-de-replication.md
§9). Pure functions, each checked on a case computed by hand
(``tests/fixtures/replication/README.md``):

- **retrievability**: published included studies present in the collected set;
- **cascade of losses**: the step where each published included study is lost (outside
  any database searched, search, title and abstract screening, retrieval of the text,
  full-text screening);
- **end-to-end** recall, precision, F1 and Jaccard index, on every published study and
  on the retrievable ones (D-103, decision 5);
- **categorical fields** of the extraction: percentage of agreement, Cohen's kappa and
  Gwet's AC1, « not reported » being a category of its own;
- **distributions**: absolute gap by category in percentage points, share of the
  categories within 5 points, same modal category, rank correlation;
- **flow diagram**: gap box by box;
- **descriptors** of the gaps, which describe and never decide (§9).
"""

import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from revue_portee.domain.metrics import cohen_kappa_nominal, gwet_ac1_nominal, wilson_interval

__all__ = [
    "NOT_REPORTED",
    "WITHIN_POINTS",
    "CategoricalAgreement",
    "CategoryGap",
    "DistributionGap",
    "EndToEnd",
    "FlowGap",
    "LossStage",
    "Proportion",
    "PublishedDistribution",
    "PublishedFlow",
    "PublishedValue",
    "StandardStudy",
    "StudyPath",
    "categorical_agreement",
    "distribution_gap",
    "end_to_end",
    "flow_gaps",
    "loss_cascade",
    "lost_at",
    "screening_loss_descriptors",
    "year_descriptors",
]

# A field the report does not give: a category of its own when values are compared.
NOT_REPORTED = ""
# Gap under which a category of a distribution counts as close (percentage points).
WITHIN_POINTS = 5.0


# --- Reference standard ---------------------------------------------------------------


class StandardStudy(BaseModel):
    """An included study of the published review (``norme/incluses.csv``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    study_id: str = Field(min_length=1)
    doi: str = ""  # normalized
    pmid: str = ""
    citation: str = ""
    title: str = ""
    in_search: bool = True  # False: « hors_recherche », outside any database searched


class PublishedValue(BaseModel):
    """A categorical value of the published extraction table, coded in the categories
    of the grid (``norme/extraction-publiee.csv``); ``value`` is empty when not
    reported, the choices of a multiple choice joined by `` | ``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    study_id: str
    field: str  # code of the grid field (D1, D2…)
    value: str


class PublishedFlow(BaseModel):
    """Numbers of the published flow diagram (``norme/resultats-publies.yaml``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    identified: int | None = Field(default=None, ge=0)
    after_duplicates: int | None = Field(default=None, ge=0)
    screened: int | None = Field(default=None, ge=0)
    full_texts_assessed: int | None = Field(default=None, ge=0)
    included_reports: int | None = Field(default=None, ge=0)
    included_studies: int | None = Field(default=None, ge=0)


class PublishedDistribution(BaseModel):
    """A published distribution of the studies on a field of the grid: count of
    studies by category, over ``n`` studies (by default, the sum of the counts)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    categories: dict[str, int] = Field(min_length=1)
    n: int | None = Field(default=None, ge=1)

    @property
    def total(self) -> int:
        return self.n if self.n is not None else sum(self.categories.values())


# --- Proportions ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Proportion:
    count: int
    total: int

    @property
    def value(self) -> float | None:
        return None if self.total == 0 else self.count / self.total

    @property
    def interval(self) -> tuple[float, float] | None:
        """95 % Wilson interval (docs/11 §8)."""
        return wilson_interval(self.count, self.total)


# --- Cascade of losses ----------------------------------------------------------------


class LossStage(StrEnum):
    OUT_OF_SEARCH = "out_of_search"  # in no database searched (grey literature…)
    SEARCH = "search"  # in a database searched, but not collected
    TITLE_ABSTRACT = "title_abstract"  # excluded at the title and abstract stage
    RETRIEVAL = "retrieval"  # kept, but its full text not obtained
    FULL_TEXT = "full_text"  # excluded at the full text


@dataclass(frozen=True, slots=True)
class StudyPath:
    """What became of a published included study in the replay. Replayed stepwise,
    the study is given to the retrieval: ``collected`` and ``kept`` are true."""

    in_search: bool
    collected: bool
    kept: bool  # kept at the title and abstract stage
    obtained: bool  # its full text obtained
    included: bool  # among the studies the tool includes


def lost_at(path: StudyPath) -> LossStage | None:
    """The step where the study was lost, or None when the tool includes it."""
    if not path.collected:
        return LossStage.SEARCH if path.in_search else LossStage.OUT_OF_SEARCH
    if not path.kept:
        return LossStage.TITLE_ABSTRACT
    if not path.obtained:
        return LossStage.RETRIEVAL
    if not path.included:
        return LossStage.FULL_TEXT
    return None


def loss_cascade(paths: Iterable[StudyPath]) -> dict[LossStage, int]:
    """Studies lost at each step, every step listed (zero when none)."""
    counts = dict.fromkeys(LossStage, 0)
    for path in paths:
        stage = lost_at(path)
        if stage is not None:
            counts[stage] += 1
    return counts


# --- End to end -----------------------------------------------------------------------


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def _f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None or precision + recall == 0:
        return None
    return 2 * precision * recall / (precision + recall)


@dataclass(frozen=True, slots=True)
class EndToEnd:
    """The studies the tool includes against the published included studies.

    ``matched`` counts the published studies matched by at least one study of the
    tool; ``tool_matched`` the studies of the tool that match a published study (two
    studies of the tool may match one published study when it did not group their
    reports). The Jaccard index divides the published studies matched by the published
    studies plus the studies of the tool that match none."""

    published: int
    retrievable: int
    tool: int
    matched: int
    matched_retrievable: int
    tool_matched: int

    @property
    def recall(self) -> Proportion:
        return Proportion(self.matched, self.published)

    @property
    def recall_retrievable(self) -> Proportion:
        return Proportion(self.matched_retrievable, self.retrievable)

    @property
    def precision(self) -> Proportion:
        return Proportion(self.tool_matched, self.tool)

    @property
    def f1(self) -> float | None:
        return _f1(self.precision.value, self.recall.value)

    @property
    def f1_retrievable(self) -> float | None:
        return _f1(self.precision.value, self.recall_retrievable.value)

    @property
    def jaccard(self) -> float | None:
        return _ratio(self.matched, self.published + self.tool - self.tool_matched)

    @property
    def jaccard_retrievable(self) -> float | None:
        return _ratio(self.matched_retrievable, self.retrievable + self.tool - self.tool_matched)


def end_to_end(
    published: Sequence[str], retrievable: Iterable[str], tool: Sequence[frozenset[str]]
) -> EndToEnd:
    """``published``: the published included studies; ``retrievable``: those of them
    the search could find (not « hors_recherche », or collected all the same);
    ``tool``: for each study the tool includes, the published studies it matches."""
    wanted = set(published)
    findable = set(retrievable) & wanted
    found = set().union(*tool) & wanted if tool else set()
    return EndToEnd(
        published=len(wanted),
        retrievable=len(findable),
        tool=len(tool),
        matched=len(found),
        matched_retrievable=len(found & findable),
        tool_matched=sum(1 for study in tool if study & wanted),
    )


# --- Categorical fields of the extraction -----------------------------------------------


@dataclass(frozen=True, slots=True)
class CategoricalAgreement:
    field: str
    compared: int
    agreed: int
    kappa: float | None
    ac1: float | None
    not_reported_published: int
    not_reported_tool: int

    @property
    def agreement(self) -> Proportion:
        return Proportion(self.agreed, self.compared)


def categorical_agreement(field: str, pairs: Sequence[tuple[str, str]]) -> CategoricalAgreement:
    """``pairs`` of (published category, tool category) for the studies compared on
    ``field``; ``NOT_REPORTED`` stands for a value not reported."""
    return CategoricalAgreement(
        field=field,
        compared=len(pairs),
        agreed=sum(1 for a, b in pairs if a == b),
        kappa=cohen_kappa_nominal(pairs),
        ac1=gwet_ac1_nominal(pairs),
        not_reported_published=sum(1 for a, _b in pairs if a == NOT_REPORTED),
        not_reported_tool=sum(1 for _a, b in pairs if b == NOT_REPORTED),
    )


# --- Distributions --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CategoryGap:
    category: str
    published: float  # percentage of the studies
    tool: float
    gap: float  # absolute, in percentage points


@dataclass(frozen=True, slots=True)
class DistributionGap:
    field: str
    published_n: int
    tool_n: int
    categories: tuple[CategoryGap, ...]
    same_mode: bool
    rank_correlation: float | None  # Spearman, over every category of either side

    @property
    def within(self) -> Proportion:
        """Categories whose gap is under ``WITHIN_POINTS``."""
        return Proportion(
            sum(1 for c in self.categories if c.gap < WITHIN_POINTS), len(self.categories)
        )


def _percent(count: int, total: int) -> float:
    return 0.0 if total == 0 else 100 * count / total


def _modes(counts: Mapping[str, int]) -> frozenset[str]:
    top = max(counts.values(), default=0)
    return frozenset(k for k, v in counts.items() if v == top and v > 0)


def _ranks(values: Sequence[float]) -> list[float]:
    """Ranks from 1, ties sharing the mean of their ranks."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def _spearman(a: Sequence[float], b: Sequence[float]) -> float | None:
    if len(a) < 2:
        return None
    ra, rb = _ranks(a), _ranks(b)
    mean_a, mean_b = sum(ra) / len(ra), sum(rb) / len(rb)
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(ra, rb, strict=True))
    var_a = sum((x - mean_a) ** 2 for x in ra)
    var_b = sum((y - mean_b) ** 2 for y in rb)
    if var_a == 0 or var_b == 0:
        return None
    return cov / math.sqrt(var_a * var_b)


def distribution_gap(
    published: PublishedDistribution, tool: Mapping[str, int], tool_n: int
) -> DistributionGap:
    """The tool's distribution of ``tool_n`` studies against the published one, over
    the published categories then the tool's other categories (sorted)."""
    names = list(published.categories) + sorted(set(tool) - set(published.categories))
    gaps = []
    for name in names:
        p = _percent(published.categories.get(name, 0), published.total)
        t = _percent(tool.get(name, 0), tool_n)
        gaps.append(CategoryGap(category=name, published=p, tool=t, gap=abs(t - p)))
    published_modes = _modes(published.categories)
    return DistributionGap(
        field=published.field,
        published_n=published.total,
        tool_n=tool_n,
        categories=tuple(gaps),
        same_mode=bool(published_modes) and published_modes == _modes(tool),
        rank_correlation=_spearman([g.published for g in gaps], [g.tool for g in gaps]),
    )


# --- Flow diagram ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FlowGap:
    box: str
    published: int
    tool: int

    @property
    def difference(self) -> int:
        return self.tool - self.published

    @property
    def relative(self) -> float | None:
        """Gap relative to the published number."""
        return _ratio(self.difference, self.published)


def flow_gaps(published: PublishedFlow, tool: Mapping[str, int | None]) -> list[FlowGap]:
    """Box by box, the boxes with a number on both sides, in the order of the diagram."""
    found = []
    for box, value in published.model_dump().items():
        counted = tool.get(box)
        if value is not None and counted is not None:
            found.append(FlowGap(box=box, published=value, tool=counted))
    return found


# --- Descriptors of the gaps (§9) -------------------------------------------------------


def screening_loss_descriptors(
    lost: Iterable[tuple[bool, str | None]],
) -> tuple[int, dict[str, int]]:
    """Studies lost at the title and abstract screening, given as (abstract present,
    criterion the AI cited first to exclude): those without an abstract, and the
    count by criterion cited (``""`` when none)."""
    rows = list(lost)
    by_criterion = Counter(code or "" for _abstract, code in rows)
    return (
        sum(1 for abstract, _code in rows if not abstract),
        dict(sorted(by_criterion.items(), key=lambda item: (-item[1], item[0]))),
    )


def year_descriptors(years: Iterable[int | None], search_end: int | None) -> dict[str, int]:
    """Inclusions of the tool absent from the published review, by year of
    publication: within the period of the original search, after it, or unknown."""
    counts = {"within": 0, "after": 0, "unknown": 0}
    for year in years:
        if year is None or search_end is None:
            counts["unknown"] += 1
        elif year > search_end:
            counts["after"] += 1
        else:
            counts["within"] += 1
    return counts
