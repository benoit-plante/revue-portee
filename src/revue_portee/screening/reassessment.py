"""Impact of a criteria change on the main screening, and reassessment (EF-VER-04, 05, 07).

When a new criteria version is activated during the main screening, the references it
touches are found from the current state (``domain.impact``). They form a reassessment
round with the new version: the AI screens them again (``screening.batch_ai``), and the
human verifies only those whose decision would change (one keeps, the other excludes).
Old decisions are never changed: the human's verification is a new decision that
supersedes the previous one. The journal records, for each change, the versions, its
type, the justification of the version, the number of references touched, and the
result of the reassessment.
"""

import secrets
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import JsonValue

from revue_portee.domain.criteria import CriteriaVersion, VersionStatus
from revue_portee.domain.ids import new_ulid
from revue_portee.domain.impact import (
    ImpactAssessment,
    ReferenceState,
    assess_impact,
    reassessment_set,
)
from revue_portee.domain.journal import EntryType
from revue_portee.domain.screening import (
    Decision,
    DecisionContext,
    DecisionValue,
    ReviewerKind,
    RoundKind,
    ScreeningRound,
    keeps,
)
from revue_portee.i18n import french
from revue_portee.i18n import gettext as _
from revue_portee.protocol.qualification import version_changes
from revue_portee.screening import main
from revue_portee.screening.batch_ai import pending_batches, waiting_for_ai
from revue_portee.screening.pilot import UnknownCriterionError, UnknownRoundError
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import criteria as criteria_repo
from revue_portee.storage.repositories import journal
from revue_portee.storage.repositories import screening as screening_repo

__all__ = [
    "NotAChangeError",
    "NothingToAssessError",
    "ReassessmentNotFinishedError",
    "ReassessmentState",
    "assess",
    "complete",
    "impacts",
    "next_version_to_assess",
    "reassessment_state",
    "verify",
]

Clock = Callable[[], datetime]


class NothingToAssessError(LookupError):
    def __init__(self) -> None:
        super().__init__(_("No new criteria version waits for its impact analysis."))


class NotAChangeError(ValueError):
    def __init__(self) -> None:
        super().__init__(
            _("The AI does not change the decision on this reference: nothing to verify.")
        )


class ReassessmentNotFinishedError(ValueError):
    def __init__(self) -> None:
        super().__init__(
            _("The reassessment is not finished: the AI or you still have references to decide.")
        )


def impacts(folder: ProjectFolder, main_round_id: str) -> list[ImpactAssessment]:
    with folder.engine.connect() as connection:
        return screening_repo.list_impacts(connection, main_round_id)


def next_version_to_assess(folder: ProjectFolder, main_round_id: str) -> CriteriaVersion | None:
    """The oldest version activated after the one the main screening started with, and
    not yet assessed: versions are assessed one after the other."""
    screening = main.get_main_round(folder, main_round_id)
    with folder.engine.connect() as connection:
        start = criteria_repo.get_version(connection, screening.criteria_version_id)
        assessed = {i.to_version_id for i in screening_repo.list_impacts(connection, screening.id)}
        versions = criteria_repo.list_versions(connection)
    assert start is not None  # noqa: S101 - a round always points to a version
    candidates = [
        v
        for v in versions
        if v.number > start.number and v.status is not VersionStatus.DRAFT and v.id not in assessed
    ]
    return min(candidates, key=lambda v: v.number) if candidates else None


def _states(state: main.MainState) -> dict[str, ReferenceState]:
    return {
        ref: ReferenceState(reference_id=ref, value=d.value, criteria_cited=d.criteria_cited)
        for ref, d in state.final.items()
        if ref in set(state.members)
    }


