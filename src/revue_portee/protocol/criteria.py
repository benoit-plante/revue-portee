"""Edit criteria through drafts and versions (EF-CAD-03 to 05, EF-VER-01, EF-VER-02).

Changing a criterion never touches the version in force: the change goes into a draft
(created on demand from the active version), and activating the draft creates the
next version. Every action is recorded in the journal, in the same transaction.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime

from pydantic import JsonValue
from sqlalchemy import Connection

from revue_portee.domain import criteria as dom
from revue_portee.domain.criteria import (
    CriteriaDiff,
    CriteriaVersion,
    Criterion,
    CriterionKind,
    PccElement,
)
from revue_portee.domain.ids import new_ulid, next_criterion_code
from revue_portee.domain.journal import EntryType
from revue_portee.i18n import french
from revue_portee.i18n import gettext as _
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import criteria as repo
from revue_portee.storage.repositories import journal

__all__ = [
    "CriteriaState",
    "NoDraftError",
    "UnknownCriterionError",
    "UnknownVersionError",
    "activate_draft",
    "add_criterion",
    "criteria_state",
    "diff",
    "discard_draft",
    "remove_criterion",
    "start_draft",
    "update_criterion",
    "version",
]

Clock = Callable[[], datetime]


class NoDraftError(LookupError):
    def __init__(self) -> None:
        super().__init__(_("There is no draft of the criteria."))


class UnknownCriterionError(LookupError):
    def __init__(self, code: str) -> None:
        super().__init__(_("Unknown criterion: {code}.").format(code=code))


class UnknownVersionError(LookupError):
    def __init__(self, number: int) -> None:
        super().__init__(_("Unknown criteria version: {number}.").format(number=number))


@dataclass(frozen=True, slots=True)
class CriteriaState:
    active: CriteriaVersion | None
    draft: CriteriaVersion | None
    versions: tuple[CriteriaVersion, ...]  # every version that left draft, oldest first


def criteria_state(folder: ProjectFolder) -> CriteriaState:
    with folder.engine.connect() as connection:
        versions = repo.list_versions(connection)
    return CriteriaState(
        active=next((v for v in versions if v.status is dom.VersionStatus.ACTIVE), None),
        draft=next((v for v in versions if v.status is dom.VersionStatus.DRAFT), None),
        versions=tuple(v for v in versions if v.status is not dom.VersionStatus.DRAFT),
    )


def version(folder: ProjectFolder, number: int) -> CriteriaVersion:
    with folder.engine.connect() as connection:
        found = repo.get_version_by_number(connection, number)
    if found is None:
        raise UnknownVersionError(number)
    return found


def diff(folder: ProjectFolder, from_number: int, to_number: int) -> CriteriaDiff:
    return dom.diff_versions(version(folder, from_number), version(folder, to_number))


def _build_criterion(
    *,
    code: str,
    pcc_element: PccElement,
    kind: CriterionKind,
    text: str,
    guidance: str,
    examples: Iterable[str],
    counterexamples: Iterable[str],
) -> Criterion:
    """One normalization for added and edited criteria: trimmed text, no empty lines."""
    return Criterion(
        code=code,
        pcc_element=pcc_element,
        kind=kind,
        text=text.strip(),
        guidance=guidance.strip(),
        examples=tuple(e.strip() for e in examples if e.strip()),
        counterexamples=tuple(e.strip() for e in counterexamples if e.strip()),
    )


def _criterion_json(criterion: Criterion) -> dict[str, JsonValue]:
    return criterion.model_dump(mode="json")


def _journal(
    connection: Connection,
    folder: ProjectFolder,
    moment: datetime,
    entry_type: str,
    summary_fr: str,
    subject: CriteriaVersion,
    tool_version: str,
    payload: dict[str, JsonValue],
) -> str:
    entry = journal.append_entry(
        connection,
        now=moment,
        actor_reviewer_id=folder.reviewer_id,
        entry_type=entry_type,
        subject_type="criteria_version",
        subject_id=subject.id,
        summary_fr=summary_fr,
        tool_version=tool_version,
        payload={"number": subject.number} | payload,
    )
    return entry.id


def _ensure_draft(
    connection: Connection, folder: ProjectFolder, moment: datetime, tool_version: str
) -> CriteriaVersion:
    draft = repo.get_draft_version(connection)
    if draft is not None:
        return draft
    active = repo.get_active_version(connection)
    if active is None:
        draft = dom.first_draft(
            version_id=new_ulid(moment), author_id=folder.reviewer_id, now=moment
        )
    else:
        draft = dom.new_draft_from(
            active, version_id=new_ulid(moment), author_id=folder.reviewer_id, now=moment
        )
    repo.insert_version(connection, draft)
    _journal(
        connection,
        folder,
        moment,
        EntryType.CRITERIA_DRAFT_STARTED,
        french("Draft of criteria version {number} started").format(number=draft.number),
        draft,
        tool_version,
        {"parent_id": draft.parent_id},
    )
    return draft


def start_draft(folder: ProjectFolder, *, now: Clock, tool_version: str) -> CriteriaVersion:
    """Return the current draft, creating it from the active version if needed."""
    with folder.write() as connection:
        return _ensure_draft(connection, folder, now(), tool_version)


def _save_draft(
    connection: Connection,
    folder: ProjectFolder,
    moment: datetime,
    draft: CriteriaVersion,
    criteria: Iterable[Criterion],
    summary_fr: str,
    tool_version: str,
    payload: dict[str, JsonValue],
) -> CriteriaVersion:
    edited = dom.with_criteria(draft, criteria)
    repo.replace_draft_criteria(connection, edited)
    _journal(
        connection,
        folder,
        moment,
        EntryType.CRITERIA_DRAFT_EDITED,
        summary_fr,
        edited,
        tool_version,
        payload,
    )
    return edited


def add_criterion(
    folder: ProjectFolder,
    *,
    pcc_element: PccElement,
    kind: CriterionKind,
    text: str,
    guidance: str = "",
    examples: Iterable[str] = (),
    counterexamples: Iterable[str] = (),
    now: Clock,
    tool_version: str,
) -> Criterion:
    """Add a criterion to the draft (created if needed), with the next free code."""
    with folder.write() as connection:
        moment = now()
        draft = _ensure_draft(connection, folder, moment, tool_version)
        code = next_criterion_code(pcc_element, repo.used_codes(connection))
        criterion = _build_criterion(
            code=code,
            pcc_element=pcc_element,
            kind=kind,
            text=text,
            guidance=guidance,
            examples=examples,
            counterexamples=counterexamples,
        )
        repo.register_code(connection, criterion, version_id=draft.id, now=moment)
        _save_draft(
            connection,
            folder,
            moment,
            draft,
            [*draft.criteria, criterion],
            french("Criterion {code} added to the draft").format(code=code),
            tool_version,
            {"action": "added", "criterion": _criterion_json(criterion)},
        )
        return criterion


def update_criterion(
    folder: ProjectFolder,
    code: str,
    *,
    kind: CriterionKind,
    text: str,
    guidance: str = "",
    examples: Iterable[str] = (),
    counterexamples: Iterable[str] = (),
    now: Clock,
    tool_version: str,
) -> Criterion:
    """Change a criterion in the draft. Its code and PCC element never change.

    An edit that changes nothing writes nothing: no draft is started for it.
    """
    with folder.write() as connection:
        moment = now()
        base = repo.get_draft_version(connection) or repo.get_active_version(connection)
        before = None if base is None else base.criterion(code)
        if before is None:
            raise UnknownCriterionError(code)
        after = _build_criterion(
            code=code,
            pcc_element=before.pcc_element,
            kind=kind,
            text=text,
            guidance=guidance,
            examples=examples,
            counterexamples=counterexamples,
        )
        if after == before:
            return before
        draft = _ensure_draft(connection, folder, moment, tool_version)
        _save_draft(
            connection,
            folder,
            moment,
            draft,
            [after if c.code == code else c for c in draft.criteria],
            french("Criterion {code} modified in the draft").format(code=code),
            tool_version,
            {
                "action": "modified",
                "before": _criterion_json(before),
                "after": _criterion_json(after),
            },
        )
        return after


def remove_criterion(folder: ProjectFolder, code: str, *, now: Clock, tool_version: str) -> None:
    """Remove a criterion from the draft (it stays in every earlier version)."""
    with folder.write() as connection:
        moment = now()
        draft = _ensure_draft(connection, folder, moment, tool_version)
        removed = draft.criterion(code)
        if removed is None:
            raise UnknownCriterionError(code)
        _save_draft(
            connection,
            folder,
            moment,
            draft,
            [c for c in draft.criteria if c.code != code],
            french("Criterion {code} removed from the draft").format(code=code),
            tool_version,
            {"action": "removed", "criterion": _criterion_json(removed)},
        )


def discard_draft(folder: ProjectFolder, *, now: Clock, tool_version: str) -> None:
    """Abandon the draft; the active version stays in force."""
    with folder.write() as connection:
        draft = repo.get_draft_version(connection)
        if draft is None:
            raise NoDraftError
        repo.delete_draft(connection, draft)
        _journal(
            connection,
            folder,
            now(),
            EntryType.CRITERIA_DRAFT_DISCARDED,
            french("Draft of criteria version {number} discarded").format(number=draft.number),
            draft,
            tool_version,
            {"criteria": [_criterion_json(c) for c in draft.criteria]},
        )


def activate_draft(
    folder: ProjectFolder, *, rationale: str, now: Clock, tool_version: str
) -> CriteriaVersion:
    """Make the draft the version in force; the previous active version is superseded."""
    with folder.write() as connection:
        moment = now()
        draft = repo.get_draft_version(connection)
        if draft is None:
            raise NoDraftError
        activated = dom.activate(draft, rationale=rationale, now=moment)
        previous = repo.get_active_version(connection)
        changes: dict[str, JsonValue] = {}
        if previous is not None:
            repo.update_version_status(connection, dom.supersede(previous))
            delta = dom.diff_versions(previous, activated)
            changes = {
                "added": [c.code for c in delta.added],
                "removed": [c.code for c in delta.removed],
                "modified": [m.code for m in delta.modified],
            }
        entry_id = _journal(
            connection,
            folder,
            moment,
            EntryType.CRITERIA_VERSION_CREATED,
            french("Criteria version {number} in force").format(number=activated.number),
            activated,
            tool_version,
            {
                "version_id": activated.id,
                "parent_id": activated.parent_id,
                "rationale": activated.rationale,
                "criteria": [_criterion_json(c) for c in activated.sorted_criteria()],
                "changes": changes,
            },
        )
        repo.update_version_status(connection, activated, journal_entry_id=entry_id)
        return activated
