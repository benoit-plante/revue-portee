"""Narrative synthesis (EF-SYN-04): every sentence rests on at least one included study;
only the person's revision is exported, never the AI's draft alone."""

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from demo import build_extracted
from revue_portee.ai.base import TaskInput
from revue_portee.ai.tasks.synthesis import DraftSynthesisInput
from revue_portee.domain.journal import EntryType
from revue_portee.domain.narrative import (
    DraftStatus,
    NarrativeSentence,
    UnsupportedSentenceError,
)
from revue_portee.domain.project import ReviewerKind
from revue_portee.extraction import prefill, validation
from revue_portee.storage.repositories import journal
from revue_portee.synthesis import narrative
from support import TOOL_VERSION
from unit.extraction.test_prefill import _with_grid, factory

AI_TEXT = "La seule étude incluse emploie un devis qualitatif."
SEEN: list[DraftSynthesisInput] = []


def drafted(item: TaskInput) -> dict[str, Any]:
    assert isinstance(item, DraftSynthesisInput)
    SEEN.append(item)
    return {"sentences": [{"text": AI_TEXT, "studies": ["S1"]}]}


def unknown_key(item: TaskInput) -> dict[str, Any]:
    return {"sentences": [{"text": "Une phrase.", "studies": ["S9"]}]}


def no_study(item: TaskInput) -> dict[str, Any]:
    return {"sentences": [{"text": "Une phrase.", "studies": []}]}


def _entries(demo: Any, kind: str) -> list[Any]:  # noqa: ANN401 - the demonstration
    with demo.folder.engine.connect() as connection:
        return [e for e in journal.list_entries(connection) if e.entry_type == kind]


def test_draft_revised_then_exported(tmp_path: Path) -> None:
    demo = build_extracted(tmp_path)
    folder = demo.folder
    ref = demo.ids()["loneliness"]
    kwargs: dict[str, Any] = {"now": demo.clock, "tool_version": TOOL_VERSION}
    SEEN.clear()
    try:
        cost = narrative.preview_ai(folder, "D1", factory=factory(drafted))
        proposed = narrative.draft_with_ai(
            folder, "D1", ceiling=Decimal(1), factory=factory(drafted), **kwargs
        )
        state = narrative.narrative_state(folder)
        before = narrative.narrative_document(folder, language="fr", **kwargs)
        revised = narrative.revise(
            folder, "D1",
            [NarrativeSentence(text="L'étude incluse est qualitative.", study_ids=(ref,))],
            **kwargs,
        )  # fmt: skip
        after_revision = narrative.narrative_state(folder).field("D1")
        paths = narrative.export_narrative(folder, language="fr", **kwargs)
        validation.record_value(folder, ref, "D1", reported=True, value="Mixte", **kwargs)
        changed = narrative.narrative_state(folder).field("D1")
        labels = narrative.narrative_state(folder).labels
        proposals = _entries(demo, EntryType.SYNTHESIS_DRAFT_PROPOSED)
        revisions = _entries(demo, EntryType.SYNTHESIS_DRAFT_REVISED)
    finally:
        folder.close()
    assert cost.items == 1
    # the model sees the values a person decided, under short keys, never the texts
    (item,) = SEEN
    assert (item.item_id, item.field.code, item.language) == ("D1", "D1", "fr")
    assert [(s.key, s.reported, s.value) for s in item.studies] == [("S1", True, "Qualitatif")]
    assert proposed.status is DraftStatus.PROPOSED
    assert proposed.reviewer_kind is ReviewerKind.AI
    assert proposed.ai_call_id is not None
    assert proposed.sentences == (NarrativeSentence(text=AI_TEXT, study_ids=(ref,)),)
    assert state.field("D1").to_revise
    assert state.field("D1").revised is None
    assert state.field("D3").studies[0][1].reported is False  # not reported counts too
    # the AI's draft alone is never exported
    text_before = "\n".join(getattr(b, "text", "") for b in before.blocks)
    assert AI_TEXT not in text_before
    assert "À rédiger" in text_before
    assert revised.status is DraftStatus.REVISED
    assert revised.supersedes_id == proposed.id
    assert not after_revision.to_revise
    assert not after_revision.outdated
    markdown = paths[0].read_text(encoding="utf-8")
    assert f"L'étude incluse est qualitative ({labels[ref]})." in markdown
    assert "## Études citées" in markdown
    assert [p.name for p in paths] == ["narratif-fr.md", "narratif-fr.docx"]
    assert changed.outdated  # a value changed since the revision
    assert proposals[0].summary_fr == "Synthèse narrative de D1 : ébauche proposée par l'IA"
    assert proposals[0].payload["studies"] == [ref]
    assert revisions[0].payload["from_ai"] is True


