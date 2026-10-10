"""Retrieval of the full texts of the references kept at the title and abstract stage
(EF-COL-02, EF-SEL-14, EF-SEL-15; docs/10-conception-texte-integral.md §2).

Open access versions are looked for in OpenAlex, then Unpaywall; the team uploads the
others, one by one or as a set of files matched by DOI then title. A reference whose
text cannot be had is declared not retrievable by the person, with a reason.

Each reference is recorded in its own transaction, after its raw answers and files:
a retrieval stopped midway resumes with the references not yet looked for (D-059).
The PDF and its text by page are kept in ``textes/`` (``<sha256>.pdf`` and
``<sha256>.pages.json``), which never goes into an archive (D-092); their URL and file
name stay out of the journal, which the public archive contains.
"""

import csv
import hashlib
import io
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import JsonValue

from revue_portee.domain.fulltext import (
    FulltextDocument,
    FulltextOrigin,
    MatchKind,
    PagedText,
    RetrievalCounts,
    RetrievalNote,
    RetrievalStatus,
    current_documents,
    match_upload,
    retrieval_counts,
    retrieval_statuses,
)
from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.domain.references import Reference
from revue_portee.fulltext.convert import (
    CONVERSION,
    CONVERTER,
    ConversionError,
    convert_pdf,
    needs_ocr,
)
from revue_portee.i18n import french
from revue_portee.i18n import gettext as _
from revue_portee.screening.report import sought_references
from revue_portee.sources.http import SourceError
from revue_portee.sources.records import OpenAccessLocation
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.raw import remove_source_pages, write_source_pages
from revue_portee.storage.repositories import fulltext as fulltext_repo
from revue_portee.storage.repositories import journal

__all__ = [
    "TEXT_FOLDER",
    "FulltextError",
    "OpenAccessFinder",
    "RetrievalReport",
    "RetrievalRow",
    "RetrievalSummary",
    "UploadOutcome",
    "UploadReport",
    "add_upload",
    "declare_not_retrievable",
    "export_missing",
    "paged_text",
    "reconvert",
    "retrieval_report",
    "retrieve_open_access",
    "upload_files",
]

Clock = Callable[[], datetime]
TEXT_FOLDER = "textes"
FIRST_PAGES = 2  # pages read to match an uploaded file to its reference


class FulltextError(ValueError):
    """An action on full texts that cannot be done (French message)."""


class OpenAccessFinder(Protocol):
    """Open access sources and the download of their PDFs (tests give a fake one)."""

    def openalex(self, reference: Reference) -> tuple[list[OpenAccessLocation], dict[str, Any]]: ...

    def unpaywall(self, doi: str) -> tuple[list[OpenAccessLocation], dict[str, Any]]: ...

    def download(self, url: str) -> bytes: ...


# --- State ----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RetrievalRow:
    reference: Reference
    status: RetrievalStatus
    document: FulltextDocument | None  # the document in force
    note: RetrievalNote | None  # the latest note, when there is no document


@dataclass(frozen=True, slots=True)
class RetrievalReport:
    counts: RetrievalCounts
    rows: list[RetrievalRow]  # sorted by title

    def row(self, reference_id: str) -> RetrievalRow | None:
        return next((r for r in self.rows if r.reference.id == reference_id), None)


def retrieval_report(folder: ProjectFolder) -> RetrievalReport:
    """Status of every reference sought for its full text (kept at the title and
    abstract stage, D-079; ``screening.report.sought_references``)."""
    sought = sought_references(folder)
    with folder.engine.connect() as connection:
        documents = fulltext_repo.list_documents(connection)
        notes = fulltext_repo.list_notes(connection)
    ids = [r.id for r in sought]
    statuses = retrieval_statuses(ids, documents, notes)
    current = current_documents(documents)
    latest: dict[str, RetrievalNote] = {}
    for note in notes:
        latest[note.reference_id] = note
    rows = [
        RetrievalRow(
            reference=r,
            status=statuses[r.id],
            document=current.get(r.id),
            note=None if r.id in current else latest.get(r.id),
        )
        for r in sought
    ]
    return RetrievalReport(counts=retrieval_counts(ids, documents, notes), rows=rows)


def _sought(folder: ProjectFolder, reference_id: str) -> RetrievalRow:
    row = retrieval_report(folder).row(reference_id)
    if row is None:
        raise FulltextError(
            _("This reference is not sought for its full text (it was not kept at screening).")
        )
    return row


# --- Files ----------------------------------------------------------------------------


def _paths(folder: ProjectFolder, sha256: str, conversion: int = CONVERSION) -> tuple[Path, Path]:
    """The PDF and the text of one conversion of it."""
    base = folder.path / TEXT_FOLDER
    text = f"{sha256}.pages.json" if conversion == 1 else f"{sha256}.c{conversion}.pages.json"
    return base / f"{sha256}.pdf", base / text


