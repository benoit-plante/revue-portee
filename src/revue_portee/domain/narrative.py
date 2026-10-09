"""Narrative synthesis, field by field (EF-SYN-04, tranche 3.6).

The AI may propose a draft of the synthesis of a field; the person revises it. Every
sentence rests on at least one included study, whoever wrote it. A draft is never
changed: a revision is a new draft that supersedes the previous one. Only the drafts a
person revised are used in the exports (``revised``), never a draft of the AI alone.
"""

from collections.abc import Collection, Iterable
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from revue_portee.domain.project import ReviewerKind

__all__ = [
    "DraftStatus",
    "NarrativeDraft",
    "NarrativeSentence",
    "UnsupportedSentenceError",
    "check_sentences",
    "current_drafts",
    "revised_drafts",
]


class DraftStatus(StrEnum):
    PROPOSED = "proposed"  # by the AI, not revised yet
    REVISED = "revised"  # by the person


class NarrativeSentence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    study_ids: tuple[str, ...] = Field(min_length=1)  # primary reports of included studies


class NarrativeDraft(BaseModel):
    """A draft of the synthesis of one field (table ``narrative_draft``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    field_code: str
    grid_version_id: str
    language: str
    sentences: tuple[NarrativeSentence, ...]
    status: DraftStatus
    reviewer_id: str
    reviewer_kind: ReviewerKind
    ai_call_id: str | None = None
    supersedes_id: str | None = None
    created_at: AwareDatetime


class UnsupportedSentenceError(ValueError):
    """A sentence without a study, or citing a study that is not included."""


def check_sentences(
    sentences: Iterable[NarrativeSentence], included: Collection[str]
) -> tuple[NarrativeSentence, ...]:
    """The sentences, once each is checked to have a text and to rest on included
    studies only; at least one sentence. UnsupportedSentenceError otherwise."""
    found = tuple(sentences)
    if not found:
        raise UnsupportedSentenceError("no sentence")
    for number, sentence in enumerate(found, start=1):
        if not sentence.text.strip():
            raise UnsupportedSentenceError(f"sentence {number}: empty")
        unknown = [s for s in sentence.study_ids if s not in included]
        if unknown:
            raise UnsupportedSentenceError(f"sentence {number}: not included: {unknown}")
    return found


def _latest(drafts: Iterable[NarrativeDraft]) -> dict[str, NarrativeDraft]:
    found: dict[str, NarrativeDraft] = {}
    for draft in sorted(drafts, key=lambda d: (d.created_at, d.id)):
        found[draft.field_code] = draft
    return found


def current_drafts(drafts: Iterable[NarrativeDraft]) -> dict[str, NarrativeDraft]:
    """The latest draft of each field, the AI's or the person's."""
    return _latest(drafts)


def revised_drafts(drafts: Iterable[NarrativeDraft]) -> dict[str, NarrativeDraft]:
    """The latest draft a person revised, for each field: the only ones exported."""
    return _latest(d for d in drafts if d.status is DraftStatus.REVISED)
