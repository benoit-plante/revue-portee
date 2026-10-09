"""Plain-language summaries (tranche 4.1), append-only."""

import json
from typing import Any

from sqlalchemy import Connection, select

from revue_portee.domain.lay_summary import LaySummary
from revue_portee.storage.db import lay_summary

__all__ = ["insert_summary", "list_summaries"]


def insert_summary(connection: Connection, summary: LaySummary, *, journal_entry_id: str) -> None:
    data = summary.model_dump(mode="python", exclude={"narrative_ids"})
    data["narrative_ids_json"] = json.dumps(list(summary.narrative_ids))
    for name in ("level", "status", "reviewer_kind"):
        data[name] = getattr(summary, name).value
    connection.execute(lay_summary.insert().values(**data, journal_entry_id=journal_entry_id))


def list_summaries(connection: Connection) -> list[LaySummary]:
    rows = connection.execute(select(lay_summary).order_by(lay_summary.c.created_at))
    found = []
    for row in rows.mappings():
        data: dict[str, Any] = {k: v for k, v in dict(row).items() if k != "journal_entry_id"}
        data["narrative_ids"] = tuple(json.loads(data.pop("narrative_ids_json")))
        found.append(LaySummary.model_validate(data))
    return found
