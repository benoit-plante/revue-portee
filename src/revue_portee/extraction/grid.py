"""Use cases of the versioned extraction grid (EF-EXT-01, EF-EXT-02, tranche 3.1).

Every change is made to a draft, started from the version in force when needed, and
recorded in the journal with the field before and after. Activating the draft makes it
the version in force (a rationale is required from version 2 on); the previous version
is superseded and stays readable. A field code is given once and never reused, even if
its field only lived in a discarded draft. The qualification of the changes and their
impact on the values already extracted come with tranche 3.4 (EF-VER-06).
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from pydantic import JsonValue
from sqlalchemy import Connection

from revue_portee.domain import grid as dom
from revue_portee.domain.criteria import VersionStatus
from revue_portee.domain.grid import FieldType, GridDiff, GridField, GridVersion, next_field_code
from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.i18n import french
from revue_portee.i18n import gettext as _
from revue_portee.resources import grid_template
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import grid as repo
from revue_portee.storage.repositories import journal, projects

__all__ = [
    "GridState",
    "NoDraftError",
    "UnknownFieldError",
    "UnknownVersionError",
    "activate_draft",
    "add_field",
    "add_template",
    "diff",
    "discard_draft",
    "grid_state",
    "remove_field",
    "start_draft",
    "update_field",
    "version",
]

Clock = Callable[[], datetime]


class NoDraftError(LookupError):
    def __init__(self) -> None:
        super().__init__(_("There is no draft of the grid."))


class UnknownFieldError(LookupError):
    def __init__(self, code: str) -> None:
        super().__init__(_("Unknown field: {code}.").format(code=code))


class UnknownVersionError(LookupError):
    def __init__(self, number: int) -> None:
        super().__init__(_("Unknown grid version: {number}.").format(number=number))


@dataclass(frozen=True, slots=True)
class GridState:
    active: GridVersion | None
    draft: GridVersion | None
    versions: tuple[GridVersion, ...]  # every version that left draft, oldest first


def grid_state(folder: ProjectFolder) -> GridState:
    with folder.engine.connect() as connection:
        versions = repo.list_versions(connection)
    return GridState(
        active=next((v for v in versions if v.status is VersionStatus.ACTIVE), None),
        draft=next((v for v in versions if v.status is VersionStatus.DRAFT), None),
        versions=tuple(v for v in versions if v.status is not VersionStatus.DRAFT),
    )


def version(folder: ProjectFolder, number: int) -> GridVersion:
    with folder.engine.connect() as connection:
        found = repo.get_version_by_number(connection, number)
    if found is None:
        raise UnknownVersionError(number)
    return found


def diff(folder: ProjectFolder, from_number: int, to_number: int) -> GridDiff:
    return dom.diff_versions(version(folder, from_number), version(folder, to_number))


def _build(
    *,
    code: str,
    label: str,
    type: FieldType,
    definition: str,
    guidance: str,
    examples: Iterable[str],
    choices: Iterable[str],
) -> GridField:
    """One normalization for added and edited fields: trimmed text, no empty lines."""
    return GridField(
        code=code,
        label=" ".join(label.split()),
        type=type,
        definition=definition.strip(),
        guidance=guidance.strip(),
        examples=tuple(e.strip() for e in examples if e.strip()),
        choices=tuple(dict.fromkeys(c.strip() for c in choices if c.strip())),
    )


def _field_json(field: GridField) -> dict[str, JsonValue]:
    return field.model_dump(mode="json")


def _journal(
    connection: Connection,
    folder: ProjectFolder,
    moment: datetime,
    entry_type: str,
    summary_fr: str,
    subject: GridVersion,
    tool_version: str,
    payload: dict[str, JsonValue],
) -> str:
    entry = journal.append_entry(
        connection,
        now=moment,
        actor_reviewer_id=folder.reviewer_id,
        entry_type=entry_type,
        subject_type="grid_version",
        subject_id=subject.id,
        summary_fr=summary_fr,
        tool_version=tool_version,
        payload={"number": subject.number} | payload,
    )
    return entry.id


def _ensure_draft(
    connection: Connection, folder: ProjectFolder, moment: datetime, tool_version: str
) -> GridVersion:
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
        connection, folder, moment, EntryType.GRID_DRAFT_STARTED,
        french("Draft of grid version {number} started").format(number=draft.number),
        draft, tool_version, {"parent_id": draft.parent_id},
    )  # fmt: skip
    return draft


def start_draft(folder: ProjectFolder, *, now: Clock, tool_version: str) -> GridVersion:
    """The current draft, created from the version in force when needed."""
    with folder.write() as connection:
        return _ensure_draft(connection, folder, now(), tool_version)


def _save(
    connection: Connection,
    folder: ProjectFolder,
    moment: datetime,
    draft: GridVersion,
    fields: Iterable[GridField],
    summary_fr: str,
    tool_version: str,
    payload: dict[str, JsonValue],
) -> GridVersion:
    edited = dom.with_fields(draft, fields)
    repo.replace_draft_fields(connection, edited)
    _journal(
        connection, folder, moment, EntryType.GRID_DRAFT_EDITED, summary_fr, edited,
        tool_version, payload,
    )  # fmt: skip
    return edited


def _add(
    connection: Connection,
    folder: ProjectFolder,
    moment: datetime,
    new: Sequence[tuple[str, FieldType, str, str, Sequence[str], Sequence[str]]],
    tool_version: str,
    summary_fr: str,
) -> list[GridField]:
    draft = _ensure_draft(connection, folder, moment, tool_version)
    used = repo.used_codes(connection)
    added = []
    for label, type, definition, guidance, examples, choices in new:
        code = next_field_code(used)
        used.add(code)
        field = _build(
            code=code, label=label, type=type, definition=definition, guidance=guidance,
            examples=examples, choices=choices,
        )  # fmt: skip
        repo.register_code(connection, code, version_id=draft.id, now=moment)
        added.append(field)
    _save(
        connection, folder, moment, draft, [*draft.fields, *added], summary_fr, tool_version,
        {"action": "added", "fields": [_field_json(f) for f in added]},
    )  # fmt: skip
    return added


def add_field(
    folder: ProjectFolder,
    *,
    label: str,
    type: FieldType,
    definition: str = "",
    guidance: str = "",
    examples: Sequence[str] = (),
    choices: Sequence[str] = (),
    now: Clock,
    tool_version: str,
) -> GridField:
    """Add a field to the draft (created if needed), with the next free code."""
    with folder.write() as connection:
        moment = now()
        (field,) = _add(
            connection, folder, moment,
            [(label, type, definition, guidance, examples, choices)], tool_version,
            french("Field added to the grid draft: {label}").format(label=" ".join(label.split())),
        )  # fmt: skip
        return field


def add_template(folder: ProjectFolder, *, now: Clock, tool_version: str) -> list[GridField]:
    """Add the fields of the starting grid (JBI, Pollock et al., 2023) to the draft, in
    the language of the project; the team adapts them before activating the grid."""
    template = grid_template()
    with folder.engine.connect() as connection:
        language = projects.get_project(connection).language
    with folder.write() as connection:
        return _add(
            connection, folder, now(),
            [(label, type, definition, "", (), choices)
             for label, type, definition, choices in template.fields_in(language)],
            tool_version,
            french("Fields of the starting grid {template} added to the draft").format(
                template=template.id
            ),
        )  # fmt: skip


def update_field(
    folder: ProjectFolder,
    code: str,
    *,
    label: str,
    type: FieldType,
    definition: str = "",
    guidance: str = "",
    examples: Sequence[str] = (),
    choices: Sequence[str] = (),
    now: Clock,
    tool_version: str,
) -> GridField:
    """Change a field in the draft; its code never changes. An edit that changes
    nothing writes nothing."""
    with folder.write() as connection:
        moment = now()
        base = repo.get_draft_version(connection) or repo.get_active_version(connection)
        before = None if base is None else base.field(code)
        if before is None:
            raise UnknownFieldError(code)
        after = _build(
            code=code, label=label, type=type, definition=definition, guidance=guidance,
            examples=examples, choices=choices,
        )  # fmt: skip
        if after == before:
            return before
        draft = _ensure_draft(connection, folder, moment, tool_version)
        _save(
            connection, folder, moment, draft,
            [after if f.code == code else f for f in draft.fields],
            french("Field {code} modified in the grid draft").format(code=code), tool_version,
            {"action": "modified", "before": _field_json(before), "after": _field_json(after)},
        )  # fmt: skip
        return after


def remove_field(folder: ProjectFolder, code: str, *, now: Clock, tool_version: str) -> None:
    """Remove a field from the draft (it stays in every earlier version)."""
    with folder.write() as connection:
        moment = now()
        draft = _ensure_draft(connection, folder, moment, tool_version)
        removed = draft.field(code)
        if removed is None:
            raise UnknownFieldError(code)
        _save(
            connection, folder, moment, draft, [f for f in draft.fields if f.code != code],
            french("Field {code} removed from the grid draft").format(code=code), tool_version,
            {"action": "removed", "field": _field_json(removed)},
        )  # fmt: skip


def discard_draft(folder: ProjectFolder, *, now: Clock, tool_version: str) -> None:
    """Abandon the draft; the version in force stays."""
    with folder.write() as connection:
        draft = repo.get_draft_version(connection)
        if draft is None:
            raise NoDraftError
        repo.delete_draft(connection, draft)
        _journal(
            connection, folder, now(), EntryType.GRID_DRAFT_DISCARDED,
            french("Draft of grid version {number} discarded").format(number=draft.number),
            draft, tool_version, {"fields": [_field_json(f) for f in draft.fields]},
        )  # fmt: skip


def activate_draft(
    folder: ProjectFolder, *, rationale: str, now: Clock, tool_version: str
) -> GridVersion:
    """Make the draft the version in force; the previous version is superseded."""
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
                "added": [f.code for f in delta.added],
                "removed": [f.code for f in delta.removed],
                "modified": {m.code: list(m.changed) for m in delta.modified},
            }
        entry_id = _journal(
            connection, folder, moment, EntryType.GRID_VERSION_CREATED,
            french("Grid version {number} in force").format(number=activated.number),
            activated, tool_version,
            {
                "version_id": activated.id,
                "parent_id": activated.parent_id,
                "rationale": activated.rationale,
                "fields": [_field_json(f) for f in activated.sorted_fields()],
                "changes": changes,
            },
        )  # fmt: skip
        repo.update_version_status(connection, activated, journal_entry_id=entry_id)
        return activated
