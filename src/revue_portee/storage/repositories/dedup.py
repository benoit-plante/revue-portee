"""Deduplication runs, candidate pairs and decisions (tranche 1.5)."""

import json
from typing import Any

from sqlalchemy import ColumnElement, Connection, select

from revue_portee.domain.dedup import DedupRun, DedupSettings, DuplicatePair, PairDecision
from revue_portee.storage.db import dedup_run, duplicate_pair, journal_entry, pair_decision

__all__ = [
    "decisions_on",
    "find_pair",
    "get_pair",
    "insert_decision",
    "insert_pairs",
    "insert_run",
    "latest_run",
    "list_decisions",
    "list_pairs",
]


def _dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def insert_run(connection: Connection, value: DedupRun, *, journal_entry_id: str) -> None:
    data = value.model_dump(mode="python")
    data["settings_json"] = _dumps(value.settings.model_dump(mode="json"))
    del data["settings"]
    connection.execute(dedup_run.insert().values(**data, journal_entry_id=journal_entry_id))


def _to_run(row: Any) -> DedupRun:  # noqa: ANN401 - SQLAlchemy row mapping
    data = {k: v for k, v in dict(row).items() if k != "journal_entry_id"}
    data["settings"] = DedupSettings.model_validate(json.loads(data.pop("settings_json")))
    return DedupRun.model_validate(data)


def latest_run(connection: Connection) -> DedupRun | None:
    row = (
        connection.execute(select(dedup_run).order_by(dedup_run.c.id.desc()).limit(1))
        .mappings()
        .one_or_none()
    )
    return None if row is None else _to_run(row)


def insert_pairs(connection: Connection, values: list[DuplicatePair]) -> None:
    rows = []
    for value in values:
        data = value.model_dump(mode="json")
        data["details_json"] = _dumps(data.pop("details"))
        rows.append(data)
    for start in range(0, len(rows), 500):
        connection.execute(duplicate_pair.insert(), rows[start : start + 500])


def _to_pair(row: Any) -> DuplicatePair:  # noqa: ANN401
    data = dict(row)
    data["details"] = json.loads(data.pop("details_json"))
    return DuplicatePair.model_validate(data)


def list_pairs(connection: Connection, run_id: str) -> list[DuplicatePair]:
    rows = connection.execute(
        select(duplicate_pair)
        .where(duplicate_pair.c.run_id == run_id)
        .order_by(duplicate_pair.c.reference_a_id, duplicate_pair.c.reference_b_id)
    ).mappings()
    return [_to_pair(row) for row in rows]


def get_pair(connection: Connection, pair_id: str) -> DuplicatePair | None:
    row = (
        connection.execute(select(duplicate_pair).where(duplicate_pair.c.id == pair_id))
        .mappings()
        .one_or_none()
    )
    return None if row is None else _to_pair(row)


def find_pair(
    connection: Connection, run_id: str, reference_a_id: str, reference_b_id: str
) -> DuplicatePair | None:
    row = (
        connection.execute(
            select(duplicate_pair).where(
                duplicate_pair.c.run_id == run_id,
                duplicate_pair.c.reference_a_id == reference_a_id,
                duplicate_pair.c.reference_b_id == reference_b_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else _to_pair(row)


def insert_decision(connection: Connection, value: PairDecision, *, journal_entry_id: str) -> None:
    connection.execute(
        pair_decision.insert().values(
            **value.model_dump(mode="python"), journal_entry_id=journal_entry_id
        )
    )


def _decisions(connection: Connection, *conditions: ColumnElement[bool]) -> list[PairDecision]:
    # The order of the journal, not of identifiers: two decisions taken in the same
    # millisecond (or after a clock change) keep the order in which they were made.
    statement = (
        select(pair_decision)
        .join(journal_entry, pair_decision.c.journal_entry_id == journal_entry.c.id)
        .where(*conditions)
        .order_by(journal_entry.c.position)
    )
    return [
        PairDecision.model_validate({k: v for k, v in dict(r).items() if k != "journal_entry_id"})
        for r in connection.execute(statement).mappings()
    ]


def list_decisions(connection: Connection) -> list[PairDecision]:
    """Every decision, in the order they were made."""
    return _decisions(connection)


def decisions_on(
    connection: Connection, reference_a_id: str, reference_b_id: str
) -> list[PairDecision]:
    """The decisions on one pair, in the order they were made."""
    return _decisions(
        connection,
        pair_decision.c.reference_a_id == reference_a_id,
        pair_decision.c.reference_b_id == reference_b_id,
    )
