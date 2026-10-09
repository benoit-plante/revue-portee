"""Archive of the project, to deposit with the review (EF-PRJ-04, ENF-REP-06).

Two kinds of archive, written in ``exports/``:

- **public** (by default): readable data only (CSV, JSON lines), the flow diagram, the
  draft methods section, the calibrations and ``projet.toml``. No abstract, no URL, no
  raw response, no database: they hold copyrighted text. Every number of the diagram
  can be recomputed from these files alone (``LISEZMOI.md`` says how);
- **complete**: the same files plus a copy of the folder without ``textes/`` (database,
  raw responses, imported files). It reopens with the tool; it is not for a public
  deposit.

Before anything is written, the text files are checked for secrets (ENF-SEC-01): a
secret found stops the export. The export is recorded in the journal with the
SHA-256 digest of the file.
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from functools import cache
from pathlib import Path

from jinja2 import Environment, PackageLoader

from revue_portee.collect.deduplication import DedupState, dedup_state
from revue_portee.config.secret_scan import scan_text
from revue_portee.config.secrets import redact
from revue_portee.domain.fulltext import current_documents, retrieval_statuses
from revue_portee.domain.journal import EntryType
from revue_portee.i18n import EXPORT_LANGUAGES, french
from revue_portee.i18n import gettext as _
from revue_portee.protocol.document import ExportFormat
from revue_portee.reporting.document import render_docx, render_markdown
from revue_portee.reporting.flow_svg import render_flow_svg
from revue_portee.reporting.methods import build_methods
from revue_portee.resources import flow_template
from revue_portee.screening import main
from revue_portee.screening.methods import methods_data
from revue_portee.screening.report import flow_report, retained_references
from revue_portee.storage.archive import (
    csv_text,
    database_copy,
    readable_tables,
    reference_rows,
    write_zip,
)
from revue_portee.storage.project_folder import DATABASE_FILE, PROJECT_FILE, ProjectFolder
from revue_portee.storage.repositories import criteria as criteria_repo
from revue_portee.storage.repositories import fulltext as fulltext_repo
from revue_portee.storage.repositories import grid as grid_repo
from revue_portee.storage.repositories import journal, projects
from revue_portee.storage.repositories import lay_summary as summary_repo
from revue_portee.storage.repositories import narrative as narrative_repo
from revue_portee.storage.repositories import screening as screening_repo
from revue_portee.storage.repositories import synthesis as synthesis_repo

__all__ = [
    "ArchiveKind",
    "ArchiveResult",
    "SecretInArchiveError",
    "archive_files",
    "export_archive",
]

Clock = Callable[[], datetime]
TEXT_SUFFIXES = (".csv", ".jsonl", ".json", ".md", ".svg", ".toml")
# Folders of the project copied into the complete archive (``textes/`` never: full
# texts are copyrighted; ``exports/`` is regenerated).
COPIED_FOLDERS = ("brut", "imports", "etalonnage")


class ArchiveKind(StrEnum):
    PUBLIC = "publique"
    COMPLETE = "complete"


class SecretInArchiveError(ValueError):
    def __init__(self, findings: list[str]) -> None:
        super().__init__(
            _("A secret was found in the archive, which was not written: {findings}").format(
                findings="; ".join(findings)
            )
        )


@dataclass(frozen=True, slots=True)
class ArchiveResult:
    path: Path
    sha256: str
    files: int


def _dedup_files(state: DedupState) -> dict[str, str]:
    primary_of = {ref: g.primary for g in state.groups for ref in g.duplicates}
    deduplication = csv_text(
        ("reference_id", "source", "duplicate_of"),
        ((ref, state.sources[ref], primary_of.get(ref)) for ref in sorted(state.references)),
    )
    pending = csv_text(
        ("reference_a_id", "reference_b_id", "rule", "score"),
        ((p.reference_a_id, p.reference_b_id, p.rule, p.score) for p in state.pending),
    )
    return {
        "references.csv": reference_rows(state.references.values()),
        "dedoublonnage.csv": deduplication,
        "paires-a-examiner.csv": pending,
    }


def _screening_files(folder: ProjectFolder, state: DedupState) -> dict[str, str]:
    duplicates = {ref for g in state.groups for ref in g.duplicates}
    remaining = sorted(ref for ref in state.references if ref not in duplicates)
    started = main.main_round(folder)
    header = (
        "reference_id",
        "in_main_screening",
        "final_decision_id",
        "ai_decision_id",
        "disagreement",
        "reconciled",
    )
    if started is None:
        rows: list[tuple[object, ...]] = [
            (ref, False, None, None, False, False) for ref in remaining
        ]
        impacts = []
    else:
        screening = main.main_state(folder, started.id)
        members = set(screening.members)
        rows = [
            (
                ref,
                ref in members,
                screening.final[ref].id if ref in screening.final else None,
                screening.ai[ref].id if ref in screening.ai else None,
                ref in screening.disagreements,
                ref in screening.reconciled,
            )
            for ref in remaining
        ]
        with folder.engine.connect() as connection:
            impacts = screening_repo.list_impacts(connection, started.id)
    with folder.engine.connect() as connection:
        numbers = {v.id: v.number for v in criteria_repo.list_versions(connection)}
        completed = {
            e.subject_id
            for e in journal.list_entries(connection)
            if e.entry_type == EntryType.REASSESSMENT_COMPLETED
        }
    reassessments = csv_text(
        ("impact_id", "from_version", "to_version", "reassessment_round_id", "touched",
         "sampled", "completed"),
        (
            (i.id, numbers[i.from_version_id], numbers[i.to_version_id], i.reassessment_round_id,
             len(i.impact.touched), i.sampled, i.id in completed)
            for i in impacts
        ),
    )  # fmt: skip
    return {"etat-du-tri.csv": csv_text(header, rows), "reevaluations.csv": reassessments}


def _fulltext_files(folder: ProjectFolder) -> dict[str, str]:
    """Status of the full text of each reference sought: never the PDF, its text, its
    URL nor its file name (D-092)."""
    sought = [item.reference.id for item in retained_references(folder)]
    with folder.engine.connect() as connection:
        documents = fulltext_repo.list_documents(connection)
        notes = fulltext_repo.list_notes(connection)
    statuses = retrieval_statuses(sought, documents, notes)
    current = current_documents(documents)
    latest = {note.reference_id: note for note in notes}
    rows = []
    for ref in sorted(statuses):
        document = current.get(ref)
        note = None if document is not None else latest.get(ref)
        rows.append(
            (
                ref,
                statuses[ref].value,
                None if document is None else document.origin.value,
                None if document is None else document.license,
                None if document is None else document.version,
                None if document is None else document.host_type,
                None if document is None else document.page_count,
                None if document is None else document.needs_ocr,
                None if document is None else document.sha256,
                None if note is None else note.reason,
            )
        )
    header = ("reference_id", "status", "origin", "license", "version", "host_type",
              "page_count", "needs_ocr", "sha256", "reason")  # fmt: skip
    return {"textes.csv": csv_text(header, rows)}


def _fulltext_screening_files(folder: ProjectFolder) -> dict[str, str]:
    """State of the full-text screening of each text of the main round."""
    from revue_portee.screening import fulltext  # imported here: import cycle with the reports

    header = ("reference_id", "final_decision_id", "ai_decision_id", "primary_reason",
              "disagreement", "reconciled")  # fmt: skip
    if fulltext.main_round(folder) is None:
        return {"etat-texte-integral.csv": csv_text(header, [])}
    state = fulltext.main_state(folder)
    rows = [
        (
            ref,
            state.final[ref].id if ref in state.final else None,
            state.ai[ref].id if ref in state.ai else None,
            state.reason(ref),
            ref in state.disagreements,
            ref in state.reconciled,
        )
        for ref in state.members
    ]
    return {"etat-texte-integral.csv": csv_text(header, rows)}


def _study_files(folder: ProjectFolder) -> dict[str, str]:
    """Studies of the included reports, and the person's decisions on pairs of reports."""
    from revue_portee.screening import studies  # imported here: import cycle with the reports

    state = studies.study_state(folder)
    reports = csv_text(
        ("reference_id", "study", "primary"),
        ((ref, s.primary, ref == s.primary) for s in state.studies for ref in s.reports),
    )
    links = csv_text(
        ("reference_a_id", "reference_b_id", "outcome", "decision_id"),
        ((a, b, d.outcome.value, d.id) for (a, b), d in sorted(state.decisions.items())),
    )
    return {"etudes.csv": reports, "liens-etudes.csv": links}


