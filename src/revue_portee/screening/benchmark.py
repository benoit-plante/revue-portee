"""Benchmark of the AI screener on a labelled SYNERGY dataset (docs/05-plan-de-validation.md).

A SYNERGY dataset is read from a local CSV file (``title``, ``abstract``,
``label_included``); the criteria come from a YAML file written for the dataset. Each
record is screened once with the configured ``screen_reference`` task, its answer is
turned into a decision with the thresholds as in the pilot (EF-SEL-07 included), and
the sensitivity, the specificity and the cost per thousand references are reported.
No project folder is involved: the raw answers go to a local JSON Lines file, and the
report, which holds only numbers, to ``docs/resultats/``.
"""

import csv
import json
import threading
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import IO

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from revue_portee.ai.base import CostEstimate, ModelProvider, ProviderCallError
from revue_portee.ai.runner import run_task
from revue_portee.ai.settings import AITaskConfig
from revue_portee.ai.tasks.screening import (
    SCREEN_REFERENCE,
    CriterionText,
    ReferenceText,
    ScreenReferenceInput,
    ScreenReferenceOutput,
)
from revue_portee.domain.criteria import CriterionKind
from revue_portee.domain.metrics import Confusion, confusion, wilson_interval
from revue_portee.domain.screening import (
    AssessmentStatus,
    CriterionAssessment,
    DecisionValue,
    Thresholds,
    ai_value,
    draw_sample,
)
from revue_portee.i18n import gettext as _
from revue_portee.screening.ai_screening import (
    MAX_ATTEMPTS,
    UnusableAnswerError,
    check_answer,
    quote_found,
    searchable_text,
)

__all__ = [
    "BenchmarkCriteria",
    "BenchmarkError",
    "BenchmarkRecord",
    "BenchmarkResult",
    "estimate",
    "read_criteria",
    "read_dataset",
    "report_markdown",
    "run_benchmark",
    "select_records",
    "to_inputs",
]

# Cost target of the roadmap (tranche 1.6), in US dollars per thousand references.
COST_TARGET_PER_THOUSAND = Decimal(5)
SENSITIVITY_TARGET = 0.95


class BenchmarkError(ValueError):
    """A dataset or a criteria file that cannot be used (French message)."""


class BenchmarkRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    title: str
    abstract: str
    included: bool


