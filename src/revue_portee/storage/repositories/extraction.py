"""Extracted values (tranche 3.2), append-only."""

import json
from typing import Any

from sqlalchemy import Connection, select

from revue_portee.domain.extraction import ExtractionPilot, ExtractionValue
from revue_portee.storage.db import extraction_pilot, extraction_value, journal_entry

__all__ = ["insert_pilot", "insert_value", "list_pilots", "list_values"]


def insert_value(connection: Connection, value: ExtractionValue, *, journal_entry_id: str) -> None:
    data = value.model_dump(mode="python", exclude={"value"})
    data["value_json"] = json.dumps(value.value, ensure_ascii=False)
    for name in ("status", "reviewer_kind", "quote_check"):
        if data[name] is not None:
            data[name] = getattr(value, name).value
    connection.execute(extraction_value.insert().values(**data, journal_entry_id=journal_entry_id))


def list_values(
    connection: Connection, *, reference_id: str | None = None
) -> list[ExtractionValue]:
    """Values in the order of the journal (oldest first)."""
    query = select(extraction_value).join(
        journal_entry, extraction_value.c.journal_entry_id == journal_entry.c.id
    )
    if reference_id is not None:
        query = query.where(extraction_value.c.reference_id == reference_id)
    rows = connection.execute(query.order_by(journal_entry.c.position)).mappings()
    found = []
    for row in rows:
        data: dict[str, Any] = {k: v for k, v in dict(row).items() if k != "journal_entry_id"}
        data["value"] = json.loads(data.pop("value_json"))
        found.append(ExtractionValue.model_validate(data))
    return found


def insert_pilot(connection: Connection, pilot: ExtractionPilot, *, journal_entry_id: str) -> None:
    data = pilot.model_dump(mode="python", exclude={"reference_ids"})
    data["reference_ids_json"] = json.dumps(list(pilot.reference_ids))
    connection.execute(extraction_pilot.insert().values(**data, journal_entry_id=journal_entry_id))


def list_pilots(connection: Connection) -> list[ExtractionPilot]:
    rows = connection.execute(select(extraction_pilot).order_by(extraction_pilot.c.number))
    found = []
    for row in rows.mappings():
        data: dict[str, Any] = {k: v for k, v in dict(row).items() if k != "journal_entry_id"}
        data["reference_ids"] = tuple(json.loads(data.pop("reference_ids_json")))
        found.append(ExtractionPilot.model_validate(data))
    return found
