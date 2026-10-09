"""Numbers of the flow diagram, computed from the data (EF-DEC-01, ENF-REP-06).

The diagram follows the PRISMA 2020 template for databases and registers, adapted to
scoping reviews (``resources/reporting/prisma_2020_flow.yaml``). In V1 it is filled
up to the end of the title and abstract screening; the full-text boxes are stages to
come. Every number comes from the project:

- identification: the references of each source, the duplicates grouped under another
  reference and the references left after deduplication (``dedup/counts.py``, D-064);
- screening: the state of each reference is its latest human decision (D-081), the
  reassessments included; a reference is excluded or kept (include or uncertain, which
  both go on to the full text, D-079);
- no reference is excluded by the AI alone in V1 (D-014): the number is computed from
  the decisions in force, so the diagram would show any such exclusion;
- full texts (tranche 2.1): once their retrieval has started, the reports not retrieved
  are those the person declared not retrievable (docs/10-conception-texte-integral.md
  §2.1.1); the texts neither obtained nor declared are left to do.

The diagram is provisional while something is left to do: references not yet screened
by the person or by the AI, disagreements to reconcile, pairs of possible duplicates
to examine, a reassessment not completed, or full texts neither obtained nor
declared not retrievable once their retrieval has started.
"""

import datetime as dt
from collections.abc import Callable, Iterable, Mapping, Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from revue_portee.dedup.counts import FlowCounts
from revue_portee.domain.fulltext import RetrievalCounts
from revue_portee.domain.screening import Decision, DecisionValue, ReviewerKind, keeps
from revue_portee.reporting.formats import integer

__all__ = [
    "FlowBox",
    "FlowNumbers",
    "FlowPhase",
    "FlowTemplate",
    "Pending",
    "ReassessmentCounts",
    "StageStatus",
    "flow_numbers",
    "pending_items",
    "reassessment_counts",
]


class StageStatus(StrEnum):
    FILLED = "filled"  # numbers computed in this version of the tool
    LATER = "later"  # a stage to come (full text, V2)


class FlowPhase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    en: str
    fr: str


