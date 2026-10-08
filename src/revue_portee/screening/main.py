"""Main title and abstract screening and reconciliation (EF-SEL-08, EF-SEL-10, EF-SEL-12).

The human reviewer screens every reference after deduplication, in an order drawn at
random with a recorded seed; the AI screens them independently (``screening.main_ai``).
The human does not see the AI's decision while screening: the references where the two
disagree (one keeps the reference, the other excludes it) form the reconciliation queue,
where the AI's rationale is shown and the human takes the final decision.

Decisions of a pilot round taken with the same criteria version count for the main
screening (D-078): those references are not screened again by the human.
"""

import secrets
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import JsonValue
from sqlalchemy import Connection

from revue_portee.domain.criteria import CriteriaVersion
from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.domain.screening import (
    Decision,
    DecisionContext,
    DecisionValue,
    ReviewerKind,
    RoundKind,
    ScreeningRound,
    Stage,
    disagree,
    draw_sample,
)
from revue_portee.i18n import french
from revue_portee.i18n import gettext as _
from revue_portee.screening.pilot import (
    NoReferencesError,
    NotInRoundError,
    UnknownCriterionError,
    UnknownRoundError,
    active_criteria,
    screenable_references,
)
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import journal
from revue_portee.storage.repositories import screening as screening_repo

__all__ = [
    "STAGE",
    "MainRoundExistsError",
    "MainState",
    "NotADisagreementError",
    "add_new_references",
    "decided_in",
    "get_main_round",
    "main_round",
    "main_state",
    "next_reference",
    "progress",
    "reconcile",
    "record_decision",
    "start_main",
]

Clock = Callable[[], datetime]
STAGE = Stage.TITLE_ABSTRACT
HUMAN = ReviewerKind.HUMAN.value
AI = ReviewerKind.AI.value


class MainRoundExistsError(ValueError):
    def __init__(self) -> None:
        super().__init__(_("The main screening has already started."))


class NotADisagreementError(ValueError):
    def __init__(self) -> None:
        super().__init__(
            _("This reference is not a disagreement between you and the AI: nothing to reconcile.")
        )


# --- The round ----------------------------------------------------------------------


def main_round(folder: ProjectFolder) -> ScreeningRound | None:
    """The main title and abstract screening, once started (there is one)."""
    with folder.engine.connect() as connection:
        rounds = screening_repo.list_screening_rounds(connection, STAGE, RoundKind.MAIN)
    return rounds[-1] if rounds else None


def get_main_round(folder: ProjectFolder, round_id: str) -> ScreeningRound:
    with folder.engine.connect() as connection:
        found = screening_repo.get_screening_round(connection, round_id)
    if found is None or found.kind is not RoundKind.MAIN:
        raise UnknownRoundError
    return found


def _carried(connection: Connection, main: ScreeningRound) -> list[str]:
    """Pilot rounds whose human decisions count for the main screening."""
    return [
        pilot.id
        for pilot in screening_repo.list_rounds(connection, STAGE)
        if pilot.criteria_version_id == main.criteria_version_id
    ]


def decided_in(connection: Connection, main: ScreeningRound) -> list[str]:
    """Rounds whose independent human decisions count for the main screening."""
    return [main.id, *_carried(connection, main)]


def start_main(
    folder: ProjectFolder, *, seed: int | None = None, now: Clock, tool_version: str
) -> ScreeningRound:
    """Start the main screening of every reference after deduplication, in an order
    drawn with ``seed`` (drawn at random and recorded when not given)."""
    if main_round(folder) is not None:
        raise MainRoundExistsError
    version = active_criteria(folder)
    population = screenable_references(folder)
    if not population:
        raise NoReferencesError
    drawn_seed = secrets.randbelow(2**31) if seed is None else seed
    order = draw_sample(population, len(population), drawn_seed)
    with folder.write() as connection:
        moment = now()
        main = ScreeningRound(
            id=new_ulid(moment),
            number=1,
            stage=STAGE,
            kind=RoundKind.MAIN,
            criteria_version_id=version.id,
            seed=drawn_seed,
            sample_size=len(order),
            created_at=moment,
            reviewer_id=folder.reviewer_id,
        )
        carried = _carried(connection, main)
        carried_decisions = len(
            screening_repo.latest_by_reference(
                connection, carried, reviewer_kind=HUMAN, contexts=["independent"]
            )
        )
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.SCREENING_STARTED,
            subject_type="screening_round",
            subject_id=main.id,
            summary_fr=french(
                "Main screening started: {count} references in an order drawn with the seed "
                "{seed}; decisions of the pilot kept: {carried}"
            ).format(count=len(order), seed=drawn_seed, carried=carried_decisions),
            tool_version=tool_version,
            payload={
                "references": len(order),
                "seed": drawn_seed,
                "criteria_version": version.number,
                "pilot_rounds_kept": list[JsonValue](carried),
                "pilot_decisions_kept": carried_decisions,
            },
        )
        screening_repo.insert_screening_round(connection, main, order, journal_entry_id=entry.id)
    return main


