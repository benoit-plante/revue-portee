"""Flow diagram of the title and abstract screening, from the project (EF-DEC-01).

The numbers are computed on every export from the data in force (``reporting/flow.py``):
deduplication links and decisions, the main screening, reconciliations and
reassessments. The diagram is written in ``exports/`` as ``diagramme-<langue>.svg``
(regenerable files, docs/03-architecture.md §4).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from revue_portee.collect.deduplication import dedup_state
from revue_portee.reporting.flow import (
    FlowNumbers,
    ReassessmentCounts,
    flow_numbers,
    reassessment_counts,
)
from revue_portee.reporting.flow_svg import FlowContext, render_flow_svg
from revue_portee.resources import flow_template
from revue_portee.screening import main, reassessment
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import criteria as criteria_repo
from revue_portee.storage.repositories import projects
from revue_portee.storage.repositories import screening as screening_repo

__all__ = ["FlowReport", "export_flow", "flow_report"]


@dataclass(frozen=True, slots=True)
class FlowReport:
    numbers: FlowNumbers
    context: FlowContext


def _reassessments(folder: ProjectFolder, main_round_id: str) -> list[ReassessmentCounts]:
    with folder.engine.connect() as connection:
        impacts = screening_repo.list_impacts(connection, main_round_id)
        numbers = {v.id: v.number for v in criteria_repo.list_versions(connection)}
    counts = []
    for impact in impacts:
        versions = {
            "from_version": numbers[impact.from_version_id],
            "to_version": numbers[impact.to_version_id],
        }
        if impact.reassessment_round_id is None:  # no reference touched
            counts.append(
                ReassessmentCounts(
                    **versions, reassessed=0, kept_to_excluded=0, excluded_to_kept=0,
                    completed=True,
                )
            )  # fmt: skip
            continue
        state = reassessment.reassessment_state(folder, impact.id)
        counts.append(
            reassessment_counts(
                **versions,
                members=state.members,
                previous=state.previous,
                verified=state.verified,
                completed=state.completed,
            )
        )
    return counts


def flow_report(
    folder: ProjectFolder, *, now: Callable[[], datetime], tool_version: str
) -> FlowReport:
    dedup = dedup_state(folder)
    duplicates = {ref for group in dedup.groups for ref in group.duplicates}
    remaining = sorted(ref for ref in dedup.references if ref not in duplicates)
    started = main.main_round(folder)
    if started is None:
        numbers = flow_numbers(dedup.counts, remaining, {}, screening_started=False)
    else:
        state = main.main_state(folder, started.id)
        numbers = flow_numbers(
            dedup.counts,
            remaining,
            state.final,
            screened_by_ai=state.ai,
            disagreements_open=len(state.queue),
            reassessments=_reassessments(folder, started.id),
        )
    with folder.engine.connect() as connection:
        project = projects.get_project(connection)
        active = criteria_repo.get_active_version(connection)
    context = FlowContext(
        project_title=project.title,
        criteria_version=None if active is None else active.number,
        tool_version=tool_version,
        generated_at=now(),
    )
    return FlowReport(numbers=numbers, context=context)


def export_flow(
    folder: ProjectFolder, *, language: str, now: Callable[[], datetime], tool_version: str
) -> Path:
    """Write the diagram in ``exports/`` and return the file path."""
    report = flow_report(folder, now=now, tool_version=tool_version)
    svg = render_flow_svg(report.numbers, flow_template(), report.context, language=language)
    target = folder.path / "exports" / f"diagramme-{language}.svg"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(svg, encoding="utf-8")
    return target
