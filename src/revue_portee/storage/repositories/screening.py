"""Pilot rounds, screening decisions, calibrations, thresholds and budget (tranche 1.6)."""

import json
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Connection, select

from revue_portee.domain.calibration import Calibration
from revue_portee.domain.screening import (
    BudgetSetting,
    CalibrationRecord,
    CriterionAssessment,
    Decision,
    PilotRound,
    Stage,
    Thresholds,
    ThresholdSetting,
)
from revue_portee.storage.db import (
    ai_call,
    budget_setting,
    calibration_model,
    decision,
    journal_entry,
    round_member,
    screening_round,
    threshold_setting,
)

__all__ = [
    "get_calibration",
    "get_round",
    "insert_budget",
    "insert_calibration",
    "insert_decision",
    "insert_round",
    "insert_threshold",
    "latest_budget",
    "latest_calibration",
    "latest_threshold",
    "list_decisions",
    "list_rounds",
    "total_spent",
]

PILOT = "pilot"


def _dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _plain(row: Any) -> dict[str, Any]:  # noqa: ANN401 - SQLAlchemy row mapping
    return {k: v for k, v in dict(row).items() if k != "journal_entry_id"}


# --- Rounds -------------------------------------------------------------------------


def insert_round(connection: Connection, value: PilotRound, *, journal_entry_id: str) -> None:
    data = value.model_dump(mode="python", exclude={"reference_ids"})
    connection.execute(
        screening_round.insert().values(**data, kind=PILOT, journal_entry_id=journal_entry_id)
    )
    connection.execute(
        round_member.insert(),
        [
            {"round_id": value.id, "position": position, "reference_id": reference_id}
            for position, reference_id in enumerate(value.reference_ids, start=1)
        ],
    )


def _to_round(connection: Connection, row: Any) -> PilotRound:  # noqa: ANN401
    data = _plain(row)
    data.pop("kind")
    members = connection.execute(
        select(round_member.c.reference_id)
        .where(round_member.c.round_id == data["id"])
        .order_by(round_member.c.position)
    ).scalars()
    return PilotRound.model_validate(data | {"reference_ids": tuple(members)})


def list_rounds(connection: Connection, stage: Stage) -> list[PilotRound]:
    rows = connection.execute(
        select(screening_round)
        .where(screening_round.c.stage == stage.value, screening_round.c.kind == PILOT)
        .order_by(screening_round.c.number)
    ).mappings()
    return [_to_round(connection, row) for row in rows]


def get_round(connection: Connection, round_id: str) -> PilotRound | None:
    row = (
        connection.execute(select(screening_round).where(screening_round.c.id == round_id))
        .mappings()
        .one_or_none()
    )
    return None if row is None else _to_round(connection, row)


# --- Decisions ----------------------------------------------------------------------


def insert_decision(connection: Connection, value: Decision, *, journal_entry_id: str) -> None:
    data = value.model_dump(mode="json", exclude={"criteria_cited", "assessments", "thresholds"})
    data["created_at"] = value.created_at
    data["criteria_cited_json"] = _dumps(list(value.criteria_cited))
    data["per_criterion_json"] = _dumps([a.model_dump(mode="json") for a in value.assessments])
    data["thresholds_json"] = (
        None if value.thresholds is None else _dumps(value.thresholds.model_dump(mode="json"))
    )
    connection.execute(decision.insert().values(**data, journal_entry_id=journal_entry_id))


def _to_decision(row: Any) -> Decision:  # noqa: ANN401
    data = _plain(row)
    data["criteria_cited"] = tuple(json.loads(data.pop("criteria_cited_json")))
    data["assessments"] = tuple(
        CriterionAssessment.model_validate(a) for a in json.loads(data.pop("per_criterion_json"))
    )
    thresholds = data.pop("thresholds_json")
    data["thresholds"] = None if thresholds is None else Thresholds.model_validate_json(thresholds)
    return Decision.model_validate(data)