def _extraction_files(folder: ProjectFolder) -> dict[str, str]:
    """The grid, every extracted value (no quote nor note), the values kept for the
    synthesis, the extraction pilots and the comments on the gaps (tranches 3.1 to 3.5)."""
    # Imported here: the extraction reads the studies, which import the screening.
    from revue_portee.extraction import validation
    from revue_portee.stakeholders import comments as consultation_uc

    with folder.engine.connect() as connection:
        versions = grid_repo.list_versions(connection)
        comments = synthesis_repo.list_comments(connection)
        drafts = narrative_repo.list_drafts(connection)
        summaries = summary_repo.list_summaries(connection)
    grid = csv_text(
        ("version", "version_id", "status", "activated_at", "code", "label", "type",
         "definition", "guidance", "choices"),
        (
            (v.number, v.id, v.status.value,
             "" if v.activated_at is None else v.activated_at.isoformat(), f.code, f.label,
             f.type.value, f.definition, f.guidance, " | ".join(f.choices))
            for v in versions
            for f in v.sorted_fields()
        ),
    )  # fmt: skip
    gap_comments = csv_text(
        ("rows_field", "columns_field", "row", "column", "text", "created_at"),
        (
            (c.rows_field, c.columns_field, c.row, c.column, c.text, c.created_at.isoformat())
            for c in comments
        ),
    )
    narratives = csv_text(
        ("draft_id", "field", "status", "reviewer_kind", "ai_call_id", "supersedes_id",
         "created_at", "sentence", "text", "study_ids"),
        (
            (d.id, d.field_code, d.status.value, d.reviewer_kind.value, d.ai_call_id or "",
             d.supersedes_id or "", d.created_at.isoformat(), number, s.text,
             " ".join(s.study_ids))
            for d in drafts
            for number, s in enumerate(d.sentences, start=1)
        ),
    )  # fmt: skip
    lay = csv_text(
        ("summary_id", "level", "language", "status", "reviewer_kind", "ai_call_id",
         "supersedes_id", "created_at", "title", "text", "readability_formula",
         "readability_index", "words", "sentences", "syllables"),
        (
            (s.id, s.level.value, s.language, s.status.value, s.reviewer_kind.value,
             s.ai_call_id or "", s.supersedes_id or "", s.created_at.isoformat(), s.title,
             s.text, *(("", "", "", "", "") if (r := s.readability) is None
                       else (r.formula, r.index, r.words, r.sentences, r.syllables)))
            for s in summaries
        ),
    )  # fmt: skip
    consultation = consultation_uc.consultation_state(folder)
    people = csv_text(
        ("stakeholder", "role", "organisation", "created_at"),
        (
            (consultation.codes[p.id], p.role, p.organisation, p.created_at.isoformat())
            for p in sorted(consultation.stakeholders, key=lambda p: consultation.codes[p.id])
        ),
    )
    kept, _count = validation.extraction_tables(folder)
    return kept | {
        # Stakeholders by code, role and organisation, never by name; comments and
        # responses without their text (unpublished communications) (tranche 4.2).
        "parties-prenantes.csv": people,
        "suivi-commentaires.csv": consultation_uc.follow_up_csv(consultation, with_text=False),
        "syntheses-vulgarisees.csv": lay,
        "syntheses-narratives.csv": narratives,
        "grille.csv": grid,
        "valeurs-extraites.csv": validation.history_table(folder),
        "pilotes-extraction.csv": validation.pilots_table(folder),
        "commentaires-lacunes.csv": gap_comments,
    }


