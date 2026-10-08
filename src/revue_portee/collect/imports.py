"""Import of RIS files exported from subscription databases (EF-COL-03, EF-COL-05).

The file is kept as is in ``imports/<sha256>.ris``; each valid record becomes a
reference with a provenance pointing to the file. Empty or malformed records are not
imported but listed with the import. A file is imported only once (same SHA-256).
"""

import hashlib
from collections.abc import Callable
from datetime import datetime

from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.domain.references import (
    ImportFile,
    Provenance,
    Reference,
    SourceKind,
)
from revue_portee.i18n import french
from revue_portee.i18n import gettext as _
from revue_portee.sources.ris import RisRecord, parse_ris
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import journal
from revue_portee.storage.repositories import references as references_repo

__all__ = [
    "AlreadyImportedError",
    "NothingToImportError",
    "UnreadableFileError",
    "import_ris",
    "imported_files",
]

Clock = Callable[[], datetime]


class AlreadyImportedError(ValueError):
    def __init__(self, existing: ImportFile) -> None:
        self.existing = existing
        super().__init__(
            _("This file was already imported on {date} (as « {name} »).").format(
                date=existing.imported_at.strftime("%Y-%m-%d"), name=existing.filename
            )
        )


class UnreadableFileError(ValueError):
    def __init__(self) -> None:
        super().__init__(_("The file is not a text file encoded in UTF-8 or Latin-1."))


class NothingToImportError(ValueError):
    def __init__(self) -> None:
        super().__init__(_("The file holds no RIS record (no line starting with « TY  - »)."))


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        return content.decode("cp1252")
    except UnicodeDecodeError as error:
        raise UnreadableFileError from error


def _reference(record: RisRecord, moment: datetime) -> Reference:
    return Reference(
        id=new_ulid(moment),
        title=record.title,
        abstract=record.abstract,
        authors=record.authors,
        year=record.year,
        container_title=record.container_title,
        volume=record.volume,
        issue=record.issue,
        pages=record.pages,
        doi=record.doi,
        pmid=record.pmid,
        language=record.language,
        doc_type=record.doc_type,
        url=record.url,
        created_at=moment,
    )


def import_ris(
    folder: ProjectFolder,
    filename: str,
    content: bytes,
    *,
    database: str = "",
    now: Clock,
    tool_version: str,
) -> ImportFile:
    """Import a RIS file. ``database`` is the database declared by the reviewer; when
    empty, the one named by the records is used."""
    sha256 = hashlib.sha256(content).hexdigest()
    with folder.engine.connect() as connection:
        existing = references_repo.get_import_by_sha256(connection, sha256)
    if existing is not None:
        raise AlreadyImportedError(existing)
    result = parse_ris(_decode(content))
    if result.total == 0:
        raise NothingToImportError
    detected = ", ".join(sorted(result.database_counts))
    declared = database.strip() or detected
    target = folder.path / "imports" / f"{sha256}.ris"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(content)
    with folder.write() as connection:
        moment = now()
        imported = ImportFile(
            id=new_ulid(moment),
            filename=filename,
            sha256=sha256,
            database_declared=declared,
            imported_at=moment,
            record_count=len(result.records),
            issues=result.issues,
            reviewer_id=folder.reviewer_id,
        )
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.IMPORT_COMPLETED,
            subject_type="import_file",
            subject_id=imported.id,
            summary_fr=french("RIS file imported: {count} records ({database})").format(
                count=len(result.records), database=declared
            ),
            tool_version=tool_version,
            payload={
                "filename": filename,
                "sha256": sha256,
                "database_declared": declared,
                "databases_detected": dict(result.database_counts),
                "records_found": result.total,
                "records_imported": len(result.records),
                "issues": [i.model_dump(mode="json") for i in result.issues],
            },
        )
        references_repo.insert_import(connection, imported, journal_entry_id=entry.id)
        for record in result.records:
            reference = _reference(record, moment)
            references_repo.insert_reference(connection, reference)
            references_repo.insert_provenance(
                connection,
                Provenance(
                    id=new_ulid(moment),
                    reference_id=reference.id,
                    source=SourceKind.RIS,
                    original_id=record.accession or f"#{record.position}",
                    import_file_id=imported.id,
                    page=record.position,
                    created_at=moment,
                ),
            )
    return imported


def imported_files(folder: ProjectFolder) -> list[ImportFile]:
    with folder.engine.connect() as connection:
        return references_repo.list_imports(connection)
