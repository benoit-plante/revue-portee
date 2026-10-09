"""Accuracy of the pre-filling against an extraction made by hand: agreement rules,
counts by field and quotes, counted by hand."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from pydantic import JsonValue
from typer.testing import CliRunner

from revue_portee.cli.main import app
from revue_portee.domain.extraction import ExtractionValue, ValueStatus
from revue_portee.domain.fulltext import QuoteCheck
from revue_portee.domain.grid import FieldType, GridField
from revue_portee.domain.project import ReviewerKind
from revue_portee.extraction import benchmark, prefill
from support import TOOL_VERSION
from unit.extraction.test_prefill import _with_grid, answer, factory

T0 = datetime(2026, 10, 9, tzinfo=UTC)


def _value(value: JsonValue, *, reported: bool = True) -> ExtractionValue:
    return ExtractionValue(
        id="V", reference_id="R", field_code="D1", grid_version_id="G", reported=reported,
        value=value, status=ValueStatus.PROPOSED, reviewer_id="AI",
        reviewer_kind=ReviewerKind.AI, ai_call_id="C", created_at=T0,
    )  # fmt: skip


def test_agreement_rules() -> None:
    text = GridField(code="D1", label="Population", type=FieldType.TEXT)
    assert benchmark.agrees(text, "older adults", _value("24 older adults in residences"))
    assert benchmark.agrees(text, "Older adults living alone", _value("older adults alone, Canada"))
    assert not benchmark.agrees(text, "children", _value("older adults"))
    assert benchmark.agrees(text, "", _value(None, reported=False))
    assert not benchmark.agrees(text, "", _value("older adults"))
    assert not benchmark.agrees(text, "older adults", _value(None, reported=False))
    assert not benchmark.agrees(text, "older adults", None)
    many = GridField(
        code="D1", label="Devis", type=FieldType.MULTIPLE_CHOICE, choices=("A", "B", "C")
    )
    assert benchmark.agrees(many, "B | A", _value(["A", "B"]))
    assert not benchmark.agrees(many, "A | Z", _value(["A"]))
    number = GridField(code="D1", label="n", type=FieldType.NUMBER)
    assert benchmark.agrees(number, "24", _value(24))


def test_measure_counted_by_hand(tmp_path: Path) -> None:
    demo = _with_grid(tmp_path)
    ref = demo.ids()["loneliness"]
    try:
        prefill.run_ai(
            demo.folder, batch_limit=Decimal(1), factory=factory(answer), now=demo.clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
    finally:
        demo.folder.close()
    # D1 not reported by both; D2 24 by both; D3 « Quantitatif » by hand, « Qualitatif » by AI
    reference = tmp_path / "main.csv"
    reference.write_text(
        f"reference,field,value\n{ref},D1,\n{ref},D2,24\n{ref},D3,Quantitatif\n"
        "10.9999/ABSENT,D1,x\n" + f"{ref},D9,ignored\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    template = tmp_path / "a-remplir.csv"
    written = runner.invoke(
        app, ["banc-extraction", str(demo.folder.path), str(template), "--modele"]
    )
    assert written.exit_code == 0, written.output
    assert template.read_text(encoding="utf-8").splitlines()[1].endswith(",D1,Pays,")
    out = tmp_path / "rapports"
    result = runner.invoke(
        app, ["banc-extraction", str(demo.folder.path), str(reference), "--sortie", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert "66.7%" in result.output
    report = (out / "extraction-main.md").read_text(encoding="utf-8")
    assert "| D3 — Devis | 1 | 0 | 0.0% |" in report
    assert "| **Total** | 3 | 2 | **66.7%** |" in report
    assert "| À la page indiquée par l'IA | 1 |" in report
    assert "| À une autre page (placée par l'outil à la page où elle se trouve) | 1 |" in report
    assert "absentes ou non pré-remplies : 1" in report
    assert "older adults" not in report  # no value nor quote of the reports
    empty = tmp_path / "vide.csv"
    empty.write_text("reference,field,value\n10.9999/X,D1,\n", encoding="utf-8")
    assert runner.invoke(app, ["banc-extraction", str(demo.folder.path), str(empty)]).exit_code == 1
    assert (
        runner.invoke(
            app, ["banc-extraction", str(demo.folder.path), str(tmp_path / "x.csv")]
        ).exit_code
        == 1
    )


def test_quotes_counted() -> None:
    test = benchmark.ExtractionTest(
        grid_number=1, studies=1, fields=[], quotes={QuoteCheck.NOT_FOUND: 2}, generated_at=None
    )
    report = benchmark.report_markdown(test)
    assert "| Introuvables (valeur signalée, sans page) | 2 |" in report
    assert "- Grille, version 1" in report
