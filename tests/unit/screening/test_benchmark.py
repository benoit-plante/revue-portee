"""SYNERGY benchmark tooling (tranche 1.6), with FakeProvider on a fictional dataset."""

import io
import json
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from revue_portee.ai.base import ModelProvider, TaskInput
from revue_portee.ai.providers.fake import FakeProvider
from revue_portee.ai.settings import AITaskConfig
from revue_portee.ai.tasks.screening import ScreenReferenceInput
from revue_portee.cli.main import app
from revue_portee.domain.screening import DecisionValue, Thresholds
from revue_portee.protocol import ai_assist
from revue_portee.resources import default_ai_settings
from revue_portee.screening import benchmark
from support import make_clock

DATA = Path(__file__).parents[2] / "fixtures" / "synergy"
THRESHOLDS = Thresholds(exclude_below=0.10, include_above=0.60)


def answer(item: TaskInput) -> dict[str, Any]:
    """Keeps a record whose title says « older »."""
    assert isinstance(item, ScreenReferenceInput)
    keep = "older" in item.reference.title.lower()
    status = "met" if keep else "not_met"
    # « older adults » is in the titles kept; for the seniors it is made up
    quote = "older adults" if keep or "seniors" in item.reference.title.lower() else ""
    return {
        "assessments": [
            {"code": "P1", "status": status, "evidence_quote": quote},
            {"code": "C1", "status": status, "evidence_quote": ""},
        ],
        "decision": "include" if keep else "exclude",
        "inclusion_probability": 0.9 if keep else 0.02,
        "rationale": "P1 et C1.",
        "decisive_criteria": ["P1"],
    }


def fake(responder: Callable[[TaskInput], dict[str, Any]] = answer) -> FakeProvider:
    return FakeProvider(
        model="fake-model",
        model_returned="fake-model-2026-10-08",
        responder=responder,
        cost_per_call=Decimal("0.001"),
    )


def run(
    provider: ModelProvider, ceiling: str = "1", workers: int = 1
) -> tuple[benchmark.BenchmarkResult, str]:
    records = benchmark.read_dataset(DATA / "mini.csv")
    criteria = benchmark.read_criteria(DATA / "criteres.yaml")
    config = default_ai_settings().enabled_task("screen_reference")
    raw = io.StringIO()
    result = benchmark.run_benchmark(
        "mini",
        records,
        criteria,
        config=config,
        provider=provider,
        thresholds=THRESHOLDS,
        ceiling=Decimal(ceiling),
        raw_output=raw,
        now=make_clock(),
        workers=workers,
    )
    return result, raw.getvalue()


def test_reads_the_dataset_and_the_criteria() -> None:
    records = benchmark.read_dataset(DATA / "mini.csv")
    assert [r.included for r in records] == [True, True, True, False, False, False]
    assert records[5].abstract == ""
    criteria = benchmark.read_criteria(DATA / "criteres.yaml")
    assert [c.code for c in criteria.criteria] == ["P1", "C1"]


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("name,label\nx,1\n", "colonnes"),
        ("title,abstract,label_included\nx,,oui\n", "Ligne 2"),
    ],
)
def test_unusable_dataset(tmp_path: Path, content: str, message: str) -> None:
    path = tmp_path / "bad.csv"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(benchmark.BenchmarkError, match=message):
        benchmark.read_dataset(path)
    with pytest.raises(benchmark.BenchmarkError):
        benchmark.read_dataset(tmp_path / "absent.csv")
    with pytest.raises(benchmark.BenchmarkError):
        benchmark.read_criteria(path)


def test_sample_keeps_every_inclusion() -> None:
    records = benchmark.read_dataset(DATA / "mini.csv")
    chosen = benchmark.select_records(records, 4, seed=3)
    assert len(chosen) == 4
    assert sum(r.included for r in chosen) == 3
    assert chosen == benchmark.select_records(records, 4, seed=3)
    assert benchmark.select_records(records, None, seed=3) == records
    assert benchmark.select_records(records, 2, seed=3) == records[:3]  # inclusions only


