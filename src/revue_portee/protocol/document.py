"""Generate the protocol from the project (EF-CAD-06, EF-CAD-07, ENF-LAN-04).

Exports are written in ``exports/`` (regenerable files, docs/03-architecture.md §4):
``protocole-<langue>.md`` and ``protocole-<langue>.docx``.
"""

from collections.abc import Callable, Sequence
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from revue_portee.domain.criteria import VersionStatus
from revue_portee.domain.grid import GridVersion, diff_versions
from revue_portee.domain.project import ReviewerKind
from revue_portee.domain.protocol import ProtocolRegistration, ProtocolText
from revue_portee.reporting.document import Document, render_docx, render_markdown
from revue_portee.reporting.protocol import (
    Deviation,
    GridDeviation,
    ProtocolData,
    build_protocol,
)
from revue_portee.resources import osf_form, peters_checklist
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import criteria as criteria_repo
from revue_portee.storage.repositories import framing as framing_repo
from revue_portee.storage.repositories import grid as grid_repo
from revue_portee.storage.repositories import projects
from revue_portee.storage.repositories import protocol as protocol_repo
from revue_portee.storage.repositories import search as search_repo

__all__ = ["ExportFormat", "export_protocol", "protocol_data", "protocol_document"]


class ExportFormat(StrEnum):
    MARKDOWN = "md"
    DOCX = "docx"


def _grid_deviations(
    versions: Sequence[GridVersion], registration: ProtocolRegistration | None
) -> tuple[GridDeviation, ...]:
    """Versions of the grid activated after the registration, from version 2 on (the
    first version is the grid of the protocol)."""
    if registration is None:
        return ()
    by_id = {v.id: v for v in versions}
    found = []
    for version in versions:
        parent = None if version.parent_id is None else by_id.get(version.parent_id)
        if (
            parent is None
            or version.activated_at is None
            or version.activated_at < registration.created_at
        ):
            continue
        delta = diff_versions(parent, version)
        found.append(
            GridDeviation(
                number=version.number,
                activated_at=version.activated_at,
                rationale=version.rationale,
                added=tuple(f.code for f in delta.added),
                modified=tuple(m.code for m in delta.modified),
                removed=tuple(f.code for f in delta.removed),
            )
        )
    return tuple(found)


def protocol_data(
    folder: ProjectFolder, *, now: Callable[[], datetime], tool_version: str
) -> ProtocolData:
    with folder.engine.connect() as connection:
        framing = framing_repo.latest_framing_version(connection)
        text = protocol_repo.latest_text_version(connection)
        versions = criteria_repo.list_versions(connection)
        deviations = tuple(
            Deviation(
                number=v.number,
                activated_at=v.activated_at,
                rationale=v.rationale,
                changes=tuple(protocol_repo.list_changes(connection, to_version_id=v.id)),
            )
            for v in versions
            if v.after_protocol_registration and v.activated_at is not None
        )
        registration = protocol_repo.latest_registration(connection)
        grid_deviations = _grid_deviations(grid_repo.list_versions(connection), registration)
        search = search_repo.latest_strategy_version(connection)
        queries = (
            ()
            if search is None
            else tuple(search_repo.list_queries(connection, strategy_version_id=search.id))
        )
        query_ids = {q.id for q in queries}
        latest_counts = {
            run.query_id: run
            for run in search_repo.list_runs(connection)
            if run.query_id in query_ids and run.result_count is not None
        }
        data = ProtocolData(
            project=projects.get_project(connection),
            reviewers=tuple(
                r
                for r in projects.list_reviewers(connection)
                if r.kind is ReviewerKind.HUMAN and r.active
            ),
            framing=None if framing is None else framing.framing,
            criteria=next((v for v in versions if v.status is VersionStatus.ACTIVE), None),
            text=ProtocolText() if text is None else text.text,
            ai=folder.ai_settings(),
            registration=registration,
            deviations=deviations,
            grid_deviations=grid_deviations,
            search=search,
            queries=queries,
            counts=tuple(latest_counts.values()),
            grid=grid_repo.get_active_version(connection)
            or grid_repo.get_draft_version(connection),
            tool_version=tool_version,
            generated_at=now(),
        )
    return data


def protocol_document(
    folder: ProjectFolder, *, language: str, now: Callable[[], datetime], tool_version: str
) -> Document:
    return build_protocol(
        protocol_data(folder, now=now, tool_version=tool_version),
        language=language,
        checklist=peters_checklist(),
        osf=osf_form(),
    )


def export_protocol(
    folder: ProjectFolder,
    *,
    language: str,
    format: ExportFormat,
    now: Callable[[], datetime],
    tool_version: str,
) -> Path:
    """Write the protocol in ``exports/`` and return the file path."""
    document = protocol_document(folder, language=language, now=now, tool_version=tool_version)
    target = folder.path / "exports" / f"protocole-{language}.{format.value}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if format is ExportFormat.MARKDOWN:
        target.write_text(render_markdown(document), encoding="utf-8")
    else:
        target.write_bytes(render_docx(document))
    return target
