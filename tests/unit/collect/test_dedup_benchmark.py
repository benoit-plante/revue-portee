"""Deduplication test on held-out annotated sets in the ASySD format (RAISE 2, 2.10),
checked on a fictional file counted by hand (tests/fixtures/dedup/asysd-mini.csv)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from revue_portee.cli.main import app
from revue_portee.collect import dedup_benchmark as bench

MINI = Path(__file__).parents[2] / "fixtures" / "dedup" / "asysd-mini.csv"
MOMENT = datetime(2026, 10, 8, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    ("text", "authors"),
    [
        ("Adeli K.Lewis G. F.", ("Adeli K.", "Lewis G. F.")),
        ("Franke K.Gaser C.de Rooij S. R.", ("Franke K.", "Gaser C.", "de Rooij S. R.")),
        ("Gagnon L.", ("Gagnon L.",)),
        ("", ()),
    ],
)
def test_split_authors(text: str, authors: tuple[str, ...]) -> None:
    assert bench.split_authors(text) == authors


def test_reads_the_asysd_format() -> None:
    records = bench.read_asysd(MINI, created_at=MOMENT)
    assert len(records) == 8
    first = records[0].reference
    assert (first.id, first.year, first.container_title, first.pages) == (
        "000001",
        2008,
        "Curr Opin Lipidol",
        "221-8",
    )
    assert records[1].reference.doi == first.doi == "10.5555/DEMO.1001"  # URL form cleaned
    assert first.abstract == ""  # abstracts are not read
    assert [r.group for r in records] == ["1", "1", "2", "2", "3", "4", "5", "5"]


def test_measured_on_a_case_counted_by_hand() -> None:
    # groups 1 (same DOI), 2 (same title in capitals) and 5 (authors in another order)
    # are pairs of duplicates; 3 and 4 have close titles but are distinct studies.
    test = bench.run_test("mini", bench.read_asysd(MINI, created_at=MOMENT), now=MOMENT)
    e = test.evaluation
    assert (test.records, test.groups) == (8, 5)
    assert (e.true_pairs, e.found_pairs, e.correct_pairs) == (3, 3, 3)
    assert (e.automatic_pairs, e.automatic_errors, e.review_pairs) == (2, 0, 1)
    assert (e.recall, e.precision) == (1.0, 1.0)
    assert test.targets_met
    report = bench.report_markdown(test)
    assert report.startswith("# Test du dédoublonnage : ASySD mini")
    assert "| Rappel | 1,000 |" in report
    assert "| Paires laissées à une personne | 1 |" in report
    assert "CC BY 4.0" in report


def test_command_line(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["banc-doublons", str(MINI), "--sortie", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "mini" in result.output
    assert (tmp_path / "dedoublonnage-asysd-asysd-mini.md").is_file()
    missing = CliRunner().invoke(app, ["banc-doublons", str(tmp_path / "absent.csv")])
    assert missing.exit_code == 1
