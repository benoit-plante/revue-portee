"""Links in force, groups of duplicates and their primary reference (EF-COL-07).

A link joins two references. It is in force when the latest person's decision on the
pair says "duplicate", or, without any decision, when the latest run grouped the pair
automatically. Groups are the connected references; nothing is deleted, so undoing a
grouping is a new decision.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from revue_portee.domain.dedup import DuplicatePair, PairDecision, PairOutcome, Proposal
from revue_portee.domain.references import Reference

__all__ = [
    "PRIMARY_RULE",
    "Group",
    "choose_primary",
    "group_references",
    "latest_decisions",
    "links_in_force",
    "pending_pairs",
]

PRIMARY_RULE = "most complete record (DOI, abstract, PMID, filled fields), then the oldest"

Pair = tuple[str, str]


@dataclass(frozen=True, slots=True)
class Group:
    primary: str
    members: tuple[str, ...]  # the primary first, then by identifier

    @property
    def duplicates(self) -> tuple[str, ...]:
        return self.members[1:]


def latest_decisions(decisions: Iterable[PairDecision]) -> dict[Pair, PairDecision]:
    """The latest decision on each pair (decisions given oldest first)."""
    latest: dict[Pair, PairDecision] = {}
    for decision in decisions:
        latest[(decision.reference_a_id, decision.reference_b_id)] = decision
    return latest


def links_in_force(pairs: Iterable[DuplicatePair], decisions: Iterable[PairDecision]) -> set[Pair]:
    """Pairs of duplicates: ``pairs`` of the latest run, then people's decisions."""
    links = {
        (p.reference_a_id, p.reference_b_id) for p in pairs if p.proposal is Proposal.DUPLICATE
    }
    for key, decision in latest_decisions(decisions).items():
        if decision.outcome is PairOutcome.DUPLICATE:
            links.add(key)
        else:
            links.discard(key)
    return links


def pending_pairs(
    pairs: Iterable[DuplicatePair],
    decisions: Iterable[PairDecision],
    groups: Iterable[Group] = (),
) -> list[DuplicatePair]:
    """Pairs left to a person that nobody has decided yet, except those whose two
    references are already in one group through other links (nothing to decide)."""
    decided = set(latest_decisions(decisions))
    group_of = {ref_id: g.primary for g in groups for ref_id in g.members}
    return [
        p
        for p in pairs
        if p.proposal is Proposal.REVIEW
        and (p.reference_a_id, p.reference_b_id) not in decided
        and (
            p.reference_a_id not in group_of
            or group_of.get(p.reference_a_id) != group_of.get(p.reference_b_id)
        )
    ]


def _completeness(ref: Reference) -> tuple[int, int, int, int]:
    filled = sum(
        1
        for value in (
            ref.title,
            ref.abstract,
            ref.authors,
            ref.year,
            ref.container_title,
            ref.volume,
            ref.issue,
            ref.pages,
            ref.language,
            ref.doc_type,
        )
        if value
    )
    return (int(bool(ref.doi)), int(bool(ref.abstract)), int(bool(ref.pmid)), filled)


def choose_primary(members: Sequence[Reference]) -> Reference:
    """The primary reference of a group (:data:`PRIMARY_RULE`)."""
    return min(
        members,
        key=lambda r: (tuple(-x for x in _completeness(r)), r.created_at, r.id),
    )


def group_references(references: Mapping[str, Reference], links: Iterable[Pair]) -> list[Group]:
    """Groups of at least two references joined by ``links``, ordered by primary."""
    parent = {ref_id: ref_id for ref_id in references}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in links:
        if a in parent and b in parent:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
    members: dict[str, list[str]] = defaultdict(list)
    for ref_id in sorted(references):
        members[find(ref_id)].append(ref_id)
    groups = []
    for ids in members.values():
        if len(ids) < 2:
            continue
        primary = choose_primary([references[i] for i in ids]).id
        groups.append(Group(primary, (primary, *(i for i in ids if i != primary))))
    return sorted(groups, key=lambda g: g.primary)
