"""The folder of a review to replay (docs/11-plan-de-replication.md §5.4).

::

    <id-revue>/
    ├── fiche.yaml              # id of the review, period of the original search
    ├── criteres.yaml           # question and criteria (format of banc-synergy)
    ├── grille.yaml             # extraction grid (format of the starting grids)
    ├── recherche/              # RIS exports and, if needed, strategie.yaml
    ├── GEL.sha256              # SHA-256 of the inputs, written before the run
    ├── norme/                  # reference standard, made after the freeze
    │   ├── incluses.csv
    │   ├── extraction-publiee.csv
    │   └── resultats-publies.yaml
    └── textes/                 # PDFs obtained by the team, never published

Everything the AI is given (criteria, grid, search) must be frozen: each of these
files is listed in ``GEL.sha256`` with its SHA-256, which must match. Only the hashes
count, never the dates of the files.
"""

import csv
import datetime as dt
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from revue_portee.domain.criteria import PccElement
from revue_portee.domain.grid import GridTemplate
from revue_portee.domain.references import clean_doi, clean_pmid
from revue_portee.domain.replication import (
    PublishedDistribution,
    PublishedFlow,
    PublishedValue,
    StandardStudy,
)
from revue_portee.domain.search import (
    BlockRole,
    ConceptBlock,
    Database,
    Limits,
    SearchStrategy,
    TermSyntaxError,
    parse_term,
)
from revue_portee.i18n import gettext as _
from revue_portee.screening.benchmark import BenchmarkCriteria, BenchmarkError, read_criteria

__all__ = [
    "CRITERIA_FILE",
    "FREEZE_FILE",
    "GRID_FILE",
    "SEARCH_FOLDER",
    "SHEET_FILE",
    "STANDARD_FOLDER",
    "TEXT_FOLDER",
    "ReplicationInputError",
    "ReviewInputs",
    "ReviewSheet",
    "SearchPlan",
    "Standard",
    "check_freeze",
    "read_inputs",
    "read_standard",
]

SHEET_FILE = "fiche.yaml"
CRITERIA_FILE = "criteres.yaml"
GRID_FILE = "grille.yaml"
SEARCH_FOLDER = "recherche"
STRATEGY_FILE = "strategie.yaml"
FREEZE_FILE = "GEL.sha256"
STANDARD_FOLDER = "norme"
TEXT_FOLDER = "textes"
_HASH_LINE = re.compile(r"^(?P<hash>[0-9a-fA-F]{64}) [ *](?P<path>.+)$")
_FLOW_KEYS = {
    "identifies": "identified",
    "apres_doublons": "after_duplicates",
    "tries": "screened",
    "textes_evalues": "full_texts_assessed",
    "inclus_rapports": "included_reports",
    "inclus_etudes": "included_studies",
}
_DATABASES = {"pubmed": Database.PUBMED, "openalex": Database.OPENALEX}


class ReplicationInputError(ValueError):
    """A review folder that cannot be replayed (French message)."""