def list_decisions(
    connection: Connection, *, round_id: str | None = None, reference_id: str | None = None
) -> list[Decision]:
    """Decisions in the order they were made (the order of the journal)."""
    conditions: list[ColumnElement[bool]] = []
    if round_id is not None:
        conditions.append(decision.c.round_id == round_id)
    if reference_id is not None:
        conditions.append(decision.c.reference_id == reference_id)
    rows = connection.execute(
        select(decision)
        .join(journal_entry, decision.c.journal_entry_id == journal_entry.c.id)
        .where(*conditions)
        .order_by(journal_entry.c.position)
    ).mappings()
    return [_to_decision(row) for row in rows]


# --- Calibration, thresholds, budget ------------------------------------------------


def insert_calibration(
    connection: Connection, value: CalibrationRecord, *, journal_entry_id: str
) -> None:
    connection.execute(
        calibration_model.insert().values(
            id=value.id,
            round_id=value.round_id,
            ai_config_id=value.ai_config_id,
            method=value.calibration.method,
            calibration_json=value.calibration.model_dump_json(),
            artifact_path=value.artifact_path,
            fitted_on_n=value.calibration.fitted_on,
            created_at=value.created_at,
            journal_entry_id=journal_entry_id,
        )
    )


def _to_calibration(row: Any) -> CalibrationRecord:  # noqa: ANN401
    return CalibrationRecord(
        id=row["id"],
        round_id=row["round_id"],
        ai_config_id=row["ai_config_id"],
        calibration=Calibration.model_validate_json(row["calibration_json"]),
        artifact_path=row["artifact_path"],
        created_at=row["created_at"],
    )


def get_calibration(connection: Connection, calibration_id: str) -> CalibrationRecord | None:
    row = (
        connection.execute(
            select(calibration_model).where(calibration_model.c.id == calibration_id)
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else _to_calibration(row)


def latest_calibration(connection: Connection, round_id: str) -> CalibrationRecord | None:
    row = (
        connection.execute(
            select(calibration_model)
            .where(calibration_model.c.round_id == round_id)
            .order_by(calibration_model.c.created_at.desc(), calibration_model.c.id.desc())
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else _to_calibration(row)


def insert_threshold(
    connection: Connection, value: ThresholdSetting, *, journal_entry_id: str
) -> None:
    data = value.model_dump(mode="python", exclude={"thresholds"})
    connection.execute(
        threshold_setting.insert().values(
            **data,
            exclude_below=value.thresholds.exclude_below,
            include_above=value.thresholds.include_above,
            journal_entry_id=journal_entry_id,
        )
    )


def latest_threshold(connection: Connection, stage: Stage) -> ThresholdSetting | None:
    row = (
        connection.execute(
            select(threshold_setting)
            .join(journal_entry, threshold_setting.c.journal_entry_id == journal_entry.c.id)
            .where(threshold_setting.c.stage == stage.value)
            .order_by(journal_entry.c.position.desc())
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    data = _plain(row)
    data["thresholds"] = Thresholds(
        exclude_below=data.pop("exclude_below"), include_above=data.pop("include_above")
    )
    return ThresholdSetting.model_validate(data)


def insert_budget(connection: Connection, value: BudgetSetting, *, journal_entry_id: str) -> None:
    connection.execute(
        budget_setting.insert().values(
            **value.model_dump(mode="python"), journal_entry_id=journal_entry_id
        )
    )


def latest_budget(connection: Connection) -> BudgetSetting | None:
    row = (
        connection.execute(
            select(budget_setting)
            .join(journal_entry, budget_setting.c.journal_entry_id == journal_entry.c.id)
            .order_by(journal_entry.c.position.desc())
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else BudgetSetting.model_validate(_plain(row))


def total_spent(connection: Connection, *, since_call_id: str | None = None) -> Decimal:
    """Cost of every model call of the project (or of those after ``since_call_id``)."""
    statement = select(ai_call.c.cost_estimate)
    if since_call_id is not None:
        statement = statement.where(ai_call.c.id > since_call_id)
    return sum((Decimal(cost) for cost in connection.execute(statement).scalars()), Decimal(0))
