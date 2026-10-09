"""Reports of a same study (EF-SEL-17): pairs proposed by the rules, examined by the AI
with quotes and pages, decided by the person; studies and primary reports."""

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from demo import FILLER, Demo, build
from revue_portee.ai.base import ModelProvider, TaskInput
from revue_portee.ai.providers.fake import FakeProvider
from revue_portee.ai.settings import AITaskConfig
from revue_portee.ai.tasks.studies import GroupReportsInput
from revue_portee.dedup.reports import ReportLinkSettings
from revue_portee.domain.fulltext import QuoteCheck
from revue_portee.domain.journal import EntryType
from revue_portee.domain.screening import DecisionValue
from revue_portee.domain.studies import LinkOutcome, LinkVerdict
from revue_portee.fulltext import retrieval
from revue_portee.protocol import notes
from revue_portee.screening import fulltext, settings, studies
from support import TOOL_VERSION, fake_factory, make_pdf

EVERY_PAIR = ReportLinkSettings(min_title_similarity=0.0)  # the rules propose every pair
CAREGIVERS = ["Family caregivers of older adults living in rural areas" + FILLER]


def _answer(item: TaskInput) -> dict[str, Any]:
    assert isinstance(item, GroupReportsInput)
    return {
        "verdict": "same",
        "evidence": [
            {"aspect": "sample", "quote_a": "Family caregivers of older adults", "page_a": 1,
             "quote_b": "We interviewed 24 older adults", "page_b": 2},
            {"aspect": "setting", "quote_a": "rural areas", "page_a": 2, "quote_b": "",
             "page_b": None},
        ],
        "rationale": "Même échantillon.",
    }  # fmt: skip


def _with_two_included(tmp_path: Path) -> tuple[Demo, dict[str, str]]:
    """The demonstration with the caregivers study obtained and included at the full
    text: two included reports, loneliness and caregivers."""
    demo = build(tmp_path)
    ids = demo.ids()
    retrieval.add_upload(
        demo.folder, ids["caregivers"], make_pdf(CAREGIVERS), filename="c.pdf", now=demo.clock,
        tool_version=TOOL_VERSION,
    )  # fmt: skip
    fulltext.add_new_texts(demo.folder, now=demo.clock, tool_version=TOOL_VERSION)
    fulltext.record_decision(
        demo.folder, demo.fulltext_round_id, ids["caregivers"], DecisionValue.INCLUDE,
        now=demo.clock, tool_version=TOOL_VERSION,
    )  # fmt: skip
    return demo, ids


def test_pairs_examined_then_decided(tmp_path: Path) -> None:
    demo, ids = _with_two_included(tmp_path)
    folder, clock = demo.folder, demo.clock
    first, second = sorted((ids["caregivers"], ids["loneliness"]))
    pair = (first, second)
    try:
        assert set(studies.included_reports(folder)) == set(pair)
        assert studies.study_state(folder).candidates == []  # default rules: nothing in common
        state = studies.study_state(folder, EVERY_PAIR)
        assert [(c.reference_a_id, c.reference_b_id) for c in state.candidates] == [pair]
        factory = fake_factory({"GroupReportsInput": _answer})
        assert studies.preview_ai(folder, factory=factory, settings=EVERY_PAIR).items == 1
        result = studies.run_ai(
            folder, batch_limit=Decimal(1), factory=factory, settings=EVERY_PAIR, now=clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
        state = studies.study_state(folder, EVERY_PAIR)
        assessment = state.assessments[pair]
        assert state.without_ai == []
        assert [len(s.reports) for s in state.studies] == [1, 1]
        studies.decide(
            folder, first, second, LinkOutcome.SAME, note="Même étude.", now=clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
        joined = studies.study_state(folder, EVERY_PAIR)
        studies.choose_primary(folder, ids["caregivers"], now=clock, tool_version=TOOL_VERSION)
        chosen = studies.study_state(folder, EVERY_PAIR)
        studies.decide(
            folder, first, second, LinkOutcome.DIFFERENT, now=clock, tool_version=TOOL_VERSION
        )
        apart = studies.study_state(folder, EVERY_PAIR)
        entries = notes.journal_entries(folder)
    finally:
        folder.close()
    assert result.screened == 1
    assert assessment.verdict is LinkVerdict.SAME
    # the reports in pair order: caregivers or loneliness first
    checks = {(e.aspect, e.check_a, e.check_b) for e in assessment.evidence}
    caregivers_first = pair[0] == ids["caregivers"]
    assert (
        ("sample", QuoteCheck.AT_PAGE, QuoteCheck.AT_PAGE) in checks if caregivers_first else True
    )
    assert any(e.check_b is None for e in assessment.evidence)  # no quote, no check
    assert joined.pending == []
    assert [s.reports for s in joined.studies] == [list(pair)]
    assert joined.studies[0].primary == ids["loneliness"]  # the oldest (2019)
    assert chosen.studies[0].primary == ids["caregivers"]
    assert chosen.study_of(ids["loneliness"]) == chosen.studies[0]
    assert chosen.study_of("nope") is None
    assert [len(s.reports) for s in apart.studies] == [1, 1]
    kinds = [e.entry_type for e in entries if e.entry_type.startswith("study.")]
    assert kinds == [
        EntryType.STUDY_LINK_ASSESSED,
        EntryType.STUDY_LINK_DECIDED,
        EntryType.STUDY_PRIMARY_CHOSEN,
        EntryType.STUDY_LINK_DECIDED,
    ]


def test_only_included_reports(tmp_path: Path) -> None:
    demo = build(tmp_path)
    try:
        ids = demo.ids()
        with pytest.raises(studies.NotIncludedError):
            studies.decide(
                demo.folder, ids["housing"], ids["loneliness"], LinkOutcome.SAME, now=demo.clock,
                tool_version=TOOL_VERSION,
            )  # fmt: skip
        with pytest.raises(studies.NotIncludedError):
            studies.decide(
                demo.folder, ids["loneliness"], ids["loneliness"], LinkOutcome.SAME,
                now=demo.clock, tool_version=TOOL_VERSION,
            )  # fmt: skip
        with pytest.raises(studies.NotIncludedError):
            studies.choose_primary(
                demo.folder, ids["housing"], now=demo.clock, tool_version=TOOL_VERSION
            )
        state = studies.study_state(demo.folder)
    finally:
        demo.folder.close()
    assert [s.reports for s in state.studies] == [[ids["loneliness"]]]


def test_ceilings(tmp_path: Path) -> None:
    demo, _ids = _with_two_included(tmp_path)
    folder, clock = demo.folder, demo.clock

    def factory(config: AITaskConfig) -> ModelProvider:
        return FakeProvider(
            model=str(config.model), responder=_answer, cost_per_call=Decimal("0.002")
        )

    try:
        stopped = studies.run_ai(
            folder, batch_limit=Decimal("0.000001"), factory=factory, settings=EVERY_PAIR,
            now=clock, tool_version=TOOL_VERSION,
        )  # fmt: skip
        settings.set_budget(folder, Decimal("0.000001"), now=clock, tool_version=TOOL_VERSION)
        project = studies.run_ai(
            folder, batch_limit=Decimal(1), factory=factory, settings=EVERY_PAIR, now=clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
    finally:
        folder.close()
    assert (stopped.screened, stopped.stopped) == (0, "batch_budget")
    assert project.stopped == "project_budget"


def test_nothing_before_the_full_text(tmp_path: Path) -> None:
    from demo import create

    demo = create(tmp_path)
    try:
        assert studies.included_reports(demo.folder) == {}
        assert studies.study_state(demo.folder).studies == []
    finally:
        demo.folder.close()
