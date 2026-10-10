"""``revue-portee banc-replication`` and the collection of a rebuilt strategy, offline."""

import hashlib
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from replication_support import Finder, copy_review, factory
from revue_portee.cli.main import app
from revue_portee.domain.project import ReplicationMode
from revue_portee.domain.search import Database
from revue_portee.replication import bench
from revue_portee.replication.inputs import read_inputs, read_standard
from revue_portee.sources.records import FetchedPage, FetchedRecord
from support import TOOL_VERSION, make_clock

runner = CliRunner()


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """The command with the fictitious AI and open access sources (no network)."""
    real = bench.run_bench
    fake = factory()

    def run(*args: Any, **kwargs: Any) -> bench.BenchOutcome:  # noqa: ANN401
        kwargs |= {"factory": fake, "finder": Finder, "wait": lambda _s: None}
        return real(*args, **kwargs)

    monkeypatch.setattr(bench, "run_bench", run)


def test_command_stops_for_texts_then_writes_the_report(tmp_path: Path, offline: None) -> None:
    review = copy_review(tmp_path)
    sortie = tmp_path / "rapports"
    args = ["banc-replication", str(review), "--plafond", "5", "--oui", "--sortie", str(sortie)]
    first = runner.invoke(app, args)
    assert first.exit_code == 0, first.output
    assert "Textes intégraux à téléverser : 1." in first.output
    assert "- 10.5555/FICT.0004 — A walking prescription" in first.output
    second = runner.invoke(app, [*args, "--poursuivre"])
    assert second.exit_code == 0, second.output
    assert "dépensé : 0.245 $ US sur 5." in second.output
    report = sortie / "replication-Fictive_2026_marche_anxiete.md"
    assert f"Rapport écrit : {report}" in second.output
    assert "référence appariée : S5, S6" in second.output
    assert "## Mode en chaîne (en-chaine)" in report.read_text(encoding="utf-8")
    stepwise = runner.invoke(app, [*args, "--poursuivre", "--mode", "par-etape"])
    assert stepwise.exit_code == 0, stepwise.output
    assert "## Mode par étape" in report.read_text(encoding="utf-8")


def test_command_asks_before_paying(tmp_path: Path, offline: None) -> None:
    review = copy_review(tmp_path)
    refused = runner.invoke(app, ["banc-replication", str(review), "--plafond", "5"], input="n\n")
    assert refused.exit_code == 1
    assert "Tri des titres et résumés : 27 éléments avec fake" in refused.output
    assert "coût non confirmé" in refused.output


def test_command_reports_the_ceiling(tmp_path: Path, offline: None) -> None:
    review = copy_review(tmp_path)
    result = runner.invoke(app, ["banc-replication", str(review), "--plafond", "0,10", "--oui"])
    assert result.exit_code == 0, result.output
    assert "Plafond atteint à l'étape « Tri des titres et résumés »" in result.output


def test_command_without_reference_standard(tmp_path: Path, offline: None) -> None:
    review = copy_review(tmp_path)
    for name in ("incluses.csv", "extraction-publiee.csv", "resultats-publies.yaml"):
        (review / "norme" / name).unlink()
    args = ["banc-replication", str(review), "--plafond", "5", "--oui", "--poursuivre",
            "--sortie", str(tmp_path)]  # fmt: skip
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "pas encore de norme de référence" in result.output
    stepwise = runner.invoke(app, [*args, "--mode", "par-etape"])
    assert stepwise.exit_code == 1
    assert "norme de référence" in stepwise.output


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["--mode", "autre"], "Mode inconnu"),
        (["--plafond", "zéro"], "montant positif"),
        (["--plafond", "-1"], "montant positif"),
    ],
)
def test_command_refuses_bad_options(tmp_path: Path, extra: list[str], message: str) -> None:
    review = copy_review(tmp_path, texts=False)
    result = runner.invoke(app, ["banc-replication", str(review), "--plafond", "1", *extra])
    assert result.exit_code == 1
    assert message in result.output


def test_command_refuses_a_broken_freeze(tmp_path: Path) -> None:
    review = copy_review(tmp_path, texts=False)
    (review / "grille.yaml").write_text("modifiée\n", "utf-8")
    result = runner.invoke(app, ["banc-replication", str(review), "--plafond", "1", "--oui"])
    assert result.exit_code == 1
    assert "grille.yaml a changé depuis le gel" in result.output


# --- Collection of a rebuilt strategy ----------------------------------------------------


class _PubMed:
    """One page of two records: the study lost at the search (S5) and another."""

    database = Database.PUBMED

    def __init__(self) -> None:
        self.fetched = 0

    def fetch(self, query: str, cursor: str | None) -> FetchedPage:
        self.fetched += 1
        records = (
            FetchedRecord("9001", {"title": "Aquatic walking classes and anxiety in older women",
                                   "doi": "10.5555/FICT.0006", "year": 2021}),
            FetchedRecord("9002", {"title": "Rowing and memory in rats", "year": 2020}),
        )  # fmt: skip
        return FetchedPage(records=records, announced=2, next_cursor=None, raw={"ids": ["9001"]})


def test_rebuilt_strategy_is_collected_once(tmp_path: Path) -> None:
    review = copy_review(tmp_path, texts=False)
    (review / "recherche" / "strategie.yaml").write_text(
        "bases: [pubmed]\nlimites: {annee_max: 2025}\n"
        "blocs:\n  - libelle: Marche\n    element: concept\n    termes: ['walking']\n",
        "utf-8",
    )
    names = ["criteres.yaml", "grille.yaml", "recherche/export-base-fictive.ris",
             "recherche/strategie.yaml"]  # fmt: skip
    (review / "GEL.sha256").write_text(
        "".join(f"{hashlib.sha256((review / n).read_bytes()).hexdigest()}  {n}\n" for n in names),
        "utf-8",
    )
    source = _PubMed()
    collector: Callable[[Database], _PubMed] = lambda _database: source  # noqa: E731
    inputs, standard = read_inputs(review), read_standard(review)
    said: list[str] = []
    for _run in range(2):
        outcome = bench.run_bench(
            inputs, bench.BenchSettings(mode=ReplicationMode.CHAINED, ceiling=Decimal(1)),
            standard=standard, factory=factory(), collector=collector,
            confirm=lambda _s, _p: False, say=said.append, now=make_clock(),
            tool_version=TOOL_VERSION,
        )  # fmt: skip
        assert outcome.stopped is bench.Stop.REFUSED
    assert source.fetched == 1  # the second run does not collect again
    assert "Collecté dans PubMed : 2 notices" in said
