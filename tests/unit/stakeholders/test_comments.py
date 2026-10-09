"""Follow-up of the stakeholders' comments (EF-CON-02): who, when, on what, what was
done; neither the name nor the text of a comment reaches the journal or the public
archive (EF-CON-03)."""

import csv
import datetime as dt
import io
from pathlib import Path
from typing import Any

import pytest

from revue_portee.domain.journal import EntryType
from revue_portee.domain.stakeholders import CommentTarget, ResponseAction
from revue_portee.screening.archive import ArchiveKind, archive_files
from revue_portee.stakeholders import comments
from support import TOOL_VERSION, make_clock, new_project

NAME = "Mireille Exemple"
COMMENT = "Le critère d'âge exclut les jeunes de 25 ans."
ANSWER = "Critère élargi à 25 ans dans la version 2."


def _consulted(tmp_path: Path) -> tuple[Any, str]:  # the project and the comment's id
    folder = new_project(tmp_path)
    clock = make_clock()
    kwargs: dict[str, Any] = {"now": clock, "tool_version": TOOL_VERSION}
    person = comments.add_stakeholder(
        folder, name=f"  {NAME} ", role="patiente  partenaire", organisation="Org. A", **kwargs
    )
    comments.add_stakeholder(folder, name="Clinicien 1", role="clinicien", **kwargs)
    first = comments.record_comment(
        folder, person.id, target=CommentTarget.CRITERIA, target_detail="P1",
        text=COMMENT, received_on=dt.date(2026, 10, 2), **kwargs,
    )  # fmt: skip
    comments.record_comment(
        folder, person.id, target=CommentTarget.LAY_SUMMARY, text="Trop long.",
        received_on=dt.date(2026, 10, 1), **kwargs,
    )  # fmt: skip
    comments.answer(folder, first.id, action=ResponseAction.DECLINED, text="Non.", **kwargs)
    comments.answer(folder, first.id, action=ResponseAction.CHANGED, text=ANSWER, **kwargs)
    return folder, first.id


def test_follow_up(tmp_path: Path) -> None:
    folder, first = _consulted(tmp_path)
    try:
        state = comments.consultation_state(folder)
        path = comments.export_follow_up(folder)
        with pytest.raises(comments.UnknownStakeholderError):
            comments.record_comment(
                folder, "UNKNOWN", target=CommentTarget.OTHER, text="x",
                received_on=dt.date(2026, 10, 3), now=make_clock(), tool_version=TOOL_VERSION,
            )  # fmt: skip
        with pytest.raises(comments.UnknownCommentError):
            comments.answer(folder, "UNKNOWN", action=ResponseAction.NOTED, text="x",
                            now=make_clock(), tool_version=TOOL_VERSION)  # fmt: skip
    finally:
        folder.close()
    person = state.stakeholders[0]
    assert (person.name, person.role) == (NAME, "patiente partenaire")  # spaces tidied
    # oldest comment first (received on October 1st)
    assert [f.comment.target for f in state.follow_ups] == [
        CommentTarget.LAY_SUMMARY, CommentTarget.CRITERIA,
    ]  # fmt: skip
    answered = state.follow_ups[1]
    assert answered.comment.id == first
    assert answered.response is not None
    assert answered.response.action is ResponseAction.CHANGED
    assert answered.response.supersedes_id is not None
    assert [f.comment.id for f in state.pending] == [state.follow_ups[0].comment.id]
    assert (state.counts.comments, state.counts.answered) == (2, 1)
    rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))
    assert [(r["stakeholder"], r["role"], r["target"], r["action"]) for r in rows] == [
        ("PP1", "patiente partenaire", "lay_summary", ""),
        ("PP1", "patiente partenaire", "criteria", "changed"),
    ]  # fmt: skip
    assert rows[1]["comment"] == COMMENT
    assert rows[1]["response"] == ANSWER
    assert NAME not in path.read_text(encoding="utf-8")  # by code and role, not by name


def test_name_and_text_never_in_the_journal_nor_the_public_archive(tmp_path: Path) -> None:
    folder, _first = _consulted(tmp_path)
    try:
        public = archive_files(folder, ArchiveKind.PUBLIC, now=make_clock(),
                               tool_version=TOOL_VERSION)  # fmt: skip
    finally:
        folder.close()
    for name, content in public.items():
        for secret in (NAME, "Clinicien 1", COMMENT, ANSWER, "Trop long."):
            assert secret.encode() not in content, (name, secret)
    journal = public["donnees/journal.jsonl"].decode()
    assert journal.count(EntryType.STAKEHOLDER_ADDED) == 2
    assert journal.count(EntryType.STAKEHOLDER_COMMENT_RECORDED) == 2
    assert journal.count(EntryType.STAKEHOLDER_COMMENT_ANSWERED) == 2
    people = list(csv.DictReader(io.StringIO(public["donnees/parties-prenantes.csv"].decode())))
    assert [(p["stakeholder"], p["role"], p["organisation"]) for p in people] == [
        ("PP1", "patiente partenaire", "Org. A"), ("PP2", "clinicien", ""),
    ]  # fmt: skip
    follow = public["donnees/suivi-commentaires.csv"].decode()
    assert follow.splitlines()[0] == (
        "stakeholder,role,organisation,target,target_detail,received_on,action,answered_on"
    )
    assert ",criteria,P1,2026-10-02,changed," in follow
