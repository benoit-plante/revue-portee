"""Pilot round of title and abstract screening (EF-SEL-01 to 05).

A pilot draws a random sample of the deduplicated references with a recorded seed.
The human reviewer screens it **blind**: the AI's decision on a reference is shown
only once the human has decided it (EF-SEL-02). The AI screens the same references
(``screening.ai_screening``). From the pairs of decisions, the calibration table is
computed and a calibration is fitted; thresholds are then fixed by a person with
their justification (``screening.settings``).
"""

import json
import secrets
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from revue_portee.collect.deduplication import dedup_state
from revue_portee.domain.calibration import (
    Calibration,
    ThresholdSuggestion,
    fit_calibration,
    suggest_exclusion_threshold,
)
from revue_portee.domain.criteria import CriteriaVersion
from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.domain.metrics import (
    CurvePoint,
    PilotMetrics,
    disagreements_by_criterion,
    pilot_metrics,
    threshold_curve,
)
from revue_portee.domain.references import Reference
from revue_portee.domain.screening import (
    BudgetSetting,
    CalibrationRecord,
    Decision,
    DecisionValue,
    PilotRound,
    ReviewerKind,
    Stage,
    Thresholds,
    draw_sample,
    must_not_exclude,
)
from revue_portee.i18n import french
from revue_portee.i18n import gettext as _
from revue_portee.screening.settings import thresholds_in_force
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import ai as ai_repo
from revue_portee.storage.repositories import criteria as criteria_repo
from revue_portee.storage.repositories import journal
from revue_portee.storage.repositories import screening as screening_repo

__all__ = [
    "STAGE",
    "NoActiveCriteriaError",
    "NoReferencesError",
    "NotInRoundError",
    "NothingToCalibrateError",
    "PilotState",
    "UnknownCriterionError",
    "UnknownRoundError",
    "criteria_of",
    "fit_round_calibration",
    "get_round",
    "latest_by_reference",
    "list_rounds",
    "pilot_state",
    "record_human_decision",
    "start_pilot",
]

Clock = Callable[[], datetime]
STAGE = Stage.TITLE_ABSTRACT


class NoActiveCriteriaError(ValueError):
    def __init__(self) -> None:
        super().__init__(_("Activate a version of the criteria before the pilot."))


class NoReferencesError(ValueError):
    def __init__(self) -> None:
        super().__init__(_("There is no reference to screen yet: collect or import first."))


class UnknownRoundError(LookupError):
    def __init__(self) -> None:
        super().__init__(_("Unknown pilot round."))


class NotInRoundError(ValueError):
    def __init__(self) -> None:
        super().__init__(_("This reference is not part of the pilot round."))


class UnknownCriterionError(ValueError):
    def __init__(self, codes: Sequence[str]) -> None:
        super().__init__(
            _("Unknown criteria for this round: {codes}.").format(codes=", ".join(codes))
        )


class NothingToCalibrateError(ValueError):
    def __init__(self) -> None:
        super().__init__(_("No reference of the round has both a human and an AI decision yet."))


# --- Starting a pilot ---------------------------------------------------------------


def _active_criteria(folder: ProjectFolder) -> CriteriaVersion:
    with folder.engine.connect() as connection:
        version = criteria_repo.get_active_version(connection)
    if version is None:
        raise NoActiveCriteriaError
    return version


def _screenable(folder: ProjectFolder) -> list[str]:
    """References after deduplication: duplicates grouped under another are left out."""
    state = dedup_state(folder)
    duplicates = {ref_id for group in state.groups for ref_id in group.duplicates}
    return sorted(ref_id for ref_id in state.references if ref_id not in duplicates)


def start_pilot(
    folder: ProjectFolder,
    *,
    size: int | None = None,
    seed: int | None = None,
    now: Clock,
    tool_version: str,
) -> PilotRound:
    """Draw a pilot sample (EF-SEL-01); ``size`` defaults to the project setting and is
    reduced to the number of references when there are fewer."""
    version = _active_criteria(folder)
    population = _screenable(folder)
    if not population:
        raise NoReferencesError
    wanted = size or folder.ai_settings().supervision.pilot_sample_size
    drawn_seed = secrets.randbelow(2**31) if seed is None else seed
    sample = draw_sample(population, min(wanted, len(population)), drawn_seed)
    with folder.write() as connection:
        moment = now()
        number = len(screening_repo.list_rounds(connection, STAGE)) + 1
        pilot = PilotRound(
            id=new_ulid(moment),
            number=number,
            stage=STAGE,
            criteria_version_id=version.id,
            seed=drawn_seed,
            sample_size=len(sample),
            reference_ids=sample,
            created_at=moment,
            reviewer_id=folder.reviewer_id,
        )
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.PILOT_STARTED,
            subject_type="screening_round",
            subject_id=pilot.id,
            summary_fr=french(
                "Pilot round {number}: references drawn: {size} of {population} (seed {seed})"
            ).format(number=number, size=len(sample), population=len(population), seed=drawn_seed),
            tool_version=tool_version,
            payload={
                "round": number,
                "seed": drawn_seed,
                "sample_size": len(sample),
                "requested_size": wanted,
                "population": len(population),
                "criteria_version": version.number,
                "reference_ids": list(sample),
            },
        )
        screening_repo.insert_round(connection, pilot, journal_entry_id=entry.id)
    return pilot


