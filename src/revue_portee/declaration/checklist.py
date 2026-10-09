"""The reporting checklist filled from the project (EF-DEC-02, tranche 4.3): the facts of
the protocol, of the methods section, of the synthesis and of the consultation, then a
proposal for each item; written in ``exports/``."""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from revue_portee.extraction.prefill import NoGridError
from revue_portee.i18n import gettext as _
from revue_portee.protocol.document import protocol_data
from revue_portee.reporting.document import Document, render_docx, render_markdown
from revue_portee.reporting.prisma_scr import ChecklistFacts, build_checklist, fill_checklist
from revue_portee.resources import reporting_checklists
from revue_portee.screening.methods import methods_data
from revue_portee.stakeholders.comments import consultation_state
from revue_portee.storage.project_folder import ProjectFolder

__all__ = [
    "DEFAULT_CHECKLIST",
    "UnknownChecklistError",
    "checklist_document",
    "checklist_facts",
    "export_checklist",
]

Clock = Callable[[], datetime]
DEFAULT_CHECKLIST = "prisma-scr-2018"


class UnknownChecklistError(LookupError):
    def __init__(self, name: str) -> None:
        super().__init__(_("Unknown checklist: {name}.").format(name=name))


def checklist_facts(folder: ProjectFolder, *, now: Clock, tool_version: str) -> ChecklistFacts:
    # Imported here: the narrative synthesis reads the extraction, which reads the screening.
    from revue_portee.synthesis.narrative import narrative_state

    try:
        revised = sum(1 for f in narrative_state(folder).fields if f.revised is not None)
    except NoGridError:
        revised = 0
    consultation = consultation_state(folder)
    return ChecklistFacts(
        protocol=protocol_data(folder, now=now, tool_version=tool_version),
        methods=methods_data(folder, now=now, tool_version=tool_version),
        narrative_fields=revised,
        stakeholders=consultation.counts.stakeholders,
        comments=consultation.counts.comments,
    )


def checklist_document(
    folder: ProjectFolder, *, checklist: str = DEFAULT_CHECKLIST, language: str, now: Clock,
    tool_version: str,
) -> Document:  # fmt: skip
    found = reporting_checklists().get(checklist)
    if found is None:
        raise UnknownChecklistError(checklist)
    facts = checklist_facts(folder, now=now, tool_version=tool_version)
    return build_checklist(
        found, fill_checklist(found, facts, language=language),
        project_title=facts.protocol.project.title, language=language,
        tool_version=tool_version, generated_at=now(),
    )  # fmt: skip


def export_checklist(
    folder: ProjectFolder, *, checklist: str = DEFAULT_CHECKLIST, language: str, now: Clock,
    tool_version: str,
) -> list[Path]:  # fmt: skip
    """Write ``exports/<checklist>-<langue>.md`` and ``.docx``."""
    document = checklist_document(
        folder, checklist=checklist, language=language, now=now, tool_version=tool_version
    )
    target = folder.path / "exports"
    target.mkdir(parents=True, exist_ok=True)
    markdown = target / f"{checklist}-{language}.md"
    markdown.write_text(render_markdown(document), encoding="utf-8")
    docx = target / f"{checklist}-{language}.docx"
    docx.write_bytes(render_docx(document))
    return [markdown, docx]
