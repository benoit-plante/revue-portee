"""Full-text screening (EF-SEL-16; docs/10-conception-texte-integral.md §3; D-102).

The reports whose full text is obtained are screened in rounds of the full-text stage:

- a **pilot**, required before the AI screens the main round: 20 texts drawn with a
  recorded seed (every text when there are fewer than 40), screened blind by the person
  and by the AI, so that the AI is measured within the review (RAISE 3);
- the **main round**, in an order drawn with a seed, in one of two modes fixed when it
  starts: **blind** (the person decides without seeing the AI; disagreements, keep
  against exclude, are reconciled with the AI's rationale and quotes in view) or
  **assisted** (the AI screens first; the person decides with its assessment, quotes
  and pages in view, and that decision is final).

The person screens every text: the AI never excludes on its own. An exclusion names
its criteria; its primary reason is the first of them in the order of the criteria.
The AI reads the text by page, without the bibliography; each quote it gives is looked
for at the page it names. A scanned text (no readable text) is screened by the person
only. Each call is recorded in its own transaction with its raw response (D-041), the
project and batch ceilings checked before each call (ENF-COU-02).
"""

import secrets
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from pydantic import JsonValue

from revue_portee.ai.base import ProviderCallError
from revue_portee.ai.providers import ProviderFactory
from revue_portee.ai.runner import run_task
from revue_portee.ai.tasks.fulltext import (
    SCREEN_FULLTEXT,
    PageOfText,
    ReportText,
    ScreenFulltextInput,
    ScreenFulltextOutput,
)
from revue_portee.ai.tasks.screening import CriterionText
from revue_portee.domain.criteria import CriteriaVersion
from revue_portee.domain.fulltext import FulltextDocument, PagedText, QuoteCheck, check_quote
from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.domain.metrics import PilotMetrics, pilot_metrics
from revue_portee.domain.references import Reference
from revue_portee.domain.screening import (
    AssessmentStatus,
    CriterionAssessment,
    Decision,
    DecisionContext,
    DecisionValue,
    PilotRound,
    ReviewerKind,
    RoundKind,
    ScreeningMode,
    ScreeningRound,
    Stage,
    Thresholds,
    ai_value,
    detect_language,
    disagree,
    draw_sample,
    keeps,
    must_not_exclude,
    primary_reason,
)
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
from revue_portee.screening.ai_screening import (
    MAX_ATTEMPTS,
    AIBatchResult,
    UnusableAnswerError,
    _answer_text,
    ai_reviewer,
    record_ai_failure,
)
from revue_portee.screening.main import NotADisagreementError
from revue_portee.screening.pilot import (
    NotInRoundError,
    UnknownCriterionError,
    UnknownRoundError,
    active_criteria,
)
from revue_portee.screening.settings import BudgetNotSetError
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.raw import read_raw_response
from revue_portee.storage.repositories import ai as ai_repo
from revue_portee.storage.repositories import criteria as criteria_repo
from revue_portee.storage.repositories import journal, projects
from revue_portee.storage.repositories import screening as screening_repo
from revue_portee.storage.repositories.ai import StoredCall

__all__ = [
    "LARGE_POPULATION",
    "PILOT_SIZE",
    "STAGE",
    "AIFirstError",
    "FulltextMainExistsError",
    "FulltextPilotState",
    "FulltextState",
    "NoTextsError",
    "NotBlindError",
    "PilotRequiredError",
    "add_new_texts",
    "ai_inputs",
    "check_answer",
    "criteria_of_round",
    "fulltext_thresholds",
    "kept",
    "main_round",
    "main_state",
    "next_text",
    "pilot_complete",
    "pilot_round",
    "pilot_state",
    "preview_ai",
    "reconcile",
    "record_decision",
    "replay_decision",
    "round_of",
    "run_ai",
    "screenable_texts",
    "start_main",
    "start_pilot",
    "store_batch_decision",
]

Clock = Callable[[], datetime]
STAGE = Stage.FULL_TEXT
PILOT_SIZE = 20  # texts of the pilot (docs/10, decision 3)…
LARGE_POPULATION = 40  # …when there are at least this many; every text otherwise
HUMAN = ReviewerKind.HUMAN.value
AI = ReviewerKind.AI.value


class NoTextsError(ValueError):
    def __init__(self) -> None:
        super().__init__(_("No full text is obtained yet: add the texts first."))


