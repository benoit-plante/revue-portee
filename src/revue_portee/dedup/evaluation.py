"""Recall and precision of deduplication against an annotated set (tranche 1.5).

The person's part is simulated by the annotation: a pair left to a person is grouped
when, and only when, the annotation says the two records are duplicates. The groups
obtained (automatic links plus those decisions) are compared, pair by pair, with the
annotated groups.
"""

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from revue_portee.dedup.matching import Candidate
from revue_portee.domain.dedup import PairKind, Proposal

__all__ = ["Evaluation", "evaluate"]


@dataclass(frozen=True, slots=True)
class Evaluation:
    records: int
    true_pairs: int  # pairs of records annotated as duplicates
    found_pairs: int  # pairs of records grouped at the end
    correct_pairs: int  # found pairs that are true pairs
    automatic_pairs: int
    automatic_errors: int  # automatic pairs that are not true pairs
    review_pairs: int  # pairs left to a person
    versions: int  # annotated pairs of versions of one work
    versions_flagged: int  # of which at least one record pair is left to a person

    @property
    def recall(self) -> float:
        return 1.0 if self.true_pairs == 0 else self.correct_pairs / self.true_pairs

    @property
    def precision(self) -> float:
        return 1.0 if self.found_pairs == 0 else self.correct_pairs / self.found_pairs


def _pairs_within(groups: Iterable[Sequence[str]]) -> set[tuple[str, str]]:
    pairs = set()
    for members in groups:
        ordered = sorted(members)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1 :]:
                pairs.add((a, b))
    return pairs


def evaluate(
    candidates: Sequence[Candidate],
    truth: Mapping[str, str],
    versions: Iterable[tuple[str, str]] = (),
) -> Evaluation:
    """``truth`` gives the annotated group of each record; ``versions`` pairs of groups
    annotated as versions of one work."""
    by_group: dict[str, list[str]] = {}
    for ref_id, group in truth.items():
        by_group.setdefault(group, []).append(ref_id)
    true_pairs = _pairs_within(by_group.values())
    parent = {ref_id: ref_id for ref_id in truth}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    automatic_errors = 0
    for c in candidates:
        same = truth[c.reference_a] == truth[c.reference_b]
        if c.proposal is Proposal.DUPLICATE:
            automatic_errors += not same
        if c.proposal is Proposal.DUPLICATE or same:
            parent[find(c.reference_a)] = find(c.reference_b)
    found: dict[str, list[str]] = {}
    for ref_id in truth:
        found.setdefault(find(ref_id), []).append(ref_id)
    found_pairs = _pairs_within(found.values())
    flagged = {
        tuple(sorted((truth[c.reference_a], truth[c.reference_b])))
        for c in candidates
        if c.proposal is Proposal.REVIEW and c.kind is PairKind.VERSION
    }
    wanted = {tuple(sorted(v)) for v in versions}
    kinds = Counter(c.proposal for c in candidates)
    return Evaluation(
        records=len(truth),
        true_pairs=len(true_pairs),
        found_pairs=len(found_pairs),
        correct_pairs=len(found_pairs & true_pairs),
        automatic_pairs=kinds[Proposal.DUPLICATE],
        automatic_errors=automatic_errors,
        review_pairs=kinds[Proposal.REVIEW],
        versions=len(wanted),
        versions_flagged=len(wanted & flagged),
    )
