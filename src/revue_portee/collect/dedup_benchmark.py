"""Deduplication measured on held-out annotated sets (RAISE 2, checklist point 2.10).

The rules of ``dedup/`` were developed on the annotated set of tranche 1.5 (D-060,
D-062), so their results there are development results. This module measures them on
sets that were never used to build them: the evaluation datasets of ASySD (Hair et
al., BMC Biology 2023; OSF 2b8uq, CC BY 4.0), deduplicated by people. Records that
share a ``duplicateid`` are duplicates of each other.

The files stay outside the repository (they hold abstracts); only the report with
numbers is versioned in ``docs/resultats/``. The rules must not be tuned on these
sets, or they would no longer be a test.
"""

import csv
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from revue_portee.dedup.evaluation import Evaluation, evaluate
from revue_portee.dedup.matching import find_candidates
from revue_portee.domain.dedup import ALGORITHM_VERSION, DedupSettings
from revue_portee.domain.references import Reference, clean_doi
from revue_portee.i18n import gettext as _

__all__ = [
    "AnnotatedRecord",
    "DedupTest",
    "read_asysd",
    "report_markdown",
    "run_test",
    "split_authors",
]

RECALL_TARGET = 0.98
PRECISION_TARGET = 0.99
SOURCE = (
    "Hair K, Bahor Z, Macleod M, Liao J, Sena ES. The Automated Systematic Search "
    "Deduplicator (ASySD). BMC Biology. 2023;21:189. doi:10.1186/s12915-023-01686-z; "
    "data: https://osf.io/2b8uq/ (CC BY 4.0)"
)
# ASySD writes the authors one after the other: "Adeli K.Lewis G. F." A new author
# starts after a period followed directly by a non-space character.
_AUTHOR_BREAK = re.compile(r"(?<=\.)(?=[^\s.])")
_YEAR = re.compile(r"^(1[0-9]{3}|20[0-9]{2}|2100)$")


@dataclass(frozen=True, slots=True)
class AnnotatedRecord:
    reference: Reference
    group: str  # records of one group are duplicates of each other


def split_authors(text: str) -> tuple[str, ...]:
    """The authors of an ASySD record, in order."""
    return tuple(part.strip() for part in _AUTHOR_BREAK.split(text) if part.strip())


def read_asysd(path: Path, *, created_at: datetime) -> list[AnnotatedRecord]:
    """The records of an ASySD ``*_duplicates_labelled.csv`` file; identifiers are the
    row numbers. Abstracts are not read: the rules do not use them to match."""
    csv.field_size_limit(2**31 - 1)
    with path.open(encoding="utf-8", errors="replace", newline="") as source:
        rows = list(csv.DictReader(source))
    records = []
    for number, row in enumerate(rows, start=1):
        year = row.get("year", "").strip()
        reference = Reference(
            id=f"{number:06d}",
            title=row.get("title", "").strip(),
            authors=split_authors(row.get("author", "")),
            year=int(year) if _YEAR.match(year) else None,
            container_title=row.get("journal", "").strip(),
            volume=row.get("volume", "").strip(),
            issue=row.get("number", "").strip(),
            pages=row.get("pages", "").strip(),
            doi=clean_doi(row.get("doi", "")),
            created_at=created_at,
        )
        records.append(AnnotatedRecord(reference, row["duplicateid"].strip()))
    return records


@dataclass(frozen=True, slots=True)
class DedupTest:
    dataset: str
    records: int
    groups: int
    settings: DedupSettings
    evaluation: Evaluation
    run_at: datetime

    @property
    def targets_met(self) -> bool:
        e = self.evaluation
        return e.recall >= RECALL_TARGET and e.precision >= PRECISION_TARGET


def run_test(
    dataset: str,
    records: list[AnnotatedRecord],
    *,
    settings: DedupSettings | None = None,
    now: datetime | None = None,
) -> DedupTest:
    """Run the rules once on ``records``; the person's decisions on the pairs left to
    them are simulated by the annotation (``dedup/evaluation.py``)."""
    chosen = settings or DedupSettings()
    candidates = find_candidates([r.reference for r in records], chosen)
    truth = {r.reference.id: r.group for r in records}
    return DedupTest(
        dataset=dataset,
        records=len(records),
        groups=len(set(truth.values())),
        settings=chosen,
        evaluation=evaluate(candidates, truth),
        run_at=now or datetime.now(UTC),
    )


def _decimal(value: float, places: int = 3) -> str:
    return f"{value:.{places}f}".replace(".", ",")


def _lines(test: DedupTest) -> Iterator[str]:
    e = test.evaluation
    yield "# " + _("Deduplication test: ASySD {dataset}").format(dataset=test.dataset)
    yield ""
    yield _("Run on {date} (UTC).").format(date=test.run_at.strftime("%Y-%m-%d %H:%M"))
    yield ""
    yield _(
        "Held-out data: these records were never used to build or tune the rules, which "
        "were not changed after this run (RAISE 2)."
    )
    yield ""
    yield "| " + _("Item") + " | " + _("Value") + " |"
    yield "|---|---|"
    rows = [
        (_("Version of the rules"), ALGORITHM_VERSION),
        (
            _("Thresholds"),
            _("review from {review}, automatic from {automatic}").format(
                review=_decimal(test.settings.review_from, 2),
                automatic=_decimal(test.settings.auto_from, 2),
            ),
        ),
        (_("Records"), str(test.records)),
        (_("Annotated groups"), str(test.groups)),
        (_("Annotated pairs of duplicates"), str(e.true_pairs)),
        (_("Pairs grouped at the end"), str(e.found_pairs)),
        (_("Of which correct"), str(e.correct_pairs)),
        (_("Recall"), _decimal(e.recall)),
        (_("Precision"), _decimal(e.precision)),
        (_("Pairs grouped automatically"), str(e.automatic_pairs)),
        (_("Of which wrong"), str(e.automatic_errors)),
        (_("Pairs left to a person"), str(e.review_pairs)),
    ]
    yield from (f"| {label} | {value} |" for label, value in rows)
    yield ""
    yield _(
        "Targets (recall at least {recall}, precision at least {precision}): {verdict}."
    ).format(
        recall=_decimal(RECALL_TARGET, 2),
        precision=_decimal(PRECISION_TARGET, 2),
        verdict=_("reached") if test.targets_met else _("not reached"),
    )
    yield ""
    yield _(
        "The person's decisions on the pairs left to them are simulated by the annotation; "
        "the pairs are compared with the annotated groups."
    )
    yield ""
    yield _("Source: {source}").format(source=SOURCE)


def report_markdown(test: DedupTest) -> str:
    return "\n".join(_lines(test)) + "\n"