def test_metrics_and_cost_on_a_case_computed_by_hand() -> None:
    result, raw = run(fake())
    # tp: records 1 and 2; fn: record 3 (no « older »); fp: record 4; tn: records 5, 6.
    assert result.values["r3"] is DecisionValue.EXCLUDE
    labels = {f"r{i}": i <= 3 for i in range(1, 7)}
    c = result.confusion(labels)
    assert (c.tp, c.fn, c.fp, c.tn) == (2, 1, 1, 2)
    assert result.spent == Decimal("0.006")
    assert result.cost_per_thousand() == Decimal("1.00")  # 0.006 * 1000 / 6
    assert result.models_returned == {"fake-model-2026-10-08"}
    assert len(raw.splitlines()) == 6
    assert json.loads(raw.splitlines()[0])["item_id"] == "r1"
    report = benchmark.report_markdown(result, benchmark.read_dataset(DATA / "mini.csv"))
    assert "| Sensibilité (références incluses conservées) | 66,7 % |" in report
    assert "| Spécificité (références exclues exclues) | 66,7 % |" in report
    assert "| Confusion (vp, fn, fp, vn) | 2, 1, 1, 2 |" in report
    # quotes: records 1, 2 and 4 found, record 3 made up
    assert (result.quotes_found, result.quotes_checked) == (3, 4)
    assert "| Citations de l'IA retrouvées dans le titre ou le résumé | 3 / 4 (75,0 %) |" in report
    assert "| Coût pour 1 000 références | 1.00 USD |" in report
    assert "non atteintes" in report


def test_retry_then_failure_and_ceiling() -> None:
    calls: list[str] = []

    def flaky(item: TaskInput) -> dict[str, Any]:
        calls.append(item.item_id)
        output = answer(item)
        if item.item_id == "r1" and calls.count("r1") == 1:
            output["assessments"] = output["assessments"][:1]  # C1 missing: asked again
        if item.item_id == "r2":
            output["decisive_criteria"] = ["Z9"]  # never usable
        return output

    result, _raw = run(fake(flaky))
    assert calls.count("r1") == 2
    assert result.values["r1"] is DecisionValue.INCLUDE
    assert calls.count("r2") == 2
    assert result.failed == ["r2"]
    assert result.spent == Decimal("0.008")
    assert result.cost_per_thousand() == Decimal("1.33")  # 8 calls for 6 references

    stopped, _raw = run(fake(), ceiling="0.0035")
    assert stopped.stopped
    assert list(stopped.values) == ["r1", "r2", "r3"]
    assert not stopped.failed


def test_parallel_calls_give_the_same_result_and_respect_the_ceiling() -> None:
    serial, _raw = run(fake())
    parallel, raw = run(fake(), workers=4)
    assert parallel.values == serial.values
    assert parallel.spent == serial.spent
    assert len(raw.splitlines()) == 6
    capped, _raw = run(fake(), ceiling="0.0035", workers=4)
    assert capped.stopped
    assert len(capped.values) == 3  # 3 calls of 0.001 fit under the ceiling, whatever the order
    assert capped.spent == Decimal("0.003")
    assert not capped.failed


def test_command_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def factory(config: AITaskConfig) -> ModelProvider:
        return fake()

    monkeypatch.setattr(ai_assist, "default_provider_factory", factory)
    out = tmp_path / "resultats"
    raw = tmp_path / "brut.jsonl"
    arguments = [
        "banc-synergy",
        str(DATA / "mini.csv"),
        "--criteres",
        str(DATA / "criteres.yaml"),
        "--plafond",
        "0,50",
        "--sortie",
        str(out),
        "--brut",
        str(raw),
        "--nom",
        "Mini",
        "--paralleles",
        "2",
    ]
    result = CliRunner().invoke(app, [*arguments, "--oui"])
    assert result.exit_code == 0, result.output
    assert "6 références (3 incluses)" in result.output
    assert "Banc SYNERGY\u00a0: Mini" in (out / "banc-synergy-Mini.md").read_text(encoding="utf-8")
    assert len(raw.read_text(encoding="utf-8").splitlines()) == 6

    refused = CliRunner().invoke(app, arguments, input="n\n")
    assert refused.exit_code == 1
    wrong = CliRunner().invoke(app, [*arguments[:5], "-1"])
    assert wrong.exit_code == 1
    assert "montant positif" in wrong.output
