"""Dry run of the replication benchmark on the fictitious review, in both modes: every
number of the report equals the count by hand of tests/fixtures/replication/README.md."""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from replication_support import TEXTS, Finder, copy_review, factory
from revue_portee.ai.providers import ProviderFactory
from revue_portee.domain.project import ReplicationMarker, ReplicationMode
from revue_portee.domain.replication import LossStage
from revue_portee.domain.screening import DecisionContext
from revue_portee.protocol.ai_assist import CostPreview
from revue_portee.replication import bench, report
from revue_portee.replication.inputs import (
    ReplicationInputError,
    ReviewInputs,
    Standard,
    read_inputs,
    read_standard,
)
from revue_portee.storage.project_folder import create_project_folder, open_project_folder
from revue_portee.storage.repositories import ai as ai_repo
from revue_portee.storage.repositories import screening as screening_repo
from support import TOOL_VERSION, make_clock

CHAINED, STEPWISE = ReplicationMode.CHAINED, ReplicationMode.STEPWISE


@dataclass
class Replay:
    review: Path
    inputs: ReviewInputs
    standard: Standard
    clock: Callable[[], datetime]
    factory: ProviderFactory
    asked: list[str]

    def run(self, mode: ReplicationMode, *, ceiling: str = "5", go_on: bool = False,
            confirm: bool = True) -> bench.BenchOutcome:  # fmt: skip
        def answer(step: str, preview: CostPreview) -> bool:
            self.asked.append(f"{step}: {preview.items}")
            return confirm

        return bench.run_bench(
            self.inputs,
            bench.BenchSettings(mode=mode, ceiling=Decimal(ceiling), go_on_without_texts=go_on),
            standard=self.standard, factory=self.factory, finder=Finder, confirm=answer,
            now=self.clock, tool_version=TOOL_VERSION,
            wait=lambda _seconds: None,
        )  # fmt: skip

    def calls(self, mode: ReplicationMode) -> Counter[str]:
        folder = open_project_folder(bench.project_path(self.review, mode), now=make_clock(),
                                     tool_version=TOOL_VERSION, record_opening=False)  # fmt: skip
        try:
            with folder.engine.connect() as connection:
                return Counter(c.task for c in ai_repo.list_calls(connection))
        finally:
            folder.close()


type Replayed = tuple[Replay, dict[str, Any]]


def _replay(tmp_path: Path) -> Replay:
    review = copy_review(tmp_path)
    return Replay(review, read_inputs(review), read_standard(review), make_clock(), factory(), [])


@pytest.fixture(scope="module")
def replayed(tmp_path_factory: pytest.TempPathFactory) -> Replayed:
    """Both modes, each stopped after the retrieval (S3 missing), then resumed."""
    replay = _replay(tmp_path_factory.mktemp("replay"))
    seen: dict[str, Any] = {}
    for mode in (CHAINED, STEPWISE):
        first = replay.run(mode)
        seen[f"{mode}-first"] = first
        seen[f"{mode}-calls-first"] = replay.calls(mode)
        seen[f"{mode}-second"] = replay.run(mode, go_on=True)
        seen[f"{mode}-calls"] = replay.calls(mode)
    return replay, seen


def _measures(replay: Replay) -> dict[ReplicationMode, report.ModeMeasures]:
    found = report.measure_review(replay.review, replay.inputs.sheet, replay.standard,
                                  now=make_clock(), tool_version=TOOL_VERSION)  # fmt: skip
    return {m.mode: m for m in found}


# --- Stop after the retrieval, then resume ---------------------------------------------


def test_stops_after_the_retrieval_with_the_texts_to_upload(replayed: Replayed) -> None:
    _replay, seen = replayed
    for mode in (CHAINED, STEPWISE):
        first = seen[f"{mode}-first"]
        assert isinstance(first, bench.BenchOutcome)
        assert first.stopped is bench.Stop.TEXTS
        assert [r.doi for r in first.missing] == ["10.5555/FICT.0004"]  # S3
    assert seen["chained-calls-first"] == Counter({"screen_reference": 28})
    assert seen["stepwise-calls-first"] == Counter()


