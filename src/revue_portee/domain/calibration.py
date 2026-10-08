"""Calibration of the AI's probability of inclusion and choice of thresholds
(EF-SEL-05, docs/03-architecture.md §6.5).

After a pilot round, the AI's raw probabilities are mapped to the share of references
the human reviewer kept (isotonic regression, pool-adjacent-violators; logistic
regression of Platt when isotonic is not chosen; identity when the pilot has a single
category). The exclusion threshold suggested is the highest one that keeps the
sensitivity on the pilot at or above the target. Pure functions.
"""

import math
from collections.abc import Sequence
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "Calibration",
    "ThresholdSuggestion",
    "fit_calibration",
    "suggest_exclusion_threshold",
]

Method = Literal["isotonic", "platt", "none"]


class Calibration(BaseModel):
    """A fitted mapping from raw to calibrated probability, serializable to JSON.

    ``isotonic``: points (x, y), linear between them, constant beyond. ``platt``:
    ``1 / (1 + exp(-(a x + b)))``. ``none``: identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    method: Method
    points: tuple[tuple[float, float], ...] = ()
    a: float = 0.0
    b: float = 0.0
    fitted_on: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.method == "isotonic" and not self.points:
            raise ValueError("an isotonic calibration has points")
        return self

    def apply(self, raw: float) -> float:
        if self.method == "none":
            return raw
        if self.method == "platt":
            return 1 / (1 + math.exp(-(self.a * raw + self.b)))
        xs = [x for x, _y in self.points]
        if raw <= xs[0]:
            return self.points[0][1]
        if raw >= xs[-1]:
            return self.points[-1][1]
        for (x0, y0), (x1, y1) in zip(self.points, self.points[1:], strict=False):
            if x0 <= raw <= x1:
                return y0 if x1 == x0 else y0 + (y1 - y0) * (raw - x0) / (x1 - x0)
        raise AssertionError("unreachable")  # pragma: no cover - raw lies in a segment


def _isotonic(scores: Sequence[float], labels: Sequence[bool]) -> tuple[tuple[float, float], ...]:
    """Pool adjacent violators on the scores sorted (ties pooled first)."""
    by_score: dict[float, list[int]] = {}
    for score, label in zip(scores, labels, strict=True):
        by_score.setdefault(score, []).append(int(label))
    # blocks of [sum of labels, count, lowest score, highest score]
    blocks: list[list[float]] = []
    for score in sorted(by_score):
        values = by_score[score]
        blocks.append([float(sum(values)), float(len(values)), score, score])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            total, count, _low, high = blocks.pop()
            blocks[-1][0] += total
            blocks[-1][1] += count
            blocks[-1][3] = high
    points: list[tuple[float, float]] = []
    for total, count, low, high in blocks:
        value = total / count
        points.append((low, value))
        if high != low:
            points.append((high, value))
    return tuple(points)


def _platt(scores: Sequence[float], labels: Sequence[bool]) -> tuple[float, float]:
    """Logistic regression of the labels on the scores (Newton's method, Platt's priors)."""
    positives = sum(labels)
    negatives = len(labels) - positives
    targets = [
        (positives + 1) / (positives + 2) if label else 1 / (negatives + 2) for label in labels
    ]
    a, b = 0.0, math.log((negatives + 1) / (positives + 1)) * -1
    for _ in range(100):
        grad_a = grad_b = h_aa = h_ab = h_bb = 0.0
        for x, t in zip(scores, targets, strict=True):
            p = 1 / (1 + math.exp(-(a * x + b)))
            d = p - t
            w = max(p * (1 - p), 1e-12)
            grad_a += d * x
            grad_b += d
            h_aa += w * x * x
            h_ab += w * x
            h_bb += w
        determinant = h_aa * h_bb - h_ab * h_ab
        if abs(determinant) < 1e-12:
            break
        step_a = (h_bb * grad_a - h_ab * grad_b) / determinant
        step_b = (h_aa * grad_b - h_ab * grad_a) / determinant
        a, b = a - step_a, b - step_b
        if abs(step_a) < 1e-9 and abs(step_b) < 1e-9:
            break
    return a, b


def fit_calibration(
    scores: Sequence[float], labels: Sequence[bool], method: Method = "isotonic"
) -> Calibration:
    """Fit on the pilot: ``scores`` are raw probabilities, ``labels`` human positives."""
    if len(scores) != len(labels):
        raise ValueError("one label per score")
    if not scores or method == "none" or len(set(labels)) < 2:
        return Calibration(method="none", fitted_on=len(scores))
    if method == "platt":
        a, b = _platt(scores, labels)
        return Calibration(method="platt", a=a, b=b, fitted_on=len(scores))
    return Calibration(method="isotonic", points=_isotonic(scores, labels), fitted_on=len(scores))


class ThresholdSuggestion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exclude_below: float = Field(ge=0, le=1)
    sensitivity: float | None
    avoided: int = Field(ge=0)
    target: float = Field(gt=0, le=1)


def suggest_exclusion_threshold(
    observations: Sequence[tuple[float, bool, bool]], target: float
) -> ThresholdSuggestion:
    """Highest exclusion threshold whose sensitivity on the pilot reaches ``target``.

    ``observations`` are (calibrated probability, human positive, protected by
    EF-SEL-07). Candidate thresholds are 0 and each observed probability: excluding
    below a probability p keeps every reference at p or above. Sensitivity is always
    preferred to the work avoided (EF-SEL-05)."""
    positives = sum(1 for _p, human, _protected in observations if human)
    best = ThresholdSuggestion(
        exclude_below=0.0, sensitivity=1.0 if positives else None, avoided=0, target=target
    )
    if positives == 0:  # nothing to protect is known: exclude nothing
        return best
    for t in sorted({p for p, _human, _protected in observations}):
        excluded = [human for p, human, protected in observations if p < t and not protected]
        sensitivity = (positives - sum(excluded)) / positives
        if sensitivity < target:
            break
        best = ThresholdSuggestion(
            exclude_below=t, sensitivity=sensitivity, avoided=len(excluded), target=target
        )
    return best
