"""Flow diagram of the title and abstract screening, from the project (EF-DEC-01).

The numbers are computed on every export from the data in force (``reporting/flow.py``):
deduplication links and decisions, the main screening, reconciliations and
reassessments. The diagram is written in ``exports/`` as ``diagramme-<langue>.svg``
(regenerable files, docs/03-architecture.md §4).

The references kept for the full text (include or uncertain) are exported as RIS and
CSV (``references-retenues.ris`` and ``.csv``) for the next steps of the review.

In a replication project (D-104), the references sought for their full text also
include those the AI could not screen (kept, and counted by the benchmark); replayed
stepwise, they are the included studies of the published review instead.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from revue_portee.collect.deduplication import dedup_state
from revue_portee.domain.fulltext import RetrievalCounts, retrieval_counts
from revue_portee.domain.project import ReplicationMode
from revue_portee.domain.references import Reference, SourceKind
from revue_portee.domain.screening import DecisionValue, keeps
from revue_portee.reporting.flow import (
    FlowNumbers,
    FulltextCounts,
    ReassessmentCounts,
    flow_numbers,
    reassessment_counts,
)
from revue_portee.reporting.flow_svg import FlowContext, render_flow_svg
from revue_portee.reporting.retained import RetainedReference, write_csv, write_ris
from revue_portee.resources import flow_template
from revue_portee.screening import main, reassessment
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import criteria as criteria_repo
from revue_portee.storage.repositories import fulltext as fulltext_repo
from revue_portee.storage.repositories import projects
from revue_portee.storage.repositories import references as references_repo
from revue_portee.storage.repositories import screening as screening_repo

__all__ = [
    "FlowReport",
    "RetainedExport",
    "RetainedFormat",
    "export_flow",
    "export_retained",
    "flow_report",
    "full_text_counts",
    "full_text_screening",
    "retained_references",
    "sought_references",
]


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


def _retrieval(folder: ProjectFolder, sought: list[str]) -> RetrievalCounts:
    """Counts of the full texts of the references ``sought``."""
    with folder.engine.connect() as connection:
        documents = fulltext_repo.list_documents(connection)
        notes = fulltext_repo.list_notes(connection)
    return retrieval_counts(sought, documents, notes)


def full_text_screening(folder: ProjectFolder) -> FulltextCounts | None:
    """The full-text screening as the diagram counts it, once its main round started."""
    # Imported here: the full-text use cases depend on this module (retained references).
    from revue_portee.screening import fulltext

    if fulltext.main_round(folder) is None:
        return None
    state = fulltext.main_state(folder)
    with folder.engine.connect() as connection:
        version = criteria_repo.get_version(connection, state.round.criteria_version_id)
    labels = {} if version is None else {c.code: c.text for c in version.criteria}
    members = set(state.members)
    final = {r: d for r, d in state.final.items() if r in members}
    reasons: dict[str, int] = {}
    for ref in state.members:
        reason = state.reason(ref)
        if reason is not None:
            reasons[reason] = reasons.get(reason, 0) + 1
    ordered = dict(sorted(reasons.items(), key=lambda item: state.order.index(item[0])
                          if item[0] in state.order else len(state.order)))  # fmt: skip
    from revue_portee.screening import studies  # see above

    grouped = studies.study_state(folder)
    return FulltextCounts(
        assessed=len(final),
        included=sum(1 for d in final.values() if d.value is DecisionValue.INCLUDE),
        uncertain=sum(1 for d in final.values() if d.value is DecisionValue.UNCERTAIN),
        excluded_by_reason=ordered,
        reason_labels={code: labels.get(code, "") for code in ordered},
        not_screened=len(members - set(state.human)),
        without_ai=len(members - set(state.ai) - set(state.unreadable)),
        disagreements=len(state.queue),
        studies=len(grouped.studies),
        study_pairs=len(grouped.pending),
    )


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
        kept = sorted(
            ref for ref in remaining if ref in state.final and keeps(state.final[ref].value)
        )
        numbers = flow_numbers(
            dedup.counts,
            remaining,
            state.final,
            screened_by_ai=state.ai,
            disagreements_open=len(state.queue),
            reassessments=_reassessments(folder, started.id),
            retrieval=_retrieval(folder, kept),
            full_text=full_text_screening(folder),
        )
    with folder.engine.connect() as connection:
        project = projects.get_project(connection)
        active = criteria_repo.get_active_version(connection)
    context = FlowContext(
        project_title=project.title,
        criteria_version=None if active is None else active.number,
        tool_version=tool_version,
        generated_at=now(),
        simulation=folder.replication is not None,
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


def full_text_counts(folder: ProjectFolder) -> RetrievalCounts:
    """Counts of the full texts of the references kept for them."""
    return _retrieval(folder, [reference.id for reference in sought_references(folder)])


# --- References kept for the full text ----------------------------------------------


class RetainedFormat(StrEnum):
    RIS = "ris"
    CSV = "csv"


@dataclass(frozen=True, slots=True)
class RetainedExport:
    path: Path
    count: int
    provisional: bool  # the screening is not finished: the list may still change


def retained_references(folder: ProjectFolder) -> list[RetainedReference]:
    """References after deduplication whose decision in force keeps them (include or
    uncertain), sorted by title."""
    started = main.main_round(folder)
    if started is None:
        return []
    dedup = dedup_state(folder)
    duplicates = {ref for group in dedup.groups for ref in group.duplicates}
    final = main.main_state(folder, started.id).final
    with folder.engine.connect() as connection:
        numbers = {v.id: v.number for v in criteria_repo.list_versions(connection)}
    kept = [
        RetainedReference(
            reference=dedup.references[ref],
            decision=decision,
            criteria_version=numbers[decision.criteria_version_id],
        )
        for ref, decision in final.items()
        if ref in dedup.references and ref not in duplicates and keeps(decision.value)
    ]
    return sorted(kept, key=lambda r: (r.reference.title.casefold(), r.reference.id))


def sought_references(folder: ProjectFolder) -> list[Reference]:
    """References whose full text is sought, sorted by title: those kept at the title
    and abstract stage; in a replication project (D-104), with those the AI could not
    screen, or, replayed stepwise, the included studies of the published review."""
    marker = folder.replication
    if marker is not None and marker.mode is ReplicationMode.STEPWISE:
        dedup = dedup_state(folder)
        with folder.engine.connect() as connection:
            ids = references_repo.reference_ids_by_source(connection, SourceKind.REFERENCE_STANDARD)
        found = [dedup.references[ref] for ref in ids if ref in dedup.references]
    else:
        found = [item.reference for item in retained_references(folder)]
        started = main.main_round(folder)
        if marker is not None and started is not None:
            from revue_portee.screening.batch_ai import exhausted  # reads the AI batches

            references = dedup_state(folder).references
            found += [references[ref] for ref in exhausted(folder, started.id)]
    return sorted(found, key=lambda r: (r.title.casefold(), r.id))


def export_retained(
    folder: ProjectFolder,
    *,
    format: RetainedFormat,
    now: Callable[[], datetime],
    tool_version: str,
) -> RetainedExport:
    """Write the references kept for the full text in ``exports/``."""
    items = retained_references(folder)
    text = write_ris(items) if format is RetainedFormat.RIS else write_csv(items)
    target = folder.path / "exports" / f"references-retenues.{format.value}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    numbers = flow_report(folder, now=now, tool_version=tool_version).numbers
    return RetainedExport(path=target, count=len(items), provisional=numbers.provisional)
