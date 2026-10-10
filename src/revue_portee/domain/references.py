"""References, their provenance, collection runs and RIS imports (EF-COL-01 to 05).

A reference is stored once, as received, and never changed: enrichment by Crossref
adds an :class:`Enrichment` and :func:`merged` gives the reference with the missing
fields filled (EF-COL-02). Every reference keeps the provenance of each time a source
gave it (EF-COL-05).
"""

import re
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from revue_portee.domain.protocol import normalize_doi
from revue_portee.domain.search import Database

__all__ = [
    "ENRICHABLE_FIELDS",
    "CollectionEnd",
    "CollectionPage",
    "CollectionRun",
    "CollectionStatus",
    "Enrichment",
    "ImportFile",
    "ImportIssue",
    "IssueKind",
    "Provenance",
    "Reference",
    "SourceKind",
    "clean_doi",
    "clean_pmid",
    "merged",
    "missing_fields",
]


class SourceKind(StrEnum):
    OPENALEX = "openalex"
    PUBMED = "pubmed"
    RIS = "ris"
    # An included study of a published review, replayed stepwise (replication, D-104).
    REFERENCE_STANDARD = "reference_standard"


class Reference(BaseModel):
    """Bibliographic fields, normalized; empty strings and tuples when unknown."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    title: str = ""
    abstract: str = ""
    authors: tuple[str, ...] = ()
    year: int | None = Field(default=None, ge=1000, le=2100)
    container_title: str = ""  # journal, book or conference
    volume: str = ""
    issue: str = ""
    pages: str = ""
    doi: str = ""  # normalized (upper case, no resolver)
    pmid: str = ""
    openalex_id: str = ""  # short form, e.g. W2741809807
    language: str = ""
    doc_type: str = ""
    url: str = ""
    created_at: AwareDatetime


# Fields that Crossref may fill when the source left them empty.
ENRICHABLE_FIELDS = ("title", "abstract", "authors", "year", "container_title", "volume",
                     "issue", "pages")  # fmt: skip


def missing_fields(reference: Reference) -> tuple[str, ...]:
    return tuple(name for name in ENRICHABLE_FIELDS if not getattr(reference, name))


class Enrichment(BaseModel):
    """Fields found by Crossref for a reference whose DOI it knows."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    reference_id: str
    source: str = "crossref"
    fields: dict[str, str | int | list[str]]  # only fields that were missing
    raw_dir: str
    created_at: AwareDatetime


def merged(reference: Reference, enrichments: list[Enrichment]) -> Reference:
    """The reference with its missing fields taken from the enrichments, oldest first;
    a field present in the reference is never replaced."""
    update: dict[str, object] = {}
    for enrichment in enrichments:
        for name, value in enrichment.fields.items():
            if name in ENRICHABLE_FIELDS and not getattr(reference, name) and name not in update:
                update[name] = tuple(value) if isinstance(value, list) else value
    return reference.model_copy(update=update) if update else reference


class Provenance(BaseModel):
    """One time a source gave a reference (EF-COL-05)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    reference_id: str
    source: SourceKind
    original_id: str  # OpenAlex work, PMID, or RIS accession number / position
    collection_run_id: str | None = None
    import_file_id: str | None = None
    query_id: str | None = None
    page: int | None = None  # raw page (collection) or record position (import)
    created_at: AwareDatetime


class CollectionRun(BaseModel):
    """Collection of every record of a query, page by page (EF-COL-01)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    query_id: str
    database: Database
    query_text: str
    started_at: AwareDatetime
    reviewer_id: str


class CollectionPage(BaseModel):
    """A page stored with its references, in one transaction: the unit of resumption."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    number: int = Field(ge=1)
    announced: int = Field(ge=0)  # number of records announced by the API
    record_count: int = Field(ge=0)  # records in the page
    new_references: int = Field(ge=0)
    next_cursor: str | None  # None after the last page
    raw_path: str  # brut/sources/<run_id>/page-NNNN.json.gz
    created_at: AwareDatetime


class CollectionStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class CollectionEnd(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    status: CollectionStatus
    announced: int | None
    collected: int  # distinct records collected
    discrepancy: str = ""  # explanation when collected differs from announced
    error: str = ""
    ended_at: AwareDatetime


class IssueKind(StrEnum):
    EMPTY = "empty"  # a record with no usable field
    NO_TYPE = "no_type"  # lines before any TY tag
    UNTERMINATED = "unterminated"  # a record not closed by ER
    BAD_LINE = "bad_line"  # a line that is neither a tag nor a continuation


class ImportIssue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: IssueKind
    line: int  # first line concerned (1-based)
    record: int | None = None  # record position (1-based), if any
    text: str = ""  # the beginning of the line concerned


class ImportFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    filename: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    format: str = "ris"
    database_declared: str  # e.g. "PsycINFO (EBSCOhost)"
    imported_at: AwareDatetime
    record_count: int  # valid records imported
    issues: tuple[ImportIssue, ...] = ()
    reviewer_id: str


_PMID = re.compile(r"^(?:pmid:?\s*)?([1-9][0-9]{0,8})$", re.IGNORECASE)


def clean_doi(value: str) -> str:
    """Normalized DOI, or "" when ``value`` holds none."""
    text = value.strip()
    if not text:
        return ""
    match = re.search(r"10\.\d{4,9}/\S+", text)
    if match is None:
        return ""
    try:
        return normalize_doi(match.group(0).rstrip(".,;)"))
    except ValueError:
        return ""


def clean_pmid(value: str) -> str:
    match = _PMID.match(value.strip())
    return match.group(1) if match else ""
