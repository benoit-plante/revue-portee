"""Accuracy of the AI's pre-filling against an extraction made by hand (tranche 3.2).

The reference is a CSV file with one row per study and field: ``reference`` (the DOI,
the PMID or the identifier of the primary report in the project), ``field`` (the code
of the field, D1, D2…) and ``value`` (empty when the report does not give it; for a
multiple choice, the choices separated by `` | ``). The values the AI proposed in the
project are compared with it field by field:

- « not reported » agrees only with « not reported »;
- numbers, dates, yes or no, and choices agree when they are equal (a multiple choice:
  the same set);
- texts agree when, once letters and digits are kept and the case folded, one contains
  the other or they share at least half of their words: an automatic, generous measure,
  to be read with the person's judgement.

Every quote of the AI is also counted by the result of its check: at the page the AI
gave, at another page (placed by the tool at the page where it is), or not found.
"""

import csv
import io
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pydantic import JsonValue

from revue_portee.domain.extraction import (
    ExtractionValue,
    InvalidValueError,
    current_values,
    parse_value,
    quote_summary,
)
from revue_portee.domain.fulltext import QuoteCheck, canonical
from revue_portee.domain.grid import FieldType, GridField, GridVersion
from revue_portee.domain.project import ReviewerKind
from revue_portee.domain.references import clean_doi
from revue_portee.extraction.prefill import extraction_state
from revue_portee.i18n import gettext as _
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import extraction as extraction_repo

__all__ = [
    "ExtractionTest",
    "FieldScore",
    "NothingToCompareError",
    "ReferenceValue",
    "agrees",
    "read_reference",
    "report_markdown",
    "run_test",
    "write_template",
]


@dataclass(frozen=True, slots=True)
class ReferenceValue:
    reference: str
    field: str
    value: str  # "" when not reported


def read_reference(path: Path) -> list[ReferenceValue]:
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return [
            ReferenceValue(row["reference"].strip(), row["field"].strip(), row["value"].strip())
            for row in csv.DictReader(stream)
        ]


def _words(text: str) -> set[str]:
    return {canonical(w) for w in text.split() if canonical(w)}


def agrees(grid_field: GridField, expected: str, actual: ExtractionValue | None) -> bool:
    """Whether the AI's value agrees with the value extracted by hand (see above)."""
    if actual is None:
        return False
    if not expected:
        return not actual.reported
    if not actual.reported:
        return False
    raw: JsonValue = (
        [part.strip() for part in expected.split(" | ")]
        if grid_field.type is FieldType.MULTIPLE_CHOICE
        else expected
    )
    if grid_field.type is FieldType.TEXT:
        a, b = canonical(expected), canonical(str(actual.value))
        if a and b and (a in b or b in a):
            return True
        left, right = _words(expected), _words(str(actual.value))
        return bool(left and right) and len(left & right) / min(len(left), len(right)) >= 0.5
    try:
        value = parse_value(grid_field, raw)
    except InvalidValueError:
        return False
    return value == actual.value


@dataclass
class FieldScore:
    code: str
    label: str
    compared: int = 0
    agreed: int = 0

    @property
    def accuracy(self) -> float | None:
        return self.agreed / self.compared if self.compared else None


@dataclass(frozen=True, slots=True)
class ExtractionTest:
    grid_number: int
    studies: int
    fields: list[FieldScore]
    quotes: dict[QuoteCheck, int]
    missing: list[str] = field(default_factory=list)  # references not found or not pre-filled
    generated_at: datetime | None = None

    @property
    def compared(self) -> int:
        return sum(f.compared for f in self.fields)

    @property
    def agreed(self) -> int:
        return sum(f.agreed for f in self.fields)


class NothingToCompareError(ValueError):
    def __init__(self) -> None:
        super().__init__(_("No study of the file is pre-filled in the project."))