class FulltextMainExistsError(ValueError):
    def __init__(self) -> None:
        super().__init__(_("The full-text screening has already started."))


class PilotRequiredError(ValueError):
    def __init__(self) -> None:
        super().__init__(
            _(
                "Complete the full-text pilot first: every text of the pilot screened by "
                "you and by the AI. It measures the AI within this review (RAISE 3)."
            )
        )


class AIFirstError(ValueError):
    def __init__(self) -> None:
        super().__init__(
            _("Assisted screening: the AI has not screened this text yet; screen it first.")
        )


class NotBlindError(ValueError):
    def __init__(self) -> None:
        super().__init__(
            _("Assisted screening has no reconciliation: your decision is the final one.")
        )


# --- Texts --------------------------------------------------------------------------


def _documents(folder: ProjectFolder) -> dict[str, tuple[Reference, FulltextDocument]]:
    return {
        row.reference.id: (row.reference, row.document)
        for row in retrieval.retrieval_report(folder).rows
        if row.document is not None
    }


def screenable_texts(folder: ProjectFolder) -> list[str]:
    """References sought whose full text is obtained, sorted by identifier."""
    return sorted(_documents(folder))


def fulltext_thresholds(folder: ProjectFolder) -> Thresholds:
    """Thresholds of the full-text stage: fixed by a person, otherwise the project
    defaults (no calibration at this stage, docs/10 §3.1)."""
    with folder.engine.connect() as connection:
        setting = screening_repo.latest_threshold(connection, STAGE)
    if setting is not None:
        return setting.thresholds
    supervision = folder.ai_settings().supervision
    return Thresholds(
        exclude_below=float(supervision.exclude_below),
        include_above=float(supervision.include_above),
    )


def _version(folder: ProjectFolder, version_id: str) -> CriteriaVersion:
    with folder.engine.connect() as connection:
        version = criteria_repo.get_version(connection, version_id)
    assert version is not None  # noqa: S101 - a round always points to a version
    return version


# --- Rounds -------------------------------------------------------------------------


def round_of(folder: ProjectFolder, round_id: str) -> ScreeningRound:
    """A round of the full-text stage, pilot or main (UnknownRoundError otherwise)."""
    return _any_round(folder, round_id)


def criteria_of_round(folder: ProjectFolder, screening: ScreeningRound) -> CriteriaVersion:
    """The criteria a round is screened with."""
    return _version(folder, screening.criteria_version_id)


def pilot_round(folder: ProjectFolder) -> PilotRound | None:
    """The latest full-text pilot."""
    with folder.engine.connect() as connection:
        rounds = screening_repo.list_rounds(connection, STAGE)
    return rounds[-1] if rounds else None


def main_round(folder: ProjectFolder) -> ScreeningRound | None:
    """The main full-text round, once started (there is one)."""
    with folder.engine.connect() as connection:
        rounds = screening_repo.list_screening_rounds(connection, STAGE, RoundKind.MAIN)
    return rounds[-1] if rounds else None


def _any_round(folder: ProjectFolder, round_id: str) -> ScreeningRound:
    with folder.engine.connect() as connection:
        found = screening_repo.get_screening_round(connection, round_id)
    if found is None or found.stage is not STAGE:
        raise UnknownRoundError
    return found


def start_pilot(
    folder: ProjectFolder, *, seed: int | None = None, now: Clock, tool_version: str
) -> PilotRound:
    """Draw the full-text pilot: 20 texts, or every text when there are fewer than 40."""
    version = active_criteria(folder)
    population = screenable_texts(folder)
    if not population:
        raise NoTextsError
    size = PILOT_SIZE if len(population) >= LARGE_POPULATION else len(population)
    drawn_seed = secrets.randbelow(2**31) if seed is None else seed
    sample = draw_sample(population, size, drawn_seed)
    with folder.write() as connection:
        moment = now()
        number = len(screening_repo.list_rounds(connection, STAGE)) + 1
        pilot = PilotRound(
            id=new_ulid(moment),
            number=number,
            stage=STAGE,
            criteria_version_id=version.id,
            seed=drawn_seed,
            sample_size=size,
            reference_ids=sample,
            created_at=moment,
            reviewer_id=folder.reviewer_id,
        )
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.PILOT_STARTED,
            subject_type="screening_round",
            subject_id=pilot.id,
            summary_fr=french(
                "Full-text pilot {number}: texts drawn: {size} of {population} (seed {seed})"
            ).format(number=number, size=size, population=len(population), seed=drawn_seed),
            tool_version=tool_version,
            payload={
                "stage": STAGE.value,
                "round": number,
                "seed": drawn_seed,
                "sample_size": size,
                "population": len(population),
                "criteria_version": version.number,
                "reference_ids": list(sample),
            },
        )
        screening_repo.insert_round(connection, pilot, journal_entry_id=entry.id)
    return pilot