def _store_files(folder: ProjectFolder, data: bytes, text: PagedText) -> tuple[str, list[Path]]:
    """Write the PDF and its text (once per content); return the hash and the files
    created by this call, to remove if the recording fails."""
    sha256 = hashlib.sha256(data).hexdigest()
    created = []
    pdf, pages = _paths(folder, sha256)
    pdf.parent.mkdir(parents=True, exist_ok=True)
    for path, content in ((pdf, data), (pages, text.model_dump_json().encode("utf-8"))):
        if not path.exists():
            path.write_bytes(content)
            created.append(path)
    return sha256, created


def paged_text(folder: ProjectFolder, document: FulltextDocument) -> PagedText:
    """Text by page of a document."""
    _pdf, pages = _paths(folder, document.sha256, document.conversion)
    return PagedText.model_validate_json(pages.read_bytes())


def _convert(data: bytes) -> PagedText:
    try:
        return convert_pdf(data)
    except ConversionError as error:
        raise FulltextError(str(error)) from error


def _record_document(
    folder: ProjectFolder,
    reference: Reference,
    data: bytes,
    text: PagedText,
    *,
    origin: FulltextOrigin,
    location: OpenAccessLocation | None = None,
    filename: str = "",
    raw_dir: str = "",
    reconverted: FulltextDocument | None = None,
    now: Clock,
    tool_version: str,
) -> FulltextDocument:
    """Record a document; ``reconverted`` is the document whose PDF was converted again
    (its source fields are kept)."""
    moment = now()
    if reconverted is not None:
        location = OpenAccessLocation(
            reconverted.url, reconverted.license, reconverted.version, reconverted.host_type
        )
        filename, raw_dir = reconverted.filename, reconverted.raw_dir
    sha256, created = _store_files(folder, data, text)
    document = FulltextDocument(
        id=new_ulid(moment),
        reference_id=reference.id,
        origin=origin,
        url="" if location is None else location.pdf_url,
        license="" if location is None else location.license,
        version="" if location is None else location.version,
        host_type="" if location is None else location.host_type,
        filename=filename,
        sha256=sha256,
        page_count=len(text.pages),
        text_chars=sum(len("".join(p.text.split())) for p in text.pages),
        needs_ocr=needs_ocr(text),
        references_page=None if text.references_start is None else text.references_start.page,
        converter=CONVERTER,
        raw_dir=raw_dir,
        created_at=moment,
        reviewer_id=folder.reviewer_id,
    )
    uploaded = origin is FulltextOrigin.UPLOAD
    if reconverted is not None:
        entry_type = EntryType.FULLTEXT_CONVERTED
        summary = french("Full text converted again ({converter}): {pages} pages")
    elif uploaded:
        entry_type = EntryType.FULLTEXT_UPLOADED
        summary = french("Full text uploaded: {pages} pages")
    else:
        entry_type = EntryType.FULLTEXT_OBTAINED
        summary = french("Full text obtained in open access ({source}): {pages} pages")
    try:
        with folder.write() as connection:
            entry = journal.append_entry(
                connection,
                now=moment,
                actor_reviewer_id=folder.reviewer_id,
                entry_type=entry_type,
                subject_type="reference",
                subject_id=reference.id,
                summary_fr=summary.format(
                    pages=document.page_count, source=origin.value, converter=CONVERTER
                ),
                tool_version=tool_version,
                payload={
                    "document_id": document.id,
                    "origin": origin.value,
                    "sha256": sha256,
                    "page_count": document.page_count,
                    "needs_ocr": document.needs_ocr,
                    "references_page": document.references_page,
                    "license": document.license,
                    "version": document.version,
                    "host_type": document.host_type,
                    "converter": CONVERTER,
                    "raw_dir": raw_dir,
                    "replaces": None if reconverted is None else reconverted.id,
                },
            )
            fulltext_repo.insert_document(connection, document, journal_entry_id=entry.id)
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return document


def _record_note(
    folder: ProjectFolder,
    reference: Reference,
    status: RetrievalStatus,
    reason: str,
    *,
    raw_dir: str = "",
    now: Clock,
    tool_version: str,
) -> RetrievalNote:
    moment = now()
    note = RetrievalNote(
        id=new_ulid(moment),
        reference_id=reference.id,
        status=status,
        reason=reason,
        raw_dir=raw_dir,
        created_at=moment,
        reviewer_id=folder.reviewer_id,
    )
    declared = status is RetrievalStatus.NOT_RETRIEVABLE
    if declared:
        summary = french("Full text declared not retrievable: {reason}").format(reason=reason)
    else:
        summary = french("Full text not found in open access")
    with folder.write() as connection:
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=(
                EntryType.FULLTEXT_NOT_RETRIEVABLE if declared else EntryType.FULLTEXT_NOT_FOUND
            ),
            subject_type="reference",
            subject_id=reference.id,
            summary_fr=summary,
            tool_version=tool_version,
            payload={
                "note_id": note.id,
                "status": status.value,
                "reason": reason,
                "raw_dir": raw_dir,
            },
        )
        fulltext_repo.insert_note(connection, note, journal_entry_id=entry.id)
    return note