def get_round(folder: ProjectFolder, round_id: str) -> PilotRound:
    with folder.engine.connect() as connection:
        found = screening_repo.get_round(connection, round_id)
    if found is None:
        raise UnknownRoundError
    return found


def list_rounds(folder: ProjectFolder) -> list[PilotRound]:
    """Pilot rounds of title and abstract screening, oldest first."""
    with folder.engine.connect() as connection:
        return screening_repo.list_rounds(connection, STAGE)


def criteria_of(folder: ProjectFolder, pilot: PilotRound) -> CriteriaVersion:
    with folder.engine.connect() as connection:
        version = criteria_repo.get_version(connection, pilot.criteria_version_id)
    assert version is not None  # noqa: S101 - a round always points to a version
    return version


# --- Human decisions ----------------------------------------------------------------


def latest_by_reference(decisions: Sequence[Decision], kind: ReviewerKind) -> dict[str, Decision]:
    latest: dict[str, Decision] = {}
    for d in decisions:
        if d.reviewer_kind is kind:
            latest[d.reference_id] = d
    return latest


def record_human_decision(
    folder: ProjectFolder,
    round_id: str,
    reference_id: str,
    value: DecisionValue,
    *,
    criteria_cited: Sequence[str] = (),
    rationale: str = "",
    now: Clock,
    tool_version: str,
) -> Decision:
    """The human reviewer's decision on a reference of the round, taken blind: the
    interface shows the AI's decision only afterwards (EF-SEL-02). A new decision on
    the same reference supersedes the previous one."""
    pilot = get_round(folder, round_id)
    if reference_id not in pilot.reference_ids:
        raise NotInRoundError
    version = criteria_of(folder, pilot)
    codes = {c.code for c in version.criteria}
    unknown = sorted(set(criteria_cited) - codes)
    if unknown:
        raise UnknownCriterionError(unknown)
    with folder.write() as connection:
        previous = latest_by_reference(
            screening_repo.list_decisions(connection, round_id=round_id), ReviewerKind.HUMAN
        ).get(reference_id)
        moment = now()
        decision = Decision(
            id=new_ulid(moment),
            reference_id=reference_id,
            stage=STAGE,
            round_id=round_id,
            reviewer_id=folder.reviewer_id,
            reviewer_kind=ReviewerKind.HUMAN,
            value=value,
            rationale=rationale.strip(),
            criteria_cited=tuple(sorted(set(criteria_cited))),
            criteria_version_id=version.id,
            blinded=True,
            supersedes_decision_id=None if previous is None else previous.id,
            tool_version=tool_version,
            created_at=moment,
        )
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.SCREENING_HUMAN_DECIDED,
            subject_type="decision",
            subject_id=decision.id,
            summary_fr=french("Pilot round {number}: human decision recorded").format(
                number=pilot.number
            ),
            tool_version=tool_version,
            payload={
                "reference": reference_id,
                "round": pilot.number,
                "value": value.value,
                "criteria_cited": list(decision.criteria_cited),
                "blinded": True,
                "supersedes": decision.supersedes_decision_id,
            },
        )
        screening_repo.insert_decision(connection, decision, journal_entry_id=entry.id)
    return decision


# --- Calibration table --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PilotState:
    round: PilotRound
    criteria: CriteriaVersion
    references: dict[str, Reference]
    human: dict[str, Decision]
    ai: dict[str, Decision]  # every AI decision, shown only once the human decided
    next_reference: str | None  # the next reference to screen blind
    metrics: PilotMetrics | None
    curve: list[CurvePoint]
    suggestion: ThresholdSuggestion | None
    disagreements: dict[str, int]
    calibration: CalibrationRecord | None
    thresholds: Thresholds
    thresholds_calibrated: bool
    budget: BudgetSetting | None
    spent: Decimal

    def visible_ai(self, reference_id: str) -> Decision | None:
        """The AI's decision, only once the human reviewer has decided (EF-SEL-02)."""
        return self.ai.get(reference_id) if reference_id in self.human else None