class ReviewSheet(BaseModel):
    """What the benchmark reads of ``fiche.yaml`` (other keys are kept for people)."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str = Field(min_length=1, pattern=r"^[\w.-]+$")
    search_end: int | None = None  # year of the latest date of the original search


@dataclass(frozen=True, slots=True)
class SearchPlan:
    """A search strategy rebuilt from the published one, and the databases to collect."""

    strategy: SearchStrategy
    databases: tuple[Database, ...]


@dataclass(frozen=True, slots=True)
class ReviewInputs:
    folder: Path
    sheet: ReviewSheet
    criteria: BenchmarkCriteria
    grid: GridTemplate
    ris_files: tuple[Path, ...]
    search: SearchPlan | None

    @property
    def texts(self) -> list[Path]:
        """PDFs of ``textes/``, sorted (the folder may not exist yet)."""
        folder = self.folder / TEXT_FOLDER
        return sorted(p for p in folder.rglob("*") if p.suffix.lower() == ".pdf" and p.is_file())


@dataclass(frozen=True, slots=True)
class Standard:
    """The reference standard (``norme/``)."""

    studies: tuple[StandardStudy, ...]
    values: tuple[PublishedValue, ...]
    flow: PublishedFlow
    distributions: tuple[PublishedDistribution, ...]
    sha256: str  # of incluses.csv


def _yaml(path: Path) -> Any:  # noqa: ANN401 - a YAML document
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ReplicationInputError(_("File not found: {path}").format(path=path)) from error
    except (OSError, yaml.YAMLError) as error:
        raise ReplicationInputError(
            _("The file {path} is unreadable.").format(path=path)
        ) from error


def _sheet(path: Path) -> ReviewSheet:
    data = _yaml(path)
    if not isinstance(data, dict):
        raise ReplicationInputError(_("The file {path} is unreadable.").format(path=path))
    search = data.get("recherche") if isinstance(data.get("recherche"), dict) else {}
    dates = search.get("date_origine") if isinstance(search, dict) else None
    listed = dates if isinstance(dates, list) else [dates]
    years = [d.year for d in listed if isinstance(d, dt.date)]
    try:
        return ReviewSheet.model_validate(
            {"id": str(data.get("id", "")), "search_end": max(years, default=None)}
        )
    except ValidationError as error:
        raise ReplicationInputError(
            _(
                "The file {path} needs an id made of letters, digits, dots, dashes or underscores."
            ).format(path=path)
        ) from error


def _grid(path: Path) -> GridTemplate:
    try:
        return GridTemplate.model_validate(_yaml(path))
    except ValidationError as error:
        raise ReplicationInputError(
            _("The grid {path} does not follow the format of the starting grids: {error}").format(
                path=path, error=error.errors()[0]["msg"]
            )
        ) from error


def _strategy(path: Path) -> SearchPlan:
    data = _yaml(path)
    try:
        blocks = tuple(
            ConceptBlock(
                code=f"B{number}",
                label=str(block["libelle"]),
                pcc_element=PccElement(block["element"]) if block.get("element") else None,
                role=BlockRole.EXCLUDE if block.get("exclure") else BlockRole.INCLUDE,
                terms=tuple(parse_term(str(line)) for line in block.get("termes", [])),
            )
            for number, block in enumerate(data.get("blocs", []), start=1)
        )
        limits = data.get("limites") or {}
        strategy = SearchStrategy(
            blocks=blocks,
            limits=Limits(year_from=limits.get("annee_min"), year_to=limits.get("annee_max")),
        )
        databases = tuple(_DATABASES[str(name).lower()] for name in data.get("bases", []))
    except (AttributeError, KeyError, TypeError, ValueError, TermSyntaxError) as error:
        raise ReplicationInputError(
            _("The search strategy {path} is invalid ({error}).").format(
                path=path, error=type(error).__name__
            )
        ) from error
    if not databases:
        raise ReplicationInputError(
            _("The search strategy {path} names no database to collect (pubmed, openalex).").format(
                path=path
            )
        )
    return SearchPlan(strategy=strategy, databases=databases)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_freeze(folder: Path, frozen: list[Path]) -> None:
    """Refuse the run unless each file of ``frozen`` is listed in ``GEL.sha256`` with
    its SHA-256 (only the hashes count, never the dates of the files)."""
    freeze = folder / FREEZE_FILE
    try:
        lines = freeze.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as error:
        raise ReplicationInputError(
            _("{file} is missing: freeze the inputs before the run (docs/11 §4).").format(
                file=FREEZE_FILE
            )
        ) from error
    listed: dict[str, str] = {}
    for line in lines:
        match = _HASH_LINE.match(line.strip())
        if match:
            listed[match.group("path").strip().removeprefix("./")] = match.group("hash").lower()
    for path in frozen:
        name = path.relative_to(folder).as_posix()
        if name not in listed:
            raise ReplicationInputError(
                _("{name} is not frozen: its SHA-256 is missing from {file}.").format(
                    name=name, file=FREEZE_FILE
                )
            )
        if _sha256(path) != listed[name]:
            raise ReplicationInputError(
                _(
                    "{name} changed since the freeze: its SHA-256 does not match {file}. The "
                    "run is refused."
                ).format(name=name, file=FREEZE_FILE)
            )


def read_inputs(folder: Path) -> ReviewInputs:
    """Read the inputs of a review folder, after checking their freeze."""
    if not folder.is_dir():
        raise ReplicationInputError(_("Folder not found: {path}").format(path=folder))
    search_folder = folder / SEARCH_FOLDER
    search_files = (
        sorted(p for p in search_folder.rglob("*") if p.is_file()) if search_folder.is_dir() else []
    )
    ris_files = tuple(p for p in search_files if p.suffix.lower() in (".ris", ".txt"))
    strategy = search_folder / STRATEGY_FILE
    if not ris_files and not strategy.is_file():
        raise ReplicationInputError(
            _("{folder} holds no RIS export nor search strategy.").format(folder=search_folder)
        )
    check_freeze(folder, [folder / CRITERIA_FILE, folder / GRID_FILE, *search_files])
    try:
        criteria = read_criteria(folder / CRITERIA_FILE)
    except BenchmarkError as error:
        raise ReplicationInputError(str(error)) from error
    return ReviewInputs(
        folder=folder,
        sheet=_sheet(folder / SHEET_FILE),
        criteria=criteria,
        grid=_grid(folder / GRID_FILE),
        ris_files=ris_files,
        search=_strategy(strategy) if strategy.is_file() else None,
    )


# --- Reference standard ---------------------------------------------------------------


def _rows(path: Path, required: set[str]) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
    except FileNotFoundError as error:
        raise ReplicationInputError(_("File not found: {path}").format(path=path)) from error
    if rows and not required <= set(rows[0]):
        raise ReplicationInputError(
            _("The file {path} needs the columns {columns}.").format(
                path=path, columns=", ".join(sorted(required))
            )
        )
    return [{k: (v or "").strip() for k, v in row.items() if k} for row in rows]


def _studies(path: Path) -> tuple[StandardStudy, ...]:
    studies = []
    for number, row in enumerate(_rows(path, {"study_id", "retrievable"}), start=2):
        retrievable = row["retrievable"].casefold()
        if retrievable not in ("oui", "hors_recherche"):
            raise ReplicationInputError(
                _("{path}, line {line}: retrievable must be oui or hors_recherche.").format(
                    path=path.name, line=number
                )
            )
        studies.append(
            StandardStudy(
                study_id=row["study_id"],
                doi=clean_doi(row.get("doi", "")),
                pmid=clean_pmid(row.get("pmid", "")),
                citation=row.get("citation", ""),
                title=row.get("title", ""),
                in_search=retrievable == "oui",
            )
        )
    ids = [s.study_id for s in studies]
    if len(set(ids)) != len(ids) or not ids:
        raise ReplicationInputError(
            _("{path} needs one row per included study, each with its own study_id.").format(
                path=path.name
            )
        )
    return tuple(studies)


def read_standard(folder: Path) -> Standard:
    """The reference standard of a review folder (made after the freeze)."""
    base = folder / STANDARD_FOLDER
    included = base / "incluses.csv"
    studies = _studies(included)
    values_path = base / "extraction-publiee.csv"
    values = (
        tuple(
            PublishedValue(study_id=r["study_id"], field=r["field"], value=r["value"])
            for r in _rows(values_path, {"study_id", "field", "value"})
        )
        if values_path.is_file()
        else ()
    )
    results_path = base / "resultats-publies.yaml"
    results = _yaml(results_path) if results_path.is_file() else {}
    try:
        diagram = (results or {}).get("diagramme") or {}
        flow = PublishedFlow.model_validate({_FLOW_KEYS[k]: v for k, v in diagram.items()})
        distributions = tuple(
            PublishedDistribution(
                field=str(item["champ"]),
                categories={str(k): int(v) for k, v in item["categories"].items()},
                n=item.get("n"),
            )
            for item in (results or {}).get("distributions") or []
        )
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise ReplicationInputError(
            _("The file {path} is unreadable.").format(path=results_path)
        ) from error
    return Standard(
        studies=studies,
        values=values,
        flow=flow,
        distributions=distributions,
        sha256=_sha256(included),
    )
