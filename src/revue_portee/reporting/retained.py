"""References kept at the title and abstract stage, for the next steps of the review.

The references whose decision in force is « include » or « uncertain » go on to the
full text (D-079, D-088). They are written as RIS, which reference managers (Zotero,
EndNote) and screening tools (Covidence, Rayyan) import, and as CSV. Each record names
its identifier in the project and the decision that kept it, so that a reference can
be found again in the archive. Pure functions: no I/O.
"""

import csv
import io
import re
from collections.abc import Iterable
from dataclasses import dataclass

from revue_portee.domain.references import Reference
from revue_portee.domain.screening import Decision

__all__ = ["RetainedReference", "ris_type", "write_csv", "write_ris"]

# Document types given by the sources (OpenAlex, Crossref) and their RIS type.
_RIS_TYPES = {
    "article": "JOUR",
    "journal-article": "JOUR",
    "review": "JOUR",
    "letter": "JOUR",
    "editorial": "JOUR",
    "book": "BOOK",
    "monograph": "BOOK",
    "book-chapter": "CHAP",
    "chapter": "CHAP",
    "dissertation": "THES",
    "report": "RPRT",
    "proceedings-article": "CPAPER",
    "preprint": "UNPB",
    "posted-content": "UNPB",
    "dataset": "DATA",
}
_RIS_CODE = re.compile(r"^[A-Z]{2,6}$")


@dataclass(frozen=True, slots=True)
class RetainedReference:
    reference: Reference
    decision: Decision  # the decision in force (human), include or uncertain
    criteria_version: int


def ris_type(reference: Reference) -> str:
    """The RIS type of a reference: kept when the source gave one, else mapped."""
    given = reference.doc_type.strip()
    if _RIS_CODE.fullmatch(given):
        return given
    mapped = _RIS_TYPES.get(given.casefold())
    if mapped:
        return mapped
    return "JOUR" if reference.container_title else "GEN"


def _line(value: str) -> str:
    """One RIS line holds one value: line breaks inside it become spaces."""
    return " ".join(value.split())


def _pages(pages: str) -> list[tuple[str, str]]:
    start, separator, end = pages.partition("-")
    if separator and start.strip() and end.strip():
        return [("SP", start.strip()), ("EP", end.strip())]
    return [("SP", pages.strip())] if pages.strip() else []


def _note(item: RetainedReference) -> str:
    ref = item.reference
    parts = [f"revue-portee: {ref.id}", f"decision: {item.decision.value.value}"]
    parts.append(f"criteria version: {item.criteria_version}")
    if ref.pmid:
        parts.append(f"PMID: {ref.pmid}")
    if ref.openalex_id:
        parts.append(f"OpenAlex: {ref.openalex_id}")
    return "; ".join(parts)


def _record(item: RetainedReference) -> list[str]:
    ref = item.reference
    fields: list[tuple[str, str]] = [("TY", ris_type(ref)), ("TI", ref.title)]
    fields += [("AU", author) for author in ref.authors]
    fields += [
        ("PY", "" if ref.year is None else str(ref.year)),
        ("JO", ref.container_title),
        ("VL", ref.volume),
        ("IS", ref.issue),
        *_pages(ref.pages),
        ("DO", ref.doi),
        ("LA", ref.language),
        ("UR", ref.url),
        ("AB", ref.abstract),
        ("KW", f"revue-portee: {item.decision.value.value}"),
        ("N1", _note(item)),
        ("ID", ref.id),
    ]
    lines = [f"{tag}  - {_line(value)}" for tag, value in fields if _line(value)]
    return [*lines, "ER  - "]


def write_ris(items: Iterable[RetainedReference]) -> str:
    """The references as RIS, one record after another, separated by a blank line."""
    records = ["\n".join(_record(item)) for item in items]
    return "\n\n".join(records) + ("\n" if records else "")


_CSV_HEADER = (
    "reference_id", "decision", "decision_context", "criteria_version", "title", "authors",
    "year", "container_title", "volume", "issue", "pages", "doi", "pmid", "openalex_id",
    "language", "doc_type", "url", "abstract",
)  # fmt: skip


def write_csv(items: Iterable[RetainedReference]) -> str:
    """The references as CSV (comma-separated, UTF-8, one row each)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(_CSV_HEADER)
    for item in items:
        ref = item.reference
        writer.writerow(
            (
                ref.id,
                item.decision.value.value,
                item.decision.context.value,
                item.criteria_version,
                ref.title,
                "; ".join(ref.authors),
                "" if ref.year is None else ref.year,
                ref.container_title,
                ref.volume,
                ref.issue,
                ref.pages,
                ref.doi,
                ref.pmid,
                ref.openalex_id,
                ref.language,
                ref.doc_type,
                ref.url,
                ref.abstract,
            )
        )
    return buffer.getvalue()