def _carried(folder: ProjectFolder, main: ScreeningRound) -> list[str]:
    """Full-text pilots whose human decisions count for the main round (same criteria
    version, D-078)."""
    with folder.engine.connect() as connection:
        pilots = screening_repo.list_rounds(connection, STAGE)
    return [p.id for p in pilots if p.criteria_version_id == main.criteria_version_id]


def start_main(
    folder: ProjectFolder,
    mode: ScreeningMode,
    *,
    seed: int | None = None,
    now: Clock,
    tool_version: str,
) -> ScreeningRound:
    """Start the main full-text round in ``mode``, fixed for the round (D-102)."""
    if main_round(folder) is not None:
        raise FulltextMainExistsError
    version = active_criteria(folder)
    population = screenable_texts(folder)
    if not population:
        raise NoTextsError
    drawn_seed = secrets.randbelow(2**31) if seed is None else seed
    order = draw_sample(population, len(population), drawn_seed)
    with folder.write() as connection:
        moment = now()
        main = ScreeningRound(
            id=new_ulid(moment),
            number=1,
            stage=STAGE,
            kind=RoundKind.MAIN,
            criteria_version_id=version.id,
            seed=drawn_seed,
            sample_size=len(order),
            created_at=moment,
            reviewer_id=folder.reviewer_id,
            mode=mode,
        )
        if mode is ScreeningMode.ASSISTED:
            summary = french(
                "Full-text screening started in assisted mode: {count} texts (seed {seed})"
            )
        else:
            summary = french(
                "Full-text screening started in blind mode: {count} texts (seed {seed})"
            )
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.SCREENING_STARTED,
            subject_type="screening_round",
            subject_id=main.id,
            summary_fr=summary.format(count=len(order), seed=drawn_seed),
            tool_version=tool_version,
            payload={
                "stage": STAGE.value,
                "mode": mode.value,
                "references": len(order),
                "seed": drawn_seed,
                "criteria_version": version.number,
            },
        )
        screening_repo.insert_screening_round(connection, main, order, journal_entry_id=entry.id)
    return main


def add_new_texts(folder: ProjectFolder, *, now: Clock, tool_version: str) -> int:
    """Add at the end of the main round the texts obtained since it started, in an order
    drawn with a recorded seed."""
    main = main_round(folder)
    if main is None:
        return 0
    with folder.engine.connect() as connection:
        members = set(screening_repo.member_ids(connection, main.id))
    new = [ref for ref in screenable_texts(folder) if ref not in members]
    if not new:
        return 0
    seed = main.seed + len(members)
    order = draw_sample(new, len(new), seed)
    with folder.write() as connection:
        journal.append_entry(
            connection,
            now=now(),
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.SCREENING_MEMBERS_ADDED,
            subject_type="screening_round",
            subject_id=main.id,
            summary_fr=french("Full-text screening: {count} new texts added").format(
                count=len(order)
            ),
            tool_version=tool_version,
            payload={"stage": STAGE.value, "references": len(order), "seed": seed},
        )
        screening_repo.append_members(connection, main.id, order)
    return len(order)


# --- The AI -------------------------------------------------------------------------


def ai_inputs(
    folder: ProjectFolder, version: CriteriaVersion, reference_ids: Sequence[str]
) -> tuple[list[ScreenFulltextInput], list[str]]:
    """What the model sees of each text (its pages without the bibliography), and the
    texts it cannot read (scanned)."""
    documents = _documents(folder)
    with folder.engine.connect() as connection:
        language = projects.get_project(connection).language
    framing = current_framing(folder)
    criteria = tuple(CriterionText.of(c) for c in version.criteria)
    inputs, unreadable = [], []
    for ref_id in reference_ids:
        reference, document = documents[ref_id]
        pages = tuple(
            PageOfText(number=p.number, text=p.text)
            for p in retrieval.paged_text(folder, document).body()
            if p.text.strip()
        )
        if document.needs_ocr or not pages:
            unreadable.append(ref_id)
            continue
        inputs.append(
            ScreenFulltextInput(
                item_id=ref_id,
                language=language,
                review_question="" if framing is None else framing.framing.question,
                criteria=criteria,
                report=ReportText(
                    title=reference.title,
                    year=reference.year,
                    container_title=reference.container_title,
                    pages=pages,
                ),
            )
        )
    return inputs, unreadable