class BenchmarkCriteria(BaseModel):
    """Criteria of a benchmark dataset (YAML file)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    review_question: str = ""
    language: str = "en"
    criteria: tuple[CriterionText, ...] = Field(min_length=1)


def read_dataset(path: Path) -> list[BenchmarkRecord]:
    """Records of a SYNERGY CSV export; ``label_included`` is 1 for an included record."""
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
    except OSError as error:
        raise BenchmarkError(_("Cannot read the file {path}.").format(path=path)) from error
    if not rows or not {"title", "label_included"} <= set(rows[0]):
        raise BenchmarkError(
            _("The file {path} needs the columns title, abstract and label_included.").format(
                path=path
            )
        )
    records = []
    for number, row in enumerate(rows, start=1):
        label = (row.get("label_included") or "").strip()
        if label not in {"0", "1"}:
            raise BenchmarkError(
                _("Line {line}: label_included must be 0 or 1.").format(line=number + 1)
            )
        records.append(
            BenchmarkRecord(
                item_id=f"r{number}",
                title=(row.get("title") or "").strip(),
                abstract=(row.get("abstract") or "").strip(),
                included=label == "1",
            )
        )
    return records


def read_criteria(path: Path) -> BenchmarkCriteria:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return BenchmarkCriteria.model_validate(data)
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise BenchmarkError(
            _("The criteria file {path} cannot be used: {error}").format(
                path=path, error=type(error).__name__
            )
        ) from error


def select_records(
    records: Sequence[BenchmarkRecord], size: int | None, seed: int
) -> list[BenchmarkRecord]:
    """Every included record, and excluded ones drawn with ``seed`` up to ``size``
    records in all (the sensitivity is measured on every inclusion)."""
    if size is None or size >= len(records):
        return list(records)
    included = [r for r in records if r.included]
    excluded = [r for r in records if not r.included]
    wanted = max(0, min(len(excluded), size - len(included)))
    drawn = draw_sample([r.item_id for r in excluded], wanted, seed)
    chosen = {r.item_id for r in included} | set(drawn)
    return [r for r in records if r.item_id in chosen]


def to_inputs(
    records: Sequence[BenchmarkRecord], criteria: BenchmarkCriteria
) -> list[ScreenReferenceInput]:
    return [
        ScreenReferenceInput(
            item_id=r.item_id,
            language=criteria.language,
            review_question=criteria.review_question,
            criteria=criteria.criteria,
            reference=ReferenceText(title=r.title, abstract=r.abstract),
        )
        for r in records
    ]


@dataclass
class BenchmarkResult:
    dataset: str
    records: int
    included: int
    thresholds: Thresholds
    provider: str
    model: str
    prompt_version: str
    started_at: datetime
    seed: int
    sampled: bool
    values: dict[str, DecisionValue] = field(default_factory=dict)  # by item id
    failed: list[str] = field(default_factory=list)
    stopped: bool = False
    spent: Decimal = Decimal(0)
    models_returned: set[str] = field(default_factory=set)
    quotes_found: int = 0  # quotes of the AI found in the title or abstract
    quotes_checked: int = 0

    def confusion(self, labels: dict[str, bool]) -> Confusion:
        include, exclude = DecisionValue.INCLUDE, DecisionValue.EXCLUDE
        return confusion(
            (include if labels[item] else exclude, value) for item, value in self.values.items()
        )

    def cost_per_thousand(self) -> Decimal | None:
        calls = len(self.values) + len(self.failed)
        return None if calls == 0 else (self.spent * 1000 / calls).quantize(Decimal("0.01"))


def _value(
    output: ScreenReferenceOutput, criteria: BenchmarkCriteria, t: Thresholds
) -> DecisionValue:
    kinds = {c.code: CriterionKind(c.kind) for c in criteria.criteria}
    assessments = [
        CriterionAssessment(code=a.code, kind=kinds[a.code], status=AssessmentStatus(a.status))
        for a in output.assessments
    ]
    return ai_value(output.inclusion_probability, t, assessments)


def run_benchmark(
    dataset: str,
    records: Sequence[BenchmarkRecord],
    criteria: BenchmarkCriteria,
    *,
    config: AITaskConfig,
    provider: ModelProvider,
    thresholds: Thresholds,
    ceiling: Decimal,
    raw_output: IO[str],
    now: Callable[[], datetime],
    seed: int = 0,
    sampled: bool = False,
    workers: int = 1,
) -> BenchmarkResult:
    """Screen every record once (one retry on an unusable answer), with up to
    ``workers`` calls at a time. The estimated cost of a call is reserved before it is
    made, so the run stops before passing ``ceiling`` whatever the number of calls in
    flight; each raw answer is written as one JSON line of ``raw_output``."""
    result = BenchmarkResult(
        dataset=dataset,
        records=len(records),
        included=sum(r.included for r in records),
        thresholds=thresholds,
        provider=provider.name,
        model=str(config.model),
        prompt_version=SCREEN_REFERENCE.prompt.version,
        started_at=now(),
        seed=seed,
        sampled=sampled,
    )
    codes = [c.code for c in criteria.criteria]
    lock = threading.Lock()
    reserved = [Decimal(0)]  # estimated cost of the calls in flight

    def reserve(estimate: Decimal) -> bool:
        with lock:
            if result.stopped or result.spent + reserved[0] + estimate > ceiling:
                result.stopped = True
                return False
            reserved[0] += estimate
            return True

    def settle(
        estimate: Decimal, cost: Decimal, item_id: str, model: str | None, raw: object
    ) -> None:
        with lock:
            reserved[0] -= estimate
            result.spent += cost
            if model:
                result.models_returned.add(model)
            _write_raw(raw_output, item_id, model, raw)

    def screen(item: ScreenReferenceInput) -> tuple[str, DecisionValue | None]:
        """("screened", value), ("failed", None) or ("not_run", None) at the ceiling."""
        estimate = provider.estimate_cost(SCREEN_REFERENCE, [item]).amount
        for _attempt in range(MAX_ATTEMPTS):
            if not reserve(estimate):
                return "not_run", None
            try:
                (answer,) = run_task(provider, SCREEN_REFERENCE, [item])
            except ProviderCallError as error:
                call = error.call
                settle(estimate, call.cost_estimate, item.item_id, None, error.raw_response)
                continue
            call = answer.call
            settle(
                estimate, call.cost_estimate, item.item_id, call.model_returned, answer.raw_response
            )
            try:
                check_answer(answer.output, codes)
            except UnusableAnswerError:
                continue
            text = searchable_text(item.reference.title, item.reference.abstract)
            checks = [quote_found(a.evidence_quote, text) for a in answer.output.assessments]
            with lock:
                result.quotes_checked += sum(1 for c in checks if c is not None)
                result.quotes_found += sum(1 for c in checks if c)
            return "screened", _value(answer.output, criteria, thresholds)
        return "failed", None

    inputs = to_inputs(records, criteria)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        outcomes = list(pool.map(screen, inputs))
    for item, (status, value) in zip(inputs, outcomes, strict=True):
        if status == "failed":
            result.failed.append(item.item_id)
        elif value is not None:
            result.values[item.item_id] = value
    return result


def _write_raw(stream: IO[str], item_id: str, model: str | None, raw: object) -> None:
    line = {"item_id": item_id, "model_returned": model, "raw_response": raw}
    stream.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
    stream.flush()  # what was paid for is kept if the run is interrupted


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}".replace(".", ",") + " %"


def _interval(successes: int, total: int) -> str:
    bounds = wilson_interval(successes, total)
    if bounds is None:
        return "—"
    return _("{low} to {high}").format(low=_percent(bounds[0]), high=_percent(bounds[1]))


def _lines(result: BenchmarkResult, labels: dict[str, bool]) -> Iterator[str]:
    c = result.confusion(labels)
    sensitivity = None if c.tp + c.fn == 0 else c.tp / (c.tp + c.fn)
    specificity = None if c.tn + c.fp == 0 else c.tn / (c.tn + c.fp)
    per_thousand = result.cost_per_thousand()
    yield "# " + _("SYNERGY benchmark: {dataset}").format(dataset=result.dataset)
    yield ""
    yield _("Run on {date} (UTC).").format(date=result.started_at.strftime("%Y-%m-%d %H:%M"))
    yield ""
    yield "| " + _("Item") + " | " + _("Value") + " |"
    yield "|---|---|"
    rows = [
        (_("Provider and model requested"), f"{result.provider} — {result.model}"),
        (_("Models returned"), ", ".join(sorted(result.models_returned)) or "—"),
        (_("Prompt template"), f"{SCREEN_REFERENCE.prompt.template_id} v{result.prompt_version}"),
        (
            _("Thresholds"),
            _("excludes below {low}, includes from {high}").format(
                low=result.thresholds.exclude_below, high=result.thresholds.include_above
            ),
        ),
        (_("Records screened"), f"{len(result.values)} / {result.records}"),
        (_("Records included in the dataset"), str(result.included)),
        (_("Failures (unusable answers)"), str(len(result.failed))),
        (
            _("Sample"),
            _("all included records and excluded ones drawn with the seed {seed}").format(
                seed=result.seed
            )
            if result.sampled
            else _("whole dataset"),
        ),
        (_("Stopped by the ceiling"), _("yes") if result.stopped else _("no")),
        (_("Sensitivity (included records kept)"), _percent(sensitivity)),
        (_("95 % interval of the sensitivity"), _interval(c.tp, c.tp + c.fn)),
        (_("Specificity (excluded records excluded)"), _percent(specificity)),
        (_("95 % interval of the specificity"), _interval(c.tn, c.tn + c.fp)),
        (_("Confusion (tp, fn, fp, tn)"), f"{c.tp}, {c.fn}, {c.fp}, {c.tn}"),
        (
            _("Quotes of the AI found in the title or abstract"),
            "—"
            if result.quotes_checked == 0
            else f"{result.quotes_found} / {result.quotes_checked} "
            f"({_percent(result.quotes_found / result.quotes_checked)})",
        ),
        (_("Cost"), f"{result.spent} USD"),
        (
            _("Cost per 1,000 references"),
            "—" if per_thousand is None else f"{per_thousand} USD",
        ),
    ]
    yield from (f"| {label} | {value} |" for label, value in rows)
    yield ""
    targets_met = (
        sensitivity is not None
        and sensitivity >= SENSITIVITY_TARGET
        and per_thousand is not None
        and per_thousand <= COST_TARGET_PER_THOUSAND
    )
    yield _(
        "Targets of the roadmap: sensitivity at or above {sensitivity} and at most {cost} USD "
        "per 1,000 references: {verdict}."
    ).format(
        sensitivity=_percent(SENSITIVITY_TARGET),
        cost=COST_TARGET_PER_THOUSAND,
        verdict=_("reached") if targets_met else _("not reached"),
    )
    yield ""
    yield _(
        "A record is kept when the AI includes it or is uncertain; the labels of the dataset "
        "(full-text inclusions) are the reference."
    )


def report_markdown(result: BenchmarkResult, records: Sequence[BenchmarkRecord]) -> str:
    labels = {r.item_id: r.included for r in records}
    return "\n".join(_lines(result, labels)) + "\n"


def estimate(provider: ModelProvider, inputs: Sequence[ScreenReferenceInput]) -> CostEstimate:
    return provider.estimate_cost(SCREEN_REFERENCE, inputs)