class FlowBox(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    phase: str
    en: str
    fr: str
    stage: StageStatus = StageStatus.FILLED

    def label(self, language: str) -> str:
        return self.fr if language == "fr" else self.en


class FlowTemplate(BaseModel):
    """The wording of the template, with its source (ENF-NOR-03)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    version: str
    date: dt.date
    source: str
    adaptation: str
    license: str
    verified: bool
    phases: tuple[FlowPhase, ...]
    boxes: tuple[FlowBox, ...]

    def box(self, box_id: str) -> FlowBox:
        return next(b for b in self.boxes if b.id == box_id)

    def phase(self, phase_id: str) -> FlowPhase:
        return next(p for p in self.phases if p.id == phase_id)


class ReassessmentCounts(BaseModel):
    """The effect of one criteria change on the screening (EF-DEC-01, EF-VER-07)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    from_version: int
    to_version: int
    reassessed: int
    kept_to_excluded: int
    excluded_to_kept: int
    completed: bool


class Pending(BaseModel):
    """What is left to do before the numbers are final (zero everywhere when final)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    not_screened: int = 0  # references with no human decision
    without_ai: int = 0  # references the AI has not screened
    disagreements: int = 0  # disagreements not reconciled
    duplicate_pairs: int = 0  # pairs of possible duplicates to examine
    reassessments: int = 0  # reassessments not completed
    texts_missing: int = 0  # full texts neither obtained nor declared not retrievable
    screening_not_started: bool = False

    @property
    def any(self) -> bool:
        return self.screening_not_started or any(
            (
                self.not_screened,
                self.without_ai,
                self.disagreements,
                self.duplicate_pairs,
                self.reassessments,
                self.texts_missing,
            )
        )


class FlowNumbers(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    identified_by_source: dict[str, int]  # source name: references, sorted by name
    identified: int
    registers: int  # V1 collects from bibliographic databases only
    duplicates_removed: int
    removed_by_automation: int  # before screening: no such removal exists in the tool
    removed_other: int  # before screening: no such removal exists in the tool
    screened: int
    excluded: int
    excluded_by_person: int
    excluded_by_automation: int
    sought: int  # kept at the title and abstract stage, going on to the full text
    not_retrieved: int | None = None  # declared not retrievable; None before retrieval
    reassessments: tuple[ReassessmentCounts, ...]
    pending: Pending

    @property
    def provisional(self) -> bool:
        return self.pending.any


def reassessment_counts(
    *,
    from_version: int,
    to_version: int,
    members: Iterable[str],
    previous: Mapping[str, Decision],
    verified: Mapping[str, Decision],
    completed: bool,
) -> ReassessmentCounts:
    """Decisions changed by a reassessment: the person's verification against the final
    decision before it (``previous``), in the sense keep or exclude (D-079, D-082)."""
    reassessed = list(dict.fromkeys(members))
    flips = [
        (keeps(previous[ref].value), keeps(verified[ref].value))
        for ref in reassessed
        if ref in previous and ref in verified
    ]
    return ReassessmentCounts(
        from_version=from_version,
        to_version=to_version,
        reassessed=len(reassessed),
        kept_to_excluded=sum(1 for before, after in flips if before and not after),
        excluded_to_kept=sum(1 for before, after in flips if not before and after),
        completed=completed,
    )


def flow_numbers(
    counts: FlowCounts,
    after_deduplication: Sequence[str],
    final: Mapping[str, Decision],
    *,
    screened_by_ai: Iterable[str] = (),
    disagreements_open: int = 0,
    reassessments: Sequence[ReassessmentCounts] = (),
    screening_started: bool = True,
    retrieval: RetrievalCounts | None = None,
) -> FlowNumbers:
    """Numbers of the diagram.

    ``after_deduplication`` lists the references left after deduplication, ``final``
    the decision in force on each reference (the latest human decision); decisions on
    references since grouped as duplicates are not counted. ``retrieval`` counts the
    full texts of the references sought.
    """
    remaining = set(after_deduplication)
    decided = {ref: d for ref, d in final.items() if ref in remaining}
    excluded = [d for d in decided.values() if d.value is DecisionValue.EXCLUDE]
    by_automation = sum(1 for d in excluded if d.reviewer_kind is ReviewerKind.AI)
    retrieving = retrieval is not None and retrieval.started
    return FlowNumbers(
        identified_by_source=dict(counts.identified_by_source),
        identified=counts.identified,
        registers=0,
        duplicates_removed=counts.duplicates_removed,
        removed_by_automation=0,
        removed_other=0,
        screened=len(decided),
        excluded=len(excluded),
        excluded_by_person=len(excluded) - by_automation,
        excluded_by_automation=by_automation,
        sought=len(decided) - len(excluded),
        not_retrieved=retrieval.not_retrievable if retrieval is not None and retrieving else None,
        reassessments=tuple(reassessments),
        pending=Pending(
            not_screened=len(remaining) - len(decided),
            without_ai=len(remaining - set(screened_by_ai)) if screening_started else 0,
            disagreements=disagreements_open,
            duplicate_pairs=counts.pending_pairs,
            reassessments=sum(1 for r in reassessments if not r.completed),
            texts_missing=(
                retrieval.not_sought + retrieval.not_found
                if retrieval is not None and retrieving
                else 0
            ),
            screening_not_started=not screening_started,
        ),
    )


def pending_items(_: Callable[[str], str], pending: Pending, language: str) -> list[str]:
    """What is left to do, one item per kind, in the export language (``_``)."""
    items = []
    if pending.screening_not_started:
        items.append(_("the main screening has not started"))
    for count, text in (
        (pending.not_screened, _("references not screened by the person: {count}")),
        (pending.without_ai, _("references not screened by the AI: {count}")),
        (pending.disagreements, _("disagreements to reconcile: {count}")),
        (pending.duplicate_pairs, _("pairs of possible duplicates to examine: {count}")),
        (pending.reassessments, _("reassessments not completed: {count}")),
        (
            pending.texts_missing,
            _("full texts neither obtained nor declared not retrievable: {count}"),
        ),
    ):
        if count:
            items.append(text.format(count=integer(count, language)))
    return items