def _members(folder: ProjectFolder, round_id: str) -> tuple[ScreeningRound, list[str]]:
    screening = _any_round(folder, round_id)
    with folder.engine.connect() as connection:
        return screening, screening_repo.member_ids(connection, round_id)


def _waiting(folder: ProjectFolder, round_id: str) -> list[str]:
    _round, members = _members(folder, round_id)
    with folder.engine.connect() as connection:
        decided = screening_repo.latest_by_reference(connection, [round_id], reviewer_kind=AI)
    return [ref for ref in members if ref not in decided]


def preview_ai(
    folder: ProjectFolder, round_id: str, *, factory: ProviderFactory = default_provider_factory
) -> CostPreview:
    """Cost of screening with the AI the texts of the round it has not screened yet."""
    screening = _any_round(folder, round_id)
    inputs, _unreadable = ai_inputs(
        folder, _version(folder, screening.criteria_version_id), _waiting(folder, round_id)
    )
    return preview(folder, SCREEN_FULLTEXT, inputs, factory=factory)


def check_answer(output: ScreenFulltextOutput, codes: Sequence[str]) -> None:
    """UnusableAnswerError unless each criterion is assessed exactly once and the
    decisive criteria are criteria of the version."""
    if sorted(a.code for a in output.assessments) != sorted(codes):
        raise UnusableAnswerError("each criterion must be assessed exactly once")
    if not set(output.decisive_criteria) <= set(codes):
        raise UnusableAnswerError("decisive criteria must be criteria of the version")


def _ai_decision(
    output: ScreenFulltextOutput,
    *,
    reference: Reference,
    text: PagedText,
    version: CriteriaVersion,
    thresholds: Thresholds,
    decision_id: str,
    round_id: str,
    reviewer_id: str,
    call_id: str,
    tool_version: str,
    moment: datetime,
) -> Decision:
    """The AI decision derived from an answer: the same answer and text always give the
    same decision (how a decision is rebuilt without calling the model again)."""
    kinds = {c.code: c.kind for c in version.criteria}
    body = text.body()
    assessments = []
    for a in sorted(output.assessments, key=lambda a: list(kinds).index(a.code)):
        check = check_quote(body, a.evidence_quote, a.page) if a.evidence_quote else None
        assessments.append(
            CriterionAssessment(
                code=a.code,
                kind=kinds[a.code],
                status=AssessmentStatus(a.status),
                evidence_quote=a.evidence_quote,
                quote_found=None if check is None else check is not QuoteCheck.NOT_FOUND,
                page=a.page,
                quote_check=check,
            )
        )
    return Decision(
        id=decision_id,
        reference_id=reference.id,
        stage=STAGE,
        round_id=round_id,
        reviewer_id=reviewer_id,
        reviewer_kind=ReviewerKind.AI,
        value=ai_value(output.inclusion_probability, thresholds, assessments),
        confidence_raw=output.inclusion_probability,
        rationale=output.rationale,
        criteria_cited=tuple(dict.fromkeys(output.decisive_criteria)),
        assessments=tuple(assessments),
        model_decision=DecisionValue(output.decision),
        thresholds=thresholds,
        criteria_version_id=version.id,
        language=detect_language(reference.language, reference.title, reference.abstract),
        ai_call_id=call_id,
        tool_version=tool_version,
        created_at=moment,
    )


