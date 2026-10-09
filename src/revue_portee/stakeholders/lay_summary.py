"""Plain-language summaries of the results (EF-CON-01, tranche 4.1).

For a language level, the AI receives the review question, the number of included
studies and the narrative synthesis the person revised, field by field (never the AI's
drafts alone, never the full texts), and drafts a title and a few paragraphs. The cost
is shown first; the project and confirmed ceilings are checked before each call (D-041,
D-069). The person revises the summary; only revised summaries are exported, with their
readability index against the target of their level. A summary is to review when the
narrative synthesis was revised since.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from pydantic import JsonValue

from revue_portee.ai.base import ProviderCallError
from revue_portee.ai.providers import ProviderFactory
from revue_portee.ai.runner import run_task
from revue_portee.ai.tasks.lay_summary import (
    DRAFT_LAY_SUMMARY,
    DraftLaySummaryInput,
    SynthesisSection,
)
from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.domain.lay_summary import (
    TARGET_INDEX,
    LayLevel,
    LaySummary,
    SummaryStatus,
    current_summaries,
    revised_summaries,
)
from revue_portee.domain.narrative import NarrativeDraft
from revue_portee.domain.project import ReviewerKind
from revue_portee.i18n import french
from revue_portee.i18n import gettext as _
from revue_portee.protocol.ai_assist import (
    CostPreview,
    call_summary,
    default_provider_factory,
    preview,
    record_call,
    record_unusable,
)
from revue_portee.protocol.framing import current_framing
from revue_portee.reporting.document import Document, render_docx, render_markdown
from revue_portee.reporting.lay_summary import build_lay_summary
from revue_portee.screening.ai_screening import MAX_ATTEMPTS, ai_reviewer
from revue_portee.screening.settings import BudgetNotSetError
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import journal, projects
from revue_portee.storage.repositories import lay_summary as summary_repo
from revue_portee.storage.repositories import screening as screening_repo
from revue_portee.synthesis.narrative import CeilingReachedError, narrative_state

__all__ = [
    "LayState",
    "LevelSummary",
    "NoRevisedSynthesisError",
    "SummaryFailedError",
    "draft_with_ai",
    "export_summary",
    "lay_state",
    "preview_ai",
    "revise",
    "summary_document",
]

Clock = Callable[[], datetime]


class NoRevisedSynthesisError(ValueError):
    def __init__(self) -> None:
        super().__init__(
            _(
                "Revise the narrative synthesis of at least one field first: the summary rests "
                "on it."
            )
        )


class SummaryFailedError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            _("The AI could not draft a usable summary; the calls are recorded in the journal.")
        )


@dataclass(frozen=True, slots=True)
class LevelSummary:
    level: LayLevel
    current: LaySummary | None  # the latest version, the AI's or the person's
    revised: LaySummary | None  # the latest version the person revised
    outdated: bool  # the narrative synthesis was revised since

    @property
    def to_revise(self) -> bool:
        return self.current is not None and self.current.status is SummaryStatus.PROPOSED


@dataclass(frozen=True, slots=True)
class LayState:
    language: str
    title: str
    studies: int
    sources: list[tuple[str, NarrativeDraft]]  # field label, revised narrative synthesis
    levels: list[LevelSummary]

    def level(self, level: LayLevel) -> LevelSummary:
        return next(s for s in self.levels if s.level is level)


def lay_state(folder: ProjectFolder) -> LayState:
    narrative = narrative_state(folder)
    with folder.engine.connect() as connection:
        summaries = summary_repo.list_summaries(connection)
        title = projects.get_project(connection).title
    sources = [(f.field.label, f.revised) for f in narrative.fields if f.revised is not None]
    latest_source = max((d.created_at for _label, d in sources), default=None)
    current, revised = current_summaries(summaries), revised_summaries(summaries)
    levels = [
        LevelSummary(
            level=level,
            current=current.get(level),
            revised=revised.get(level),
            outdated=revised.get(level) is not None
            and latest_source is not None
            and latest_source > revised[level].created_at,
        )
        for level in LayLevel
    ]
    return LayState(
        language=narrative.language, title=title, studies=len(narrative.studies),
        sources=sources, levels=levels,
    )  # fmt: skip


def _input(folder: ProjectFolder, state: LayState, level: LayLevel) -> DraftLaySummaryInput:
    if not state.sources:
        raise NoRevisedSynthesisError
    framing = current_framing(folder)
    return DraftLaySummaryInput(
        item_id=level.value,
        language=state.language,
        level=level.value,
        target_index=TARGET_INDEX[level],
        review_title=state.title,
        review_question="" if framing is None else framing.framing.question,
        studies=max(1, state.studies),
        sections=tuple(
            SynthesisSection(label=label, text=" ".join(s.text for s in draft.sentences))
            for label, draft in state.sources
        ),
    )


def preview_ai(
    folder: ProjectFolder, level: LayLevel, *,
    factory: ProviderFactory = default_provider_factory,
) -> CostPreview:  # fmt: skip
    """Cost of a draft of the summary of ``level`` (one call)."""
    return preview(folder, DRAFT_LAY_SUMMARY, [_input(folder, lay_state(folder), level)],
                   factory=factory)  # fmt: skip


def _record(folder: ProjectFolder, summary: LaySummary, entry_type: str, text: str,
            extra: dict[str, JsonValue], *, tool_version: str) -> None:  # fmt: skip
    found = summary.readability
    payload: dict[str, JsonValue] = {
        "level": summary.level.value,
        "narrative": [*summary.narrative_ids],
        "supersedes": summary.supersedes_id,
        "readability": None if found is None else found.index,
        "formula": None if found is None else found.formula,
    }
    with folder.write() as connection:
        entry = journal.append_entry(
            connection, now=summary.created_at, actor_reviewer_id=folder.reviewer_id,
            entry_type=entry_type, subject_type="lay_summary", subject_id=summary.id,
            summary_fr=text, tool_version=tool_version, payload=payload | extra,
        )  # fmt: skip
        summary_repo.insert_summary(connection, summary, journal_entry_id=entry.id)


def draft_with_ai(
    folder: ProjectFolder,
    level: LayLevel,
    *,
    ceiling: Decimal,
    factory: ProviderFactory = default_provider_factory,
    now: Clock,
    tool_version: str,
) -> LaySummary:
    """Ask the AI for a draft of the summary of ``level``, under ``ceiling`` and the
    project budget, checked before each call."""
    state = lay_state(folder)
    item = _input(folder, state, level)
    with folder.engine.connect() as connection:
        budget = screening_repo.latest_budget(connection)
    if budget is None:
        raise BudgetNotSetError
    provider = factory(folder.ai_settings().enabled_task(DRAFT_LAY_SUMMARY.name))
    estimate = provider.estimate_cost(DRAFT_LAY_SUMMARY, [item]).amount
    spent = Decimal(0)
    for _attempt in range(MAX_ATTEMPTS):
        with folder.engine.connect() as connection:
            project_spent = screening_repo.total_spent(connection)
        if project_spent + estimate > budget.limit_amount or spent + estimate > ceiling:
            if spent:
                break
            raise CeilingReachedError
        try:
            (result,) = run_task(provider, DRAFT_LAY_SUMMARY, [item])
        except ProviderCallError as error:
            stored = record_call(
                folder, task=DRAFT_LAY_SUMMARY.name, item_id=error.item_id, call=error.call,
                raw_response=error.raw_response, now=now, tool_version=tool_version,
            )  # fmt: skip
            spent += stored.record.cost_estimate
            continue
        stored = record_call(
            folder, task=DRAFT_LAY_SUMMARY.name, item_id=result.item_id, call=result.call,
            raw_response=result.raw_response, now=now, tool_version=tool_version,
        )  # fmt: skip
        spent += stored.record.cost_estimate
        paragraphs = [p.strip() for p in result.output.paragraphs if p.strip()]
        if not paragraphs:
            record_unusable(folder, stored, ValueError("no paragraph"), now=now,
                            tool_version=tool_version)  # fmt: skip
            continue
        reviewer_id = ai_reviewer(folder, stored, now=now, tool_version=tool_version)
        current = state.level(level).current
        moment = now()
        summary = LaySummary(
            id=new_ulid(moment), level=level, language=state.language,
            title=result.output.title.strip(), text="\n\n".join(paragraphs),
            status=SummaryStatus.PROPOSED, reviewer_id=reviewer_id,
            reviewer_kind=ReviewerKind.AI, ai_call_id=stored.id,
            supersedes_id=None if current is None else current.id,
            narrative_ids=tuple(d.id for _label, d in state.sources), created_at=moment,
        )  # fmt: skip
        _record(
            folder, summary, EntryType.LAY_SUMMARY_PROPOSED,
            french("Plain-language summary ({level}): draft proposed by the AI").format(
                level=level.value
            ),
            call_summary(stored), tool_version=tool_version,
        )  # fmt: skip
        return summary
    with folder.write() as connection:
        journal.append_entry(
            connection, now=now(), actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.LAY_SUMMARY_AI_FAILED, subject_type="lay_level",
            subject_id=level.value,
            summary_fr=french(
                "Plain-language summary ({level}): the AI gave no usable draft (attempts: {n})"
            ).format(level=level.value, n=MAX_ATTEMPTS),
            tool_version=tool_version, payload={"level": level.value, "attempts": MAX_ATTEMPTS},
        )  # fmt: skip
    raise SummaryFailedError


def revise(
    folder: ProjectFolder,
    level: LayLevel,
    *,
    title: str,
    text: str,
    now: Clock,
    tool_version: str,
) -> LaySummary:
    """The person's summary for ``level`` (a text is required)."""
    state = lay_state(folder)
    if not state.sources:
        raise NoRevisedSynthesisError
    cleaned = "\n\n".join(p.strip() for p in text.replace("\r\n", "\n").split("\n\n") if p.strip())
    if not cleaned:
        raise ValueError("empty summary")
    current = state.level(level).current
    moment = now()
    summary = LaySummary(
        id=new_ulid(moment), level=level, language=state.language, title=title.strip(),
        text=cleaned, status=SummaryStatus.REVISED, reviewer_id=folder.reviewer_id,
        reviewer_kind=ReviewerKind.HUMAN,
        supersedes_id=None if current is None else current.id,
        narrative_ids=tuple(d.id for _label, d in state.sources), created_at=moment,
    )  # fmt: skip
    _record(
        folder, summary, EntryType.LAY_SUMMARY_REVISED,
        french("Plain-language summary ({level}): revised by the person").format(
            level=level.value
        ),
        {"from_ai": current is not None and current.reviewer_kind is ReviewerKind.AI},
        tool_version=tool_version,
    )  # fmt: skip
    return summary


def summary_document(
    folder: ProjectFolder, level: LayLevel, *, now: Clock, tool_version: str
) -> Document:
    state = lay_state(folder)
    found = state.level(level)
    return build_lay_summary(
        found.revised, level=level, review_title=state.title, language=state.language,
        outdated=found.outdated, tool_version=tool_version, generated_at=now(),
    )  # fmt: skip


def export_summary(
    folder: ProjectFolder, level: LayLevel, *, now: Clock, tool_version: str
) -> list[Path]:
    """Write ``exports/vulgarisation-<level>.md`` and ``.docx``: the revised summary only."""
    document = summary_document(folder, level, now=now, tool_version=tool_version)
    target = folder.path / "exports"
    target.mkdir(parents=True, exist_ok=True)
    markdown = target / f"vulgarisation-{level.value}.md"
    markdown.write_text(render_markdown(document), encoding="utf-8")
    docx = target / f"vulgarisation-{level.value}.docx"
    docx.write_bytes(render_docx(document))
    return [markdown, docx]
