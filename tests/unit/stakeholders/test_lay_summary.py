"""Plain-language summaries (EF-CON-01): drafted by the AI from the narrative synthesis
the person revised (never from the AI's drafts), revised by the person, exported with
their readability index."""

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from demo import build_extracted
from revue_portee.ai.base import TaskInput
from revue_portee.ai.tasks.lay_summary import DraftLaySummaryInput
from revue_portee.domain.journal import EntryType
from revue_portee.domain.lay_summary import LayLevel, SummaryStatus
from revue_portee.domain.narrative import NarrativeSentence
from revue_portee.stakeholders import lay_summary
from revue_portee.storage.repositories import journal
from revue_portee.synthesis import narrative
from revue_portee.synthesis.narrative import CeilingReachedError
from support import TOOL_VERSION
from unit.extraction.test_prefill import factory
from unit.synthesis.test_narrative import AI_TEXT, drafted

SEEN: list[DraftLaySummaryInput] = []
PLAIN = "Une seule étude a été retenue. Elle parle de personnes âgées qui déménagent."


def summarized(item: TaskInput) -> dict[str, Any]:
    assert isinstance(item, DraftLaySummaryInput)
    SEEN.append(item)
    return {"title": "Ce que dit la recherche", "paragraphs": [PLAIN, "  "]}


def empty(item: TaskInput) -> dict[str, Any]:
    return {"title": "Rien", "paragraphs": ["   "]}


def _with_synthesis(tmp_path: Path) -> Any:  # noqa: ANN401 - the demonstration
    """The demonstration with a draft of the AI on D1 then the person's revision, and a
    draft of the AI on D2 that no one revised."""
    demo = build_extracted(tmp_path)
    ref = demo.ids()["loneliness"]
    kwargs: dict[str, Any] = {"now": demo.clock, "tool_version": TOOL_VERSION}
    narrative.draft_with_ai(demo.folder, "D1", ceiling=Decimal(1), factory=factory(drafted),
                            **kwargs)  # fmt: skip
    narrative.revise(
        demo.folder, "D1", [NarrativeSentence(text="L'étude est qualitative.", study_ids=(ref,))],
        **kwargs,
    )  # fmt: skip
    narrative.draft_with_ai(demo.folder, "D2", ceiling=Decimal(1), factory=factory(drafted),
                            **kwargs)  # fmt: skip
    return demo


def test_drafted_revised_then_exported(tmp_path: Path) -> None:
    demo = _with_synthesis(tmp_path)
    ref = demo.ids()["loneliness"]
    folder = demo.folder
    kwargs: dict[str, Any] = {"now": demo.clock, "tool_version": TOOL_VERSION}
    SEEN.clear()
    try:
        cost = lay_summary.preview_ai(folder, LayLevel.GENERAL, factory=factory(summarized))
        proposed = lay_summary.draft_with_ai(
            folder, LayLevel.GENERAL, ceiling=Decimal(1), factory=factory(summarized), **kwargs
        )
        before = lay_summary.lay_state(folder).level(LayLevel.GENERAL)
        not_yet = lay_summary.export_summary(folder, LayLevel.GENERAL, **kwargs)[0].read_text(
            encoding="utf-8"
        )
        own = lay_summary.revise(
            folder, LayLevel.GENERAL, title=" Ce que dit la recherche ",
            text="Le chat dort.\r\n\r\nIl fait beau.", **kwargs,
        )  # fmt: skip
        paths = lay_summary.export_summary(folder, LayLevel.GENERAL, **kwargs)
        narrative.revise(
            folder, "D2", [NarrativeSentence(text="En résidence.", study_ids=(ref,))], **kwargs
        )
        after = lay_summary.lay_state(folder).level(LayLevel.GENERAL)
        with folder.engine.connect() as connection:
            entries = [
                e for e in journal.list_entries(connection)
                if e.entry_type in (EntryType.LAY_SUMMARY_PROPOSED, EntryType.LAY_SUMMARY_REVISED)
            ]  # fmt: skip
    finally:
        folder.close()
    assert cost.items == 1
    # the AI sees the revised synthesis of D1 only, never the AI's draft of D2
    (item,) = SEEN
    assert (item.item_id, item.level, item.language, item.studies) == ("general", "general",
                                                                        "fr", 1)  # fmt: skip
    assert [(s.label, s.text) for s in item.sections] == [("Devis", "L'étude est qualitative.")]
    assert AI_TEXT not in str(item.model_dump())
    assert item.target_index == 60.0
    assert proposed.status is SummaryStatus.PROPOSED
    assert proposed.text == PLAIN  # the empty paragraph is dropped
    assert proposed.ai_call_id is not None
    assert len(proposed.narrative_ids) == 1
    assert before.to_revise
    assert before.revised is None
    assert "À rédiger" in not_yet
    assert PLAIN not in not_yet  # the AI's draft alone is never exported
    assert own.status is SummaryStatus.REVISED
    assert own.supersedes_id == proposed.id
    assert (own.title, own.text) == ("Ce que dit la recherche", "Le chat dort.\n\nIl fait beau.")
    markdown = paths[0].read_text(encoding="utf-8")
    assert [p.name for p in paths] == ["vulgarisation-general.md", "vulgarisation-general.docx"]
    assert "Indice de lisibilité (Kandel-Moles) : 130,4" in markdown
    assert after.outdated  # the narrative synthesis was revised since
    # Une(1) seule(1) étude(2) a(1) été(2) retenue(3). Elle(1) parle(1) de(1) personnes(2)
    # âgées(2) qui(1) déménagent(4): 13 words, 2 sentences, 22 syllables
    # 207 - 1.015 x 6.5 - 73.6 x 22 / 13 = 75.85
    assert entries[0].payload["readability"] == 75.8
    assert entries[1].payload["readability"] == 130.4
    assert entries[1].payload["from_ai"] is True


def test_refusals(tmp_path: Path) -> None:
    demo = build_extracted(tmp_path)
    kwargs: dict[str, Any] = {"now": demo.clock, "tool_version": TOOL_VERSION}
    try:
        with pytest.raises(lay_summary.NoRevisedSynthesisError):  # nothing revised yet
            lay_summary.preview_ai(demo.folder, LayLevel.GENERAL, factory=factory(summarized))
        with pytest.raises(lay_summary.NoRevisedSynthesisError):
            lay_summary.revise(demo.folder, LayLevel.GENERAL, title="", text="Texte.", **kwargs)
    finally:
        demo.folder.close()
    demo = _with_synthesis(tmp_path / "b")
    try:
        with pytest.raises(lay_summary.SummaryFailedError):
            lay_summary.draft_with_ai(demo.folder, LayLevel.INFORMED, ceiling=Decimal(1),
                                      factory=factory(empty), **kwargs)  # fmt: skip
        with pytest.raises(CeilingReachedError):
            lay_summary.draft_with_ai(demo.folder, LayLevel.INFORMED, ceiling=Decimal(0),
                                      factory=factory(summarized), **kwargs)  # fmt: skip
        with pytest.raises(ValueError, match="empty"):
            lay_summary.revise(demo.folder, LayLevel.INFORMED, title="T", text=" \n\n ",
                               **kwargs)  # fmt: skip
        state = lay_summary.lay_state(demo.folder)
    finally:
        demo.folder.close()
    assert state.level(LayLevel.INFORMED).current is None