def _store_ai_decision(
    folder: ProjectFolder,
    screening: ScreeningRound,
    stored: StoredCall,
    output: ScreenFulltextOutput,
    reference: Reference,
    text: PagedText,
    version: CriteriaVersion,
    thresholds: Thresholds,
    reviewer_id: str,
    *,
    now: Clock,
    tool_version: str,
) -> Decision:
    with folder.write() as connection:
        moment = now()
        decision = _ai_decision(
            output,
            reference=reference,
            text=text,
            version=version,
            thresholds=thresholds,
            decision_id=new_ulid(moment),
            round_id=screening.id,
            reviewer_id=reviewer_id,
            call_id=stored.id,
            tool_version=tool_version,
            moment=moment,
        )
        checks: dict[str, JsonValue] = {
            a.code: None if a.quote_check is None else a.quote_check.value
            for a in decision.assessments
        }
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.SCREENING_AI_DECIDED,
            subject_type="decision",
            subject_id=decision.id,
            summary_fr=french("Full-text screening: AI decision recorded"),
            tool_version=tool_version,
            payload=call_summary(stored)
            | {
                "stage": STAGE.value,
                "reference": reference.id,
                "value": decision.value.value,
                "model_decision": output.decision,
                "confidence_raw": decision.confidence_raw,
                "thresholds": thresholds.model_dump(mode="json"),
                "criteria_cited": list(decision.criteria_cited),
                "quote_checks": checks,
                "rule_sel_07": must_not_exclude(decision.assessments),
            },
        )
        screening_repo.insert_decision(connection, decision, journal_entry_id=entry.id)
    return decision


def store_batch_decision(
    folder: ProjectFolder,
    screening: ScreeningRound,
    _label: str,
    stored: StoredCall,
    output: ScreenFulltextOutput,
    reference_id: str,
    version: CriteriaVersion,
    *,
    now: Clock,
    tool_version: str,
) -> Decision:
    """Record the AI's decision on a text from a batch answer (``screening.batch_ai``)."""
    reference, document = _documents(folder)[reference_id]
    return _store_ai_decision(
        folder,
        screening,
        stored,
        output,
        reference,
        retrieval.paged_text(folder, document),
        version,
        fulltext_thresholds(folder),
        ai_reviewer(folder, stored, now=now, tool_version=tool_version),
        now=now,
        tool_version=tool_version,
    )


def run_ai(
    folder: ProjectFolder,
    round_id: str,
    *,
    batch_limit: Decimal,
    factory: ProviderFactory = default_provider_factory,
    now: Clock,
    tool_version: str,
) -> AIBatchResult:
    """Screen with the AI the texts of the round it has not screened yet, one call at a
    time. The main round needs a completed pilot (docs/10, decision 3). Before each
    call, the project ceiling and ``batch_limit`` are checked (ENF-COU-02); what was
    screened stays recorded."""
    screening = _any_round(folder, round_id)
    if screening.kind is RoundKind.MAIN and not pilot_complete(folder):
        raise PilotRequiredError
    with folder.engine.connect() as connection:
        budget = screening_repo.latest_budget(connection)
    if budget is None:
        raise BudgetNotSetError
    version = _version(folder, screening.criteria_version_id)
    provider = factory(folder.ai_settings().enabled_task(SCREEN_FULLTEXT.name))
    thresholds = fulltext_thresholds(folder)
    documents = _documents(folder)
    inputs, _unreadable = ai_inputs(folder, version, _waiting(folder, round_id))
    codes = [c.code for c in version.criteria]
    screened, failed, stopped = 0, [], ""
    spent = Decimal(0)
    for item in inputs:
        estimate = provider.estimate_cost(SCREEN_FULLTEXT, [item]).amount
        decided = False
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
                (result,) = run_task(provider, SCREEN_FULLTEXT, [item])
            except ProviderCallError as error:
                stored = record_call(
                    folder, task=SCREEN_FULLTEXT.name, item_id=error.item_id, call=error.call,
                    raw_response=error.raw_response, now=now, tool_version=tool_version,
                )  # fmt: skip
                spent += stored.record.cost_estimate
                continue
            stored = record_call(
                folder, task=SCREEN_FULLTEXT.name, item_id=result.item_id, call=result.call,
                raw_response=result.raw_response, now=now, tool_version=tool_version,
            )  # fmt: skip
            spent += stored.record.cost_estimate
            try:
                check_answer(result.output, codes)
            except UnusableAnswerError as error:
                record_unusable(folder, stored, error, now=now, tool_version=tool_version)
                continue
            reference, document = documents[item.item_id]
            _store_ai_decision(
                folder,
                screening,
                stored,
                result.output,
                reference,
                retrieval.paged_text(folder, document),
                version,
                thresholds,
                ai_reviewer(folder, stored, now=now, tool_version=tool_version),
                now=now,
                tool_version=tool_version,
            )
            decided = True
            break
        if decided:
            screened += 1
        elif stopped:
            break  # not a failure: the text waits for the next batch
        else:
            failed.append(item.item_id)
            record_ai_failure(
                folder,
                screening.id,
                french(
                    "Full-text screening: the AI could not screen a text (attempts: {n})"
                ).format(n=MAX_ATTEMPTS),
                item.item_id,
                now=now,
                tool_version=tool_version,
            )
    outcome = AIBatchResult(screened=screened, failed=failed, stopped=stopped, spent=spent)
    with folder.write() as connection:
        moment = now()
        if stopped:
            journal.append_entry(
                connection,
                now=moment,
                actor_reviewer_id=folder.reviewer_id,
                entry_type=EntryType.BUDGET_REACHED,
                subject_type="screening_round",
                subject_id=screening.id,
                summary_fr=french("Budget reached: the AI batch stopped before the next call"),
                tool_version=tool_version,
                payload={"ceiling": stopped, "spent": str(spent)},
            )
        journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.SCREENING_AI_BATCH_ENDED,
            subject_type="screening_round",
            subject_id=screening.id,
            summary_fr=french(
                "Full-text screening: AI screening of {screened} texts ({failed} failed)"
            ).format(screened=screened, failed=len(failed)),
            tool_version=tool_version,
            payload={
                "stage": STAGE.value,
                "screened": screened,
                "failed": list(failed),
                "stopped": stopped,
                "spent": str(spent),
            },
        )
    return outcome


