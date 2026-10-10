"""Screening decisions, pilot rounds and thresholds (EF-SEL-01 to 09, ENF-TRA-01).

The AI reviewer assesses each criterion (met / not met / cannot tell), gives its own
decision and the probability that the reference should be included. The value
recorded for the AI comes from that probability and the thresholds in force (EF-SEL-09),
then from the rule of EF-SEL-07: a reference with an inclusion criterion that cannot be
told, and no criterion that fails it, is never excluded. A criterion fails a reference
when it is an inclusion criterion not met, or an exclusion criterion met (its reason
for exclusion applies). Decisions are only added,
never changed (ENF-TRA-02).

At the full-text stage (tranche 2.2, D-102), each round has a mode: blind double
screening (the person decides without seeing the AI, disagreements are reconciled) or
assisted screening (the AI screens first and the person decides with its assessment in
view). Each assessment of the AI names the page of its quote, which the tool looks for
in the text. An exclusion reports one primary reason: the first criterion cited, in the
order of the criteria.
"""

import random
import re
import unicodedata
from collections.abc import Iterable, Sequence
from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from revue_portee.domain.calibration import Calibration
from revue_portee.domain.criteria import CriterionKind
from revue_portee.domain.fulltext import QuoteCheck
from revue_portee.domain.project import ReviewerKind

__all__ = [
    "AIBatch",
    "AIBatchEnd",
    "AssessmentStatus",
    "BudgetSetting",
    "CalibrationRecord",
    "CriterionAssessment",
    "Decision",
    "DecisionContext",
    "DecisionValue",
    "PilotRound",
    "QuoteCheck",
    "ReviewerKind",
    "RoundKind",
    "ScreeningMode",
    "ScreeningRound",
    "Stage",
    "ThresholdSetting",
    "Thresholds",
    "ai_value",
    "detect_language",
    "disagree",
    "draw_sample",
    "keeps",
    "must_not_exclude",
    "page_quote_counts",
    "primary_reason",
    "quote_counts",
]


class Stage(StrEnum):
    TITLE_ABSTRACT = "title_abstract"
    FULL_TEXT = "full_text"


class DecisionValue(StrEnum):
    INCLUDE = "include"
    EXCLUDE = "exclude"
    UNCERTAIN = "uncertain"


class AssessmentStatus(StrEnum):
    MET = "met"
    NOT_MET = "not_met"
    CANNOT_TELL = "cannot_tell"


class RoundKind(StrEnum):
    PILOT = "pilot"
    MAIN = "main"  # every reference, human and AI independently (EF-SEL-08)
    REASSESSMENT = "reassessment"  # references touched by a criteria change (EF-VER-05)


def keeps(value: DecisionValue) -> bool:
    """A reference goes on to the full text unless it is excluded."""
    return value is not DecisionValue.EXCLUDE


def disagree(human: DecisionValue, ai: DecisionValue) -> bool:
    """The human and the AI disagree when one keeps the reference and the other
    excludes it; « include » against « uncertain » is not a disagreement."""
    return keeps(human) != keeps(ai)


class DecisionContext(StrEnum):
    INDEPENDENT = "independent"  # pilot and main screening
    RECONCILIATION = "reconciliation"
    REASSESSMENT = "reassessment"
    AUDIT = "audit"
    ASSISTED = "assisted"  # full text, the AI's assessment in view (D-102)
    REPLICATION = "replication"  # the AI's decision is final: replication projects only


class ScreeningMode(StrEnum):
    """How a full-text round is screened (D-102), fixed when the round starts."""

    BLIND = "blind"  # double screening, the AI shown only to reconcile
    ASSISTED = "assisted"  # the AI first, the person decides with it in view


