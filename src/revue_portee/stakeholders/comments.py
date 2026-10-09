"""Stakeholders, their comments and what was done with them (EF-CON-02, EF-CON-03,
tranche 4.2).

The journal never holds a stakeholder's name nor the text of a comment: the journal
goes into the public archive. It records the stakeholder's id, role and organisation,
the target of each comment and the action taken. The export of the follow-up (for the
report) names each stakeholder by a code (PP1, PP2…) and a role, not by name.
"""

import csv
import datetime as dt
import io
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import JsonValue
from sqlalchemy import Connection

from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.domain.stakeholders import (
    Comment,
    CommentResponse,
    CommentTarget,
    ConsultationCounts,
    ResponseAction,
    Stakeholder,
    consultation_counts,
    responses_in_force,
    stakeholder_codes,
)
from revue_portee.i18n import french
from revue_portee.i18n import gettext as _
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import journal
from revue_portee.storage.repositories import stakeholders as repo

__all__ = [
    "ConsultationState",
    "FollowUp",
    "UnknownCommentError",
    "UnknownStakeholderError",
    "add_stakeholder",
    "answer",
    "consultation_state",
    "export_follow_up",
    "follow_up_csv",
    "record_comment",
]

Clock = Callable[[], datetime]


class UnknownStakeholderError(LookupError):
    def __init__(self) -> None:
        super().__init__(_("Unknown stakeholder."))


class UnknownCommentError(LookupError):
    def __init__(self) -> None:
        super().__init__(_("Unknown comment."))


@dataclass(frozen=True, slots=True)
class FollowUp:
    comment: Comment
    stakeholder: Stakeholder
    code: str  # PP1, PP2…
    response: CommentResponse | None  # the response in force


@dataclass(frozen=True, slots=True)
class ConsultationState:
    stakeholders: list[Stakeholder]
    codes: dict[str, str]
    follow_ups: list[FollowUp]  # oldest comment first
    counts: ConsultationCounts

    @property
    def pending(self) -> list[FollowUp]:
        return [f for f in self.follow_ups if f.response is None]


def consultation_state(folder: ProjectFolder) -> ConsultationState:
    with folder.engine.connect() as connection:
        people = repo.list_stakeholders(connection)
        comments = repo.list_comments(connection)
        responses = repo.list_responses(connection)
    by_id = {p.id: p for p in people}
    codes = stakeholder_codes(people)
    in_force = responses_in_force(responses)
    ordered = sorted(comments, key=lambda c: (c.received_on, c.created_at, c.id))
    return ConsultationState(
        stakeholders=people,
        codes=codes,
        follow_ups=[
            FollowUp(
                comment=c,
                stakeholder=by_id[c.stakeholder_id],
                code=codes[c.stakeholder_id],
                response=in_force.get(c.id),
            )
            for c in ordered
        ],
        counts=consultation_counts(people, comments, responses),
    )


def _journal(
    folder: ProjectFolder, connection: Connection, moment: datetime, entry_type: str,
    subject: tuple[str, str], summary: str, payload: dict[str, JsonValue], tool_version: str,
) -> str:  # fmt: skip
    entry = journal.append_entry(
        connection,
        now=moment,
        actor_reviewer_id=folder.reviewer_id,
        entry_type=entry_type,
        subject_type=subject[0],
        subject_id=subject[1],
        summary_fr=summary,
        tool_version=tool_version,
        payload=payload,
    )
    return entry.id


def add_stakeholder(
    folder: ProjectFolder, *, name: str, role: str, organisation: str = "", now: Clock,
    tool_version: str,
) -> Stakeholder:  # fmt: skip
    """Record a stakeholder: a name (or a pseudonym), a role and an organisation only."""
    moment = now()
    person = Stakeholder(
        id=new_ulid(moment), name=" ".join(name.split()), role=" ".join(role.split()),
        organisation=" ".join(organisation.split()), created_at=moment,
        reviewer_id=folder.reviewer_id,
    )  # fmt: skip
    with folder.write() as connection:
        # The name stays out of the journal: the journal goes into the public archive.
        entry_id = _journal(
            folder, connection, moment, EntryType.STAKEHOLDER_ADDED, ("stakeholder", person.id),
            french("Stakeholder added ({role})").format(role=person.role),
            {"role": person.role, "organisation": person.organisation}, tool_version,
        )  # fmt: skip
        repo.insert_stakeholder(connection, person, journal_entry_id=entry_id)
    return person