def replay_decision(folder: ProjectFolder, decision_id: str) -> Decision:
    """Rebuild a full-text AI decision from the raw response kept in the project and the
    text, without any call to the model (ENF-REP-02)."""
    with folder.engine.connect() as connection:
        found = next(
            (d for d in screening_repo.list_decisions(connection) if d.id == decision_id), None
        )
        if found is None or found.ai_call_id is None or found.stage is not STAGE:
            raise LookupError(decision_id)
        stored = ai_repo.get_call(connection, found.ai_call_id)
    assert stored is not None  # noqa: S101 - an AI decision always has its call
    assert stored.record.response_path is not None  # noqa: S101 - and its raw response
    assert found.thresholds is not None  # noqa: S101
    raw = read_raw_response(folder.path, stored.record.response_path)
    output = ScreenFulltextOutput.model_validate_json(_answer_text(raw))
    reference, document = _documents(folder)[found.reference_id]
    return _ai_decision(
        output,
        reference=reference,
        text=retrieval.paged_text(folder, document),
        version=_version(folder, found.criteria_version_id),
        thresholds=found.thresholds,
        decision_id=found.id,
        round_id=found.round_id or "",
        reviewer_id=found.reviewer_id,
        call_id=stored.id,
        tool_version=found.tool_version,
        moment=found.created_at,
    )


# --- The person ---------------------------------------------------------------------


def _decided_in(folder: ProjectFolder, screening: ScreeningRound) -> list[str]:
    if screening.kind is RoundKind.MAIN:
        return [screening.id, *_carried(folder, screening)]
    return [screening.id]


def record_decision(
    folder: ProjectFolder,
    round_id: str,
    reference_id: str,
    value: DecisionValue,
    *,
    criteria_cited: Sequence[str] = (),
    rationale: str = "",
    now: Clock,
    tool_version: str,
) -> Decision:
    """The person's decision on a text of a full-text round: blind in a pilot and in a
    blind round, with the AI's assessment in view in an assisted round (the AI must
    have screened the text first). An exclusion names its criteria (EF-SEL-12); a new
    decision on the same text supersedes the previous one."""
    screening, members = _members(folder, round_id)
    if reference_id not in members:
        raise NotInRoundError
    assisted = screening.kind is RoundKind.MAIN and screening.mode is ScreeningMode.ASSISTED
    context = DecisionContext.ASSISTED if assisted else DecisionContext.INDEPENDENT
    version = _version(folder, screening.criteria_version_id)
    unknown = sorted(set(criteria_cited) - {c.code for c in version.criteria})
    if unknown:
        raise UnknownCriterionError(unknown)
    order = [c.code for c in version.criteria]
    with folder.write() as connection:
        if assisted and not screening_repo.latest_by_reference(
            connection, [screening.id], reviewer_kind=AI
        ).get(reference_id):
            raise AIFirstError
        previous = screening_repo.latest_by_reference(
            connection, _decided_in(folder, screening), reviewer_kind=HUMAN,
            contexts=[context.value],
        ).get(reference_id)  # fmt: skip
        moment = now()
        decision = Decision(
            id=new_ulid(moment),
            reference_id=reference_id,
            stage=STAGE,
            round_id=screening.id,
            reviewer_id=folder.reviewer_id,
            reviewer_kind=ReviewerKind.HUMAN,
            value=value,
            rationale=rationale.strip(),
            criteria_cited=tuple(sorted(set(criteria_cited), key=order.index)),
            criteria_version_id=version.id,
            context=context,
            blinded=not assisted,
            supersedes_decision_id=None if previous is None else previous.id,
            tool_version=tool_version,
            created_at=moment,
        )
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.SCREENING_HUMAN_DECIDED,
            subject_type="decision",
            subject_id=decision.id,
            summary_fr=french("Full-text screening: human decision recorded"),
            tool_version=tool_version,
            payload={
                "stage": STAGE.value,
                "reference": reference_id,
                "round": screening.kind.value,
                "value": value.value,
                "criteria_cited": list(decision.criteria_cited),
                "primary_reason": primary_reason(decision.criteria_cited, order)
                if value is DecisionValue.EXCLUDE
                else None,
                "blinded": not assisted,
                "context": context.value,
                "supersedes": decision.supersedes_decision_id,
            },
        )
        screening_repo.insert_decision(connection, decision, journal_entry_id=entry.id)
    return decision