def run_test(
    folder: ProjectFolder, rows: Sequence[ReferenceValue], *, now: datetime
) -> ExtractionTest:
    state = extraction_state(folder)
    if state.grid is None:
        raise NothingToCompareError
    grid: GridVersion = state.grid
    by_key: dict[str, str] = {}
    for study in state.studies:
        ref = study.primary
        for key in (ref.id, clean_doi(ref.doi), ref.pmid):
            if key:
                by_key[key.upper()] = ref.id
    with folder.engine.connect() as connection:
        ai_values = [
            v
            for v in extraction_repo.list_values(connection)
            if v.reviewer_kind is ReviewerKind.AI and v.grid_version_id == grid.id
        ]
    current = current_values(ai_values)
    scores = {f.code: FieldScore(f.code, f.label) for f in grid.sorted_fields()}
    seen: set[str] = set()
    missing = []
    for row in rows:
        key = clean_doi(row.reference) or row.reference
        ref_id = by_key.get(key.upper())
        grid_field = grid.field(row.field)
        if grid_field is None:
            continue
        if ref_id is None or (ref_id, row.field) not in current:
            missing.append(row.reference)
            continue
        seen.add(ref_id)
        score = scores[row.field]
        score.compared += 1
        score.agreed += agrees(grid_field, row.value, current[ref_id, row.field])
    if not seen:
        raise NothingToCompareError
    compared = [v for v in current.values() if v.reference_id in seen]
    return ExtractionTest(
        grid_number=grid.number,
        studies=len(seen),
        fields=list(scores.values()),
        quotes=dict(quote_summary(compared)),
        missing=sorted(set(missing)),
        generated_at=now,
    )


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


def report_markdown(test: ExtractionTest) -> str:
    """Report in French (numbers only, no value nor quote of the reports)."""
    total = sum(test.quotes.values())
    at_page = test.quotes.get(QuoteCheck.AT_PAGE, 0)
    other = test.quotes.get(QuoteCheck.OTHER_PAGE, 0)
    not_found = test.quotes.get(QuoteCheck.NOT_FOUND, 0)
    lines = [
        "# Exactitude du pré-remplissage de la grille par l'IA",
        "",
        f"- Date : {test.generated_at:%Y-%m-%d}; grille, version {test.grid_number}"
        if test.generated_at
        else f"- Grille, version {test.grid_number}",
        f"- Études comparées à l'extraction faite à la main : {test.studies}",
        "",
        "| Champ | Valeurs comparées | Concordantes | Exactitude |",
        "|---|---|---|---|",
        *(
            f"| {f.code} — {f.label} | {f.compared} | {f.agreed} | {_percent(f.accuracy)} |"
            for f in test.fields
        ),
        f"| **Total** | {test.compared} | {test.agreed} | "
        f"**{_percent(test.agreed / test.compared if test.compared else None)}** |",
        "",
        "## Citations de l'IA",
        "",
        "| Vérification | Citations |",
        "|---|---|",
        f"| À la page indiquée par l'IA | {at_page} |",
        f"| À une autre page (placée par l'outil à la page où elle se trouve) | {other} |",
        f"| Introuvables (valeur signalée, sans page) | {not_found} |",
        f"| **Citations retrouvées, affichées à leur page** | **{at_page + other}** "
        f"(toujours la page où la citation se trouve : vérification automatique) |",
        f"| Pages données par l'IA exactes | {_percent(at_page / total if total else None)} |",
        "",
        "Concordance automatique : les textes concordent quand l'un contient l'autre ou "
        "qu'ils partagent au moins la moitié de leurs mots; à relire avec le jugement de la "
        "personne.",
        "",
    ]
    if test.missing:
        lines += [f"Références du fichier absentes ou non pré-remplies : {len(test.missing)}.", ""]
    return "\n".join(lines)


def write_template(grid: GridVersion, references: Sequence[str]) -> str:
    """A CSV file to fill by hand: one row per study and field, values empty."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(("reference", "field", "label", "value"))
    for reference in references:
        for f in grid.sorted_fields():
            writer.writerow((reference, f.code, f.label, ""))
    return buffer.getvalue()
