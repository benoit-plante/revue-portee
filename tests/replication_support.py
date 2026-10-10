"""The fictitious review of the replication benchmark (tests/fixtures/replication/README.md).

The review folder is copied into a temporary folder and its ``textes/`` filled with
small PDFs; the AI is a ``FakeProvider`` whose answers depend on the title of each
reference only, so that every number of the report can be counted by hand.
"""

import shutil
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from revue_portee.ai.base import ModelProvider, TaskInput
from revue_portee.ai.providers.fake import FakeBatches, FakeProvider
from revue_portee.ai.settings import AITaskConfig
from revue_portee.ai.tasks.extraction import ExtractFieldsInput
from revue_portee.ai.tasks.fulltext import ScreenFulltextInput
from revue_portee.ai.tasks.screening import ScreenReferenceInput
from revue_portee.ai.tasks.studies import GroupReportsInput
from revue_portee.ai.tasks.synthesis import DraftSynthesisInput
from revue_portee.domain.references import Reference
from revue_portee.sources.records import OpenAccessLocation
from support import make_pdf

FIXTURE = Path(__file__).parent / "fixtures" / "replication" / "revue"
COST = Decimal("0.01")  # per call; half in a batch
# Keys of the references, by a part of their title (the first that matches counts).
KEYS = (
    ("twelve-month follow-up", "S1b"),
    ("brisk walking groups", "S1"),
    ("nordic walking", "S2"),
    ("walking prescription", "S3"),
    ("neighbourhood strolls", "S4"),
    ("aquatic walking", "S5"),
    ("marcher pour apaiser", "S6"),
    ("walking football", "R10"),
    ("treadmill walking", "R11"),
    ("dog walking", "R12"),
    ("garden walking", "R13"),
)
FILLER = "\n" + "\n".join(["The participants walked and their anxiety was measured."] * 5)
# PDFs of textes/: file name and the text of their first page (S3 has none; S2 is in
# open access).
TEXTS = {
    "10.5555_fict.0001.pdf": "Brisk walking groups and anxiety in community-dwelling older "
    "adults\nTrial registration: NCT01234567",
    "10.5555_fict.0002.pdf": "Twelve-month follow-up of brisk walking groups for late-life "
    "anxiety\nTrial registration: NCT01234567",
    "10.5555_fict.0005.pdf": "Neighbourhood strolls and wellbeing in retirement",
    "10.5555_fict.0006.pdf": "Aquatic walking classes and anxiety in older women",
    "dube-2016-memoire.pdf": "Dube F. Marcher pour apaiser l'anxiete des aines : memoire de "
    "maitrise. Universite fictive; 2016.",
    "10.5555_fict.0010.pdf": "Walking football and anxiety symptoms in older men",
    "10.5555_fict.0011.pdf": "Treadmill walking and anxiety in adults over seventy",
    "10.5555_fict.0012.pdf": "Dog walking and loneliness among seniors",
    "10.5555_fict.0013.pdf": "Garden walking programmes in assisted living",
}
OPEN_ACCESS_URL = "https://repository.example.org/nordic-walking.pdf"


def key_of(title: str) -> str:
    lowered = title.lower()
    return next((key for part, key in KEYS if part in lowered), "other")


def copy_review(tmp_path: Path, *, texts: bool = True) -> Path:
    """The review folder, copied, with its PDFs in ``textes/``."""
    target = tmp_path / "Fictive_2026_marche_anxiete"
    shutil.copytree(FIXTURE, target)
    if texts:
        folder = target / "textes"
        folder.mkdir()
        for name, first in TEXTS.items():
            (folder / name).write_bytes(make_pdf([first + FILLER, "Results" + FILLER]))
    return target


# --- The AI ---------------------------------------------------------------------------

# Title and abstract: probability of inclusion by key; R13 gets unusable answers.
SCREEN = {"S1": 0.9, "S1b": 0.9, "S2": 0.9, "S3": 0.9, "R10": 0.9, "R11": 0.9, "R12": 0.4}
# Full text: probability of inclusion by key (absent: excluded, P1 not met).
FULL_TEXT = {"S1": 0.9, "S1b": 0.9, "R10": 0.85, "R11": 0.4, "S4": 0.8, "S5": 0.8, "S6": 0.3}
# Extraction: D1 (design), D2 (setting), D3 (follow-up; None: not reported).
EXTRACTED: dict[str, tuple[str, str, str | None]] = {
    "S1": ("Essai randomisé", "Communauté", "oui"),
    "S2": ("Quasi expérimental", "Résidence", "non"),
    "S4": ("Qualitatif", "Communauté", None),
    "S5": ("Essai randomisé", "Hôpital", "oui"),
    "S6": ("Qualitatif", "Communauté", "non"),
    "R10": ("Quasi expérimental", "Résidence", "non"),
    "R11": ("Essai randomisé", "Hôpital", None),
}


