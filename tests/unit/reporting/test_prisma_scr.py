"""The reporting checklist filled from the project (EF-DEC-02, ENF-NOR-03): the 22 items
of PRISMA-ScR 2018, proposals from the project data, and a new version added as a file
without a change of code."""

from datetime import date
from pathlib import Path

import yaml

from revue_portee.domain.framing import Framing
from revue_portee.domain.protocol import ProtocolRegistration, ProtocolSection, ProtocolText
from revue_portee.reporting.document import render_markdown
from revue_portee.reporting.prisma_scr import (
    RESOLVERS,
    ChecklistFacts,
    build_checklist,
    fill_checklist,
)
from revue_portee.resources import load_checklists, reporting_checklists
from unit.reporting.test_methods import data as methods
from unit.reporting.test_protocol import NOW
from unit.reporting.test_protocol import data as protocol

PRISMA = reporting_checklists()["prisma-scr-2018"]


def test_the_22_items_of_prisma_scr_2018() -> None:
    assert [i.id for i in PRISMA.items] == [str(n) for n in range(1, 23)]
    assert [i.id for i in PRISMA.items if i.optional] == ["12", "16"]  # 20 essential, 2 optional
    assert PRISMA.verified
    assert "doi:10.7326/M18-0850" in PRISMA.source
    # every source of the 2018 version is known: nothing is left unknown
    assert {s for i in PRISMA.items for s in i.sources} <= set(RESOLVERS)


def _facts(**changes: object) -> ChecklistFacts:
    registration = ProtocolRegistration(
        id="r", doi="10.17605/OSF.IO/ABCDE", registered_on=date(2026, 10, 1),
        criteria_version_id=None, created_at=NOW, reviewer_id="h",
    )  # fmt: skip
    return ChecklistFacts(
        protocol=protocol(
            framing=Framing(question="Que sait-on ?", population="Aînés", concept="Logement"),
            registration=registration,
            text=ProtocolText(
                sections={
                    ProtocolSection.BACKGROUND: "Contexte.",
                    ProtocolSection.FUNDING: "Aucun.",
                }
            ),
        ),
        methods=methods(),
        narrative_fields=3,
        **changes,  # type: ignore[arg-type]
    )


def _proposals(language: str = "fr") -> dict[str, str]:
    return {
        f.item.id: " ".join(f.proposals)
        for f in fill_checklist(PRISMA, _facts(), language=language)
    }


def test_proposals_from_the_project() -> None:
    found = _proposals()
    assert found["1"] == (
        "Titre du rapport : « Soutien à la parentalité ». Ajoutez « revue de portée » au titre."
    )
    assert found["3"] == "Introduction ; tirée du protocole (section « background »)."
    assert found["4"] == (
        "Question de la revue : « Que sait-on ? ». population: Aînés ; concept: Logement."
    )
    assert found["5"] == "Protocole enregistré sur OSF le 2026-10-01 : DOI 10.17605/OSF.IO/ABCDE."
    assert "1 000 références triées par 1 personne(s)" in found["9"]
    assert found["12"].startswith("Non faite")
    assert "révisée pour 3 champs" in found["18"]
    assert found["19"] == ""  # left to the team
    assert found["21"] == ""
    assert found["22"] == "Financement : voir le protocole (section « funding »)."
    english = _proposals("en")
    assert english["5"] == "Protocol registered on OSF on 2026-10-01: DOI 10.17605/OSF.IO/ABCDE."


def test_document() -> None:
    filled = fill_checklist(PRISMA, _facts(), language="fr")
    text = render_markdown(
        build_checklist(PRISMA, filled, project_title="Démo", language="fr",
                        tool_version="0.1", generated_at=NOW)
    )  # fmt: skip
    done = sum(1 for f in filled if not f.to_complete)
    assert f"Éléments avec une proposition : {done} sur 22." in text
    assert "| 12 (facultatif) |" in text
    assert "| 21 | Conclusions" in text
    assert "À compléter par l'équipe." in text
    assert "sources de données que cette version" not in text.casefold()


def test_a_new_version_needs_no_new_code(tmp_path: Path) -> None:
    """PRISMA-ScR 2026, when it is published: a new file, with sources known or not."""
    folder = tmp_path / "checklists"
    folder.mkdir()
    (folder / "prisma_scr_2026.yaml").write_text(
        yaml.safe_dump({
            "id": "prisma-scr-2026", "name": "PRISMA-ScR", "version": "2026",
            "published": "2026-12-01", "source": "Hypothetical update", "verified": False,
            "items": [
                {"id": "1", "section": "title", "en": "Title", "fr": "Titre",
                 "sources": ["title"]},
                {"id": "23", "section": "methods", "en": "Use of automation tools",
                 "fr": "Usage d'outils d'automatisation", "sources": ["automation.tools"]},
            ],
        }, allow_unicode=True),
        encoding="utf-8",
    )  # fmt: skip
    found = load_checklists(folder)
    assert list(found) == ["prisma-scr-2026"]
    new = found["prisma-scr-2026"]
    filled = fill_checklist(new, _facts(), language="fr")
    assert filled[0].proposals  # a known source: proposed
    assert (filled[1].proposals, filled[1].unknown) == ((), ("automation.tools",))
    text = render_markdown(
        build_checklist(new, filled, project_title="Démo", language="fr", tool_version="0.1",
                        generated_at=NOW)
    )  # fmt: skip
    assert "laissés à l'équipe) : automation.tools." in text
