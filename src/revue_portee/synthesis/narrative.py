"""Narrative synthesis, field by field (EF-SYN-04, tranche 3.6).

For a field of the grid in force, the AI receives the values a person decided for each
included study (never the full texts), under short keys (S1, S2…), and drafts a few
sentences, each citing the keys of the studies it rests on. The tool maps the keys
back to the studies and refuses a sentence without a study or with an unknown key (the
call is asked again once). The cost is shown first; the project and confirmed ceilings
are checked before each call (D-041, D-069).

The person revises the draft: every sentence, kept, changed or added, rests on at least
one included study. Only revised drafts are exported; a draft is to review when values
of its field, or the field itself, changed since.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from pydantic import JsonValue

from revue_portee.ai.base import ProviderCallError
from revue_portee.ai.providers import ProviderFactory
from revue_portee.ai.runner import run_task
from revue_portee.ai.tasks.extraction import FieldText
from revue_portee.ai.tasks.synthesis import (
    DRAFT_SYNTHESIS,
    DraftSynthesisInput,
    DraftSynthesisOutput,
    StudyValue,
)
from revue_portee.domain.extraction import ExtractionValue, for_synthesis
from revue_portee.domain.grid import GridField, GridVersion, field_changes
from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.domain.narrative import (
    DraftStatus,
    NarrativeDraft,
    NarrativeSentence,
    UnsupportedSentenceError,
    check_sentences,
    current_drafts,
    revised_drafts,
)
from revue_portee.domain.project import ReviewerKind
from revue_portee.extraction.prefill import NoGridError, StudyExtraction, extraction_state
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
from revue_portee.reporting.narrative import NarrativeSection, build_narrative
from revue_portee.screening.ai_screening import MAX_ATTEMPTS, UnusableAnswerError, ai_reviewer
from revue_portee.screening.settings import BudgetNotSetError
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import extraction as extraction_repo
from revue_portee.storage.repositories import grid as grid_repo
from revue_portee.storage.repositories import journal, projects
from revue_portee.storage.repositories import narrative as narrative_repo
from revue_portee.storage.repositories import screening as screening_repo

__all__ = [
    "CeilingReachedError",
    "DraftFailedError",
    "FieldNarrative",
    "NarrativeState",
    "NothingToSynthesizeError",
    "UnknownFieldError",
    "draft_with_ai",
    "export_narrative",
    "narrative_document",
    "narrative_state",
    "preview_ai",
    "revise",
]

Clock = Callable[[], datetime]


class UnknownFieldError(LookupError):
    def __init__(self, code: str) -> None:
        super().__init__(_("Unknown field: {code}.").format(code=code))


class NothingToSynthesizeError(ValueError):
    def __init__(self) -> None:
        super().__init__(_("No included study has a value decided by a person on this field."))


class CeilingReachedError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(_("The call would exceed the ceiling: nothing was asked."))


class DraftFailedError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            _("The AI could not draft a usable synthesis; the calls are recorded in the journal.")
        )


@dataclass(frozen=True, slots=True)
class FieldNarrative:
    field: GridField
    studies: list[tuple[StudyExtraction, ExtractionValue]]  # values decided by a person
    current: NarrativeDraft | None  # the latest draft, the AI's or the person's
    revised: NarrativeDraft | None  # the latest draft the person revised
    outdated: bool  # values or the field changed since the revision

    @property
    def to_revise(self) -> bool:
        return self.current is not None and self.current.status is DraftStatus.PROPOSED


@dataclass(frozen=True, slots=True)
class NarrativeState:
    grid: GridVersion
    language: str
    studies: list[StudyExtraction]
    fields: list[FieldNarrative]

    def field(self, code: str) -> FieldNarrative:
        found = next((f for f in self.fields if f.field.code == code), None)
        if found is None:
            raise UnknownFieldError(code)
        return found

    @property
    def labels(self) -> dict[str, str]:
        # Imported here: the maps import this package's sibling, which reads the grid.
        from revue_portee.synthesis.maps import study_label

        return {s.primary.id: study_label(s.primary) for s in self.studies}


def _changed_since(draft: NarrativeDraft, field: GridField, versions: dict[str, GridVersion],
                   values: Sequence[ExtractionValue]) -> bool:  # fmt: skip
    made = versions.get(draft.grid_version_id)
    before = None if made is None else made.field(field.code)
    if before is None or field_changes(before, field):
        return True
    return any(v.created_at > draft.created_at for v in values)


def narrative_state(folder: ProjectFolder) -> NarrativeState:
    state = extraction_state(folder)
    if state.grid is None:
        raise NoGridError
    with folder.engine.connect() as connection:
        stored = extraction_repo.list_values(connection)
        drafts = narrative_repo.list_drafts(connection)
        versions = {v.id: v for v in grid_repo.list_versions(connection)}
        language = projects.get_project(connection).language
    kept = for_synthesis(stored)
    current, revised = current_drafts(drafts), revised_drafts(drafts)
    fields = []
    for grid_field in state.grid.sorted_fields():
        decided = [
            (study, kept[study.primary.id, grid_field.code])
            for study in state.studies
            if (study.primary.id, grid_field.code) in kept
        ]
        last = revised.get(grid_field.code)
        fields.append(
            FieldNarrative(
                field=grid_field,
                studies=decided,
                current=current.get(grid_field.code),
                revised=last,
                outdated=last is not None
                and _changed_since(last, grid_field, versions, [v for _s, v in decided]),
            )
        )
    return NarrativeState(grid=state.grid, language=language, studies=state.studies, fields=fields)


def _shown(value: ExtractionValue) -> str:
    if isinstance(value.value, list):
        return " | ".join(str(v) for v in value.value)
    if value.value is True:
        return "yes"
    if value.value is False:
        return "no"
    return "" if value.value is None else str(value.value)


def _input(folder: ProjectFolder, state: NarrativeState, code: str) -> DraftSynthesisInput:
    target = state.field(code)
    if not target.studies:
        raise NothingToSynthesizeError
    labels = state.labels
    framing = current_framing(folder)
    return DraftSynthesisInput(
        item_id=code,
        language=state.language,
        review_question="" if framing is None else framing.framing.question,
        field=FieldText.of(target.field),
        studies=tuple(
            StudyValue(
                key=f"S{number}",
                label=labels[study.primary.id],
                reported=value.reported,
                value=_shown(value) if value.reported else "",
                quote=value.quote if value.reported else "",
            )
            for number, (study, value) in enumerate(target.studies, start=1)
        ),
    )


def preview_ai(
    folder: ProjectFolder, code: str, *, factory: ProviderFactory = default_provider_factory
) -> CostPreview:
    """Cost of a draft of the synthesis of field ``code`` (one call)."""
    return preview(folder, DRAFT_SYNTHESIS, [_input(folder, narrative_state(folder), code)],
                   factory=factory)  # fmt: skip


def check_answer(
    output: DraftSynthesisOutput, item: DraftSynthesisInput, by_key: dict[str, str]
) -> tuple[NarrativeSentence, ...]:
    """The sentences with their studies, the keys mapped back to the studies.
    UnusableAnswerError when a sentence has no study, an unknown key or no text."""
    try:
        return check_sentences(
            (
                NarrativeSentence(
                    text=s.text.strip(),
                    study_ids=tuple(dict.fromkeys(by_key.get(k.strip(), k) for k in s.studies)),
                )
                for s in output.sentences
            ),
            set(by_key.values()),
        )
    except (UnsupportedSentenceError, ValueError) as error:
        raise UnusableAnswerError(str(error)) from error


def _record(folder: ProjectFolder, draft: NarrativeDraft, entry_type: str, summary: str,
            payload_extra: dict[str, JsonValue], *, tool_version: str) -> None:  # fmt: skip
    cited: list[JsonValue] = [*sorted({i for s in draft.sentences for i in s.study_ids})]
    payload: dict[str, JsonValue] = {
        "field": draft.field_code,
        "sentences": len(draft.sentences),
        "studies": cited,
        "supersedes": draft.supersedes_id,
    }
    with folder.write() as connection:
        entry = journal.append_entry(
            connection,
            now=draft.created_at,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=entry_type,
            subject_type="narrative_draft",
            subject_id=draft.id,
            summary_fr=summary,
            tool_version=tool_version,
            payload=payload | payload_extra,
        )
        narrative_repo.insert_draft(connection, draft, journal_entry_id=entry.id)


def draft_with_ai(
    folder: ProjectFolder,
    code: str,
    *,
    ceiling: Decimal,
    factory: ProviderFactory = default_provider_factory,
    now: Clock,
    tool_version: str,
) -> NarrativeDraft:
    """Ask the AI for a draft of the synthesis of field ``code``, under ``ceiling`` and
    the project budget, checked before each call."""
    state = narrative_state(folder)
    item = _input(folder, state, code)
    by_key = {
        f"S{number}": study.primary.id
        for number, (study, _value) in enumerate(state.field(code).studies, start=1)
    }
    with folder.engine.connect() as connection:
        budget = screening_repo.latest_budget(connection)
    if budget is None:
        raise BudgetNotSetError
    provider = factory(folder.ai_settings().enabled_task(DRAFT_SYNTHESIS.name))
    estimate = provider.estimate_cost(DRAFT_SYNTHESIS, [item]).amount
    spent = Decimal(0)
    for _attempt in range(MAX_ATTEMPTS):
        with folder.engine.connect() as connection:
            project_spent = screening_repo.total_spent(connection)
        if project_spent + estimate > budget.limit_amount or spent + estimate > ceiling:
            if spent:
                break
            raise CeilingReachedError
        try:
            (result,) = run_task(provider, DRAFT_SYNTHESIS, [item])
        except ProviderCallError as error:
            stored = record_call(
                folder, task=DRAFT_SYNTHESIS.name, item_id=error.item_id, call=error.call,
                raw_response=error.raw_response, now=now, tool_version=tool_version,
            )  # fmt: skip
            spent += stored.record.cost_estimate
            continue
        stored = record_call(
            folder, task=DRAFT_SYNTHESIS.name, item_id=result.item_id, call=result.call,
            raw_response=result.raw_response, now=now, tool_version=tool_version,
        )  # fmt: skip
        spent += stored.record.cost_estimate
        try:
            sentences = check_answer(result.output, item, by_key)
        except UnusableAnswerError as error:
            record_unusable(folder, stored, error, now=now, tool_version=tool_version)
            continue
        reviewer_id = ai_reviewer(folder, stored, now=now, tool_version=tool_version)
        current = state.field(code).current
        moment = now()
        draft = NarrativeDraft(
            id=new_ulid(moment), field_code=code, grid_version_id=state.grid.id,
            language=state.language, sentences=sentences, status=DraftStatus.PROPOSED,
            reviewer_id=reviewer_id, reviewer_kind=ReviewerKind.AI, ai_call_id=stored.id,
            supersedes_id=None if current is None else current.id, created_at=moment,
        )  # fmt: skip
        _record(
            folder, draft, EntryType.SYNTHESIS_DRAFT_PROPOSED,
            french("Narrative synthesis of {field}: draft proposed by the AI").format(
                field=code
            ),
            call_summary(stored), tool_version=tool_version,
        )  # fmt: skip
        return draft
    with folder.write() as connection:
        journal.append_entry(
            connection,
            now=now(),
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.SYNTHESIS_AI_FAILED,
            subject_type="field",
            subject_id=code,
            summary_fr=french(
                "Narrative synthesis of {field}: the AI gave no usable draft (attempts: {n})"
            ).format(field=code, n=MAX_ATTEMPTS),
            tool_version=tool_version,
            payload={"field": code, "attempts": MAX_ATTEMPTS},
        )
    raise DraftFailedError


def revise(
    folder: ProjectFolder,
    code: str,
    sentences: Sequence[NarrativeSentence],
    *,
    now: Clock,
    tool_version: str,
) -> NarrativeDraft:
    """The person's synthesis of field ``code``: every sentence rests on at least one
    included study (UnsupportedSentenceError otherwise)."""
    state = narrative_state(folder)
    target = state.field(code)
    checked = check_sentences(
        (NarrativeSentence(text=s.text.strip(), study_ids=s.study_ids) for s in sentences),
        {s.primary.id for s in state.studies},
    )
    moment = now()
    draft = NarrativeDraft(
        id=new_ulid(moment), field_code=code, grid_version_id=state.grid.id,
        language=state.language, sentences=checked, status=DraftStatus.REVISED,
        reviewer_id=folder.reviewer_id, reviewer_kind=ReviewerKind.HUMAN,
        supersedes_id=None if target.current is None else target.current.id, created_at=moment,
    )  # fmt: skip
    _record(
        folder, draft, EntryType.SYNTHESIS_DRAFT_REVISED,
        french("Narrative synthesis of {field}: revised by the person").format(field=code),
        {"from_ai": target.current is not None
         and target.current.reviewer_kind is ReviewerKind.AI},
        tool_version=tool_version,
    )  # fmt: skip
    return draft


def narrative_document(
    folder: ProjectFolder, *, language: str, now: Clock, tool_version: str
) -> Document:
    state = narrative_state(folder)
    with folder.engine.connect() as connection:
        title = projects.get_project(connection).title
    labels = state.labels
    references = [
        (
            s.primary.id,
            labels[s.primary.id],
            ". ".join(
                part
                for part in (
                    ", ".join(s.primary.authors[:3]) + (" et al" if len(s.primary.authors) > 3
                                                        else ""),
                    s.primary.title, s.primary.container_title, str(s.primary.year or ""),
                    f"doi:{s.primary.doi.lower()}" if s.primary.doi else "",
                )
                if part
            ),
        )
        for s in state.studies
    ]  # fmt: skip
    return build_narrative(
        [NarrativeSection(field=f.field, revised=f.revised, outdated=f.outdated)
         for f in state.fields],
        references, project_title=title, language=language, tool_version=tool_version,
        generated_at=now(),
    )  # fmt: skip


def export_narrative(
    folder: ProjectFolder, *, language: str, now: Clock, tool_version: str
) -> list[Path]:
    """Write ``exports/synthese/narratif-<langue>.md`` and ``.docx``: the revised
    synthesis only."""
    document = narrative_document(folder, language=language, now=now, tool_version=tool_version)
    target = folder.path / "exports" / "synthese"
    target.mkdir(parents=True, exist_ok=True)
    markdown = target / f"narratif-{language}.md"
    markdown.write_text(render_markdown(document), encoding="utf-8")
    docx = target / f"narratif-{language}.docx"
    docx.write_bytes(render_docx(document))
    return [markdown, docx]