def _screening(item: ScreenReferenceInput | ScreenFulltextInput, probability: float | None,
               page: bool) -> dict[str, Any]:  # fmt: skip
    """An answer on every criterion: an excluded reference fails P1 (S4: C1)."""
    if probability is None:  # R13: an answer on criteria that do not exist
        return {
            "assessments": [{"code": "Z9", "status": "met", "evidence_quote": ""}],
            "decision": "include",
            "inclusion_probability": 0.9,
            "rationale": "Réponse fictive inutilisable.",
            "decisive_criteria": ["Z9"],
        }
    kept = probability >= 0.10
    failing = "C" if key_of(_title(item)) == "S4" else "P"
    assessments: list[dict[str, Any]] = []
    for criterion in item.criteria:
        if criterion.kind == "exclusion":
            status = "not_met"
        else:
            status = "met" if kept or not criterion.code.startswith(failing) else "not_met"
        entry: dict[str, Any] = {"code": criterion.code, "status": status, "evidence_quote": ""}
        if page:
            entry["page"] = None
        assessments.append(entry)
    decisive = [a["code"] for a in assessments if a["status"] == "not_met" and not kept]
    return {
        "assessments": assessments,
        "decision": "include" if probability >= 0.6 else ("uncertain" if kept else "exclude"),
        "inclusion_probability": probability,
        "rationale": "Réponse fictive.",
        "decisive_criteria": decisive or [item.criteria[0].code],
    }


def _title(item: ScreenReferenceInput | ScreenFulltextInput) -> str:
    return item.reference.title if isinstance(item, ScreenReferenceInput) else item.report.title


def respond(item: TaskInput) -> dict[str, Any]:
    if isinstance(item, ScreenReferenceInput):
        key = key_of(item.reference.title)
        if key == "R13":
            return _screening(item, None, page=False)
        return _screening(item, SCREEN.get(key, 0.05), page=False)
    if isinstance(item, ScreenFulltextInput):
        return _screening(item, FULL_TEXT.get(key_of(item.report.title), 0.05), page=True)
    if isinstance(item, GroupReportsInput):
        pair = {key_of(item.report_a.title), key_of(item.report_b.title)}
        return {
            "verdict": "same" if pair == {"S1", "S1b"} else "different",
            "evidence": [{"aspect": "registration", "quote_a": "", "quote_b": ""}],
            "rationale": "Réponse fictive.",
        }
    if isinstance(item, ExtractFieldsInput):
        design, setting, follow_up = EXTRACTED[key_of(item.report.title)]
        given = {"D1": design, "D2": setting, "D3": follow_up}
        return {
            "values": [
                {"code": f.code, "reported": given[f.code] is not None,
                 "value": given[f.code] or ""}
                for f in item.fields
            ]
        }  # fmt: skip
    assert isinstance(item, DraftSynthesisInput)
    return {"sentences": [{"text": "Synthèse fictive.", "studies": [item.studies[0].key]}]}


def factory(batches: FakeBatches | None = None) -> Callable[[AITaskConfig], ModelProvider]:
    store = batches or FakeBatches()

    def build(config: AITaskConfig) -> ModelProvider:
        return FakeProvider(
            model=str(config.model),
            model_returned="fake-model-2026-10-09",
            responder=respond,
            cost_per_call=COST,
            batches=store,
        )

    return build


class Finder:
    """Open access: only the Nordic walking study (S2) is found, in OpenAlex."""

    def openalex(self, reference: Reference) -> tuple[list[OpenAccessLocation], dict[str, Any]]:
        if key_of(reference.title) == "S2":
            return [OpenAccessLocation(OPEN_ACCESS_URL, "cc-by", "publishedVersion",
                                       "repository")], {"results": [{"id": "W1"}]}  # fmt: skip
        return [], {"results": []}

    def unpaywall(self, doi: str) -> tuple[list[OpenAccessLocation], dict[str, Any]]:
        return [], {"doi": doi.lower(), "is_oa": False}

    def download(self, url: str) -> bytes:
        assert url == OPEN_ACCESS_URL
        return make_pdf(["Nordic walking in long-term care residents" + FILLER, "Results" + FILLER])