def test_unusable_answers_are_asked_again_then_refused(tmp_path: Path) -> None:
    demo = build_extracted(tmp_path)
    kwargs: dict[str, Any] = {"now": demo.clock, "tool_version": TOOL_VERSION}
    try:
        for responder in (unknown_key, no_study):
            with pytest.raises(narrative.DraftFailedError):
                narrative.draft_with_ai(
                    demo.folder, "D2", ceiling=Decimal(1), factory=factory(responder), **kwargs
                )
        with pytest.raises(narrative.CeilingReachedError):
            narrative.draft_with_ai(
                demo.folder, "D2", ceiling=Decimal(0), factory=factory(drafted), **kwargs
            )
        with pytest.raises(narrative.UnknownFieldError):
            narrative.preview_ai(demo.folder, "D9", factory=factory(drafted))
        unusable = _entries(demo, EntryType.AI_RESULT_UNUSABLE)
        failed = _entries(demo, EntryType.SYNTHESIS_AI_FAILED)
        state = narrative.narrative_state(demo.folder)
    finally:
        demo.folder.close()
    assert len(unusable) >= 4  # two attempts for each responder
    assert len(failed) == 2
    assert state.field("D2").current is None


def test_every_sentence_rests_on_an_included_study(tmp_path: Path) -> None:
    demo = build_extracted(tmp_path)
    ref = demo.ids()["loneliness"]
    kwargs: dict[str, Any] = {"now": demo.clock, "tool_version": TOOL_VERSION}
    try:
        with pytest.raises(UnsupportedSentenceError):
            narrative.revise(demo.folder, "D1", [], **kwargs)
        with pytest.raises(UnsupportedSentenceError):
            narrative.revise(
                demo.folder, "D1",
                [NarrativeSentence(text="Hors corpus.", study_ids=("01NOTINCLUDED",))],
                **kwargs,
            )  # fmt: skip
        with pytest.raises(UnsupportedSentenceError):
            narrative.revise(
                demo.folder, "D1", [NarrativeSentence(text="  ", study_ids=(ref,))], **kwargs
            )
        with pytest.raises(ValueError, match="at least 1"):
            NarrativeSentence(text="Sans étude.", study_ids=())
        # the person may write a synthesis without any draft of the AI
        own = narrative.revise(
            demo.folder, "D2", [NarrativeSentence(text="En résidence.", study_ids=(ref,))],
            **kwargs,
        )  # fmt: skip
    finally:
        demo.folder.close()
    assert own.supersedes_id is None


def test_nothing_to_synthesize_without_decided_values(tmp_path: Path) -> None:
    demo = _with_grid(tmp_path)
    try:
        from unit.extraction.test_prefill import answer

        prefill.run_ai(
            demo.folder, batch_limit=Decimal(1), factory=factory(answer), now=demo.clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
        with pytest.raises(narrative.NothingToSynthesizeError):  # the AI's values only
            narrative.preview_ai(demo.folder, "D1", factory=factory(drafted))
    finally:
        demo.folder.close()