def record_comment(
    folder: ProjectFolder,
    stakeholder_id: str,
    *,
    target: CommentTarget,
    text: str,
    received_on: dt.date,
    target_detail: str = "",
    now: Clock,
    tool_version: str,
) -> Comment:
    with folder.engine.connect() as connection:
        known = {p.id for p in repo.list_stakeholders(connection)}
    if stakeholder_id not in known:
        raise UnknownStakeholderError
    moment = now()
    comment = Comment(
        id=new_ulid(moment), stakeholder_id=stakeholder_id, target=target,
        target_detail=target_detail.strip(), text=text.strip(), received_on=received_on,
        created_at=moment, reviewer_id=folder.reviewer_id,
    )  # fmt: skip
    with folder.write() as connection:
        # The text stays out of the journal: it is an unpublished communication.
        entry_id = _journal(
            folder, connection, moment, EntryType.STAKEHOLDER_COMMENT_RECORDED,
            ("stakeholder_comment", comment.id),
            french("Stakeholder comment recorded on {target}").format(target=target.value),
            {"stakeholder": stakeholder_id, "target": target.value,
             "target_detail": comment.target_detail, "received_on": received_on.isoformat()},
            tool_version,
        )  # fmt: skip
        repo.insert_comment(connection, comment, journal_entry_id=entry_id)
    return comment


def answer(
    folder: ProjectFolder,
    comment_id: str,
    *,
    action: ResponseAction,
    text: str,
    now: Clock,
    tool_version: str,
) -> CommentResponse:
    """What was done with a comment; a new response supersedes the previous one."""
    state = consultation_state(folder)
    found = next((f for f in state.follow_ups if f.comment.id == comment_id), None)
    if found is None:
        raise UnknownCommentError
    moment = now()
    response = CommentResponse(
        id=new_ulid(moment), comment_id=comment_id, action=action, text=text.strip(),
        supersedes_id=None if found.response is None else found.response.id,
        created_at=moment, reviewer_id=folder.reviewer_id,
    )  # fmt: skip
    with folder.write() as connection:
        entry_id = _journal(
            folder, connection, moment, EntryType.STAKEHOLDER_COMMENT_ANSWERED,
            ("comment_response", response.id),
            french("Stakeholder comment answered: {action}").format(action=action.value),
            {"comment": comment_id, "action": action.value,
             "supersedes": response.supersedes_id},
            tool_version,
        )  # fmt: skip
        repo.insert_response(connection, response, journal_entry_id=entry_id)
    return response


def follow_up_csv(state: ConsultationState, *, with_text: bool) -> str:
    """One row per comment: code, role and organisation of its author (never the name),
    target, date, and the response in force; the texts only when ``with_text``."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    header = ["stakeholder", "role", "organisation", "target", "target_detail", "received_on",
              "action", "answered_on"]  # fmt: skip
    if with_text:
        header += ["comment", "response"]
    writer.writerow(header)
    for f in state.follow_ups:
        row: list[object] = [
            f.code, f.stakeholder.role, f.stakeholder.organisation, f.comment.target.value,
            f.comment.target_detail, f.comment.received_on.isoformat(),
            "" if f.response is None else f.response.action.value,
            "" if f.response is None else f.response.created_at.date().isoformat(),
        ]  # fmt: skip
        if with_text:
            row += [f.comment.text, "" if f.response is None else f.response.text]
        writer.writerow(row)
    return buffer.getvalue()


def export_follow_up(folder: ProjectFolder) -> Path:
    """Write ``exports/suivi-commentaires.csv``, texts included, for the team's report
    (the stakeholders by code and role, not by name)."""
    target = folder.path / "exports" / "suivi-commentaires.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(follow_up_csv(consultation_state(folder), with_text=True), encoding="utf-8")
    return target
