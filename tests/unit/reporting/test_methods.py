"""Draft methods section built from synthetic data (EF-DEC-03): every branch of the
text, in French and English."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from revue_portee.domain.changes import ChangeType
from revue_portee.reporting.document import Heading, Paragraph, Table, render_docx, render_markdown
from revue_portee.reporting.flow import FlowNumbers, Pending, ReassessmentCounts
from revue_portee.reporting.methods import (
    ChangeSummary,
    CostLine,
    MethodsData,
    ModelUse,
    PilotSummary,
    ScreeningSummary,
    ThresholdSummary,
    build_methods,
)
from revue_portee.resources import tool_validation

MOMENT = datetime(2026, 10, 8, 12, tzinfo=UTC)
FLOW = FlowNumbers(
    identified_by_source={"PubMed": 1200},
    identified=1200,
    registers=0,
    duplicates_removed=200,
    removed_by_automation=0,
    removed_other=0,
    screened=1000,
    excluded=900,
    excluded_by_person=900,
    excluded_by_automation=0,
    sought=100,
    reassessments=(),
    pending=Pending(),
)
PILOT = PilotSummary(
    number=2,
    sample_size=100,
    seed=42,
    criteria_version=1,
    compared=100,
    agreement=0.9,
    kappa=0.6154,
    ac1=0.8,
    sensitivity=0.95,
    sensitivity_interval=(0.8, 0.99),
    specificity=0.88,
    specificity_interval=(0.8, 0.93),
    true_positives=19,
    false_positives=9,
    false_negatives=1,
    true_negatives=71,
    calibration_method="isotonic",
    calibration_fitted_on=100,
    rounds=2,
)
COUNTS = ReassessmentCounts(
    from_version=1,
    to_version=2,
    reassessed=20,
    kept_to_excluded=1,
    excluded_to_kept=2,
    completed=False,
)


def data(**changes: object) -> MethodsData:
    base = MethodsData(
        project_title="Revue",
        tool_version="0.1.0 (abc123)",
        generated_at=MOMENT,
        human_reviewers=1,
        provider="anthropic",
        model="model-a",
        params={"max_tokens": "8000", "effort": "low"},
        templates=(("screen_reference", "2", 1100),),
        models=(
            ModelUse(
                provider="anthropic",
                model_requested="model-a",
                model_returned="model-a-20261001",
                calls=1100,
                first=MOMENT,
                last=MOMENT,
            ),
        ),
        pilot=PILOT,
        thresholds=ThresholdSummary(
            exclude_below=0.05,
            include_above=0.6,
            calibrated=True,
            set_by_person=True,
            target_sensitivity=Decimal("0.95"),
            justification="Aucune inclusion manquée sous 0,05.",
        ),
        screening=ScreeningSummary(
            references=1000,
            by_person=1000,
            by_ai=1000,
            by_both=1000,
            disagreements=50,
            reconciled=50,
            reconciled_with_ai=20,
            quotes_found=2870,
            quotes_checked=2900,
        ),
        flow=FLOW,
        changes=(
            ChangeSummary(
                changes=(("C1", ChangeType.CLARIFICATION), ("P1", ChangeType.NARROWING)),
                justification="Précision du concept.",
                sampled=True,
                counts=COUNTS,
            ),
        ),
        costs=(
            CostLine(
                phase="pilot",
                calls=100,
                amount=Decimal("0.1"),
                input_tokens=150_000,
                output_tokens=20_000,
            ),
            CostLine(
                phase="main",
                calls=1000,
                amount=Decimal("0.25"),
                input_tokens=1_500_000,
                output_tokens=200_000,
            ),
            CostLine(
                phase="reassessment",
                calls=20,
                amount=Decimal("0.01"),
                input_tokens=30_000,
                output_tokens=4_000,
            ),
            CostLine(phase="unlinked", calls=2, amount=Decimal("0.002"), input_tokens=3_000),
        ),
        other_costs=CostLine(phase="other", calls=3, amount=Decimal("0.03")),
        currency="USD",
        prices_as_of="2026-10-06",
        validation=tool_validation(),
    )
    return base.model_copy(update=changes)


def text_of(language: str, **changes: object) -> str:
    return render_markdown(build_methods(data(**changes), language=language))


def test_english_draft_reports_every_part() -> None:
    document = build_methods(data(), language="en")
    headings = [b.text for b in document.blocks if isinstance(b, Heading)]
    assert headings == [
        "Revue: use of AI in title and abstract screening (methods, draft)",
        "Description and rationale",
        "Validation",
        "Results of the screening with the AI",
        "Limitations and ethics",
        "Funding and conflicts of interest",
        "References",
    ]
    text = render_markdown(document)
    assert "| anthropic | model-a | model-a-20261001 | 1,100 | 2026-10-08 | 2026-10-08 |" in text
    assert "screen_reference, version 2 (1,100 calls)" in text
    assert "effort=low; max_tokens=8000" in text
    # the configuration differs from the evaluated one (model and prompt template version)
    assert "differs from the one evaluated (model model-a; prompt template version 2)" in text
    assert "(seed 42)" in text
    assert "(round 2 of 2)" in text
    assert "| Sensitivity (95% CI) | 95.0% (80.0% to 99.0%) |" in text
    assert "| Cohen's kappa | 0.62 |" in text
    assert "both keep: 19; AI keeps, person excludes: 9; AI excludes, person keeps: 1" in text
    assert "calibrated on the pilot (isotonic, 100 decisions)" in text
    assert "calibrated probability of inclusion was below 0.05" in text
    assert "Target sensitivity: 95.0%." in text
    assert "“Aucune inclusion manquée sous 0,05.”" in text
    assert "Disagreements between the person and the AI" in text
    assert "{count}" not in text
    assert "followed the AI for 20 and the person's first decision for 30" in text
    assert "found word for word in the title or abstract" in text
    assert "2,870 of 2,900 (99.0%)" in text
    assert "(C1: clarification; P1: narrowing)" in text
    assert "Clarifications were reassessed on a random sample." in text
    assert "The reassessment is not completed." in text
    assert "| Failed calls not linked to a round | 2 | 3,000 | 0 | 0.0020 |" in text
    # by hand: 1,683,000 tokens read, 224,000 written; 1,907,000 for 1,000 references
    assert "| Total of the screening | 1,122 | 1,683,000 | 224,000 | 0.3620 |" in text
    assert "processed 1,907,000 tokens, about 1,907 per reference screened." in text
    assert "Other uses of the AI in the project (framing, criteria, search): 3 calls" in text
    assert "rests on 20 included references (95% CI 76.4% to 99.1%)" in text
    assert "tested on its development set" in text
    assert "neither a test on held-out data nor a validation" in text
    assert "validated" not in text
    assert "No reference was excluded by the AI alone." in text
    assert render_docx(document)[:2] == b"PK"


def test_docx_is_the_same_at_another_time(monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    document = build_methods(data(), language="en")
    first = render_docx(document)
    later = time.time() + 120
    monkeypatch.setattr(time, "time", lambda: later)
    monkeypatch.setattr(time, "localtime", lambda *_: time.gmtime(later))
    assert render_docx(document) == first


def test_french_typography() -> None:
    text = text_of("fr")
    assert text.startswith("# Revue : usage de l'IA au tri des titres et résumés")
    assert "| Sensibilité (IC à 95 %) | 95,0 % (80,0 % à 99,0 %) |" in text
    assert "| Kappa de Cohen | 0,62 |" in text
    assert "« Aucune inclusion manquée sous 0,05. »" in text
    assert "| Total du tri | 1 122 | 1 683 000 | 224 000 | 0,3620 |" in text
    assert "Critères, version 1 à 2" in text


def test_without_ai_pilot_nor_screening() -> None:
    document = build_methods(
        data(
            models=(),
            templates=(),
            pilot=None,
            screening=None,
            changes=(),
            thresholds=ThresholdSummary(
                exclude_below=0.1, include_above=0.6, calibrated=False, set_by_person=False
            ),
            flow=FLOW.model_copy(update={"pending": Pending(screening_not_started=True)}),
            other_costs=CostLine(phase="other", calls=0, amount=Decimal(0)),
        ),
        language="en",
    )
    text = render_markdown(document)
    assert "No AI was used to screen titles and abstracts." in text
    assert "Provisional: the screening is not finished (the main screening has not started)." in (
        text
    )
    assert "The main screening has not started." in text
    assert "differs from the one evaluated" not in text  # nothing to compare
    assert "No pilot round" not in text  # no AI: no pilot nor thresholds to report
    assert "Other uses of the AI" not in text


def test_pilot_and_thresholds_by_default() -> None:
    text = text_of(
        "en",
        pilot=None,
        thresholds=ThresholdSummary(
            exclude_below=0.1, include_above=0.6, calibrated=False, set_by_person=False
        ),
        changes=(),
        model=tool_validation().configuration.model,
        templates=(("screen_reference", "1", 1100),),
    )
    assert "No pilot round was recorded before the screening." in text
    assert "the project defaults (0.10 and 0.60)" in text
    assert "The criteria did not change during the screening." in text
    assert "differs from the one evaluated" not in text


def test_missing_measures_and_thresholds_without_calibration() -> None:
    pilot = PILOT.model_copy(
        update={
            "kappa": None,
            "sensitivity": None,
            "sensitivity_interval": None,
            "calibration_method": None,
        }
    )
    thresholds = ThresholdSummary(
        exclude_below=0.1, include_above=0.6, calibrated=False, set_by_person=True
    )
    document = build_methods(data(pilot=pilot, thresholds=thresholds), language="en")
    table = next(b for b in document.blocks if isinstance(b, Table) and b.header[0] == "Measure")
    values = {row[0]: row[1] for row in table.rows}
    assert values["Cohen's kappa"] == "—"
    assert values["Sensitivity (95% CI)"] == "—"
    assert values["Agreement"] == "90.0%"
    paragraphs = " ".join(b.text for b in document.blocks if isinstance(b, Paragraph))
    assert "when its probability of inclusion was below 0.10" in paragraphs
    assert "Target sensitivity" not in paragraphs
    assert "calibrated on the pilot" not in paragraphs


def test_validation_on_held_out_data() -> None:
    held_out = tool_validation().model_copy(update={"dataset_role": "test"})
    text = text_of("en", validation=held_out)
    assert "These reviews were held out: they were not used to build the tool." in text
    assert "The tool was evaluated on systematic reviews in psychology" in text
    assert "development set" not in text


def test_environmental_impact_without_tokens() -> None:
    costs = (CostLine(phase="main", calls=5, amount=Decimal("0.01")),)
    text = text_of("en", costs=costs)
    assert "(energy, water, emissions) was not measured." in text
    assert "tokens per reference" not in text


def test_data_extraction() -> None:
    from revue_portee.reporting.methods import ExtractionSummary, FieldAgreementLine

    summary = ExtractionSummary(
        grid_version=2, fields=3, studies=12, provider="anthropic", model="model-b",
        template_version="1", ai_studies=11, validated=20, corrected=8, rejected=2,
        extracted=4, pending=2, quotes_at_page=25, quotes_other_page=3, quotes_not_found=1,
        pilot_studies=5, pilot_seed=42,
        pilot_agreement=(
            FieldAgreementLine(code="D1", label="Pays", compared=5, agreed=5),
            FieldAgreementLine(code="D2", label="Devis", compared=5, agreed=3),
            FieldAgreementLine(code="D3", label="n", compared=0, agreed=0),
        ),
    )  # fmt: skip
    french = text_of("fr", extraction=summary)
    assert "## Extraction des données" in french
    assert "version 2 de la grille d'extraction (3 champs), pour 12 études incluses" in french
    assert "a prérempli la grille pour 11 études" in french
    assert "à la page indiquée, 25 ; à une autre page, 3 ; introuvable, 1." in french
    assert "valeurs validées, 20 ; corrigées, 8 ; rejetées, 2 ;" in french
    assert "pas encore vérifiées, 2." in french
    assert "(graine 42)" in french
    assert "par champ : D1 5 sur 5 ; D2 3 sur 5." in french
    english = text_of("en", extraction=summary.model_copy(update={"ai_studies": 0}))
    assert "## Data extraction" in english
    assert "pre-filled" not in english  # the AI did not pre-fill
    assert "Data extraction" not in text_of("en")
