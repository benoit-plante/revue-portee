"""The complete methods section (EF-DEC-03, EF-VER-07, tranche 4.4): every step of the
review, the deviations from the protocol, the use of AI by task, and the appendix that
tells the external reviewer where each element of the reporting of AI use is."""

import datetime as dt
from decimal import Decimal

from revue_portee.reporting.document import Heading, Table, render_markdown
from revue_portee.reporting.methods import (
    AI_REPORTING_ELEMENTS,
    AITaskUse,
    ConsultationSummary,
    DeviationLine,
    ExtractionSummary,
    LayLine,
    RegistrationLine,
    SearchLine,
    SynthesisSummary,
    build_methods,
)
from unit.reporting.test_methods import data

COMPLETE = {
    "extraction": ExtractionSummary(grid_version=2, fields=7, studies=12, validated=40),
    "registration": RegistrationLine(doi="10.17605/OSF.IO/ABCDE",
                                     registered_on=dt.date(2026, 10, 1)),
    "deviations": (
        DeviationLine(kind="criteria", number=2, activated_on=dt.date(2026, 10, 5),
                      rationale="Adultes"),
        DeviationLine(kind="grid", number=2, activated_on=dt.date(2026, 10, 6), rationale=""),
    ),
    "search": (SearchLine(database="PubMed", executed_on=dt.date(2026, 9, 30), records=1234),),
    "dedup_algorithm": "1",
    "pairs_decided": 3,
    "synthesis": SynthesisSummary(gap_comments=2, lay=(
        LayLine(level="general", formula="Kandel-Moles", index=64.25, target=60.0),)),
    "consultation": ConsultationSummary(
        stakeholders=3, by_role={"clinicien": 1, "patient partenaire": 3}, comments=4,
        answered=3, by_action={"changed": 2, "noted": 1},
    ),
    "ai_tasks": (
        AITaskUse(task="extract_fields", provider="anthropic",
                  models_returned=("model-b-20261001",), template_versions=("2",), calls=12,
                  amount=Decimal("0.0412")),
        AITaskUse(task="screen_reference", provider="anthropic",
                  models_returned=("model-a-20261001",), template_versions=("1",), calls=1100,
                  amount=Decimal("3.5")),
    ),
}  # fmt: skip


def test_every_step_in_french() -> None:
    document = build_methods(data(**COMPLETE), language="fr")
    text = render_markdown(document)
    assert text.startswith("# Revue : méthode et usage de l'IA (ébauche)")
    headings = [b.text for b in document.blocks if isinstance(b, Heading) and b.level == 2]
    # the steps of the review, in order, then the appendix for the external reviewer
    assert headings[:2] == ["Protocole et écarts", "Recherche et dédoublonnage"]
    assert headings.index("Extraction des données") < headings.index(
        "Synthèse et synthèses vulgarisées"
    ) < headings.index("Consultation des parties prenantes") < headings.index(
        "Usage de l'IA par tâche"
    )  # fmt: skip
    assert headings[-1] == "Annexe : déclaration de l'usage de l'IA"
    assert (
        "Le protocole a été enregistré sur OSF le 2026-10-01 (DOI 10.17605/OSF.IO/ABCDE)." in text
    )
    assert "- Critères, version 2 (2026-10-05) : « Adultes »" in text
    assert "- Grille d'extraction, version 2 (2026-10-06) : —" in text
    assert "- PubMed : 1 234 références (recherche du 2026-09-30)" in text
    assert "(algorithme, version 1)" in text
    assert "les paires ambiguës (3). Doublons retirés" in text
    assert "dont 2 ont été commentées par la personne." in text
    assert "- le grand public : 64,2 (Kandel-Moles), cible de 60 ou plus" in text
    assert (
        "3 parties prenantes ont été consultées et ont formulé 4 commentaires (selon le rôle "
        "de leur auteur : clinicien (1) ; patient partenaire (3))."
    ) in text
    assert "Suites données : la revue a été modifiée (2) ; pris en compte sans " in text
    assert "en attente d'une suite : 1." in text
    assert "| extract_fields | model-b-20261001 | 2 | 12 |" in text
    assert "| screen_reference | model-a-20261001 | 1 | 1 100 |" in text


def test_the_appendix_points_to_sections_that_exist() -> None:
    """For the external methodologist: every element of EF-DEC-03 is reported, and the
    section the appendix names for it is in the document."""
    for language in ("fr", "en"):
        document = build_methods(data(**COMPLETE), language=language)
        headings = {b.text for b in document.blocks if isinstance(b, Heading)}
        appendix = [b for b in document.blocks if isinstance(b, Table)][-1]
        assert len(appendix.rows) == len(AI_REPORTING_ELEMENTS) == 11
        for _element, section in appendix.rows:
            assert section in headings, (language, section)
    elements = [row[0] for row in appendix.rows]  # the English document, last
    assert elements[0] == "tool and version"
    assert "conflicts of interest" in elements


def test_screening_only_keeps_its_title_and_has_no_appendix() -> None:
    text = render_markdown(build_methods(data(), language="en"))
    assert text.startswith("# Revue: use of AI in title and abstract screening")
    assert "Protocol and deviations" not in text
    assert "Appendix: reporting of the use of AI" not in text


def test_without_registration_nor_search_runs() -> None:
    plain = COMPLETE | {"registration": None, "deviations": (), "search": ()}
    text = render_markdown(build_methods(data(**plain), language="en"))
    assert "To be completed: where the protocol was published or registered" in text
    # no search run from the tool: the records imported, and the dates to complete
    assert "Records imported by database: PubMed (1,200)." in text
    assert "To be completed: the date of each search" in text
    registered = COMPLETE | {"deviations": ()}
    assert "No version of the criteria or of the extraction grid was activated" in render_markdown(
        build_methods(data(**registered), language="en")
    )
    quiet = COMPLETE | {"consultation": ConsultationSummary(
        stakeholders=0, by_role={}, comments=0, answered=0, by_action={})}  # fmt: skip
    assert "Consultation of stakeholders" not in render_markdown(
        build_methods(data(**quiet), language="en")
    )
