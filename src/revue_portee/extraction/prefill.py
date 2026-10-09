"""Pre-filling of the extraction grid by the AI (EF-EXT-03, tranche 3.2).

Each included study (``screening.studies``) is charted from the text of its primary
report: the AI gives, for each field of the grid in force, a value with its quote and
page, or « not reported ». The tool checks every value against the type of its field
(an answer that does not fit is asked again once) and looks for every quote in the
text (``domain.extraction.place_quote``). The values of a study are recorded together,
after the call and its raw response (D-041); the project and batch ceilings are checked
before each call. A study is pre-filled once for each version of the grid.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from pydantic import JsonValue

from revue_portee.ai.base import ProviderCallError
from revue_portee.ai.providers import ProviderFactory
from revue_portee.ai.runner import run_task
from revue_portee.ai.tasks.extraction import (
    EXTRACT_FIELDS,
    ExtractFieldsInput,
    ExtractFieldsOutput,
    FieldText,
)
from revue_portee.ai.tasks.fulltext import PageOfText, ReportText
from revue_portee.domain.extraction import (
    ExtractionValue,
    InvalidValueError,
    ValueStatus,
    current_values,
    parse_value,
    place_quote,
)
from revue_portee.domain.fulltext import FulltextDocument, PagedText
from revue_portee.domain.grid import GridVersion
from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.domain.project import ReviewerKind
from revue_portee.domain.references import Reference
from revue_portee.fulltext import retrieval
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
from revue_portee.screening import studies
from revue_portee.screening.ai_screening import (
    MAX_ATTEMPTS,
    AIBatchResult,
    UnusableAnswerError,
    ai_reviewer,
)
from revue_portee.screening.settings import BudgetNotSetError
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import extraction as extraction_repo
from revue_portee.storage.repositories import grid as grid_repo
from revue_portee.storage.repositories import journal, projects
from revue_portee.storage.repositories import screening as screening_repo
from revue_portee.storage.repositories.ai import StoredCall

__all__ = [
    "ExtractionState",
    "NoGridError",
    "StudyExtraction",
    "check_answer",
    "extraction_state",
    "preview_ai",
    "run_ai",
]

Clock = Callable[[], datetime]


class NoGridError(LookupError):
    def __init__(self) -> None:
        super().__init__(_("Activate a version of the extraction grid first."))


def _grid(folder: ProjectFolder) -> GridVersion:
    with folder.engine.connect() as connection:
        grid = grid_repo.get_active_version(connection)
    if grid is None:
        raise NoGridError
    return grid


# --- State --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StudyExtraction:
    primary: Reference
    reports: list[str]  # the reports of the study
    readable: bool  # its primary report has readable text
    values: dict[str, ExtractionValue] = field(default_factory=dict)  # by field code

    @property
    def prefilled(self) -> bool:
        return bool(self.values)


@dataclass(frozen=True, slots=True)
class ExtractionState:
    grid: GridVersion | None
    studies: list[StudyExtraction]

    @property
    def waiting(self) -> list[StudyExtraction]:
        """Studies with readable text the AI has not pre-filled with this grid version."""
        if self.grid is None:
            return []
        version = self.grid.id
        return [
            s
            for s in self.studies
            if s.readable and not any(v.grid_version_id == version and v.reviewer_kind is
                                       ReviewerKind.AI for v in s.values.values())
        ]  # fmt: skip


def extraction_state(folder: ProjectFolder) -> ExtractionState:
    with folder.engine.connect() as connection:
        grid = grid_repo.get_active_version(connection)
        values = current_values(extraction_repo.list_values(connection))
    included = studies.included_reports(folder)
    found = []
    for study in studies.study_state(folder).studies:
        reference, document = included[study.primary]
        found.append(
            StudyExtraction(
                primary=reference,
                reports=study.reports,
                readable=not document.needs_ocr,
                values={
                    code: value for (ref, code), value in values.items() if ref == study.primary
                },
            )
        )
    return ExtractionState(grid=grid, studies=found)


# --- The AI -------------------------------------------------------------------------


def _documents(folder: ProjectFolder) -> dict[str, tuple[Reference, FulltextDocument]]:
    return studies.included_reports(folder)


def _input(
    folder: ProjectFolder,
    grid: GridVersion,
    reference: Reference,
    text: PagedText,
    language: str,
    question: str,
) -> ExtractFieldsInput:
    return ExtractFieldsInput(
        item_id=reference.id,
        language=language,
        review_question=question,
        fields=tuple(FieldText.of(f) for f in grid.sorted_fields()),
        report=ReportText(
            title=reference.title,
            year=reference.year,
            container_title=reference.container_title,
            pages=tuple(
                PageOfText(number=p.number, text=p.text) for p in text.body() if p.text.strip()
            ),
        ),
    )


def _inputs(
    folder: ProjectFolder, grid: GridVersion, waiting: Sequence[StudyExtraction]
) -> list[tuple[ExtractFieldsInput, PagedText]]:
    documents = _documents(folder)
    with folder.engine.connect() as connection:
        language = projects.get_project(connection).language
    framing = current_framing(folder)
    question = "" if framing is None else framing.framing.question
    found = []
    for study in waiting:
        reference, document = documents[study.primary.id]
        text = retrieval.paged_text(folder, document)
        found.append((_input(folder, grid, reference, text, language, question), text))
    return found


def preview_ai(
    folder: ProjectFolder, *, factory: ProviderFactory = default_provider_factory
) -> CostPreview:
    """Cost of pre-filling the studies the AI has not pre-filled with this grid."""
    grid = _grid(folder)
    items = [item for item, _text in _inputs(folder, grid, extraction_state(folder).waiting)]
    return preview(folder, EXTRACT_FIELDS, items, factory=factory)


def check_answer(output: ExtractFieldsOutput, grid: GridVersion) -> dict[str, JsonValue]:
    """The value of each field, checked against its type (None: not reported).
    UnusableAnswerError unless each field is answered exactly once with a valid value."""
    codes = [f.code for f in grid.fields]
    if sorted(v.code for v in output.values) != sorted(codes):
        raise UnusableAnswerError("each field must be answered exactly once")
    values: dict[str, JsonValue] = {}
    for answer in output.values:
        grid_field = grid.field(answer.code)
        assert grid_field is not None  # noqa: S101 - checked above
        if not answer.reported:
            values[answer.code] = None
            continue
        raw: JsonValue = list(answer.selected) if answer.selected else answer.value
        try:
            values[answer.code] = parse_value(grid_field, raw)
        except InvalidValueError as error:
            raise UnusableAnswerError(str(error)) from error
    return values


def _store(
    folder: ProjectFolder,
    grid: GridVersion,
    reference_id: str,
    text: PagedText,
    stored: StoredCall,
    output: ExtractFieldsOutput,
    values: dict[str, JsonValue],
    *,
    now: Clock,
    tool_version: str,
) -> list[ExtractionValue]:
    reviewer_id = ai_reviewer(folder, stored, now=now, tool_version=tool_version)
    body = text.body()
    answers = {a.code: a for a in output.values}
    with folder.write() as connection:
        moment = now()
        recorded = []
        for grid_field in grid.sorted_fields():
            answer = answers[grid_field.code]
            reported = values[grid_field.code] is not None
            quote = answer.quote.strip() if reported else ""
            page, check = place_quote(body, quote, answer.page)
            recorded.append(
                ExtractionValue(
                    id=new_ulid(moment),
                    reference_id=reference_id,
                    field_code=grid_field.code,
                    grid_version_id=grid.id,
                    reported=reported,
                    value=values[grid_field.code],
                    quote=quote,
                    page=page,
                    model_page=answer.page if reported else None,
                    quote_check=check,
                    status=ValueStatus.PROPOSED,
                    reviewer_id=reviewer_id,
                    reviewer_kind=ReviewerKind.AI,
                    ai_call_id=stored.id,
                    created_at=moment,
                )
            )
        reported_count = sum(1 for v in recorded if v.reported)
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.EXTRACTION_AI_PROPOSED,
            subject_type="reference",
            subject_id=reference_id,
            summary_fr=french(
                "Extraction: values proposed by the AI for a study (fields reported: "
                "{reported} of {fields})"
            ).format(reported=reported_count, fields=len(recorded)),
            tool_version=tool_version,
            payload=call_summary(stored)
            | {
                "reference": reference_id,
                "grid_version": grid.number,
                "fields": len(recorded),
                "reported": reported_count,
                "quote_checks": {
                    v.field_code: None if v.quote_check is None else v.quote_check.value
                    for v in recorded
                },
            },
        )
        for value in recorded:
            extraction_repo.insert_value(connection, value, journal_entry_id=entry.id)
    return recorded


def run_ai(
    folder: ProjectFolder,
    *,
    batch_limit: Decimal,
    factory: ProviderFactory = default_provider_factory,
    now: Clock,
    tool_version: str,
) -> AIBatchResult:
    """Pre-fill the studies the AI has not pre-filled with the grid in force, one call
    at a time, the project ceiling and ``batch_limit`` checked before each call."""
    grid = _grid(folder)
    with folder.engine.connect() as connection:
        budget = screening_repo.latest_budget(connection)
    if budget is None:
        raise BudgetNotSetError
    provider = factory(folder.ai_settings().enabled_task(EXTRACT_FIELDS.name))
    screened, failed, stopped = 0, [], ""
    spent = Decimal(0)
    for item, text in _inputs(folder, grid, extraction_state(folder).waiting):
        estimate = provider.estimate_cost(EXTRACT_FIELDS, [item]).amount
        done = False
        for _attempt in range(MAX_ATTEMPTS):
            with folder.engine.connect() as connection:
                project_spent = screening_repo.total_spent(connection)
            if project_spent + estimate > budget.limit_amount:
                stopped = "project_budget"
                break
            if spent + estimate > batch_limit:
                stopped = "batch_budget"
                break
            try:
                (result,) = run_task(provider, EXTRACT_FIELDS, [item])
            except ProviderCallError as error:
                stored = record_call(
                    folder, task=EXTRACT_FIELDS.name, item_id=error.item_id, call=error.call,
                    raw_response=error.raw_response, now=now, tool_version=tool_version,
                )  # fmt: skip
                spent += stored.record.cost_estimate
                continue
            stored = record_call(
                folder, task=EXTRACT_FIELDS.name, item_id=result.item_id, call=result.call,
                raw_response=result.raw_response, now=now, tool_version=tool_version,
            )  # fmt: skip
            spent += stored.record.cost_estimate
            try:
                values = check_answer(result.output, grid)
            except UnusableAnswerError as error:
                record_unusable(folder, stored, error, now=now, tool_version=tool_version)
                continue
            _store(
                folder, grid, item.item_id, text, stored, result.output, values, now=now,
                tool_version=tool_version,
            )  # fmt: skip
            done = True
            break
        if done:
            screened += 1
        elif stopped:
            break
        else:
            failed.append(item.item_id)
            with folder.write() as connection:
                journal.append_entry(
                    connection,
                    now=now(),
                    actor_reviewer_id=folder.reviewer_id,
                    entry_type=EntryType.EXTRACTION_AI_FAILED,
                    subject_type="reference",
                    subject_id=item.item_id,
                    summary_fr=french(
                        "Extraction: the AI could not pre-fill a study (attempts: {n})"
                    ).format(n=MAX_ATTEMPTS),
                    tool_version=tool_version,
                    payload={"reference": item.item_id, "attempts": MAX_ATTEMPTS},
                )
    return AIBatchResult(screened=screened, failed=failed, stopped=stopped, spent=spent)
