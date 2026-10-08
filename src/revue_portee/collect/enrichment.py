"""Enrichment of references by DOI with Crossref (EF-COL-02).

For each reference with a DOI and missing fields, not yet checked, Crossref is asked
(at most three requests at a time). Only fields the reference lacks are recorded,
in an :class:`Enrichment`: the reference itself never changes. A DOI unknown to
Crossref is recorded too (empty enrichment), so it is not asked again.
"""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from pydantic import JsonValue

from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.domain.references import Enrichment, Reference, merged, missing_fields
from revue_portee.i18n import french
from revue_portee.sources import close_source, default_crossref
from revue_portee.sources.crossref import MAX_CONCURRENCY, fields_from_work
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.raw import remove_source_pages, write_source_pages
from revue_portee.storage.repositories import journal
from revue_portee.storage.repositories import references as references_repo

__all__ = [
    "EnrichmentSummary",
    "WorkSource",
    "enrich_references",
    "enrichment_candidates",
    "references_with_enrichment",
]

Clock = Callable[[], datetime]


class WorkSource(Protocol):
    def work(self, doi: str) -> tuple[dict[str, Any] | None, dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class EnrichmentSummary:
    checked: int
    enriched: int  # references that received at least one field
    not_found: int  # DOIs unknown to Crossref
    fields: int  # fields added in total


def enrichment_candidates(folder: ProjectFolder) -> list[Reference]:
    """References with a DOI and missing fields, never checked with Crossref."""
    with folder.engine.connect() as connection:
        checked = references_repo.list_enrichments(connection)
        return [
            r
            for r in references_repo.list_references(connection)
            if r.doi and missing_fields(r) and r.id not in checked
        ]


def enrich_references(
    folder: ProjectFolder,
    *,
    now: Clock,
    tool_version: str,
    source: Callable[[], WorkSource] = default_crossref,
    limit: int | None = None,
    max_workers: int = MAX_CONCURRENCY,
) -> EnrichmentSummary:
    """Ask Crossref for the missing fields of the candidates (``limit`` at most)."""
    candidates = enrichment_candidates(folder)[:limit]
    if not candidates:
        return EnrichmentSummary(checked=0, enriched=0, not_found=0, fields=0)
    crossref = source()
    try:
        with ThreadPoolExecutor(max_workers=min(max_workers, MAX_CONCURRENCY)) as pool:
            answers = list(pool.map(lambda r: crossref.work(r.doi), candidates))
    finally:
        close_source(crossref)
    moment = now()
    batch_id = new_ulid(moment)
    pages: list[JsonValue] = [raw for _work, raw in answers]
    raw_dir = write_source_pages(folder.path, batch_id, pages)
    try:
        with folder.write() as connection:
            items: list[Enrichment] = []
            for reference, (work, _raw) in zip(candidates, answers, strict=True):
                found = {} if work is None else fields_from_work(work)
                missing = set(missing_fields(reference))
                items.append(
                    Enrichment(
                        id=new_ulid(moment),
                        reference_id=reference.id,
                        fields={k: v for k, v in found.items() if k in missing},
                        raw_dir=raw_dir,
                        created_at=moment,
                    )
                )
            not_found = sum(1 for _w, _r in answers if _w is None)
            enriched = [e for e in items if e.fields]
            added = sum(len(e.fields) for e in items)
            entry = journal.append_entry(
                connection,
                now=moment,
                actor_reviewer_id=folder.reviewer_id,
                entry_type=EntryType.ENRICH_COMPLETED,
                subject_type="enrichment",
                subject_id=batch_id,
                summary_fr=french(
                    "Crossref: references completed: {enriched} of {checked} checked"
                ).format(enriched=len(enriched), checked=len(items)),
                tool_version=tool_version,
                payload={
                    "checked": len(items),
                    "enriched": len(enriched),
                    "not_found": not_found,
                    "fields_added": added,
                    "raw_dir": raw_dir,
                },
            )
            for item in items:
                references_repo.insert_enrichment(connection, item, journal_entry_id=entry.id)
    except BaseException:
        remove_source_pages(folder.path, raw_dir)
        raise
    return EnrichmentSummary(
        checked=len(items), enriched=len(enriched), not_found=not_found, fields=added
    )


def references_with_enrichment(folder: ProjectFolder) -> list[Reference]:
    """Every reference, its missing fields filled by Crossref when found."""
    with folder.engine.connect() as connection:
        enrichments = references_repo.list_enrichments(connection)
        return [
            merged(r, enrichments.get(r.id, []))
            for r in references_repo.list_references(connection)
        ]