def add_new_references(
    folder: ProjectFolder, round_id: str, *, now: Clock, tool_version: str
) -> int:
    """Add at the end of the main screening the references found since it started (a
    later collection or import), in an order drawn with a recorded seed."""
    main = get_main_round(folder, round_id)
    with folder.engine.connect() as connection:
        members = set(screening_repo.member_ids(connection, main.id))
    new = [ref for ref in screenable_references(folder) if ref not in members]
    if not new:
        return 0
    seed = main.seed + len(members)
    order = draw_sample(new, len(new), seed)
    with folder.write() as connection:
        journal.append_entry(
            connection,
            now=now(),
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.SCREENING_MEMBERS_ADDED,
            subject_type="screening_round",
            subject_id=main.id,
            summary_fr=french("Main screening: {count} new references added").format(
                count=len(order)
            ),
            tool_version=tool_version,
            payload={"references": len(order), "seed": seed},
        )
        screening_repo.append_members(connection, main.id, order)
    return len(order)


# --- Human screening ----------------------------------------------------------------


def next_reference(
    folder: ProjectFolder, round_id: str, *, priority: bool = False, skip: Sequence[str] = ()
) -> str | None:
    """The next reference to screen: in the drawn order, or, with ``priority``, those
    the AI finds most likely to be included first (EF-SEL-10)."""
    main = get_main_round(folder, round_id)
    with folder.engine.connect() as connection:
        return screening_repo.next_to_screen(
            connection,
            main.id,
            decided_in=decided_in(connection, main),
            priority=priority,
            skip=skip,
        )


def _checked_codes(version: CriteriaVersion, cited: Sequence[str]) -> tuple[str, ...]:
    unknown = sorted(set(cited) - {c.code for c in version.criteria})
    if unknown:
        raise UnknownCriterionError(unknown)
    return tuple(sorted(set(cited)))


def _human_decision(
    folder: ProjectFolder,
    main: ScreeningRound,
    reference_id: str,
    value: DecisionValue,
    *,
    context: DecisionContext,
    criteria_cited: Sequence[str],
    rationale: str,
    supersedes: str | None,
    moment: datetime,
    tool_version: str,
) -> Decision:
    version = active_criteria(folder)
    return Decision(
        id=new_ulid(moment),
        reference_id=reference_id,
        stage=STAGE,
        round_id=main.id,
        reviewer_id=folder.reviewer_id,
        reviewer_kind=ReviewerKind.HUMAN,
        value=value,
        rationale=rationale.strip(),
        criteria_cited=_checked_codes(version, criteria_cited),
        criteria_version_id=version.id,
        context=context,
        blinded=context is DecisionContext.INDEPENDENT,
        supersedes_decision_id=supersedes,
        tool_version=tool_version,
        created_at=moment,
    )


def _latest_human(
    connection: Connection, rounds: Sequence[str], reference_id: str, contexts: Sequence[str]
) -> Decision | None:
    found = None
    for d in screening_repo.list_decisions(connection, reference_id=reference_id):
        human = d.reviewer_kind is ReviewerKind.HUMAN
        if human and d.round_id in rounds and d.context.value in contexts:
            found = d
    return found


def record_decision(
    folder: ProjectFolder,
    round_id: str,
    reference_id: str,
    value: DecisionValue,
    *,
    criteria_cited: Sequence[str] = (),
    rationale: str = "",
    now: Clock,
    tool_version: str,
) -> Decision:
    """The human reviewer's independent decision, taken without seeing the AI's
    (EF-SEL-08); an exclusion names its criteria (EF-SEL-12). A new decision on the
    same reference supersedes the previous one."""
    main = get_main_round(folder, round_id)
    with folder.write() as connection:
        if not screening_repo.is_member(connection, main.id, reference_id):
            raise NotInRoundError
        previous = _latest_human(
            connection, decided_in(connection, main), reference_id, ["independent"]
        )
        moment = now()
        decision = _human_decision(
            folder,
            main,
            reference_id,
            value,
            context=DecisionContext.INDEPENDENT,
            criteria_cited=criteria_cited,
            rationale=rationale,
            supersedes=None if previous is None else previous.id,
            moment=moment,
            tool_version=tool_version,
        )
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.SCREENING_HUMAN_DECIDED,
            subject_type="decision",
            subject_id=decision.id,
            summary_fr=french("Main screening: human decision recorded"),
            tool_version=tool_version,
            payload={
                "reference": reference_id,
                "round": "main",
                "value": value.value,
                "criteria_cited": list(decision.criteria_cited),
                "blinded": True,
                "supersedes": decision.supersedes_decision_id,
            },
        )
        screening_repo.insert_decision(connection, decision, journal_entry_id=entry.id)
    return decision