def test_resumes_without_calling_again(replayed: Replayed) -> None:
    replay, seen = replayed
    for mode in (CHAINED, STEPWISE):
        second = seen[f"{mode}-second"]
        assert isinstance(second, bench.BenchOutcome)
        assert second.stopped is bench.Stop.NONE
    assert seen["chained-calls"] == Counter(
        {"screen_reference": 28, "screen_fulltext": 7, "group_reports": 1, "extract_fields": 3,
         "draft_synthesis": 3}
    )  # fmt: skip
    assert seen["stepwise-calls"] == Counter(
        {"screen_fulltext": 5, "extract_fields": 5, "draft_synthesis": 3}
    )
    assert seen["chained-second"].spent == Decimal("0.245")
    assert seen["stepwise-second"].spent == Decimal("0.105")
    # A third run finds everything done: no call, no question.
    asked = len(replay.asked)
    again = replay.run(CHAINED, go_on=True)
    assert again.stopped is bench.Stop.NONE
    assert replay.calls(CHAINED) == seen["chained-calls"]
    assert len(replay.asked) == asked


def test_ai_decisions_are_final_in_the_replication_project(replayed: Replayed) -> None:
    replay, _seen = replayed
    folder = open_project_folder(bench.project_path(replay.review, CHAINED), now=make_clock(),
                                 tool_version=TOOL_VERSION, record_opening=False)  # fmt: skip
    try:
        assert folder.replication == ReplicationMarker(
            review_id="Fictive_2026_marche_anxiete", mode=CHAINED
        )
        with folder.engine.connect() as connection:
            decisions = screening_repo.list_decisions(connection)
        assert len(decisions) == 26 + 7  # title and abstract, then full text
        assert {d.context for d in decisions} == {DecisionContext.REPLICATION}
        # The value comes from the probability and the thresholds, never from the model.
        assert all(d.thresholds is not None and d.confidence_raw is not None for d in decisions)
        svg = (folder.path / "exports" / "diagramme-fr.svg").read_text(encoding="utf-8")
        assert "Simulation de réplication — ne constitue pas une revue" in svg
    finally:
        folder.close()


# --- Every number of the report ---------------------------------------------------------


def test_chained_measures_equal_the_count_by_hand(replayed: Replayed) -> None:
    m = _measures(replayed[0])[CHAINED]
    assert m.completed
    assert (m.identified, m.after_duplicates, m.unmatched) == (29, 27, 2)
    assert (m.retrievability.count, m.retrievability.total) == (4, 6)
    assert (m.retrievability_in_search.count, m.retrievability_in_search.total) == (4, 5)
    assert (m.screened, m.screened_excluded, m.screened_uncertain) == (27, 19, 1)
    assert m.screening_recall is not None
    assert (m.screening_recall.count, m.screening_recall.total) == (3, 4)
    assert (m.sought, m.open_access, m.uploaded, m.not_obtained) == (8, 1, 6, 1)
    assert (m.full_text_assessed, m.full_text_kept, m.full_text_uncertain) == (7, 4, 1)
    assert (m.full_text_recall.count, m.full_text_recall.total) == (1, 2)
    assert (m.reports, m.studies) == (4, 3)
    assert [(a.field, a.compared, a.agreed, a.kappa, a.ac1) for a in m.agreement] == [
        ("D1", 1, 1, None, None), ("D2", 1, 1, None, None), ("D3", 1, 1, None, None)
    ]  # fmt: skip
    d1, d2 = m.distributions
    assert [c.gap for c in d1.categories] == pytest.approx([50.0, 50 / 3, 100 / 3])
    assert (d1.within.count, d1.same_mode) == (0, False)
    assert d1.rank_correlation == pytest.approx(-0.5)
    assert d2.field == "D2"
    assert [c.gap for c in d2.categories] == pytest.approx([0, 0, 0])
    assert (d2.within.count, d2.same_mode, d2.rank_correlation) == (3, True, None)
    assert [(g.box, g.published, g.tool) for g in m.flow] == [
        ("identified", 30, 29), ("after_duplicates", 27, 27), ("screened", 27, 27),
        ("full_texts_assessed", 8, 7), ("included_reports", 7, 4), ("included_studies", 6, 3),
    ]  # fmt: skip
    e = m.end_to_end
    assert e is not None
    assert (e.published, e.retrievable, e.tool, e.matched, e.tool_matched) == (6, 5, 3, 1, 1)
    assert e.f1 == pytest.approx(2 / 9)
    assert e.f1_retrievable == pytest.approx(0.25)
    assert e.jaccard == pytest.approx(1 / 8)
    assert e.jaccard_retrievable == pytest.approx(1 / 7)
    assert m.cascade == dict.fromkeys(LossStage, 1)
    assert (m.lost_without_abstract, m.lost_by_criterion) == (1, {"C1": 1})
    assert m.extra_years == {"within": 1, "after": 1, "unknown": 0}
    costs = {c.task: (c.calls, c.unusable, c.amount) for c in m.costs}
    assert costs["screen_reference"] == (28, 2, Decimal("0.140"))
    assert sum(c.calls for c in m.costs) == 42
    assert m.kept_unusable == 1