# --- Pilot state --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FulltextPilotState:
    round: PilotRound
    human: dict[str, Decision]
    ai: dict[str, Decision]
    unreadable: list[str]  # scanned: the AI cannot screen them
    metrics: PilotMetrics | None

    @property
    def next_reference(self) -> str | None:
        return next((r for r in self.round.reference_ids if r not in self.human), None)

    @property
    def complete(self) -> bool:
        """Every text decided by the person, and by the AI when it can read it."""
        members = self.round.reference_ids
        return all(r in self.human for r in members) and all(
            r in self.ai or r in self.unreadable for r in members
        )

    def visible_ai(self, reference_id: str) -> Decision | None:
        """The AI's decision, only once the person has decided (EF-SEL-02)."""
        return self.ai.get(reference_id) if reference_id in self.human else None


def pilot_state(folder: ProjectFolder, round_id: str) -> FulltextPilotState:
    with folder.engine.connect() as connection:
        pilot = screening_repo.get_round(connection, round_id)
        if pilot is None or pilot.stage is not STAGE:
            raise UnknownRoundError
        human = screening_repo.latest_by_reference(connection, [round_id], reviewer_kind=HUMAN)
        ai = screening_repo.latest_by_reference(connection, [round_id], reviewer_kind=AI)
    documents = _documents(folder)
    unreadable = [r for r in pilot.reference_ids if r in documents and documents[r][1].needs_ocr]
    pairs = [(human[r].value, ai[r].value) for r in pilot.reference_ids if r in human and r in ai]
    return FulltextPilotState(
        round=pilot,
        human=human,
        ai=ai,
        unreadable=unreadable,
        metrics=pilot_metrics(pairs) if pairs else None,
    )


def pilot_complete(folder: ProjectFolder) -> bool:
    pilot = pilot_round(folder)
    return pilot is not None and pilot_state(folder, pilot.id).complete


# --- Main state ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FulltextState:
    round: ScreeningRound
    members: list[str]  # in screening order
    human: dict[str, Decision]  # blind or assisted decisions, the pilot's included
    ai: dict[str, Decision]
    reconciled: dict[str, Decision]
    final: dict[str, Decision]  # the latest human decision on each text
    unreadable: list[str]  # scanned: the AI cannot screen them
    order: list[str]  # codes of the criteria, for the primary reasons
    disagreements: list[str] = field(default_factory=list)
    queue: list[str] = field(default_factory=list)  # disagreements not reconciled

    @property
    def assisted(self) -> bool:
        return self.round.mode is ScreeningMode.ASSISTED

    def visible_ai(self, reference_id: str) -> Decision | None:
        """Assisted: the AI is shown before the person decides. Blind: only to
        reconcile a disagreement (D-102)."""
        if self.assisted or reference_id in self.disagreements:
            return self.ai.get(reference_id)
        return None

    def reason(self, reference_id: str) -> str | None:
        """Primary reason of the exclusion in force on a text, if excluded."""
        decision = self.final.get(reference_id)
        if decision is None or decision.value is not DecisionValue.EXCLUDE:
            return None
        return primary_reason(decision.criteria_cited, self.order)

    @property
    def followed_ai(self) -> tuple[int, int]:
        """Assisted decisions that keep or exclude as the AI did, and assisted decisions
        compared: ``(followed, compared)``."""
        compared = [
            (d, self.ai[r])
            for r, d in self.human.items()
            if d.context is DecisionContext.ASSISTED and r in self.ai
        ]
        return sum(1 for h, a in compared if not disagree(h.value, a.value)), len(compared)


