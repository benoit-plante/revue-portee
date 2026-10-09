"""Screening rounds, decisions, calibrations, thresholds, budget (tranche 1.6), AI batches
and impact assessments (tranche 1.7)."""

import json
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Connection, exists, func, select

from revue_portee.domain.calibration import Calibration
from revue_portee.domain.impact import Impact, ImpactAssessment
from revue_portee.domain.screening import (
    AIBatch,
    AIBatchEnd,
    BudgetSetting,
    CalibrationRecord,
    CriterionAssessment,
    Decision,
    PilotRound,
    RoundKind,
    ScreeningRound,
    Stage,
    Thresholds,
    ThresholdSetting,
)
from revue_portee.storage.db import (
    ai_batch,
    ai_batch_end,
    ai_call,
    budget_setting,
    calibration_model,
    decision,
    impact_assessment,
    journal_entry,
    round_member,
    screening_round,
    threshold_setting,
)

__all__ = [
    "append_members",
    "batch_attempts",
    "batch_end",
    "batch_item_ids_recorded",
    "batch_spent",
    "count_decided",
    "get_ai_batch",
    "get_calibration",
    "get_impact",
    "get_round",
    "get_screening_round",
    "insert_ai_batch",
    "insert_batch_end",
    "insert_budget",
    "insert_calibration",
    "insert_decision",
    "insert_impact",
    "insert_round",
    "insert_screening_round",
    "insert_threshold",
    "is_member",
    "latest_budget",
    "latest_by_reference",
    "latest_calibration",
    "latest_threshold",
    "list_ai_batches",
    "list_decisions",
    "list_impacts",
    "list_rounds",
    "list_screening_rounds",
    "member_count",
    "member_ids",
    "next_to_screen",
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
    data.pop("mode")  # a pilot is always screened blind
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
        connection.execute(
            select(screening_round).where(
                screening_round.c.id == round_id, screening_round.c.kind == PILOT
            )
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else _to_round(connection, row)


def insert_screening_round(
    connection: Connection,
    value: ScreeningRound,
    members: Sequence[str],
    *,
    journal_entry_id: str,
) -> None:
    connection.execute(
        screening_round.insert().values(
            **value.model_dump(mode="python"), journal_entry_id=journal_entry_id
        )
    )
    append_members(connection, value.id, members)


def append_members(connection: Connection, round_id: str, reference_ids: Sequence[str]) -> None:
    """Add references at the end of a round, in the order given."""
    if not reference_ids:
        return
    last = connection.execute(
        select(func.coalesce(func.max(round_member.c.position), 0)).where(
            round_member.c.round_id == round_id
        )
    ).scalar_one()
    connection.execute(
        round_member.insert(),
        [
            {"round_id": round_id, "position": last + offset, "reference_id": reference_id}
            for offset, reference_id in enumerate(reference_ids, start=1)
        ],
    )


def get_screening_round(connection: Connection, round_id: str) -> ScreeningRound | None:
    row = (
        connection.execute(select(screening_round).where(screening_round.c.id == round_id))
        .mappings()
        .one_or_none()
    )
    return None if row is None else ScreeningRound.model_validate(_plain(row))


def list_screening_rounds(
    connection: Connection, stage: Stage, kind: RoundKind
) -> list[ScreeningRound]:
    rows = connection.execute(
        select(screening_round)
        .where(screening_round.c.stage == stage.value, screening_round.c.kind == kind.value)
        .order_by(screening_round.c.number)
    ).mappings()
    return [ScreeningRound.model_validate(_plain(row)) for row in rows]


def member_ids(connection: Connection, round_id: str) -> list[str]:
    return list(
        connection.execute(
            select(round_member.c.reference_id)
            .where(round_member.c.round_id == round_id)
            .order_by(round_member.c.position)
        ).scalars()
    )


def member_count(connection: Connection, round_id: str) -> int:
    return int(
        connection.execute(
            select(func.count())
            .select_from(round_member)
            .where(round_member.c.round_id == round_id)
        ).scalar_one()
    )


def is_member(connection: Connection, round_id: str, reference_id: str) -> bool:
    return (
        connection.execute(
            select(round_member.c.position).where(
                round_member.c.round_id == round_id, round_member.c.reference_id == reference_id
            )
        ).first()
        is not None
    )


def _human_decided(decided_in: Sequence[str], reference: Any) -> Any:  # noqa: ANN401
    """Whether ``reference`` has an independent human decision in ``decided_in`` (read
    from the index ``ix_decision_reference_kind`` alone)."""
    return exists().where(
        decision.c.reference_id == reference,
        decision.c.reviewer_kind == "human",
        decision.c.context == "independent",
        decision.c.round_id.in_(decided_in),
    )


def next_to_screen(
    connection: Connection,
    round_id: str,
    *,
    decided_in: Sequence[str],
    priority: bool = False,
    skip: Sequence[str] = (),
) -> str | None:
    """The first member of the round with no human decision in any of the rounds
    ``decided_in``: in the round's order, or, with ``priority``, by the AI's probability
    of inclusion, highest first, then the references the AI has not screened in the
    round's order. Indexed queries that stop at the first reference found, whatever the
    number of references (ENF-PER-01)."""
    if priority:
        probability = func.coalesce(decision.c.confidence_calibrated, decision.c.confidence_raw)
        query = select(decision.c.reference_id).where(
            decision.c.round_id == round_id,
            decision.c.reviewer_kind == "ai",
            ~_human_decided(decided_in, decision.c.reference_id),
        )
        if skip:
            query = query.where(decision.c.reference_id.not_in(skip))
        found = connection.execute(query.order_by(probability.desc()).limit(1)).scalar_one_or_none()
        if found is not None:
            return str(found)
    query = select(round_member.c.reference_id).where(
        round_member.c.round_id == round_id,
        ~_human_decided(decided_in, round_member.c.reference_id),
    )
    if skip:
        query = query.where(round_member.c.reference_id.not_in(skip))
    return connection.execute(query.order_by(round_member.c.position).limit(1)).scalar_one_or_none()


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


def count_decided(connection: Connection, round_id: str, *, decided_in: Sequence[str]) -> int:
    """Members of the round with an independent human decision in ``decided_in``: the
    decisions of the round itself (read from an index), and those of the other rounds
    (pilots, a few references) whose reference is a member not decided in the round."""
    independent = (decision.c.reviewer_kind == "human", decision.c.context == "independent")
    own = connection.execute(
        select(func.count(func.distinct(decision.c.reference_id))).where(
            decision.c.round_id == round_id, *independent
        )
    ).scalar_one()
    others = [r for r in decided_in if r != round_id]
    if not others:
        return int(own)
    member = (
        select(round_member.c.position)
        .where(
            round_member.c.round_id == round_id,
            round_member.c.reference_id == decision.c.reference_id,
        )
        .exists()
    )
    carried = connection.execute(
        select(func.count(func.distinct(decision.c.reference_id))).where(
            decision.c.round_id.in_(others),
            *independent,
            member,
            ~_human_decided([round_id], decision.c.reference_id),
        )
    ).scalar_one()
    return int(own) + int(carried)


def latest_by_reference(
    connection: Connection,
    round_ids: Sequence[str],
    *,
    reviewer_kind: str,
    contexts: Sequence[str] | None = None,
) -> dict[str, Decision]:
    """The latest decision on each reference among the rounds ``round_ids``, in the
    order of the journal."""
    conditions: list[ColumnElement[bool]] = [
        decision.c.round_id.in_(round_ids),
        decision.c.reviewer_kind == reviewer_kind,
    ]
    if contexts is not None:
        conditions.append(decision.c.context.in_(contexts))
    rows = connection.execute(
        select(decision)
        .join(journal_entry, decision.c.journal_entry_id == journal_entry.c.id)
        .where(*conditions)
        .order_by(journal_entry.c.position)
    ).mappings()
    latest: dict[str, Decision] = {}
    for row in rows:
        found = _to_decision(row)
        latest[found.reference_id] = found
    return latest


# --- AI batches ---------------------------------------------------------------------


def insert_ai_batch(connection: Connection, value: AIBatch, *, journal_entry_id: str) -> None:
    data = value.model_dump(mode="python", exclude={"item_ids"})
    connection.execute(
        ai_batch.insert().values(
            **data, item_ids_json=_dumps(list(value.item_ids)), journal_entry_id=journal_entry_id
        )
    )


def _to_batch(row: Any) -> AIBatch:  # noqa: ANN401
    data = _plain(row)
    data["item_ids"] = tuple(json.loads(data.pop("item_ids_json")))
    return AIBatch.model_validate(data)


def get_ai_batch(connection: Connection, batch_id: str) -> AIBatch | None:
    row = connection.execute(select(ai_batch).where(ai_batch.c.id == batch_id)).mappings().first()
    return None if row is None else _to_batch(row)


def list_ai_batches(connection: Connection, round_id: str) -> list[AIBatch]:
    rows = connection.execute(
        select(ai_batch).where(ai_batch.c.round_id == round_id).order_by(ai_batch.c.id)
    ).mappings()
    return [_to_batch(row) for row in rows]


def insert_batch_end(connection: Connection, value: AIBatchEnd, *, journal_entry_id: str) -> None:
    connection.execute(
        ai_batch_end.insert().values(
            batch_id=value.batch_id,
            screened=value.screened,
            failed_json=_dumps(list(value.failed)),
            spent=value.spent,
            created_at=value.created_at,
            journal_entry_id=journal_entry_id,
        )
    )


def batch_end(connection: Connection, batch_id: str) -> AIBatchEnd | None:
    row = (
        connection.execute(select(ai_batch_end).where(ai_batch_end.c.batch_id == batch_id))
        .mappings()
        .first()
    )
    if row is None:
        return None
    data = _plain(row)
    data["failed"] = tuple(json.loads(data.pop("failed_json")))
    return AIBatchEnd.model_validate(data)


def batch_spent(connection: Connection, provider_batch_ids: Sequence[str]) -> Decimal:
    """Cost of the calls recorded for the provider batches."""
    costs = connection.execute(
        select(ai_call.c.cost_estimate).where(ai_call.c.batch_id.in_(provider_batch_ids))
    ).scalars()
    return sum((Decimal(cost) for cost in costs), Decimal(0))


def batch_attempts(connection: Connection, provider_batch_ids: Sequence[str]) -> dict[str, int]:
    """Number of calls recorded for each item in the provider batches."""
    rows = connection.execute(
        select(ai_call.c.item_id, func.count())
        .where(ai_call.c.batch_id.in_(provider_batch_ids))
        .group_by(ai_call.c.item_id)
    ).all()
    return {item: int(count) for item, count in rows}


def batch_item_ids_recorded(connection: Connection, provider_batch_id: str) -> set[str]:
    """Items of a provider batch whose call is already recorded (collection resumes)."""
    return set(
        connection.execute(
            select(ai_call.c.item_id).where(ai_call.c.batch_id == provider_batch_id)
        ).scalars()
    )


# --- Impact assessments -------------------------------------------------------------


def insert_impact(
    connection: Connection, value: ImpactAssessment, *, journal_entry_id: str
) -> None:
    connection.execute(
        impact_assessment.insert().values(
            id=value.id,
            from_version_id=value.from_version_id,
            to_version_id=value.to_version_id,
            main_round_id=value.main_round_id,
            changes_json=value.impact.model_dump_json(),
            touched_count=len(value.impact.touched),
            reassessment_round_id=value.reassessment_round_id,
            seed=value.seed,
            sampled=value.sampled,
            created_at=value.created_at,
            reviewer_id=value.reviewer_id,
            journal_entry_id=journal_entry_id,
        )
    )


def _to_impact(row: Any) -> ImpactAssessment:  # noqa: ANN401
    data = _plain(row)
    data.pop("touched_count")
    data["impact"] = Impact.model_validate_json(data.pop("changes_json"))
    return ImpactAssessment.model_validate(data)


def get_impact(connection: Connection, impact_id: str) -> ImpactAssessment | None:
    row = (
        connection.execute(select(impact_assessment).where(impact_assessment.c.id == impact_id))
        .mappings()
        .first()
    )
    return None if row is None else _to_impact(row)


def list_impacts(connection: Connection, main_round_id: str) -> list[ImpactAssessment]:
    rows = connection.execute(
        select(impact_assessment)
        .join(journal_entry, impact_assessment.c.journal_entry_id == journal_entry.c.id)
        .where(impact_assessment.c.main_round_id == main_round_id)
        .order_by(journal_entry.c.position)
    ).mappings()
    return [_to_impact(row) for row in rows]


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
