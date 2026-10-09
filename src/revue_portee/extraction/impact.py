"""Impact of a new version of the extraction grid on the values (EF-VER-06, tranche 3.4).

When a version is activated, each change touches studies (``domain.extraction.
grid_impact``): an added field leaves every included study to complete; a modified
field flags the values given under its former definition, to review; a removed field
archives its values. The impact is recorded in the journal with the activation; what
remains to do is then followed from the values in force: a study is completed once it
has a value on the added field, a value is reviewed once it was confirmed, corrected,
validated or rejected under the field in force.
"""

from dataclasses import dataclass

from pydantic import JsonValue

from revue_portee.domain.extraction import (
    ChangeKind,
    GridChangeImpact,
    grid_impact,
    stale,
)
from revue_portee.domain.grid import GridVersion, diff_versions
from revue_portee.domain.journal import EntryType
from revue_portee.domain.project import ReviewerKind
from revue_portee.extraction.prefill import extraction_state
from revue_portee.i18n import french
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import extraction as extraction_repo
from revue_portee.storage.repositories import grid as grid_repo
from revue_portee.storage.repositories import journal

__all__ = [
    "ChangeFollowUp",
    "GridImpactState",
    "assess",
    "counts",
    "impact_state",
    "payload",
    "summary",
]


def assess(
    folder: ProjectFolder, previous: GridVersion, activated: GridVersion
) -> tuple[GridChangeImpact, ...]:
    """The studies each change from ``previous`` to ``activated`` touches."""
    studies = [s.primary.id for s in extraction_state(folder).studies]
    with folder.engine.connect() as connection:
        values = extraction_repo.list_values(connection)
    return grid_impact(diff_versions(previous, activated), studies, values)


def counts(changes: tuple[GridChangeImpact, ...]) -> dict[ChangeKind, int]:
    """Studies to complete (distinct), values to review, values archived."""
    added = {s for c in changes if c.kind is ChangeKind.ADDED for s in c.studies}
    return {
        ChangeKind.ADDED: len(added),
        ChangeKind.MODIFIED: sum(len(c.studies) for c in changes if c.kind is ChangeKind.MODIFIED),
        ChangeKind.REMOVED: sum(len(c.studies) for c in changes if c.kind is ChangeKind.REMOVED),
    }


def summary(activated: GridVersion, changes: tuple[GridChangeImpact, ...]) -> str:
    found = counts(changes)
    return french(
        "Impact of grid version {number}: studies to complete: {added}; values to review: "
        "{modified}; values archived: {removed}"
    ).format(
        number=activated.number,
        added=found[ChangeKind.ADDED],
        modified=found[ChangeKind.MODIFIED],
        removed=found[ChangeKind.REMOVED],
    )


def payload(
    previous: GridVersion, activated: GridVersion, changes: tuple[GridChangeImpact, ...]
) -> dict[str, JsonValue]:
    return {
        "from_version": previous.number,
        "to_version": activated.number,
        "changes": [change.model_dump(mode="json") for change in changes],
    }


@dataclass(frozen=True, slots=True)
class ChangeFollowUp:
    change: GridChangeImpact
    remaining: tuple[str, ...]  # studies still to complete or to review (none: archived)


@dataclass(frozen=True, slots=True)
class GridImpactState:
    from_number: int
    to_number: int
    changes: list[ChangeFollowUp]


def impact_state(folder: ProjectFolder) -> GridImpactState | None:
    """The impact recorded when the version in force was activated, with what remains."""
    with folder.engine.connect() as connection:
        grid = grid_repo.get_active_version(connection)
        if grid is None:
            return None
        entry = next(
            (
                e
                for e in reversed(journal.list_entries(connection))
                if e.entry_type == EntryType.GRID_IMPACT_ASSESSED and e.subject_id == grid.id
            ),
            None,
        )
    if entry is None:
        return None
    raw = entry.payload
    changes_raw = raw.get("changes")
    changes = [
        GridChangeImpact.model_validate(item)
        for item in (changes_raw if isinstance(changes_raw, list) else [])
    ]
    with folder.engine.connect() as connection:
        versions = {v.id: v for v in grid_repo.list_versions(connection)}
    current = {s.primary.id: s.values for s in extraction_state(folder).studies}

    def decided(study: str, code: str) -> bool:
        value = current.get(study, {}).get(code)
        field = grid.field(code)
        return (
            value is not None
            and value.reviewer_kind is ReviewerKind.HUMAN
            and field is not None
            and not stale(value, versions, field)
        )

    follow = [
        ChangeFollowUp(
            change=change,
            remaining=()
            if change.kind is ChangeKind.REMOVED
            else tuple(s for s in change.studies if s in current and not decided(s, change.code)),
        )
        for change in changes
    ]
    return GridImpactState(
        from_number=int(str(raw.get("from_version", 0))),
        to_number=grid.number,
        changes=follow,
    )