def test_stepwise_measures_equal_the_count_by_hand(replayed: Replayed) -> None:
    m = _measures(replayed[0])[STEPWISE]
    assert m.completed
    assert (m.identified, m.after_duplicates, m.unmatched) == (29, 27, 2)
    assert (m.retrievability.count, m.retrievability.total) == (4, 6)
    assert m.screening_recall is None
    assert m.end_to_end is None
    assert not m.flow
    assert (m.sought, m.open_access, m.uploaded, m.not_obtained) == (6, 1, 4, 1)
    assert (m.full_text_assessed, m.full_text_kept, m.full_text_uncertain) == (5, 4, 1)
    assert (m.full_text_recall.count, m.full_text_recall.total) == (4, 5)
    assert (m.reports, m.studies) == (5, 5)
    agreement = {a.field: a for a in m.agreement}
    assert [(a.compared, a.agreed) for a in agreement.values()] == [(5, 4)] * 3
    assert agreement["D1"].kappa == pytest.approx(0.48 / 0.68)
    assert agreement["D1"].ac1 == pytest.approx(0.47 / 0.67)
    assert agreement["D2"].kappa == pytest.approx(0.6875)
    assert agreement["D2"].ac1 == pytest.approx(0.49 / 0.69)
    assert agreement["D3"].kappa == pytest.approx(0.6875)
    assert agreement["D3"].ac1 == pytest.approx(0.49 / 0.69)
    assert (agreement["D3"].not_reported_published, agreement["D3"].not_reported_tool) == (1, 1)
    d1, d2 = m.distributions
    assert [c.tool for c in d1.categories] == pytest.approx([40.0, 20.0, 40.0])
    assert d1.rank_correlation == pytest.approx(-0.8660254)
    assert (d1.within.count, d1.same_mode) == (0, False)
    assert [c.tool for c in d2.categories] == pytest.approx([60.0, 20.0, 20.0])
    assert (d2.within.count, d2.same_mode, d2.rank_correlation) == (0, False, None)
    assert sum(c.calls for c in m.costs) == 13
    assert m.kept_unusable == 0


def test_report_holds_numbers_only(replayed: Replayed, tmp_path: Path) -> None:
    replay, _seen = replayed
    measures = list(_measures(replay).values())
    text = report.report_markdown(
        replay.inputs.sheet, replay.standard, measures, generated_at=make_clock()(),
        tool_version=TOOL_VERSION,
    )  # fmt: skip
    assert text.startswith("# Réplication — Fictive_2026_marche_anxiete")
    assert "Simulation de réplication — ne constitue pas une revue." in text
    assert "## Mode en chaîne (en-chaine)" in text
    assert "## Mode par étape (par-etape)" in text
    assert "| Rappel par rapport à la revue publiée | 1/6 (16,7%)" in text
    assert "| F1 | 0,222 | 0,250 |" in text
    assert "| Indice de Jaccard | 0,125 | 0,143 |" in text
    assert "| D1 | 5 | 4/5 (80,0%)" in text
    assert "| Études incluses | 6 | 3 | -3 | -50,0% |" in text
    assert "**0.245**" in text
    assert "**0.105**" in text
    # No title, abstract, URL nor raw response (as the public archive, D-092).
    ris = (replay.review / "recherche" / "export-base-fictive.ris").read_text(encoding="utf-8")
    for line in ris.splitlines():
        if line.startswith(("TI  - ", "AB  - ")):
            assert line[6:] not in text
    assert "http" not in text
    assert "Réponse fictive" not in text
    for first in TEXTS.values():
        assert first.splitlines()[0] not in text
    # The vocabulary of a concordance, not of an accuracy.
    assert "sensibilité" not in text.lower()
    assert "erreur" not in text.lower()


# --- Ceiling, refusal and guards ----------------------------------------------------------


