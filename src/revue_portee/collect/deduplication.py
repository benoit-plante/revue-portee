"""Deduplication of the references of a project (EF-COL-06 to EF-COL-08).

A run compares every reference (with its Crossref enrichment) and records the pairs
it finds; pairs between the two thresholds wait for a person, whose decision is
recorded in its own transaction with its journal entry. Nothing is deleted: groups of
duplicates are computed from the links in force, and undoing a grouping is a decision
"not duplicates" on one of its links (EF-COL-07).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from pydantic import JsonValue

from revue_portee.collect.enrichment import references_with_enrichment
from revue_portee.dedup.counts import FlowCounts, flow_counts
from revue_portee.dedup.groups import (
    PRIMARY_RULE,
    Group,
    group_references,
    latest_decisions,
    links_in_force,
    pending_pairs,
)
from revue_portee.dedup.matching import Candidate, find_candidates
from revue_portee.domain.dedup import (
    DedupRun,
    DedupSettings,
    DuplicatePair,
    PairDecision,
    PairKind,
    PairOutcome,
    Proposal,
)
from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.domain.references import Reference
from revue_portee.i18n import french
from revue_portee.i18n import gettext as _
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import dedup as dedup_repo
from revue_portee.storage.repositories import journal
from revue_portee.storage.repositories import references as references_repo

__all__ = [
    "DedupState",
    "NoReferencesError",
    "UnknownPairError",
    "decide_pair",
    "dedup_state",
    "run_deduplication",
]

Clock = Callable[[], datetime]


class NoReferencesError(ValueError):
    def __init__(self) -> None:
        super().__init__(_("There is no reference to deduplicate yet: collect or import first."))


class UnknownPairError(ValueError):
    def __init__(self) -> None:
        super().__init__(_("These two references are not a pair of the deduplication."))


def _pairs(run_id: str, candidates: list[Candidate], moment: datetime) -> list[DuplicatePair]:
    return [
        DuplicatePair(
            id=new_ulid(moment),
            run_id=run_id,
            reference_a_id=c.reference_a,
            reference_b_id=c.reference_b,
            kind=c.kind,
            rule=c.rule,
            score=c.score,
            proposal=c.proposal,
            details={k: round(v, 4) if isinstance(v, float) else v for k, v in c.details.items()},
        )
        for c in candidates
    ]


def run_deduplication(
    folder: ProjectFolder,
    settings: DedupSettings,
    *,
    now: Clock,
    tool_version: str,
) -> DedupRun:
    """Compare every reference and record the pairs found (EF-COL-06)."""
    references = references_with_enrichment(folder)
    if not references:
        raise NoReferencesError
    candidates = find_candidates(references, settings)
    with folder.write() as connection:
        moment = now()
        run = DedupRun(
            id=new_ulid(moment),
            created_at=moment,
            reviewer_id=folder.reviewer_id,
            settings=settings,
            reference_count=len(references),
            automatic_pairs=sum(c.proposal is Proposal.DUPLICATE for c in candidates),
            review_pairs=sum(c.proposal is Proposal.REVIEW for c in candidates),
        )
        by_kind: dict[str, JsonValue] = {
            kind.value: sum(c.kind is kind for c in candidates) for kind in PairKind
        }
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.DEDUP_COMPLETED,
            subject_type="dedup_run",
            subject_id=run.id,
            summary_fr=french(
                "Deduplication: references compared: {references}; pairs grouped "
                "automatically: {automatic}; pairs to review: {review}"
            ).format(
                references=run.reference_count,
                automatic=run.automatic_pairs,
                review=run.review_pairs,
            ),
            tool_version=tool_version,
            payload={
                "settings": settings.model_dump(mode="json"),
                "references": run.reference_count,
                "automatic_pairs": run.automatic_pairs,
                "review_pairs": run.review_pairs,
                "pairs_by_kind": by_kind,
                "primary_rule": PRIMARY_RULE,
            },
        )
        dedup_repo.insert_run(connection, run, journal_entry_id=entry.id)
        dedup_repo.insert_pairs(connection, _pairs(run.id, candidates, moment))
    return run


def decide_pair(
    folder: ProjectFolder,
    reference_a_id: str,
    reference_b_id: str,
    outcome: PairOutcome,
    *,
    note: str = "",
    now: Clock,
    tool_version: str,
) -> PairDecision:
    """Record a person's decision on two references: a pair of the latest run, or a
    link in force (to undo a grouping)."""
    a, b = sorted((reference_a_id, reference_b_id))
    with folder.write() as connection:
        run = dedup_repo.latest_run(connection)
        pair = None if run is None else dedup_repo.find_pair(connection, run.id, a, b)
        decisions = dedup_repo.decisions_on(connection, a, b)
        if pair is None and not decisions:
            raise UnknownPairError
        before = (a, b) in links_in_force([] if pair is None else [pair], decisions)
        moment = now()
        decision = PairDecision(
            id=new_ulid(moment),
            reference_a_id=a,
            reference_b_id=b,
            pair_id=None if pair is None else pair.id,
            outcome=outcome,
            reviewer_id=folder.reviewer_id,
            note=note.strip(),
            created_at=moment,
        )
        if outcome is PairOutcome.DUPLICATE:
            summary = french("Deduplication: two references grouped as duplicates")
        else:
            summary = french("Deduplication: two references kept apart")
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.DEDUP_PAIR_DECIDED,
            subject_type="pair_decision",
            subject_id=decision.id,
            summary_fr=summary,
            tool_version=tool_version,
            payload={
                "reference_a": a,
                "reference_b": b,
                "outcome": outcome.value,
                "grouped_before": before,
                "pair": None if pair is None else pair.id,
                "kind": None if pair is None else pair.kind.value,
                "rule": None if pair is None else pair.rule,
                "score": None if pair is None else pair.score,
                "note": decision.note,
            },
        )
        dedup_repo.insert_decision(connection, decision, journal_entry_id=entry.id)
    return decision


@dataclass(frozen=True, slots=True)
class DedupState:
    run: DedupRun | None
    pairs: dict[tuple[str, str], DuplicatePair]  # of the latest run
    decisions: dict[tuple[str, str], PairDecision]  # latest decision per pair
    links: set[tuple[str, str]]
    groups: list[Group]
    pending: list[DuplicatePair]
    references: dict[str, Reference]
    sources: dict[str, str]
    counts: FlowCounts
    new_references: int  # references added since the latest run


def dedup_state(folder: ProjectFolder) -> DedupState:
    references = {r.id: r for r in references_with_enrichment(folder)}
    with folder.engine.connect() as connection:
        run = dedup_repo.latest_run(connection)
        pairs = [] if run is None else dedup_repo.list_pairs(connection, run.id)
        decisions = dedup_repo.list_decisions(connection)
        sources = references_repo.source_names(connection)
    links = links_in_force(pairs, decisions)
    groups = group_references(references, links)
    pending = pending_pairs(pairs, decisions, groups)
    source_of = {ref_id: sources.get(ref_id, "") for ref_id in references}
    return DedupState(
        run=run,
        pairs={(p.reference_a_id, p.reference_b_id): p for p in pairs},
        decisions=latest_decisions(decisions),
        links=links,
        groups=groups,
        pending=pending,
        references=references,
        sources=source_of,
        counts=flow_counts(source_of, groups, pending_pairs=len(pending)),
        new_references=0 if run is None else max(0, len(references) - run.reference_count),
    )
