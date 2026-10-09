"""Stakeholders and their comments (EF-CON-02, EF-CON-03): no personal data beyond name,
role and organisation (schema test), and the follow-up counted by hand."""

import datetime as dt
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from revue_portee.domain.stakeholders import (
    STAKEHOLDER_FIELDS,
    Comment,
    CommentResponse,
    CommentTarget,
    ResponseAction,
    Stakeholder,
    consultation_counts,
    responses_in_force,
    stakeholder_codes,
)
from revue_portee.storage.db import comment_response, stakeholder, stakeholder_comment
from revue_portee.storage.project_folder import DATABASE_FILE
from support import new_project, raw_sqlite

T0 = datetime(2026, 10, 9, tzinfo=UTC)
RECORD = {"id", "created_at", "reviewer_id"}  # the record itself, not the person
PERSONAL = ("mail", "phone", "tel", "address", "adresse", "birth", "naissance", "age",
            "gender", "sexe", "ip")  # fmt: skip


def test_no_personal_data_beyond_name_role_organisation(tmp_path: Path) -> None:
    """EF-CON-03, the acceptance criterion of tranche 4.2."""
    allowed = set(STAKEHOLDER_FIELDS) | RECORD
    assert set(Stakeholder.model_fields) == allowed
    assert {c.name for c in stakeholder.columns} == allowed | {"journal_entry_id"}
    # the database a project really has, after its migrations
    folder = new_project(tmp_path)
    folder.close()
    with raw_sqlite(folder.path / DATABASE_FILE) as db:
        columns = {row[1] for row in db.execute("pragma table_info(stakeholder)")}
    assert columns == allowed | {"journal_entry_id"}
    # nothing about the person elsewhere: comments and responses hold no personal field
    for table in (stakeholder_comment, comment_response):
        for column in table.columns:
            assert not any(word in column.name for word in PERSONAL), column.name
    with pytest.raises(ValidationError):
        Stakeholder.model_validate(
            {"id": "S", "name": "A", "role": "B", "created_at": T0, "reviewer_id": "R",
             "email": "contact@example.org"}
        )  # fmt: skip


def _person(sid: str, role: str, minutes: int) -> Stakeholder:
    return Stakeholder(id=sid, name=f"Personne {sid}", role=role, organisation="Org",
                       created_at=T0 + timedelta(minutes=minutes), reviewer_id="R")  # fmt: skip


def _comment(cid: str, who: str, target: CommentTarget) -> Comment:
    return Comment(id=cid, stakeholder_id=who, target=target, text="…",
                   received_on=dt.date(2026, 10, 1), created_at=T0, reviewer_id="R")  # fmt: skip


def _response(rid: str, cid: str, action: ResponseAction, minutes: int) -> CommentResponse:
    return CommentResponse(id=rid, comment_id=cid, action=action, text="…",
                           created_at=T0 + timedelta(minutes=minutes), reviewer_id="R")  # fmt: skip


def test_follow_up_counted_by_hand() -> None:
    # 3 people (2 patient partners, 1 clinician); 4 comments; 3 answered, one twice
    people = [_person("B", "patient partenaire", 2), _person("A", "clinicien", 1),
              _person("C", "patient partenaire", 3)]  # fmt: skip
    comments = [
        _comment("c1", "A", CommentTarget.CRITERIA),
        _comment("c2", "B", CommentTarget.RESULTS),
        _comment("c3", "B", CommentTarget.RESULTS),
        _comment("c4", "C", CommentTarget.LAY_SUMMARY),
    ]
    responses = [
        _response("r1", "c1", ResponseAction.DECLINED, 1),
        _response("r2", "c1", ResponseAction.CHANGED, 2),  # replaces r1
        _response("r3", "c2", ResponseAction.NOTED, 3),
        _response("r4", "c4", ResponseAction.CHANGED, 4),
    ]
    assert {k: v.id for k, v in responses_in_force(responses).items()} == {
        "c1": "r2", "c2": "r3", "c4": "r4",
    }  # fmt: skip
    counts = consultation_counts(people, comments, responses)
    assert (counts.stakeholders, counts.comments, counts.answered, counts.pending) == (3, 4, 3, 1)
    assert counts.by_target == {
        CommentTarget.CRITERIA: 1, CommentTarget.RESULTS: 2, CommentTarget.LAY_SUMMARY: 1,
    }  # fmt: skip
    assert counts.by_action == {ResponseAction.CHANGED: 2, ResponseAction.NOTED: 1}
    assert counts.by_role == {"clinicien": 1, "patient partenaire": 3}
    # codes in the order the people were recorded
    assert stakeholder_codes(people) == {"A": "PP1", "B": "PP2", "C": "PP3"}