def assess(
    folder: ProjectFolder,
    main_round_id: str,
    *,
    seed: int | None = None,
    sample_clarifications: bool = True,
    now: Clock,
    tool_version: str,
) -> ImpactAssessment:
    """Impact analysis of the next version to assess, and the reassessment round of the
    references it touches (a sample of those touched by clarifications only)."""
    version = next_version_to_assess(folder, main_round_id)
    if version is None:
        raise NothingToAssessError
    changes = version_changes(folder, version.id)
    state = main.main_state(folder, main_round_id)
    impact = assess_impact([(c.code, c.change_type) for c in changes], _states(state))
    drawn_seed = secrets.randbelow(2**31) if seed is None else seed
    targets = reassessment_set(impact, seed=drawn_seed, sample_clarifications=sample_clarifications)
    from_version_id = changes[0].from_version_id if changes else str(version.parent_id)
    with folder.write() as connection:
        moment = now()
        from_version = criteria_repo.get_version(connection, from_version_id)
        assert from_version is not None  # noqa: S101 - a change points to its versions
        number = (
            len(
                screening_repo.list_screening_rounds(connection, main.STAGE, RoundKind.REASSESSMENT)
            )
            + 1
        )
        reassessment: ScreeningRound | None = None
        if targets:
            reassessment = ScreeningRound(
                id=new_ulid(moment),
                number=number,
                stage=main.STAGE,
                kind=RoundKind.REASSESSMENT,
                criteria_version_id=version.id,
                seed=drawn_seed,
                sample_size=len(targets),
                created_at=moment,
                reviewer_id=folder.reviewer_id,
            )
        assessment = ImpactAssessment(
            id=new_ulid(moment),
            from_version_id=from_version.id,
            to_version_id=version.id,
            main_round_id=state.round.id,
            impact=impact,
            reassessment_round_id=None if reassessment is None else reassessment.id,
            seed=drawn_seed,
            sampled=sample_clarifications,
            created_at=moment,
            reviewer_id=folder.reviewer_id,
        )
        per_change: list[JsonValue] = [
            {
                "code": c.code,
                "change_type": c.change_type.value,
                "touched": len(c.reference_ids),
                "reassessed": len(set(c.reference_ids) & set(targets)),
            }
            for c in impact.changes
        ]
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.IMPACT_ASSESSED,
            subject_type="impact_assessment",
            subject_id=assessment.id,
            summary_fr=french(
                "Impact of criteria version {to} (from version {source}): references "
                "touched: {touched}; to reassess: {reassessed}"
            ).format(
                to=version.number,
                source=from_version.number,
                touched=len(impact.touched),
                reassessed=len(targets),
            ),
            tool_version=tool_version,
            payload={
                "from_version": from_version.number,
                "to_version": version.number,
                "justification": version.rationale,
                "changes": per_change,
                "touched": len(impact.touched),
                "reassessed": len(targets),
                "seed": drawn_seed,
                "clarifications_sampled": sample_clarifications,
            },
        )
        if reassessment is not None:
            started = journal.append_entry(
                connection,
                now=moment,
                actor_reviewer_id=folder.reviewer_id,
                entry_type=EntryType.REASSESSMENT_STARTED,
                subject_type="screening_round",
                subject_id=reassessment.id,
                summary_fr=french(
                    "Reassessment {number} started: {count} references with criteria version "
                    "{version}"
                ).format(number=number, count=len(targets), version=version.number),
                tool_version=tool_version,
                payload={"impact": assessment.id, "references": len(targets)},
            )
            screening_repo.insert_screening_round(
                connection, reassessment, targets, journal_entry_id=started.id
            )
        screening_repo.insert_impact(connection, assessment, journal_entry_id=entry.id)
    return assessment


# --- Reassessment -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReassessmentState:
    assessment: ImpactAssessment
    round: ScreeningRound
    members: list[str]
    previous: dict[str, Decision]  # the final human decision before the reassessment
    ai: dict[str, Decision]
    verified: dict[str, Decision]
    changed: list[str] = field(default_factory=list)  # the AI would change the decision
    queue: list[str] = field(default_factory=list)  # changes not verified yet
    ai_waiting: int = 0  # references the AI has still to screen
    ai_running: int = 0  # batches still running
    completed: bool = False


def _get(folder: ProjectFolder, impact_id: str) -> tuple[ImpactAssessment, ScreeningRound]:
    with folder.engine.connect() as connection:
        found = screening_repo.get_impact(connection, impact_id)
        if found is None or found.reassessment_round_id is None:
            raise UnknownRoundError
        screening = screening_repo.get_screening_round(connection, found.reassessment_round_id)
    assert screening is not None  # noqa: S101 - the round was recorded with the impact
    return found, screening


def _completed(folder: ProjectFolder, impact_id: str) -> bool:
    with folder.engine.connect() as connection:
        return any(
            e.entry_type == EntryType.REASSESSMENT_COMPLETED and e.subject_id == impact_id
            for e in journal.list_entries(connection)
        )


def reassessment_state(folder: ProjectFolder, impact_id: str) -> ReassessmentState:
    assessment, screening = _get(folder, impact_id)
    with folder.engine.connect() as connection:
        main_round = screening_repo.get_screening_round(connection, assessment.main_round_id)
        assert main_round is not None  # noqa: S101
        earlier = [
            i.reassessment_round_id
            for i in screening_repo.list_impacts(connection, assessment.main_round_id)
            if i.reassessment_round_id is not None
            and i.reassessment_round_id != screening.id
            and i.created_at <= assessment.created_at
        ]
        members = screening_repo.member_ids(connection, screening.id)
        previous_all = screening_repo.latest_by_reference(
            connection, [*main.decided_in(connection, main_round), *earlier], reviewer_kind="human"
        )
        ai = screening_repo.latest_by_reference(connection, [screening.id], reviewer_kind="ai")
        verified = screening_repo.latest_by_reference(
            connection, [screening.id], reviewer_kind="human"
        )
    previous = {ref: previous_all[ref] for ref in members if ref in previous_all}
    changed = [
        ref
        for ref in members
        if ref in ai and ref in previous and keeps(ai[ref].value) != keeps(previous[ref].value)
    ]
    return ReassessmentState(
        assessment=assessment,
        round=screening,
        members=members,
        previous=previous,
        ai=ai,
        verified=verified,
        changed=changed,
        queue=[ref for ref in changed if ref not in verified],
        ai_waiting=len(waiting_for_ai(folder, screening.id)),
        ai_running=len(pending_batches(folder, screening.id)),
        completed=_completed(folder, impact_id),
    )