def test_ceiling_stops_before_the_next_call_without_loss(tmp_path: Path) -> None:
    replay = _replay(tmp_path)
    stopped = replay.run(CHAINED, ceiling="0.10")
    assert stopped.stopped is bench.Stop.CEILING
    assert stopped.spent == Decimal("0.100")
    assert replay.calls(CHAINED) == Counter({"screen_reference": 20})
    folder = open_project_folder(bench.project_path(replay.review, CHAINED), now=make_clock(),
                                 tool_version=TOOL_VERSION, record_opening=False)  # fmt: skip
    with folder.engine.connect() as connection:
        assert len(screening_repo.list_decisions(connection)) in (19, 20)  # R13 unusable
    folder.close()
    resumed = replay.run(CHAINED, ceiling="5", go_on=True)
    assert resumed.stopped is bench.Stop.NONE
    assert replay.calls(CHAINED)["screen_reference"] == 28
    assert resumed.spent == Decimal("0.245")


def test_ceiling_reached_by_the_other_steps(tmp_path: Path) -> None:
    replay = _replay(tmp_path)
    # Title and abstract (0.14) and full text (0.035) fit; the pair of reports does not.
    stopped = replay.run(CHAINED, ceiling="0.18", go_on=True)
    assert (stopped.stopped, stopped.step) == (bench.Stop.CEILING, "Rapports d'une même étude")
    stopped = replay.run(CHAINED, ceiling="0.19", go_on=True)
    assert (stopped.stopped, stopped.step) == (bench.Stop.CEILING, "Extraction")
    stopped = replay.run(CHAINED, ceiling="0.225", go_on=True)
    assert (stopped.stopped, stopped.step) == (bench.Stop.CEILING, "Synthèse narrative")
    assert replay.run(CHAINED, ceiling="1", go_on=True).stopped is bench.Stop.NONE


def test_refused_cost_stops_before_any_call(tmp_path: Path) -> None:
    replay = _replay(tmp_path)
    outcome = replay.run(CHAINED, confirm=False)
    assert (outcome.stopped, outcome.step) == (bench.Stop.REFUSED, "Tri des titres et résumés")
    assert replay.asked == ["Tri des titres et résumés: 27"]
    assert replay.calls(CHAINED) == Counter()
    stepwise = replay.run(STEPWISE, confirm=False, go_on=True)
    assert (stepwise.stopped, stepwise.step) == (bench.Stop.REFUSED, "Tri des textes intégraux")


def test_refusals_at_the_later_steps(tmp_path: Path) -> None:
    replay = _replay(tmp_path)
    for refused in ("Rapports d'une même étude", "Extraction", "Synthèse narrative de D1"):
        steps: list[str] = []

        def answer(step: str, _preview: CostPreview, steps: list[str] = steps,
                   refused: str = refused) -> bool:  # fmt: skip
            steps.append(step)
            return step != refused

        outcome = bench.run_bench(
            replay.inputs, bench.BenchSettings(mode=CHAINED, ceiling=Decimal(5),
                                               go_on_without_texts=True),
            standard=replay.standard, factory=replay.factory, finder=Finder, confirm=answer,
            now=replay.clock, tool_version=TOOL_VERSION,
            wait=lambda _seconds: None,
        )  # fmt: skip
        assert outcome.stopped is bench.Stop.REFUSED
        assert steps[-1] == refused


def test_stepwise_needs_the_reference_standard(tmp_path: Path) -> None:
    replay = _replay(tmp_path)
    with pytest.raises(ReplicationInputError, match="norme de référence"):
        bench.run_bench(
            replay.inputs, bench.BenchSettings(mode=STEPWISE, ceiling=Decimal(1)),
            confirm=lambda _s, _p: True, now=replay.clock, tool_version=TOOL_VERSION,
        )  # fmt: skip


def test_another_project_in_the_place_is_refused(tmp_path: Path) -> None:
    replay = _replay(tmp_path)
    create_project_folder(
        bench.project_path(replay.review, CHAINED), title="Autre", language="fr",
        reviewer_name="banc-replication", now=make_clock(), tool_version=TOOL_VERSION,
        replication=ReplicationMarker(review_id="Autre_revue", mode=CHAINED),
    ).close()  # fmt: skip
    with pytest.raises(ReplicationInputError, match="pas le projet de réplication"):
        replay.run(CHAINED)


def test_changed_standard_is_refused_stepwise(tmp_path: Path) -> None:
    replay = _replay(tmp_path)
    replay.run(STEPWISE)
    included = replay.review / "norme" / "incluses.csv"
    included.write_text(included.read_text(encoding="utf-8") + "S7,,,Autre.,oui,\n", "utf-8")
    replay.standard = read_standard(replay.review)
    with pytest.raises(ReplicationInputError, match="a changé depuis son importation"):
        replay.run(STEPWISE)
