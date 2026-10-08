"""Agreement and accuracy of the AI reviewer against the human reviewer (EF-SEL-03).

Pure functions, each checked on a case computed by hand. Decisions are made binary the
way screening uses them: a reference is **positive** when it is not excluded (include
or uncertain: it goes on to the next stage), negative when it is excluded. The human
reviewer is the reference standard.
"""

import math
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from revue_portee.domain.screening import DecisionValue

__all__ = [
    "Confusion",
    "CurvePoint",
    "PilotMetrics",
    "cohen_kappa",
    "confusion",
    "disagreements_by_criterion",
    "gwet_ac1",
    "pilot_metrics",
    "threshold_curve",
    "wilson_interval",
]


def _positive(value: DecisionValue) -> bool:
    return value is not DecisionValue.EXCLUDE


@dataclass(frozen=True, slots=True)
class Confusion:
    """AI against human: tp both positive, fn human positive and AI excludes, etc."""

    tp: int
    fn: int
    fp: int
    tn: int

    @property
    def n(self) -> int:
        return self.tp + self.fn + self.fp + self.tn


def confusion(pairs: Iterable[tuple[DecisionValue, DecisionValue]]) -> Confusion:
    """``pairs`` of (human value, AI value)."""
    counts = Counter((_positive(h), _positive(a)) for h, a in pairs)
    return Confusion(
        tp=counts[(True, True)],
        fn=counts[(True, False)],
        fp=counts[(False, True)],
        tn=counts[(False, False)],
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def cohen_kappa(c: Confusion) -> float | None:
    """Cohen's kappa; None when chance agreement is total (one category only)."""
    if c.n == 0:
        return None
    observed = (c.tp + c.tn) / c.n
    expected = ((c.tp + c.fp) * (c.tp + c.fn) + (c.fn + c.tn) * (c.fp + c.tn)) / c.n**2
    return None if expected == 1 else (observed - expected) / (1 - expected)


def gwet_ac1(c: Confusion) -> float | None:
    """Gwet's AC1 for two raters and two categories."""
    if c.n == 0:
        return None
    observed = (c.tp + c.tn) / c.n
    pi = ((c.tp + c.fp) / c.n + (c.tp + c.fn) / c.n) / 2
    expected = 2 * pi * (1 - pi)
    return None if expected == 1 else (observed - expected) / (1 - expected)


def wilson_interval(successes: int, total: int, z: float = 1.959964) -> tuple[float, float] | None:
    """95 % Wilson score interval of a proportion; None without observations."""
    if total == 0:
        return None
    p = successes / total
    centre = p + z * z / (2 * total)
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    denominator = 1 + z * z / total
    return ((centre - margin) / denominator, (centre + margin) / denominator)


@dataclass(frozen=True, slots=True)
class PilotMetrics:
    confusion: Confusion
    agreement: float | None
    kappa: float | None
    ac1: float | None
    sensitivity: float | None
    sensitivity_interval: tuple[float, float] | None
    specificity: float | None
    specificity_interval: tuple[float, float] | None


def pilot_metrics(pairs: Iterable[tuple[DecisionValue, DecisionValue]]) -> PilotMetrics:
    c = confusion(pairs)
    return PilotMetrics(
        confusion=c,
        agreement=_ratio(c.tp + c.tn, c.n),
        kappa=cohen_kappa(c),
        ac1=gwet_ac1(c),
        sensitivity=_ratio(c.tp, c.tp + c.fn),
        sensitivity_interval=wilson_interval(c.tp, c.tp + c.fn),
        specificity=_ratio(c.tn, c.tn + c.fp),
        specificity_interval=wilson_interval(c.tn, c.tn + c.fp),
    )


@dataclass(frozen=True, slots=True)
class CurvePoint:
    threshold: float  # the AI excludes below this probability of inclusion
    sensitivity: float | None
    avoided: int  # references the AI would exclude
    avoided_share: float


def threshold_curve(
    observations: Sequence[tuple[float, bool, bool]], thresholds: Sequence[float]
) -> list[CurvePoint]:
    """For each threshold, the AI's sensitivity and the references it would exclude.

    ``observations`` are (probability of inclusion, human positive, protected), a
    protected reference being one that EF-SEL-07 forbids to exclude."""
    positives = sum(1 for _p, human, _protected in observations if human)
    points = []
    for t in thresholds:
        excluded = [(human, p) for p, human, protected in observations if p < t and not protected]
        missed = sum(1 for human, _p in excluded if human)
        points.append(
            CurvePoint(
                threshold=t,
                sensitivity=_ratio(positives - missed, positives),
                avoided=len(excluded),
                avoided_share=len(excluded) / len(observations) if observations else 0.0,
            )
        )
    return points


def disagreements_by_criterion(
    rows: Iterable[tuple[DecisionValue, DecisionValue, Sequence[str]]],
) -> dict[str, int]:
    """Disagreements counted by criterion cited (by the AI, or by the human for the
    references the AI kept): ``rows`` of (human value, AI value, criteria cited)."""
    counts: Counter[str] = Counter()
    for human, ai, cited in rows:
        if _positive(human) != _positive(ai):
            counts.update(set(cited) or {""})
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))
