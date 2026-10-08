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
    "BATCH_SIZE",
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


BATCH_SIZE = 100


def _store_batch(
    folder: ProjectFolder,
    batch: list[Reference],
    answers: list[tuple[dict[str, Any] | None, dict[str, Any]]],
    *,
    now: Clock,
    tool_version: str,
) -> EnrichmentSummary:
    """Record one batch, with its raw answers and journal entry, in one transaction."""
    moment = now()
    batch_id = new_ulid(moment)
    pages: list[JsonValue] = [raw for _work, raw in answers]
    raw_dir = write_source_pages(folder.path, batch_id, pages)
    try:
        with folder.write() as connection:
            items: list[Enrichment] = []
            for reference, (work, _raw) in zip(batch, answers, strict=True):
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
            summary = EnrichmentSummary(
                checked=len(items),
                enriched=sum(1 for e in items if e.fields),
                not_found=sum(1 for work, _raw in answers if work is None),
                fields=sum(len(e.fields) for e in items),
            )
            entry = journal.append_entry(
                connection,
                now=moment,
                actor_reviewer_id=folder.reviewer_id,
                entry_type=EntryType.ENRICH_COMPLETED,
                subject_type="enrichment",
                subject_id=batch_id,
                summary_fr=french(
                    "Crossref: references completed: {enriched} of {checked} checked"
                ).format(enriched=summary.enriched, checked=summary.checked),
                tool_version=tool_version,
                payload={
                    "checked": summary.checked,
                    "enriched": summary.enriched,
                    "not_found": summary.not_found,
                    "fields_added": summary.fields,
                    "raw_dir": raw_dir,
                },
            )
            for item in items:
                references_repo.insert_enrichment(connection, item, journal_entry_id=entry.id)
    except BaseException:
        remove_source_pages(folder.path, raw_dir)
        raise
    return summary


def enrich_references(
    folder: ProjectFolder,
    *,
    now: Clock,
    tool_version: str,
    source: Callable[[], WorkSource] = default_crossref,
    limit: int | None = None,
    max_workers: int = MAX_CONCURRENCY,
    batch_size: int = BATCH_SIZE,
) -> EnrichmentSummary:
    """Ask Crossref for the missing fields of the candidates (``limit`` at most).

    Answers are recorded by batches of ``batch_size``, each in its own transaction:
    after a failure, the batches already recorded are kept and are not asked again."""
    candidates = enrichment_candidates(folder)[:limit]
    total = EnrichmentSummary(checked=0, enriched=0, not_found=0, fields=0)
    if not candidates:
        return total
    crossref = source()
    try:
        with ThreadPoolExecutor(max_workers=min(max_workers, MAX_CONCURRENCY)) as pool:
            for start in range(0, len(candidates), batch_size):
                batch = candidates[start : start + batch_size]
                answers = list(pool.map(lambda r: crossref.work(r.doi), batch))
                done = _store_batch(folder, batch, answers, now=now, tool_version=tool_version)
                total = EnrichmentSummary(
                    checked=total.checked + done.checked,
                    enriched=total.enriched + done.enriched,
                    not_found=total.not_found + done.not_found,
                    fields=total.fields + done.fields,
                )
    finally:
        close_source(crossref)
    return total


def references_with_enrichment(folder: ProjectFolder) -> list[Reference]:
    """Every reference, its missing fields filled by Crossref when found."""
    with folder.engine.connect() as connection:
        enrichments = references_repo.list_enrichments(connection)
        return [
            merged(r, enrichments.get(r.id, []))
            for r in references_repo.list_references(connection)
        ]
