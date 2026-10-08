"""Thresholds and budget of the AI reviewer (EF-SEL-05, EF-SEL-09, ENF-COU-02)."""

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.domain.screening import (
    BudgetSetting,
    CalibrationRecord,
    Stage,
    Thresholds,
    ThresholdSetting,
)
from revue_portee.i18n import french
from revue_portee.i18n import gettext as _
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import journal
from revue_portee.storage.repositories import screening as screening_repo

__all__ = ["BudgetNotSetError", "set_budget", "set_thresholds", "thresholds_in_force"]

Clock = Callable[[], datetime]
STAGE = Stage.TITLE_ABSTRACT


class BudgetNotSetError(ValueError):
    def __init__(self) -> None:
        super().__init__(
            _("Set the AI budget of the project before the first batch of screening (ENF-COU-02).")
        )


def thresholds_in_force(folder: ProjectFolder) -> tuple[Thresholds, CalibrationRecord | None]:
    """Thresholds fixed by a person, with their calibration; else the project defaults
    (EF-SEL-09), on raw probabilities."""
    with folder.engine.connect() as connection:
        setting = screening_repo.latest_threshold(connection, STAGE)
        calibration = (
            None
            if setting is None or setting.calibration_id is None
            else screening_repo.get_calibration(connection, setting.calibration_id)
        )
    if setting is not None:
        return setting.thresholds, calibration
    supervision = folder.ai_settings().supervision
    return (
        Thresholds(
            exclude_below=float(supervision.exclude_below),
            include_above=float(supervision.include_above),
        ),
        None,
    )


def set_budget(
    folder: ProjectFolder, amount: Decimal, *, currency: str = "USD", now: Clock, tool_version: str
) -> BudgetSetting:
    """Ceiling of the project's spending on model calls (ENF-COU-02)."""
    with folder.write() as connection:
        moment = now()
        budget = BudgetSetting(
            id=new_ulid(moment),
            limit_amount=amount,
            currency=currency,
            reviewer_id=folder.reviewer_id,
            created_at=moment,
        )
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.BUDGET_SET,
            subject_type="budget_setting",
            subject_id=budget.id,
            summary_fr=french("AI budget of the project: {amount} {currency}").format(
                amount=amount, currency=currency
            ),
            tool_version=tool_version,
            payload={"limit": str(amount), "currency": currency},
        )
        screening_repo.insert_budget(connection, budget, journal_entry_id=entry.id)
    return budget


def set_thresholds(
    folder: ProjectFolder,
    thresholds: Thresholds,
    *,
    justification: str,
    target_sensitivity: Decimal,
    round_id: str | None = None,
    calibration_id: str | None = None,
    now: Clock,
    tool_version: str,
) -> ThresholdSetting:
    """Thresholds fixed by a person with their justification (EF-SEL-05)."""
    with folder.write() as connection:
        moment = now()
        setting = ThresholdSetting(
            id=new_ulid(moment),
            stage=STAGE,
            thresholds=thresholds,
            target_sensitivity=target_sensitivity,
            justification=justification.strip(),
            based_on_round_id=round_id,
            calibration_id=calibration_id,
            reviewer_id=folder.reviewer_id,
            created_at=moment,
        )
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.THRESHOLDS_SET,
            subject_type="threshold_setting",
            subject_id=setting.id,
            summary_fr=french(
                "Screening thresholds: exclude below {low}, include from {high}"
            ).format(low=thresholds.exclude_below, high=thresholds.include_above),
            tool_version=tool_version,
            payload={
                "exclude_below": thresholds.exclude_below,
                "include_above": thresholds.include_above,
                "target_sensitivity": str(target_sensitivity),
                "justification": setting.justification,
                "round": round_id,
                "calibration": calibration_id,
            },
        )
        screening_repo.insert_threshold(connection, setting, journal_entry_id=entry.id)
    return setting