class CriterionAssessment(BaseModel):
    """The AI's assessment of one criterion, with the passage it rests on (EF-SEL-06)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    kind: CriterionKind
    status: AssessmentStatus
    evidence_quote: str = ""
    quote_found: bool | None = None  # the quote is in the title or abstract, or the text
    page: int | None = None  # full text: the page the AI gives for its quote
    quote_check: QuoteCheck | None = None  # full text: found at that page, elsewhere, not


def quote_counts(assessments: Iterable[CriterionAssessment]) -> tuple[int, int]:
    """Quotes found in the title or abstract, and quotes checked (an assessment without a
    quote is not checked): ``(found, checked)``."""
    checked = [a.quote_found for a in assessments if a.quote_found is not None]
    return sum(1 for found in checked if found), len(checked)


def page_quote_counts(assessments: Iterable[CriterionAssessment]) -> dict[QuoteCheck, int]:
    """Full-text quotes by result of their check: found at the page given, at another
    page, or not found (assessments without a quote are not checked)."""
    counts = dict.fromkeys(QuoteCheck, 0)
    for a in assessments:
        if a.quote_check is not None:
            counts[a.quote_check] += 1
    return counts


def primary_reason(cited: Iterable[str], order: Sequence[str]) -> str | None:
    """Primary reason of an exclusion (D-102): the first criterion cited in the order of
    the criteria (``order``, their codes); codes no longer in the version come last."""
    codes = list(dict.fromkeys(cited))
    if not codes:
        return None
    rank = {code: i for i, code in enumerate(order)}
    return min(codes, key=lambda code: (rank.get(code, len(rank)), codes.index(code)))


def _fails(a: CriterionAssessment) -> bool:
    if a.kind is CriterionKind.INCLUSION:
        return a.status is AssessmentStatus.NOT_MET
    return a.status is AssessmentStatus.MET  # the reason for exclusion applies


def must_not_exclude(assessments: Iterable[CriterionAssessment]) -> bool:
    """EF-SEL-07: an inclusion criterion cannot be told and no criterion fails."""
    items = list(assessments)
    unknown = any(
        a.kind is CriterionKind.INCLUSION and a.status is AssessmentStatus.CANNOT_TELL
        for a in items
    )
    return unknown and not any(_fails(a) for a in items)


class Thresholds(BaseModel):
    """EF-SEL-09: below ``exclude_below`` the AI excludes, from ``include_above`` it
    includes, uncertain in between. Applied to the probability of inclusion."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    exclude_below: float = Field(ge=0, le=1)
    include_above: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.exclude_below > self.include_above:
            raise ValueError("exclude_below must not exceed include_above")
        return self


def ai_value(
    probability: float, thresholds: Thresholds, assessments: Iterable[CriterionAssessment]
) -> DecisionValue:
    """Value recorded for the AI: thresholds on the probability, then EF-SEL-07."""
    if probability < thresholds.exclude_below:
        value = DecisionValue.EXCLUDE
    elif probability >= thresholds.include_above:
        value = DecisionValue.INCLUDE
    else:
        value = DecisionValue.UNCERTAIN
    if value is DecisionValue.EXCLUDE and must_not_exclude(assessments):
        return DecisionValue.UNCERTAIN
    return value


class Decision(BaseModel):
    """One screening decision (table ``decision``), human or AI (ENF-TRA-01).

    An AI decision points to its model call (``ai_call_id``), which holds the provider,
    the requested and returned model, the prompt template and its version, the prompt
    digest, the parameters, the tokens, the cost and the raw response."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    reference_id: str
    stage: Stage
    round_id: str | None
    reviewer_id: str
    reviewer_kind: ReviewerKind
    value: DecisionValue
    confidence_raw: float | None = Field(default=None, ge=0, le=1)
    confidence_calibrated: float | None = Field(default=None, ge=0, le=1)
    rationale: str = ""
    criteria_cited: tuple[str, ...] = ()
    assessments: tuple[CriterionAssessment, ...] = ()
    model_decision: DecisionValue | None = None  # the AI's own decision, before the rules
    thresholds: Thresholds | None = None
    calibration_id: str | None = None  # calibration of confidence_calibrated
    criteria_version_id: str
    language: str = ""  # detected language of the reference (ENF-LAN-05)
    context: DecisionContext = DecisionContext.INDEPENDENT
    blinded: bool = False
    supersedes_decision_id: str | None = None
    ai_call_id: str | None = None
    tool_version: str
    created_at: AwareDatetime

    @model_validator(mode="after")
    def _complete(self) -> Self:
        if self.reviewer_kind is ReviewerKind.AI:
            missing = [
                name
                for name, value in (
                    ("ai_call_id", self.ai_call_id),
                    ("confidence_raw", self.confidence_raw),
                    ("rationale", self.rationale),
                    ("criteria_cited", self.criteria_cited),
                    ("assessments", self.assessments),
                    ("model_decision", self.model_decision),
                    ("thresholds", self.thresholds),
                )
                if value in (None, "", ())
            ]
            if missing:
                raise ValueError(f"an AI decision needs: {', '.join(missing)}")
            if (self.confidence_calibrated is None) != (self.calibration_id is None):
                raise ValueError("a calibrated confidence names its calibration")
        elif self.ai_call_id is not None:
            raise ValueError("a human decision has no model call")
        if (
            self.reviewer_kind is ReviewerKind.HUMAN
            and self.value is DecisionValue.EXCLUDE
            and not self.criteria_cited
        ):
            raise ValueError("a human exclusion names its criteria (EF-SEL-12)")
        return self


class ScreeningRound(BaseModel):
    """A round of screening without its members (table ``screening_round``): the main
    screening of every reference, in an order drawn with ``seed``, or a reassessment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    number: int = Field(ge=1)
    stage: Stage
    kind: RoundKind
    criteria_version_id: str
    seed: int
    sample_size: int = Field(ge=0)  # members when the round was created
    created_at: AwareDatetime
    reviewer_id: str
    mode: ScreeningMode = ScreeningMode.BLIND  # full text (D-102); blind before it


