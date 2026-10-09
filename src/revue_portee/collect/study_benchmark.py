"""Test of the rules that propose reports of a same study (tranche 2.3, EF-SEL-17).

Reference standard: PubMed records that PubMed links to a ClinicalTrials.gov number
(``DataBankList``); records with the same number report the same trial. The number
given by PubMed is used only as the label: the rules see the title, the authors and the
abstract, as they would in a review (where the number may appear in the abstract).
Records linked to several numbers are left out.

Building a set calls PubMed (E-utilities); testing it is local. The sets stay outside
the repository (abstracts); the reports in ``docs/resultats/`` give only numbers.
"""

import csv
import io
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from revue_portee.dedup.reports import (
    PairEvaluation,
    ReportCandidate,
    ReportLinkSettings,
    candidate_pairs,
    evaluate_pairs,
    features,
)
from revue_portee.domain.references import Reference
from revue_portee.sources.pubmed import PubMed, databank_accessions, parse_pubmed_xml

__all__ = [
    "StudyRecord",
    "StudyTest",
    "build_set",
    "read_set",
    "report_markdown",
    "run_test",
    "write_set",
]

_HEADER = ("pmid", "study", "title", "authors", "year", "journal", "abstract")


@dataclass(frozen=True, slots=True)
class StudyRecord:
    pmid: str
    study: str  # the ClinicalTrials.gov number given by PubMed (the label)
    title: str
    authors: tuple[str, ...]
    year: int | None
    journal: str
    abstract: str


def build_set(
    pubmed: PubMed,
    query: str,
    *,
    limit: int,
    progress: Callable[[int], None] | None = None,
) -> list[StudyRecord]:
    """Records retrieved by ``query`` (at most ``limit``) with exactly one
    ClinicalTrials.gov number."""
    records: list[StudyRecord] = []
    cursor: str | None = None
    seen = 0
    while seen < limit:
        page = pubmed.fetch(query, cursor)
        accessions = databank_accessions(str(page.raw))
        for record in parse_pubmed_xml(str(page.raw)):
            seen += 1
            numbers = accessions.get(record.original_id, frozenset())
            if len(numbers) != 1:
                continue
            f = record.fields
            records.append(
                StudyRecord(
                    pmid=record.original_id,
                    study=next(iter(numbers)),
                    title=str(f.get("title", "")),
                    authors=tuple(f.get("authors", ())),
                    year=f.get("year"),
                    journal=str(f.get("container_title", "")),
                    abstract=str(f.get("abstract", "")),
                )
            )
        if progress is not None:
            progress(seen)
        cursor = page.next_cursor
        if cursor is None:
            break
    return records


def write_set(records: Sequence[StudyRecord]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(_HEADER)
    for r in records:
        writer.writerow(
            (r.pmid, r.study, r.title, "; ".join(r.authors), r.year or "", r.journal, r.abstract)
        )
    return buffer.getvalue()


def read_set(path: Path) -> list[StudyRecord]:
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    with path.open(encoding="utf-8", newline="") as stream:
        return [
            StudyRecord(
                pmid=row["pmid"],
                study=row["study"],
                title=row["title"],
                authors=tuple(a for a in row["authors"].split("; ") if a),
                year=int(row["year"]) if row["year"] else None,
                journal=row["journal"],
                abstract=row["abstract"],
            )
            for row in csv.DictReader(stream)
        ]


@dataclass(frozen=True, slots=True)
class StudyTest:
    name: str
    records: int
    studies: int
    studies_with_several: int
    settings: ReportLinkSettings
    evaluation: PairEvaluation
    by_rule: dict[str, tuple[int, int]]  # rule: (proposed, true)
    generated_at: datetime


def run_test(
    name: str,
    records: Sequence[StudyRecord],
    *,
    now: datetime,
    settings: ReportLinkSettings | None = None,
) -> StudyTest:
    chosen = settings or ReportLinkSettings()
    references = [
        Reference(
            id=r.pmid,
            title=r.title,
            abstract=r.abstract,
            authors=r.authors,
            year=r.year,
            container_title=r.journal,
            created_at=now,
        )
        for r in records
    ]
    candidates = candidate_pairs([features(ref) for ref in references], chosen)
    study_of = {r.pmid: r.study for r in records}
    evaluation = evaluate_pairs(
        [(c.reference_a_id, c.reference_b_id) for c in candidates], study_of
    )
    sizes = Counter(study_of.values())
    return StudyTest(
        name=name,
        records=len(records),
        studies=len(sizes),
        studies_with_several=sum(1 for n in sizes.values() if n > 1),
        settings=chosen,
        evaluation=evaluation,
        by_rule=_by_rule(candidates, study_of),
        generated_at=now,
    )


def _by_rule(
    candidates: Sequence[ReportCandidate], study_of: dict[str, str]
) -> dict[str, tuple[int, int]]:
    proposed: Counter[str] = Counter()
    true: Counter[str] = Counter()
    for c in candidates:
        proposed[c.rule] += 1
        true[c.rule] += study_of[c.reference_a_id] == study_of[c.reference_b_id]
    return {rule: (proposed[rule], true[rule]) for rule in sorted(proposed)}


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


def report_markdown(test: StudyTest, *, role: str) -> str:
    """Report in French for ``docs/resultats/`` (numbers only); ``role`` says whether
    the set served to develop the rules or to test them."""
    e = test.evaluation
    lines = [
        f"# Rapports d'une même étude : règles, jeu {test.name}",
        "",
        f"- Date : {test.generated_at:%Y-%m-%d}; rôle du jeu : **{role}**",
        f"- Notices : {test.records}; études (numéros ClinicalTrials.gov) : {test.studies}, "
        f"dont {test.studies_with_several} avec plusieurs rapports",
        f"- Réglages : auteurs en commun ≥ {test.settings.min_shared_authors} et mots communs "
        f"≥ {test.settings.min_text_overlap:.2f}, ou 1 auteur et mots communs ≥ "
        f"{test.settings.single_author_overlap:.2f}; similarité des titres ≥ "
        f"{test.settings.min_title_similarity:.2f}",
        "",
        "| Mesure | Valeur |",
        "|---|---|",
        f"| Paires d'une même étude | {e.true_pairs} |",
        f"| Paires proposées | {e.proposed} |",
        f"| Paires d'une même étude proposées | {e.found} |",
        f"| **Rappel** | **{_percent(e.recall)}** |",
        f"| Précision | {_percent(e.precision)} |",
        "",
        "| Règle | Paires proposées | Dont d'une même étude |",
        "|---|---|---|",
        *(f"| {rule} | {p} | {t} |" for rule, (p, t) in test.by_rule.items()),
        "",
        "Les paires proposées sont ensuite examinées par l'IA et décidées par une personne : "
        "la précision des règles mesure la charge de travail, le rappel ce que l'outil peut "
        "manquer.",
        "",
    ]
    return "\n".join(lines)
