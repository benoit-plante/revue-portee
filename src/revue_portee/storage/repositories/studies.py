"""Reports of a same study (tranche 2.3), append-only."""

import json
from typing import Any

from sqlalchemy import Connection, select

from revue_portee.domain.studies import (
    LinkEvidence,
    PrimaryChoice,
    StudyLinkAssessment,
    StudyLinkDecision,
)
from revue_portee.storage.db import (
    journal_entry,
    primary_report_choice,
    study_link_assessment,
    study_link_decision,
)

__all__ = [
    "insert_assessment",
    "insert_choice",
    "insert_decision",
    "list_assessments",
    "list_choices",
    "list_decisions",
]


def _plain(row: Any) -> dict[str, Any]:  # noqa: ANN401 - SQLAlchemy row mapping
    return {k: v for k, v in dict(row).items() if k != "journal_entry_id"}


def insert_assessment(
    connection: Connection, value: StudyLinkAssessment, *, journal_entry_id: str
) -> None:
    data = value.model_dump(mode="python", exclude={"evidence"})
    data["verdict"] = value.verdict.value
    data["evidence_json"] = json.dumps(
        [e.model_dump(mode="json") for e in value.evidence], ensure_ascii=False, sort_keys=True
    )
    connection.execute(
        study_link_assessment.insert().values(**data, journal_entry_id=journal_entry_id)
    )


def insert_decision(
    connection: Connection, value: StudyLinkDecision, *, journal_entry_id: str
) -> None:
    data = value.model_dump(mode="python")
    data["outcome"] = value.outcome.value
    connection.execute(
        study_link_decision.insert().values(**data, journal_entry_id=journal_entry_id)
    )


def insert_choice(connection: Connection, value: PrimaryChoice, *, journal_entry_id: str) -> None:
    connection.execute(
        primary_report_choice.insert().values(
            **value.model_dump(mode="python"), journal_entry_id=journal_entry_id
        )
    )


def list_assessments(connection: Connection) -> list[StudyLinkAssessment]:
    """Every examination of the AI, in the order of the journal."""
    rows = connection.execute(
        select(study_link_assessment)
        .join(journal_entry, study_link_assessment.c.journal_entry_id == journal_entry.c.id)
        .order_by(journal_entry.c.position)
    ).mappings()
    found = []
    for row in rows:
        data = _plain(row)
        data["evidence"] = tuple(
            LinkEvidence.model_validate(e) for e in json.loads(data.pop("evidence_json"))
        )
        found.append(StudyLinkAssessment.model_validate(data))
    return found


def list_decisions(connection: Connection) -> list[StudyLinkDecision]:
    """Every decision of the person, in the order of the journal."""
    rows = connection.execute(
        select(study_link_decision)
        .join(journal_entry, study_link_decision.c.journal_entry_id == journal_entry.c.id)
        .order_by(journal_entry.c.position)
    ).mappings()
    return [StudyLinkDecision.model_validate(_plain(row)) for row in rows]


def list_choices(connection: Connection) -> list[PrimaryChoice]:
    """Every choice of a primary report, in the order of the journal."""
    rows = connection.execute(
        select(primary_report_choice)
        .join(journal_entry, primary_report_choice.c.journal_entry_id == journal_entry.c.id)
        .order_by(journal_entry.c.position)
    ).mappings()
    return [PrimaryChoice.model_validate(_plain(row)) for row in rows]