CURVE_THRESHOLDS = (0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5)


def _observations(
    pairs: Sequence[tuple[Decision, Decision]], calibration: Calibration | None
) -> list[tuple[float, bool, bool]]:
    rows = []
    for human, ai in pairs:
        raw = ai.confidence_raw if ai.confidence_raw is not None else 0.0
        p = raw if calibration is None else calibration.apply(raw)
        rows.append((p, human.value is not DecisionValue.EXCLUDE, must_not_exclude(ai.assessments)))
    return rows


def pilot_state(folder: ProjectFolder, round_id: str) -> PilotState:
    pilot = get_round(folder, round_id)
    version = criteria_of(folder, pilot)
    with folder.engine.connect() as connection:
        decisions = screening_repo.list_decisions(connection, round_id=round_id)
        calibration = screening_repo.latest_calibration(connection, round_id)
        budget = screening_repo.latest_budget(connection)
        spent = screening_repo.total_spent(connection)
    human = latest_by_reference(decisions, ReviewerKind.HUMAN)
    ai = latest_by_reference(decisions, ReviewerKind.AI)
    pairs = [(human[r], ai[r]) for r in pilot.reference_ids if r in human and r in ai]
    target = float(folder.ai_settings().supervision.target_sensitivity)
    fitted = None if calibration is None else calibration.calibration
    observations = _observations(pairs, fitted)
    thresholds, calibration_in_force = thresholds_in_force(folder)
    references = dedup_state(folder).references
    return PilotState(
        round=pilot,
        criteria=version,
        references={r: references[r] for r in pilot.reference_ids if r in references},
        human=human,
        ai=ai,
        next_reference=next((r for r in pilot.reference_ids if r not in human), None),
        metrics=pilot_metrics((h.value, a.value) for h, a in pairs) if pairs else None,
        curve=threshold_curve(observations, CURVE_THRESHOLDS) if pairs else [],
        suggestion=suggest_exclusion_threshold(observations, target) if pairs else None,
        disagreements=disagreements_by_criterion(
            (
                h.value,
                a.value,
                a.criteria_cited if a.value is DecisionValue.EXCLUDE else h.criteria_cited,
            )
            for h, a in pairs
        ),
        calibration=calibration,
        thresholds=thresholds,
        thresholds_calibrated=calibration_in_force is not None,
        budget=budget,
        spent=spent,
    )


def fit_round_calibration(
    folder: ProjectFolder, round_id: str, *, now: Clock, tool_version: str
) -> CalibrationRecord:
    """Fit the calibration of the AI's probability on the round (EF-SEL-05) and save it
    in ``etalonnage/``."""
    pilot = get_round(folder, round_id)
    with folder.engine.connect() as connection:
        decisions = screening_repo.list_decisions(connection, round_id=round_id)
        human = latest_by_reference(decisions, ReviewerKind.HUMAN)
        ai = latest_by_reference(decisions, ReviewerKind.AI)
        pairs = [(human[r], ai[r]) for r in pilot.reference_ids if r in human and r in ai]
        if not pairs:
            raise NothingToCalibrateError
        last_call = ai_repo.get_call(connection, str(pairs[-1][1].ai_call_id))
    assert last_call is not None  # noqa: S101 - an AI decision always has its call
    method = folder.ai_settings().supervision.calibration_method
    fitted = fit_calibration(
        [a.confidence_raw or 0.0 for _h, a in pairs],
        [h.value is not DecisionValue.EXCLUDE for h, _a in pairs],
        method,
    )
    with folder.write() as connection:
        moment = now()
        record_id = new_ulid(moment)
        relative = f"etalonnage/{record_id}.json"
        (folder.path / relative).write_text(fitted.model_dump_json(indent=1) + "\n", "utf-8")
        record = CalibrationRecord(
            id=record_id,
            round_id=round_id,
            ai_config_id=last_call.ai_config_id,
            calibration=fitted,
            artifact_path=relative,
            created_at=moment,
        )
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.CALIBRATION_FITTED,
            subject_type="calibration_model",
            subject_id=record.id,
            summary_fr=french(
                "Pilot round {number}: calibration fitted ({method}, decisions: {count})"
            ).format(number=pilot.number, method=fitted.method, count=len(pairs)),
            tool_version=tool_version,
            payload={
                "round": pilot.number,
                "method": fitted.method,
                "requested_method": method,
                "fitted_on": len(pairs),
                "artifact": relative,
                "calibration": json.loads(fitted.model_dump_json()),
            },
        )
        screening_repo.insert_calibration(connection, record, journal_entry_id=entry.id)
    return record