def main_state(folder: ProjectFolder, round_id: str | None = None) -> FulltextState:
    main = main_round(folder) if round_id is None else _any_round(folder, round_id)
    if main is None or main.kind is not RoundKind.MAIN:
        raise UnknownRoundError
    rounds = _decided_in(folder, main)
    with folder.engine.connect() as connection:
        members = screening_repo.member_ids(connection, main.id)
        human = screening_repo.latest_by_reference(
            connection, rounds, reviewer_kind=HUMAN, contexts=["independent", "assisted"]
        )
        ai = screening_repo.latest_by_reference(connection, [main.id], reviewer_kind=AI)
        reconciled = screening_repo.latest_by_reference(
            connection, [main.id], reviewer_kind=HUMAN, contexts=["reconciliation"]
        )
        final = screening_repo.latest_by_reference(connection, rounds, reviewer_kind=HUMAN)
    documents = _documents(folder)
    blind = main.mode is ScreeningMode.BLIND
    disagreements = [
        r
        for r in members
        if blind and r in human and r in ai and disagree(human[r].value, ai[r].value)
    ]
    return FulltextState(
        round=main,
        members=members,
        human=human,
        ai=ai,
        reconciled=reconciled,
        final=final,
        unreadable=[r for r in members if r in documents and documents[r][1].needs_ocr],
        order=[c.code for c in _version(folder, main.criteria_version_id).criteria],
        disagreements=disagreements,
        queue=[r for r in disagreements if r not in reconciled],
    )


def next_text(state: FulltextState, *, skip: Sequence[str] = ()) -> str | None:
    """The next text for the person, in the drawn order; in assisted mode, only texts
    the AI has screened (or cannot read)."""
    for ref in state.members:
        if ref in state.human or ref in skip:
            continue
        if state.assisted and ref not in state.ai and ref not in state.unreadable:
            continue
        return ref
    return None


def reconcile(
    folder: ProjectFolder,
    reference_id: str,
    value: DecisionValue,
    *,
    criteria_cited: Sequence[str] = (),
    rationale: str = "",
    now: Clock,
    tool_version: str,
) -> Decision:
    """The final decision on a disagreement of the blind round, the AI's rationale and
    quotes in view."""
    state = main_state(folder)
    if state.assisted:
        raise NotBlindError
    if reference_id not in state.disagreements:
        raise NotADisagreementError
    unknown = sorted(set(criteria_cited) - set(state.order))
    if unknown:
        raise UnknownCriterionError(unknown)
    human, ai = state.human[reference_id], state.ai[reference_id]
    with folder.write() as connection:
        moment = now()
        decision = Decision(
            id=new_ulid(moment),
            reference_id=reference_id,
            stage=STAGE,
            round_id=state.round.id,
            reviewer_id=folder.reviewer_id,
            reviewer_kind=ReviewerKind.HUMAN,
            value=value,
            rationale=rationale.strip(),
            criteria_cited=tuple(sorted(set(criteria_cited), key=state.order.index)),
            criteria_version_id=state.round.criteria_version_id,
            context=DecisionContext.RECONCILIATION,
            supersedes_decision_id=human.id,
            tool_version=tool_version,
            created_at=moment,
        )
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.SCREENING_RECONCILED,
            subject_type="decision",
            subject_id=decision.id,
            summary_fr=french(
                "Full-text screening: disagreement reconciled (you: {human}, AI: {ai}, "
                "final: {final})"
            ).format(human=human.value.value, ai=ai.value.value, final=value.value),
            tool_version=tool_version,
            payload={
                "stage": STAGE.value,
                "reference": reference_id,
                "human_decision": human.id,
                "ai_decision": ai.id,
                "value": value.value,
                "criteria_cited": list(decision.criteria_cited),
            },
        )
        screening_repo.insert_decision(connection, decision, journal_entry_id=entry.id)
    return decision


def kept(state: FulltextState) -> list[str]:
    """Texts whose decision in force keeps them."""
    return [r for r in state.members if r in state.final and keeps(state.final[r].value)]