# --- Open access ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RetrievalSummary:
    looked_for: int
    obtained: int
    not_found: int


def _look_for(
    folder: ProjectFolder,
    reference: Reference,
    finder: OpenAccessFinder,
    *,
    now: Clock,
    tool_version: str,
) -> bool:
    """Look for one reference in OpenAlex, then Unpaywall; record what was found.

    A source that cannot answer stops the retrieval (nothing is recorded for this
    reference); a PDF that cannot be downloaded or read only moves on to the next."""
    answers: list[JsonValue] = []
    attempts: list[JsonValue] = []
    asks: list[tuple[FulltextOrigin, Callable[[], tuple[list[OpenAccessLocation], Any]]]] = [
        (FulltextOrigin.OPENALEX, lambda: finder.openalex(reference)),
    ]
    if reference.doi:
        asks.append((FulltextOrigin.UNPAYWALL, lambda: finder.unpaywall(reference.doi)))
    tried: set[str] = set()
    found: tuple[FulltextOrigin, OpenAccessLocation, bytes, PagedText] | None = None
    for origin, ask in asks:
        locations, raw = ask()
        answers.append({"source": origin.value, "answer": raw})
        for location in locations:
            if location.pdf_url in tried:
                continue
            tried.add(location.pdf_url)
            try:
                data = finder.download(location.pdf_url)
                text = convert_pdf(data)
            except (SourceError, ConversionError) as error:
                attempts.append(
                    {"source": origin.value, "url": location.pdf_url, "error": str(error)}
                )
                continue
            attempts.append({"source": origin.value, "url": location.pdf_url, "error": None})
            found = (origin, location, data, text)
            break
        if found is not None:
            break
    item_id = new_ulid(now())
    raw_dir = write_source_pages(folder.path, item_id, [*answers, {"downloads": attempts}])
    try:
        if found is None:
            _record_note(
                folder, reference, RetrievalStatus.NOT_FOUND,
                french("no open access PDF could be downloaded ({count} tried)").format(
                    count=len(attempts)
                ),
                raw_dir=raw_dir, now=now, tool_version=tool_version,
            )  # fmt: skip
            return False
        origin, location, data, text = found
        _record_document(
            folder, reference, data, text, origin=origin, location=location, raw_dir=raw_dir,
            now=now, tool_version=tool_version,
        )  # fmt: skip
    except BaseException:
        remove_source_pages(folder.path, raw_dir)
        raise
    return True


