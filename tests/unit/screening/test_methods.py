"""Draft methods section from the demonstration project (EF-DEC-03): each number is
the one counted by hand (tests/fixtures/demo/README.md)."""

from decimal import Decimal
from pathlib import Path

import pytest

from demo import build, create, deduplicate, run_pilot
from revue_portee.domain.changes import ChangeType
from revue_portee.protocol.document import ExportFormat
from revue_portee.reporting.document import Paragraph
from revue_portee.screening.methods import export_methods, methods_data, methods_document
from support import TOOL_VERSION, make_clock


def test_demonstration_counted_by_hand(tmp_path: Path) -> None:
    demo = build(tmp_path)
    try:
        data = methods_data(demo.folder, now=make_clock(), tool_version=TOOL_VERSION)
    finally:
        demo.folder.close()
    # five references screened by the AI in the main screening, two reassessed
    (model,) = data.models
    assert (model.model_returned, model.calls) == ("fake-model-2026-10-07", 7)
    assert data.templates == (("screen_reference", "1", 7),)
    assert data.human_reviewers == 1
    assert data.pilot is None
    assert not data.thresholds.set_by_person
    screening = data.screening
    assert screening is not None
    assert (screening.references, screening.by_person, screening.by_ai, screening.by_both) == (
        5,
        5,
        5,
        5,
    )
    # the gardens study: the person followed the AI
    assert (screening.disagreements, screening.reconciled, screening.reconciled_with_ai) == (
        1,
        1,
        1,
    )
    (change,) = data.changes
    assert change.changes == (("P1", ChangeType.BROADENING),)
    assert change.justification == "Population élargie à tous les adultes."
    assert (change.counts.reassessed, change.counts.excluded_to_kept) == (2, 1)
    costs = {c.phase: (c.calls, c.amount) for c in data.costs}
    # FakeProvider: 0.002 per call, at half price through the batch API
    assert costs == {
        "pilot": (0, Decimal(0)),
        "main": (5, Decimal("0.005")),
        "reassessment": (2, Decimal("0.002")),
        "unlinked": (0, Decimal(0)),
    }
    assert data.other_costs.calls == 0


def test_pilot_counted_by_hand(tmp_path: Path) -> None:
    demo = create(tmp_path)
    try:
        deduplicate(demo)
        round_id = run_pilot(demo)
        data = methods_data(demo.folder, now=make_clock(), tool_version=TOOL_VERSION)
    finally:
        demo.folder.close()
    summary = data.pilot
    assert summary is not None
    assert (summary.number, summary.sample_size, summary.seed, summary.compared) == (1, 5, 7, 5)
    # person keeps caregivers, gardens, loneliness; the AI keeps caregivers, loneliness
    confusion = (
        summary.true_positives,
        summary.false_positives,
        summary.false_negatives,
        summary.true_negatives,
    )
    assert confusion == (2, 0, 1, 2)
    assert summary.agreement == pytest.approx(0.8)
    assert summary.sensitivity == pytest.approx(2 / 3)
    assert summary.specificity == pytest.approx(1.0)
    assert summary.kappa == pytest.approx((0.8 - 0.48) / (1 - 0.48))
    assert summary.ac1 == pytest.approx((0.8 - 0.5) / (1 - 0.5))
    assert summary.calibration_method is not None
    assert summary.calibration_fitted_on == 5
    thresholds = data.thresholds
    assert thresholds.set_by_person
    assert thresholds.calibrated
    assert (thresholds.exclude_below, thresholds.include_above) == (0.05, 0.6)
    assert thresholds.target_sensitivity == Decimal("0.95")
    assert data.screening is None
    costs = {c.phase: c.calls for c in data.costs}
    assert costs["pilot"] == 5  # one synchronous call per reference
    assert round_id


def test_export_in_both_languages(tmp_path: Path) -> None:
    demo = build(tmp_path)
    try:
        french = methods_document(demo.folder, language="fr", now=make_clock(), tool_version="0.1")
        paths = [
            export_methods(
                demo.folder, language=language, format=fmt, now=make_clock(), tool_version="0.1"
            )
            for language in ("fr", "en")
            for fmt in ExportFormat
        ]
    finally:
        demo.folder.close()
    assert [p.name for p in paths] == [
        "methode-fr.md",
        "methode-fr.docx",
        "methode-en.md",
        "methode-en.docx",
    ]
    text = paths[0].read_text(encoding="utf-8")
    assert text.startswith("# Soutien à la parentalité et santé mentale des enfants : usage")
    assert "Références triées : 5 ; exclues : 2" in text
    assert "Aucune référence n'a été exclue par l'IA seule." in text
    placeholders = [b for b in french.blocks if isinstance(b, Paragraph) and b.placeholder]
    assert len(placeholders) == 3  # rationale, limitations of the review, funding
