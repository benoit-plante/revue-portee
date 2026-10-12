"""Tranche 3.11 on the fictitious review: a coding grid added after a complete run.
The fields it changes are extracted and drafted again, and the report counts the
duration run by run."""

from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from replication_support import Crossref, Finder, copy_review, factory
from revue_portee.domain.project import ReplicationMode
from revue_portee.protocol.ai_assist import CostPreview
from revue_portee.replication import bench, report
from revue_portee.replication.inputs import read_inputs, read_standard
from revue_portee.storage.project_folder import open_project_folder
from revue_portee.storage.repositories import ai as ai_repo
from revue_portee.storage.repositories import narrative as narrative_repo
from support import START, TOOL_VERSION, make_clock
from unit.replication.test_coding_grid import CODED_VALUES, CODING_GRID

STEPWISE = ReplicationMode.STEPWISE
CLOCK = make_clock()  # one clock for both runs: the second comes after the first


def _run(review: Path) -> bench.BenchOutcome:
    def answer(_step: str, _preview: CostPreview) -> bool:
        return True

    return bench.run_bench(
        read_inputs(review),
        bench.BenchSettings(mode=STEPWISE, ceiling=Decimal(5), go_on_without_texts=True),
        standard=read_standard(review), factory=factory(clock=CLOCK), finder=Finder,
        crossref=Crossref,
        confirm=answer, now=CLOCK, tool_version=TOOL_VERSION, wait=lambda _s: None,
    )  # fmt: skip


@pytest.fixture(scope="module")
def regraded(tmp_path_factory: pytest.TempPathFactory) -> Path:
    review = copy_review(tmp_path_factory.mktemp("regraded"))
    assert _run(review).stopped is bench.Stop.NONE
    (review / "norme" / "grille-codage.yaml").write_text(CODING_GRID, encoding="utf-8")
    values = review / "norme" / "extraction-publiee.csv"
    values.write_bytes(values.read_bytes() + CODED_VALUES.encode("utf-8"))
    assert _run(review).stopped is bench.Stop.NONE
    return review


def test_changed_fields_are_drafted_again(regraded: Path) -> None:
    folder = open_project_folder(bench.project_path(regraded, STEPWISE), now=make_clock(),
                                 tool_version=TOOL_VERSION, record_opening=False)  # fmt: skip
    try:
        with folder.engine.connect() as connection:
            drafts = Counter(d.field_code for d in narrative_repo.list_drafts(connection))
            calls = Counter(c.task for c in ai_repo.list_calls(connection))
    finally:
        folder.close()
    # The coding grid defines D2 more precisely and adds D4 and D5: the 5 studies with a
    # text are extracted again for them only, D2 is drafted again, D4 and D5 for the
    # first time; D1 and D3 are left as they were.
    assert calls["extract_fields"] == 5 + 5
    assert drafts == {"D1": 1, "D2": 2, "D3": 1, "D4": 1, "D5": 1}
    assert calls["draft_synthesis"] == 6


def test_run_minutes_by_hand() -> None:
    def at(seconds: int) -> datetime:
        return START + timedelta(seconds=seconds)

    calls = [at(s) for s in (90, 0, 30, 200, 260, 430, 400)]
    ends = [at(300), at(100), at(350)]  # the third run made no call
    # Run 1: 0 to 90 s; run 2: 200 to 260 s; after the last end, an interrupted run.
    assert report.run_minutes(calls, ends) == (1.5, 1.0, 0.5)
    assert report.run_minutes([], ends) == ()
    assert report.run_minutes([at(5)], []) == (0.0,)


def test_the_duration_is_counted_run_by_run(regraded: Path) -> None:
    sheet, standard = read_inputs(regraded).sheet, read_standard(regraded)
    measures = report.measure_review(regraded, sheet, standard, now=make_clock(),
                                     tool_version=TOOL_VERSION)  # fmt: skip
    (m,) = measures
    assert len(m.run_minutes) == 2
    assert m.duration_minutes == pytest.approx(sum(m.run_minutes))
    text = report.report_markdown(sheet, standard, measures, generated_at=make_clock()(),
                                  tool_version=TOOL_VERSION)  # fmt: skip
    first, second = (f"{x:.1f}".replace(".", ",") for x in m.run_minutes)
    assert f"(2 exécutions : {first} + {second})" in text