class AIBatch(BaseModel):
    """References sent to the provider's asynchronous batch API (table ``ai_batch``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    round_id: str
    task: str
    criteria_version_id: str  # the criteria the model was given
    provider: str
    provider_batch_id: str
    item_ids: tuple[str, ...] = Field(min_length=1)
    estimate: Decimal = Field(ge=0)
    created_at: AwareDatetime
    reviewer_id: str


class AIBatchEnd(BaseModel):
    """The results of a batch, once all recorded (table ``ai_batch_end``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    batch_id: str
    screened: int = Field(ge=0)
    failed: tuple[str, ...] = ()
    spent: Decimal = Field(ge=0)
    created_at: AwareDatetime


class PilotRound(BaseModel):
    """A pilot round: a random sample drawn with a recorded seed (EF-SEL-01)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    number: int = Field(ge=1)
    stage: Stage
    criteria_version_id: str
    seed: int
    sample_size: int = Field(ge=1)
    reference_ids: tuple[str, ...]
    created_at: AwareDatetime
    reviewer_id: str

    @model_validator(mode="after")
    def _sized(self) -> Self:
        if len(self.reference_ids) != self.sample_size:
            raise ValueError("the sample holds sample_size references")
        if len(set(self.reference_ids)) != len(self.reference_ids):
            raise ValueError("a reference is drawn at most once")
        return self


class CalibrationRecord(BaseModel):
    """A calibration fitted on a pilot round, for one AI configuration (EF-SEL-05)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    round_id: str
    ai_config_id: str
    calibration: Calibration
    artifact_path: str  # etalonnage/<id>.json
    created_at: AwareDatetime


class ThresholdSetting(BaseModel):
    """Thresholds fixed by a person, with their justification (EF-SEL-05, EF-SEL-09)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    stage: Stage
    thresholds: Thresholds
    target_sensitivity: Decimal = Field(gt=0, le=1)
    justification: str = Field(min_length=1)
    based_on_round_id: str | None = None
    calibration_id: str | None = None  # thresholds apply to calibrated probabilities
    reviewer_id: str
    created_at: AwareDatetime


class BudgetSetting(BaseModel):
    """Ceiling on what the project spends on model calls (ENF-COU-02); the latest
    setting counts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    limit_amount: Decimal = Field(gt=0)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    reviewer_id: str
    created_at: AwareDatetime


def draw_sample(reference_ids: Sequence[str], size: int, seed: int) -> tuple[str, ...]:
    """``size`` references drawn at random with ``seed`` (ENF-REP-01): the same ids and
    seed always give the same sample, in drawing order."""
    population = sorted(set(reference_ids))
    if size > len(population):
        raise ValueError("the sample cannot be larger than the references")
    return tuple(random.Random(seed).sample(population, size))  # noqa: S311 - not security


_WORD = re.compile(r"[a-z]+")
_FRENCH_WORDS = (
    "le la les des du un une et en est dans pour que qui sur par au aux avec ce ces "
    "son sa ses leur leurs pas plus ou etre entre chez selon aupres"
)
_ENGLISH_WORDS = (
    "the of and in to a is for on with that by as are from at this an be or its "
    "their which was were among between"
)
_STOPWORDS = {"fr": frozenset(_FRENCH_WORDS.split()), "en": frozenset(_ENGLISH_WORDS.split())}
_LANGUAGE_NAMES = {
    "fr": "fr",
    "fre": "fr",
    "fra": "fr",
    "french": "fr",
    "francais": "fr",
    "en": "en",
    "eng": "en",
    "english": "en",
    "anglais": "en",
}


def detect_language(declared: str, *texts: str) -> str:
    """ISO 639-1 code of a reference (ENF-LAN-05): the language declared by the source
    when it is recognized, else French or English by their common words, else ""."""
    name = unicodedata.normalize("NFKD", declared.strip().casefold())
    name = "".join(c for c in name if not unicodedata.combining(c))
    if name in _LANGUAGE_NAMES:
        return _LANGUAGE_NAMES[name]
    if re.fullmatch(r"[a-z]{2}", name):
        return name
    text = unicodedata.normalize("NFKD", " ".join(texts).casefold())
    words = _WORD.findall("".join(c for c in text if not unicodedata.combining(c)))
    counts = {lang: sum(w in stop for w in words) for lang, stop in _STOPWORDS.items()}
    best = max(counts, key=lambda lang: counts[lang])
    if counts[best] >= 2 and counts[best] > 2 * min(counts.values()):
        return best
    return ""