# --- State, disagreements, reconciliation -------------------------------------------


@dataclass(frozen=True, slots=True)
class MainState:
    round: ScreeningRound
    members: list[str]  # in screening order
    human: dict[str, Decision]  # independent decisions, the pilot's included
    ai: dict[str, Decision]
    reconciled: dict[str, Decision]
    final: dict[str, Decision]  # the latest human decision on each reference
    disagreements: list[str] = field(default_factory=list)  # in screening order
    queue: list[str] = field(default_factory=list)  # disagreements not reconciled yet

    def visible_ai(self, reference_id: str) -> Decision | None:
        """The AI's decision is shown only to reconcile a disagreement (EF-SEL-08)."""
        return self.ai.get(reference_id) if reference_id in self.disagreements else None


def main_state(folder: ProjectFolder, round_id: str) -> MainState:
    main = get_main_round(folder, round_id)
    with folder.engine.connect() as connection:
        rounds = decided_in(connection, main)
        members = screening_repo.member_ids(connection, main.id)
        human = screening_repo.latest_by_reference(
            connection, rounds, reviewer_kind=HUMAN, contexts=["independent"]
        )
        ai = screening_repo.latest_by_reference(connection, [main.id], reviewer_kind=AI)
        reconciled = screening_repo.latest_by_reference(
            connection, [main.id], reviewer_kind=HUMAN, contexts=["reconciliation"]
        )
        reassessed = [
            impact.reassessment_round_id
            for impact in screening_repo.list_impacts(connection, main.id)
            if impact.reassessment_round_id is not None
        ]
        final = screening_repo.latest_by_reference(
            connection, [*rounds, *reassessed], reviewer_kind=HUMAN
        )
    disagreements = [
        ref
        for ref in members
        if ref in human and ref in ai and disagree(human[ref].value, ai[ref].value)
    ]
    return MainState(
        round=main,
        members=members,
        human=human,
        ai=ai,
        reconciled=reconciled,
        final=final,
        disagreements=disagreements,
        queue=[ref for ref in disagreements if ref not in reconciled],
    )


@dataclass(frozen=True, slots=True)
class Progress:
    members: int
    human: int
    ai: int
    disagreements: int
    reconciled: int
    to_reconcile: int


def progress(state: MainState) -> Progress:
    members = set(state.members)
    return Progress(
        members=len(members),
        human=len(members & state.human.keys()),
        ai=len(members & state.ai.keys()),
        disagreements=len(state.disagreements),
        reconciled=len(state.disagreements) - len(state.queue),
        to_reconcile=len(state.queue),
    )


def reconcile(
    folder: ProjectFolder,
    round_id: str,
    reference_id: str,
    value: DecisionValue,
    *,
    criteria_cited: Sequence[str] = (),
    rationale: str = "",
    now: Clock,
    tool_version: str,
) -> Decision:
    """The final, human decision on a disagreement, taken with the AI's rationale in
    view (EF-SEL-08)."""
    state = main_state(folder, round_id)
    if reference_id not in state.disagreements:
        raise NotADisagreementError
    human, ai = state.human[reference_id], state.ai[reference_id]
    with folder.write() as connection:
        moment = now()
        decision = _human_decision(
            folder,
            state.round,
            reference_id,
            value,
            context=DecisionContext.RECONCILIATION,
            criteria_cited=criteria_cited,
            rationale=rationale,
            supersedes=human.id,
            moment=moment,
            tool_version=tool_version,
        )
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.SCREENING_RECONCILED,
            subject_type="decision",
            subject_id=decision.id,
            summary_fr=french(
                "Main screening: disagreement reconciled (you: {human}, AI: {ai}, final: {final})"
            ).format(human=human.value.value, ai=ai.value.value, final=value.value),
            tool_version=tool_version,
            payload={
                "reference": reference_id,
                "human_decision": human.id,
                "ai_decision": ai.id,
                "human_value": human.value.value,
                "ai_value": ai.value.value,
                "value": value.value,
                "criteria_cited": list(decision.criteria_cited),
            },
        )
        screening_repo.insert_decision(connection, decision, journal_entry_id=entry.id)
    return decision