def retrieve_open_access(
    folder: ProjectFolder,
    *,
    now: Clock,
    tool_version: str,
    finder: Callable[[], OpenAccessFinder],
    retry_not_found: bool = False,
    limit: int | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> RetrievalSummary:
    """Look for the open access PDF of the references never looked for (and, with
    ``retry_not_found``, of those not found before), ``limit`` at most."""
    wanted = {RetrievalStatus.NOT_SOUGHT}
    if retry_not_found:
        wanted.add(RetrievalStatus.NOT_FOUND)
    candidates = [r.reference for r in retrieval_report(folder).rows if r.status in wanted]
    candidates = candidates[:limit]
    if not candidates:
        return RetrievalSummary(looked_for=0, obtained=0, not_found=0)
    source = finder()
    obtained = 0
    try:
        for done, reference in enumerate(candidates, start=1):
            if _look_for(folder, reference, source, now=now, tool_version=tool_version):
                obtained += 1
            if progress is not None:
                progress(done, len(candidates))
    finally:
        close = getattr(source, "close", None)
        if callable(close):
            close()
    return RetrievalSummary(
        looked_for=len(candidates), obtained=obtained, not_found=len(candidates) - obtained
    )


def reconvert(folder: ProjectFolder, *, now: Clock, tool_version: str) -> int:
    """Convert again, with the rules in force, the documents in force converted by an
    older version: each new conversion is added as a document (the old one stays, with
    its text, D-028). Returns the number of documents converted again."""
    done = 0
    for row in retrieval_report(folder).rows:
        document = row.document
        if document is None or document.conversion >= CONVERSION:
            continue
        pdf, _text = _paths(folder, document.sha256, document.conversion)
        data = pdf.read_bytes()
        _record_document(
            folder, row.reference, data, _convert(data), origin=document.origin,
            reconverted=document, now=now, tool_version=tool_version,
        )  # fmt: skip
        done += 1
    return done


# --- Uploads and declarations ---------------------------------------------------------


def add_upload(
    folder: ProjectFolder,
    reference_id: str,
    data: bytes,
    *,
    filename: str,
    now: Clock,
    tool_version: str,
) -> FulltextDocument:
    """Add a PDF obtained by the team for a reference sought; the same file already in
    force for it is not added again."""
    row = _sought(folder, reference_id)
    text = _convert(data)
    if row.document is not None and row.document.sha256 == hashlib.sha256(data).hexdigest():
        return row.document
    return _record_document(
        folder, row.reference, data, text, origin=FulltextOrigin.UPLOAD,
        filename=Path(filename).name, now=now, tool_version=tool_version,
    )  # fmt: skip


@dataclass(frozen=True, slots=True)
class UploadOutcome:
    filename: str
    reference_id: str | None = None
    kind: MatchKind | None = None
    message: str = ""  # why the file was not added


@dataclass(frozen=True, slots=True)
class UploadReport:
    added: list[UploadOutcome] = field(default_factory=list)
    already: list[UploadOutcome] = field(default_factory=list)  # same file already in force
    unmatched: list[UploadOutcome] = field(default_factory=list)
    unreadable: list[UploadOutcome] = field(default_factory=list)


def upload_files(
    folder: ProjectFolder,
    files: Iterable[tuple[str, bytes]],
    *,
    now: Clock,
    tool_version: str,
) -> UploadReport:
    """Add a set of PDFs, each matched to a reference sought by the DOI in its name,
    the DOI in its first pages, then the title (docs/10 §2.1.1). Files that match no
    reference, or more than one, are listed and not added."""
    report = UploadReport()
    sought = {row.reference.id: row for row in retrieval_report(folder).rows}
    dois = {ref: row.reference.doi for ref, row in sought.items()}
    titles = {ref: row.reference.title for ref, row in sought.items()}
    for name, data in files:
        filename = Path(name).name
        try:
            text = _convert(data)
        except FulltextError as error:
            report.unreadable.append(UploadOutcome(filename=filename, message=str(error)))
            continue
        first = "\n".join(page.text for page in text.pages[:FIRST_PAGES])
        match = match_upload(filename, first, dois, titles)
        if match.reference_id is None:
            report.unmatched.append(UploadOutcome(filename=filename))
            continue
        row = sought[match.reference_id]
        outcome = UploadOutcome(filename=filename, reference_id=row.reference.id, kind=match.kind)
        if row.document is not None and row.document.sha256 == hashlib.sha256(data).hexdigest():
            report.already.append(outcome)
            continue
        document = _record_document(
            folder, row.reference, data, text, origin=FulltextOrigin.UPLOAD, filename=filename,
            now=now, tool_version=tool_version,
        )  # fmt: skip
        sought[row.reference.id] = RetrievalRow(
            reference=row.reference, status=RetrievalStatus.OBTAINED, document=document, note=None
        )
        report.added.append(outcome)
    return report


def declare_not_retrievable(
    folder: ProjectFolder,
    reference_id: str,
    reason: str,
    *,
    now: Clock,
    tool_version: str,
) -> RetrievalNote:
    """Declare that the full text of a reference cannot be obtained (counted in the
    diagram as "Reports not retrieved"); a text added later takes precedence."""
    reason = " ".join(reason.split())
    if not reason:
        raise FulltextError(_("Give the reason why the full text cannot be obtained."))
    row = _sought(folder, reference_id)
    if row.document is not None:
        raise FulltextError(_("A full text is already obtained for this reference."))
    return _record_note(
        folder, row.reference, RetrievalStatus.NOT_RETRIEVABLE, reason, now=now,
        tool_version=tool_version,
    )  # fmt: skip


# --- References still without a text -------------------------------------------------

_MISSING_HEADER = (
    "reference_id", "status", "doi", "pmid", "title", "authors", "year", "container_title",
    "volume", "issue", "pages", "reason",
)  # fmt: skip


def export_missing(folder: ProjectFolder) -> tuple[Path, int]:
    """Write ``exports/textes-manquants.csv``: the references sought without a text,
    to look for through the institution's access. Returns the file and its rows."""
    rows = [r for r in retrieval_report(folder).rows if r.document is None]
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(_MISSING_HEADER)
    for row in rows:
        ref = row.reference
        writer.writerow(
            (
                ref.id, row.status.value, ref.doi, ref.pmid, ref.title, "; ".join(ref.authors),
                "" if ref.year is None else ref.year, ref.container_title, ref.volume,
                ref.issue, ref.pages, "" if row.note is None else row.note.reason,
            )
        )  # fmt: skip
    target = folder.path / "exports" / "textes-manquants.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(buffer.getvalue(), encoding="utf-8")
    return target, len(rows)