def _exports(folder: ProjectFolder, *, now: Clock, tool_version: str) -> dict[str, bytes]:
    report = flow_report(folder, now=now, tool_version=tool_version)
    data = methods_data(folder, now=now, tool_version=tool_version)
    files: dict[str, bytes] = {
        "donnees/diagramme.json": (report.numbers.model_dump_json(indent=1) + "\n").encode()
    }
    for language in EXPORT_LANGUAGES:
        svg = render_flow_svg(report.numbers, flow_template(), report.context, language=language)
        files[f"exports/diagramme-{language}.svg"] = svg.encode()
        document = build_methods(data, language=language)
        markdown = f"exports/methode-{language}.{ExportFormat.MARKDOWN.value}"
        files[markdown] = render_markdown(document).encode()
        files[f"exports/methode-{language}.{ExportFormat.DOCX.value}"] = render_docx(document)
    return files


@cache
def _environment() -> Environment:
    return Environment(
        loader=PackageLoader("revue_portee.reporting", "templates"),
        autoescape=False,  # noqa: S701 - Markdown, not HTML
        keep_trailing_newline=True,
    )


def archive_files(
    folder: ProjectFolder, kind: ArchiveKind, *, now: Clock, tool_version: str
) -> dict[str, bytes]:
    """Every file of the archive, by its path in the archive."""
    moment = now()
    files: dict[str, bytes] = {}
    state = dedup_state(folder)
    tables = (
        readable_tables(folder)
        | _dedup_files(state)
        | _screening_files(folder, state)
        | _fulltext_files(folder)
        | _fulltext_screening_files(folder)
        | _study_files(folder)
        | _extraction_files(folder)
    )
    files |= {f"donnees/{name}": text.encode() for name, text in tables.items()}
    files |= _exports(folder, now=lambda: moment, tool_version=tool_version)
    files[PROJECT_FILE] = (folder.path / PROJECT_FILE).read_bytes()
    copied = COPIED_FOLDERS if kind is ArchiveKind.COMPLETE else ("etalonnage",)
    for name in copied:
        for path in sorted((folder.path / name).rglob("*")):
            if path.is_file():
                files[path.relative_to(folder.path).as_posix()] = path.read_bytes()
    if kind is ArchiveKind.COMPLETE:
        files[DATABASE_FILE] = database_copy(folder)
    with folder.engine.connect() as connection:
        title = projects.get_project(connection).title
    readme = (
        _environment()
        .get_template("archive_readme.md.j2")
        .render(
            title=title,
            public=kind is ArchiveKind.PUBLIC,
            tool_version=tool_version,
            date=moment.date().isoformat(),
        )
    )
    files["LISEZMOI.md"] = readme.encode()
    return files


