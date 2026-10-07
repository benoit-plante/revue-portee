"""AI configurations, calls, framing suggestions and qualification proposals."""

import json
from collections.abc import Iterable
from datetime import datetime

from pydantic import BaseModel, ConfigDict, JsonValue
from sqlalchemy import Connection, select

from revue_portee.ai.base import AICallRecord
from revue_portee.domain.changes import ChangeType, QualificationProposal
from revue_portee.domain.criteria import Criterion
from revue_portee.domain.journal import canonical_json
from revue_portee.domain.suggestions import (
    AISuggestion,
    SuggestionKind,
    SuggestionOutcome,
    SuggestionReview,
)
from revue_portee.storage.db import (
    ai_call,
    ai_config,
    ai_suggestion,
    qualification_proposal,
    suggestion_review,
)

__all__ = [
    "StoredCall",
    "ensure_config",
    "get_call",
    "get_suggestion",
    "insert_call",
    "insert_proposal",
    "insert_review",
    "insert_suggestions",
    "latest_proposals",
    "list_calls",
    "list_reviews",
    "list_suggestions",
]


class StoredCall(BaseModel):
    """A recorded model call (table ``ai_call``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    ai_config_id: str
    task: str
    item_id: str
    record: AICallRecord


def ensure_config(
    connection: Connection,
    *,
    config_id: str,
    task: str,
    provider: str,
    model: str,
    template_id: str,
    template_version: str,
    params: dict[str, JsonValue],
    now: datetime,
) -> tuple[str, bool]:
    """Id of the identical configuration if one exists, else of a new one (and True)."""
    params_json = canonical_json(params)
    existing = connection.execute(
        select(ai_config.c.id).where(
            ai_config.c.task == task,
            ai_config.c.provider == provider,
            ai_config.c.model_requested == model,
            ai_config.c.prompt_template_id == template_id,
            ai_config.c.prompt_template_version == template_version,
            ai_config.c.params_json == params_json,
        )
    ).scalar()
    if existing is not None:
        return str(existing), False
    connection.execute(
        ai_config.insert().values(
            id=config_id,
            task=task,
            provider=provider,
            model_requested=model,
            prompt_template_id=template_id,
            prompt_template_version=template_version,
            params_json=params_json,
            created_at=now,
        )
    )
    return config_id, True


def insert_call(
    connection: Connection,
    *,
    call_id: str,
    ai_config_id: str,
    task: str,
    item_id: str,
    record: AICallRecord,
    response_path: str | None,
) -> StoredCall:
    data = record.model_dump(exclude={"params", "response_path"})
    connection.execute(
        ai_call.insert().values(
            id=call_id,
            ai_config_id=ai_config_id,
            task=task,
            item_id=item_id,
            params_json=canonical_json(record.params),
            response_path=response_path,
            **data,
        )
    )
    stored = record.model_copy(update={"response_path": response_path})
    return StoredCall(
        id=call_id, ai_config_id=ai_config_id, task=task, item_id=item_id, record=stored
    )


def _to_call(row: dict[str, object]) -> StoredCall:
    fields = {
        key: value
        for key, value in row.items()
        if key not in {"id", "ai_config_id", "task", "item_id", "params_json"}
    }
    record = AICallRecord.model_validate(fields | {"params": json.loads(str(row["params_json"]))})
    return StoredCall(
        id=str(row["id"]),
        ai_config_id=str(row["ai_config_id"]),
        task=str(row["task"]),
        item_id=str(row["item_id"]),
        record=record,
    )


def get_call(connection: Connection, call_id: str) -> StoredCall | None:
    row = connection.execute(select(ai_call).where(ai_call.c.id == call_id)).mappings()
    found = row.one_or_none()
    return None if found is None else _to_call(dict(found))


def list_calls(connection: Connection, *, task: str | None = None) -> list[StoredCall]:
    query = select(ai_call).order_by(ai_call.c.created_at, ai_call.c.id)
    if task is not None:
        query = query.where(ai_call.c.task == task)
    return [_to_call(dict(row)) for row in connection.execute(query).mappings()]


def insert_suggestions(connection: Connection, suggestions: Iterable[AISuggestion]) -> None:
    rows = [s.model_dump(mode="python") for s in suggestions]
    if rows:
        connection.execute(ai_suggestion.insert(), rows)


def _to_suggestion(row: dict[str, object]) -> AISuggestion:
    return AISuggestion.model_validate(row | {"kind": SuggestionKind(str(row["kind"]))})


def list_suggestions(connection: Connection) -> list[AISuggestion]:
    rows = connection.execute(
        select(ai_suggestion).order_by(ai_suggestion.c.created_at, ai_suggestion.c.position)
    ).mappings()
    return [_to_suggestion(dict(row)) for row in rows]


def get_suggestion(connection: Connection, suggestion_id: str) -> AISuggestion | None:
    row = connection.execute(
        select(ai_suggestion).where(ai_suggestion.c.id == suggestion_id)
    ).mappings()
    found = row.one_or_none()
    return None if found is None else _to_suggestion(dict(found))


def insert_review(
    connection: Connection, review: SuggestionReview, *, journal_entry_id: str
) -> None:
    connection.execute(
        suggestion_review.insert().values(
            **review.model_dump(mode="python"), journal_entry_id=journal_entry_id
        )
    )


def list_reviews(connection: Connection) -> dict[str, SuggestionReview]:
    """Human reviews, by suggestion id."""
    rows = connection.execute(select(suggestion_review)).mappings()
    reviews = (
        SuggestionReview.model_validate(
            {k: v for k, v in row.items() if k != "journal_entry_id"}
            | {"outcome": SuggestionOutcome(str(row["outcome"]))}
        )
        for row in rows
    )
    return {review.suggestion_id: review for review in reviews}


def insert_proposal(connection: Connection, proposal: QualificationProposal) -> None:
    data = proposal.model_dump(mode="python", exclude={"after"})
    connection.execute(
        qualification_proposal.insert().values(
            **data, after_json=canonical_json(proposal.after.model_dump(mode="json"))
        )
    )


def latest_proposals(
    connection: Connection, draft_version_id: str
) -> dict[str, QualificationProposal]:
    """Most recent AI proposal for each criterion code of a draft."""
    rows = connection.execute(
        select(qualification_proposal)
        .where(qualification_proposal.c.draft_version_id == draft_version_id)
        .order_by(qualification_proposal.c.created_at, qualification_proposal.c.id)
    ).mappings()
    latest: dict[str, QualificationProposal] = {}
    for row in rows:
        data = {k: v for k, v in row.items() if k != "after_json"}
        latest[str(row["code"])] = QualificationProposal.model_validate(
            data
            | {
                "change_type": ChangeType(str(row["change_type"])),
                "after": Criterion.model_validate_json(str(row["after_json"])),
            }
        )
    return latest
