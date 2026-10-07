"""Qualification of criteria changes (EF-VER-03).

While a draft differs from the version in force, the AI (task
``qualify_criterion_change``) may propose a type for each modified criterion. The
human confirms or corrects every type when activating the draft
(:func:`revue_portee.protocol.criteria.activate_draft`): no version comes into force
without it.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection

from revue_portee.ai.base import TaskResult
from revue_portee.ai.providers import ProviderFactory
from revue_portee.ai.tasks import (
    QUALIFY_CRITERION_CHANGE,
    CriterionSnapshot,
    QualifyChangeInput,
    QualifyChangeOutput,
)
from revue_portee.domain import criteria as dom
from revue_portee.domain.changes import (
    ChangeType,
    CriterionChange,
    QualificationError,
    QualificationProposal,
    qualify,
)
from revue_portee.domain.criteria import CriteriaDiff, CriteriaVersion, code_sort_key
from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.domain.project import ReviewerKind
from revue_portee.i18n import french
from revue_portee.i18n import gettext as _
from revue_portee.protocol import ai_assist
from revue_portee.protocol.ai_assist import CostPreview, call_summary, default_provider_factory
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import ai as ai_repo
from revue_portee.storage.repositories import criteria as criteria_repo
from revue_portee.storage.repositories import journal, projects
from revue_portee.storage.repositories import protocol as protocol_repo
from revue_portee.storage.repositories.ai import StoredCall

__all__ = [
    "MissingQualificationError",
    "NothingToQualifyError",
    "PendingQualification",
    "pending_qualification",
    "preview_proposals",
    "record_changes",
    "request_proposals",
    "version_changes",
]

Clock = Callable[[], datetime]


class MissingQualificationError(ValueError):
    def __init__(self, error: QualificationError) -> None:
        self.missing = error.missing
        self.invalid = error.invalid
        codes = ", ".join(error.missing + error.invalid)
        super().__init__(
            _(
                "Confirm the type of change (broadening, narrowing or clarification) "
                "of each modified criterion before activating: {codes}."
            ).format(codes=codes)
        )


class NothingToQualifyError(LookupError):
    def __init__(self) -> None:
        super().__init__(_("The draft has no modified criterion to qualify."))


@dataclass(frozen=True, slots=True)
class PendingQualification:
    """The changes of the draft compared with the version in force."""

    draft: CriteriaVersion
    active: CriteriaVersion
    diff: CriteriaDiff
    proposals: dict[str, QualificationProposal]  # by code, only those still applicable


def _pending(connection: Connection) -> PendingQualification | None:
    draft = criteria_repo.get_draft_version(connection)
    active = criteria_repo.get_active_version(connection)
    if draft is None or active is None:
        return None
    proposals = {
        code: proposal
        for code, proposal in ai_repo.latest_proposals(connection, draft.id).items()
        if proposal.applies_to(draft)
    }
    return PendingQualification(
        draft=draft, active=active, diff=dom.diff_versions(active, draft), proposals=proposals
    )


def pending_qualification(folder: ProjectFolder) -> PendingQualification | None:
    with folder.engine.connect() as connection:
        return _pending(connection)


def _inputs(connection: Connection) -> list[QualifyChangeInput]:
    pending = _pending(connection)
    if pending is None or not pending.diff.modified:
        raise NothingToQualifyError
    language = projects.get_project(connection).language
    return [
        QualifyChangeInput(
            item_id=m.code,
            language=language,
            code=m.code,
            pcc_element=m.after.pcc_element.value,
            before=CriterionSnapshot.of(m.before),
            after=CriterionSnapshot.of(m.after),
        )
        for m in pending.diff.modified
    ]


def preview_proposals(
    folder: ProjectFolder, *, factory: ProviderFactory = default_provider_factory
) -> CostPreview:
    with folder.engine.connect() as connection:
        inputs = _inputs(connection)
    return ai_assist.preview(folder, QUALIFY_CRITERION_CHANGE, inputs, factory=factory)


def request_proposals(
    folder: ProjectFolder,
    *,
    now: Clock,
    tool_version: str,
    factory: ProviderFactory = default_provider_factory,
) -> list[QualificationProposal]:
    """Ask the AI to qualify every modified criterion of the draft (one call each)."""
    with folder.engine.connect() as connection:
        inputs = _inputs(connection)
        pending = _pending(connection)
    assert pending is not None  # noqa: S101 - checked by _inputs
    draft = pending.draft
    received: list[QualificationProposal] = []

    def store(
        connection: Connection, stored: StoredCall, result: TaskResult[QualifyChangeOutput]
    ) -> None:
        moment = now()
        after = draft.criterion(result.item_id)
        assert after is not None  # noqa: S101 - the input came from the draft
        proposal = QualificationProposal(
            id=new_ulid(moment),
            draft_version_id=draft.id,
            code=result.item_id,
            ai_call_id=stored.id,
            change_type=ChangeType(result.output.change_type),
            confidence=result.output.confidence,
            rationale=result.output.rationale.strip(),
            after=after,
            created_at=moment,
        )
        ai_repo.insert_proposal(connection, proposal)
        journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.CRITERIA_CHANGE_PROPOSED,
            subject_type="qualification_proposal",
            subject_id=proposal.id,
            summary_fr=french("AI proposes to qualify the change of {code}: {type}").format(
                code=proposal.code, type=proposal.change_type.value
            ),
            tool_version=tool_version,
            payload=call_summary(stored)
            | {
                "draft_version_id": draft.id,
                "code": proposal.code,
                "change_type": proposal.change_type.value,
                "confidence": proposal.confidence,
                "rationale": proposal.rationale,
            },
        )
        received.append(proposal)

    ai_assist.run_and_record(
        folder,
        QUALIFY_CRITERION_CHANGE,
        inputs,
        on_result=store,
        now=now,
        tool_version=tool_version,
        factory=factory,
    )
    return received


def record_changes(
    connection: Connection,
    folder: ProjectFolder,
    *,
    previous: CriteriaVersion,
    draft: CriteriaVersion,
    choices: Mapping[str, ChangeType],
    moment: datetime,
    tool_version: str,
) -> list[CriterionChange]:
    """Check and store the confirmed qualification of every change of ``draft``
    (within the activation transaction). Raises :class:`MissingQualificationError`."""
    try:
        qualified = qualify(dom.diff_versions(previous, draft), choices)
    except QualificationError as error:
        raise MissingQualificationError(error) from error
    proposals = {
        code: p
        for code, p in ai_repo.latest_proposals(connection, draft.id).items()
        if p.applies_to(draft)
    }
    changes: list[CriterionChange] = []
    for code, change_type in qualified:
        proposal = proposals.get(code)
        by_ai = proposal is not None and proposal.change_type is change_type
        change = CriterionChange(
            id=new_ulid(moment),
            from_version_id=previous.id,
            to_version_id=draft.id,
            code=code,
            change_type=change_type,
            proposed_by=ReviewerKind.AI if by_ai else ReviewerKind.HUMAN,
            proposal_id=None if proposal is None else proposal.id,
            confirmed_by=folder.reviewer_id,
            created_at=moment,
        )
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.CRITERIA_CHANGE_QUALIFIED,
            subject_type="criterion_change",
            subject_id=change.id,
            summary_fr=french("Change of {code} qualified: {type}").format(
                code=code, type=change_type.value
            ),
            tool_version=tool_version,
            payload={
                "from_version_id": previous.id,
                "to_version_id": draft.id,
                "code": code,
                "change_type": change_type.value,
                "proposed_by": change.proposed_by.value,
                "proposal_id": change.proposal_id,
                "ai_proposed_type": None if proposal is None else proposal.change_type.value,
            },
        )
        protocol_repo.insert_change(connection, change, journal_entry_id=entry.id)
        changes.append(change)
    return changes


def version_changes(folder: ProjectFolder, version_id: str) -> list[CriterionChange]:
    """Confirmed qualifications of the changes that produced a version."""
    with folder.engine.connect() as connection:
        changes = protocol_repo.list_changes(connection, to_version_id=version_id)
    return sorted(changes, key=lambda change: code_sort_key(change.code))