def _check_secrets(files: dict[str, bytes]) -> None:
    findings = []
    for name, content in sorted(files.items()):
        if not name.endswith(TEXT_SUFFIXES):
            continue
        text = content.decode("utf-8")
        findings += [str(f) for f in scan_text(text, path=name)]
        if redact(text) != text:
            findings.append(f"{name}: {_('secret value')}")
    if findings:
        raise SecretInArchiveError(findings)


def export_archive(
    folder: ProjectFolder,
    *,
    kind: ArchiveKind = ArchiveKind.PUBLIC,
    now: Clock,
    tool_version: str,
) -> ArchiveResult:
    """Write the archive in ``exports/`` and record it in the journal."""
    moment = now()
    files = archive_files(folder, kind, now=lambda: moment, tool_version=tool_version)
    _check_secrets(files)
    root = f"{folder.path.stem}-archive-{kind.value}"
    stamp = moment.strftime("%Y%m%dT%H%M%SZ")
    target = folder.path / "exports" / f"archive-{kind.value}-{stamp}.zip"
    write_zip(target, {f"{root}/{name}": content for name, content in files.items()}, moment)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    relative = target.relative_to(folder.path).as_posix()
    with folder.write() as connection:
        journal.append_entry(
            connection,
            now=now(),
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.ARCHIVE_EXPORTED,
            subject_type="archive",
            subject_id=None,
            summary_fr=french("Archive exported ({kind}): {file}").format(
                kind=kind.value, file=relative
            ),
            tool_version=tool_version,
            payload={"kind": kind.value, "file": relative, "sha256": digest, "files": len(files)},
        )
    return ArchiveResult(path=target, sha256=digest, files=len(files))
