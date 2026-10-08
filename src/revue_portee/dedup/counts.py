"""Numbers of the flow diagram computed from the data (EF-COL-08).

Records identified by source are the references each source gave; duplicates removed
are the references grouped under another one. Nothing is typed in by hand.
"""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from revue_portee.dedup.groups import Group

__all__ = ["FlowCounts", "flow_counts"]


@dataclass(frozen=True, slots=True)
class FlowCounts:
    identified_by_source: dict[str, int]  # source name: records, sorted by name
    identified: int
    duplicates_removed: int
    after_deduplication: int
    pending_pairs: int


def flow_counts(
    source_of: Mapping[str, str], groups: Iterable[Group], *, pending_pairs: int = 0
) -> FlowCounts:
    """``source_of`` gives the source name of each reference."""
    by_source = Counter(source_of.values())
    removed = sum(sum(1 for ref_id in group.duplicates if ref_id in source_of) for group in groups)
    total = len(source_of)
    return FlowCounts(
        identified_by_source=dict(sorted(by_source.items())),
        identified=total,
        duplicates_removed=removed,
        after_deduplication=total - removed,
        pending_pairs=pending_pairs,
    )
