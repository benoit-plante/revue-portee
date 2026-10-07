"""Protocol text and registration (EF-CAD-06, EF-CAD-08).

The free-text sections of the protocol are versioned: each change is a new immutable
version. Recording the DOI of the registered protocol (OSF) marks every criteria
version activated afterwards as a deviation from the protocol, to be reported.
"""

from collections.abc import Callable
from datetime import date, datetime

from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.domain.protocol import (
    ProtocolRegistration,
    ProtocolText,
    ProtocolTextVersion,
    normalize_doi,
)
from revue_portee.i18n import french
from revue_portee.i18n import gettext as _
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import criteria as criteria_repo
from revue_portee.storage.repositories import journal
from revue_portee.storage.repositories import protocol as protocol_repo

__all__ = [
    "InvalidDoiError",
    "InvalidRegistrationDateError",
    "current_protocol_text",
    "current_registration",
    "register_protocol",
    "save_protocol_text",
]

Clock = Callable[[], datetime]


class InvalidDoiError(ValueError):
    def __init__(self) -> None:
        super().__init__(
            _("Enter a DOI such as 10.17605/OSF.IO/ABCDE (with or without https://doi.org/).")
        )


class InvalidRegistrationDateError(ValueError):
    def __init__(self) -> None:
        super().__init__(_("The registration date cannot be in the future."))


def current_protocol_text(folder: ProjectFolder) -> ProtocolTextVersion | None:
    with folder.engine.connect() as connection:
        return protocol_repo.latest_text_version(connection)


def save_protocol_text(
    folder: ProjectFolder, text: ProtocolText, *, now: Clock, tool_version: str
) -> ProtocolTextVersion | None:
    """Store a new version of the free text, unless nothing changed.

    Returns the current version (``None`` if nothing was ever written).
    """
    with folder.write() as connection:
        latest = protocol_repo.latest_text_version(connection)
        if (latest is None and not text.sections) or (latest is not None and latest.text == text):
            return latest
        moment = now()
        version = ProtocolTextVersion(
            id=new_ulid(moment),
            number=1 if latest is None else latest.number + 1,
            created_at=moment,
            author_id=folder.reviewer_id,
            text=text,
        )
        previous = {} if latest is None else latest.text.sections
        changed = sorted(
            s.value
            for s in set(previous) | set(text.sections)
            if previous.get(s, "") != text.sections.get(s, "")
        )
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.PROTOCOL_TEXT_UPDATED,
            subject_type="protocol_text_version",
            subject_id=version.id,
            summary_fr=french("Protocol text updated (version {number})").format(
                number=version.number
            ),
            tool_version=tool_version,
            payload={
                "number": version.number,
                "changed_sections": list(changed),
                "sections": {s.value: t for s, t in text.sections.items()},
            },
        )
        protocol_repo.insert_text_version(connection, version, journal_entry_id=entry.id)
        return version


def current_registration(folder: ProjectFolder) -> ProtocolRegistration | None:
    with folder.engine.connect() as connection:
        return protocol_repo.latest_registration(connection)


def register_protocol(
    folder: ProjectFolder, doi: str, registered_on: date, *, now: Clock, tool_version: str
) -> ProtocolRegistration:
    """Record the DOI and date of the protocol registration (EF-CAD-08)."""
    try:
        normalized = normalize_doi(doi)
    except ValueError as error:
        raise InvalidDoiError from error
    moment = now()
    if registered_on > moment.date():
        raise InvalidRegistrationDateError
    with folder.write() as connection:
        active = criteria_repo.get_active_version(connection)
        registration = ProtocolRegistration(
            id=new_ulid(moment),
            doi=normalized,
            registered_on=registered_on,
            criteria_version_id=None if active is None else active.id,
            created_at=moment,
            reviewer_id=folder.reviewer_id,
        )
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.PROTOCOL_REGISTERED,
            subject_type="protocol_registration",
            subject_id=registration.id,
            summary_fr=french("Protocol registered: DOI {doi}").format(doi=normalized),
            tool_version=tool_version,
            payload={
                "doi": normalized,
                "registered_on": registered_on.isoformat(),
                "criteria_version_id": registration.criteria_version_id,
                "criteria_version_number": None if active is None else active.number,
            },
        )
        protocol_repo.insert_registration(connection, registration, journal_entry_id=entry.id)
        return registration