def verify(
    folder: ProjectFolder,
    impact_id: str,
    reference_id: str,
    value: DecisionValue,
    *,
    criteria_cited: Sequence[str] = (),
    rationale: str = "",
    now: Clock,
    tool_version: str,
) -> Decision:
    """The human's decision on a reference whose decision the AI would change, with the
    new criteria version; it supersedes the previous final decision (EF-VER-05)."""
    state = reassessment_state(folder, impact_id)
    if reference_id not in state.changed:
        raise NotAChangeError
    with folder.engine.connect() as connection:
        version = criteria_repo.get_version(connection, state.round.criteria_version_id)
    assert version is not None  # noqa: S101
    unknown = sorted(set(criteria_cited) - {c.code for c in version.criteria})
    if unknown:
        raise UnknownCriterionError(unknown)
    previous = state.previous[reference_id]
    with folder.write() as connection:
        moment = now()
        decision = Decision(
            id=new_ulid(moment),
            reference_id=reference_id,
            stage=main.STAGE,
            round_id=state.round.id,
            reviewer_id=folder.reviewer_id,
            reviewer_kind=ReviewerKind.HUMAN,
            value=value,
            rationale=rationale.strip(),
            criteria_cited=tuple(sorted(set(criteria_cited))),
            criteria_version_id=version.id,
            context=DecisionContext.REASSESSMENT,
            supersedes_decision_id=previous.id,
            tool_version=tool_version,
            created_at=moment,
        )
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.REASSESSMENT_DECIDED,
            subject_type="decision",
            subject_id=decision.id,
            summary_fr=french(
                "Reassessment {number}: decision verified (before: {before}, AI: {ai}, "
                "final: {final})"
            ).format(
                number=state.round.number,
                before=previous.value.value,
                ai=state.ai[reference_id].value.value,
                final=value.value,
            ),
            tool_version=tool_version,
            payload={
                "impact": impact_id,
                "reference": reference_id,
                "previous_decision": previous.id,
                "ai_decision": state.ai[reference_id].id,
                "previous_value": previous.value.value,
                "ai_value": state.ai[reference_id].value.value,
                "value": value.value,
                "criteria_cited": list(decision.criteria_cited),
            },
        )
        screening_repo.insert_decision(connection, decision, journal_entry_id=entry.id)
    return decision


def complete(
    folder: ProjectFolder, impact_id: str, *, now: Clock, tool_version: str
) -> dict[str, JsonValue]:
    """Record the result of the reassessment, for each change and in all (EF-VER-07)."""
    state = reassessment_state(folder, impact_id)
    if state.queue or state.ai_running or state.ai_waiting:
        raise ReassessmentNotFinishedError
    members = set(state.members)

    def result(refs: Sequence[str]) -> dict[str, JsonValue]:
        chosen = set(refs) & members
        changed = [r for r in chosen if r in state.verified]
        reversed_ = [
            r for r in changed if keeps(state.verified[r].value) != keeps(state.previous[r].value)
        ]
        return {
            "reassessed": len(chosen),
            "screened_by_ai": len(chosen & state.ai.keys()),
            "ai_changes": len(set(state.changed) & chosen),
            "decisions_changed": len(reversed_),
            "confirmed": len(chosen & state.ai.keys()) - len(reversed_),
        }

    changes: list[JsonValue] = [
        dict[str, JsonValue]({"code": c.code, "change_type": c.change_type.value})
        | result(c.reference_ids)
        for c in state.assessment.impact.changes
    ]
    total = result(state.members)
    with folder.write() as connection:
        journal.append_entry(
            connection,
            now=now(),
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.REASSESSMENT_COMPLETED,
            subject_type="impact_assessment",
            subject_id=impact_id,
            summary_fr=french(
                "Reassessment {number} completed: references reassessed: {reassessed}; "
                "decisions changed: {changed}"
            ).format(
                number=state.round.number,
                reassessed=total["reassessed"],
                changed=total["decisions_changed"],
            ),
            tool_version=tool_version,
            payload={"changes": changes, "total": total},
        )
    return total
