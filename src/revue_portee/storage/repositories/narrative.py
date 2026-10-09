"""Drafts of the narrative synthesis (tranche 3.6), append-only."""

import json
from typing import Any

from sqlalchemy import Connection, select

from revue_portee.domain.narrative import NarrativeDraft
from revue_portee.storage.db import narrative_draft

__all__ = ["insert_draft", "list_drafts"]


def insert_draft(connection: Connection, draft: NarrativeDraft, *, journal_entry_id: str) -> None:
    data = draft.model_dump(mode="python", exclude={"sentences"})
    data["sentences_json"] = json.dumps(
        [s.model_dump(mode="json") for s in draft.sentences], ensure_ascii=False
    )
    data["status"] = draft.status.value
    data["reviewer_kind"] = draft.reviewer_kind.value
    connection.execute(narrative_draft.insert().values(**data, journal_entry_id=journal_entry_id))


def list_drafts(connection: Connection) -> list[NarrativeDraft]:
    rows = connection.execute(select(narrative_draft).order_by(narrative_draft.c.created_at))
    found = []
    for row in rows.mappings():
        data: dict[str, Any] = {k: v for k, v in dict(row).items() if k != "journal_entry_id"}
        data["sentences"] = json.loads(data.pop("sentences_json"))
        found.append(NarrativeDraft.model_validate(data))
    return found
