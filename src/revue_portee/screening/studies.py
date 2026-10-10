"""Reports of a same study (EF-SEL-17, tranche 2.3).

Among the reports included at the full text, rules propose the pairs that may report
one study (``dedup.reports``: same trial registration number, shared authors and words,
close titles). The AI examines each pair in the two texts and names what they share,
with a quote and its page in each report, which the tool looks for; a person decides,
pair by pair (D-061 for the same principle at deduplication). The person may also join
two reports the rules did not propose. A study is a group of reports joined by the
« same study » decisions in force; its primary report is the one the person chose,
otherwise the oldest.

Each call is recorded in its own transaction with its raw response (D-041); the cost
is shown before, and the project and batch ceilings are checked before each call.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from revue_portee.ai.base import ProviderCallError
from revue_portee.ai.providers import ProviderFactory
from revue_portee.ai.runner import run_task
from revue_portee.ai.tasks.fulltext import PageOfText
from revue_portee.ai.tasks.studies import (
    GROUP_REPORTS,
    GroupReportsInput,
    GroupReportsOutput,
    ReportExcerpt,
)
from revue_portee.dedup.reports import (
    ReportCandidate,
    ReportLinkSettings,
    candidate_pairs,
    features,
    group_reports,
)
from revue_portee.domain.fulltext import FulltextDocument, PagedText, QuoteCheck, check_quote
from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.domain.project import ReplicationMode
from revue_portee.domain.references import Reference
from revue_portee.domain.screening import DecisionContext, DecisionValue, keeps
from revue_portee.domain.studies import (
    LinkEvidence,
    LinkOutcome,
    LinkVerdict,
    PrimaryChoice,
    StudyLinkAssessment,
    StudyLinkDecision,
    latest_by_pair,
    linked_pairs,
    primary_report,
    same_pair,
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
from revue_portee.screening.ai_screening import (
    MAX_ATTEMPTS,
    AIBatchResult,
    UnusableAnswerError,
    ai_reviewer,
)
from revue_portee.screening.settings import BudgetNotSetError
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import journal, projects
from revue_portee.storage.repositories import screening as screening_repo
from revue_portee.storage.repositories import studies as studies_repo
from revue_portee.storage.repositories.ai import StoredCall

__all__ = [
    "EXCERPT_CHARS",
    "NotIncludedError",
    "Study",
    "StudyState",
    "choose_primary",
    "decide",
    "included_reports",
    "preview_ai",
    "run_ai",
    "study_state",
]

Clock = Callable[[], datetime]
EXCERPT_CHARS = 12_000  # characters of each text the model sees (its first pages)


class NotIncludedError(ValueError):
    def __init__(self) -> None:
        super().__init__(_("Only reports included at the full text can be grouped into studies."))


# --- Reports ------------------------------------------------------------------------


def included_reports(folder: ProjectFolder) -> dict[str, tuple[Reference, FulltextDocument]]:
    """Reports whose decision in force at the full text is « include », with their text.

    In a replication project (D-104), the AI's decision is final and a text it keeps
    (« uncertain » too) goes on, as do the texts it could not screen (unusable answers,
    scanned texts): they are kept, as a person would keep them. Replayed stepwise, each
    step gets the published inputs: every included study of the published review whose
    text is obtained, whatever the AI decided at the full text."""
    # Imported here: the full-text use cases import the reports, which import this module.
    from revue_portee.screening import batch_ai, fulltext

    marker = folder.replication
    if marker is not None and marker.mode is ReplicationMode.STEPWISE:
        return {
            row.reference.id: (row.reference, row.document)
            for row in retrieval.retrieval_report(folder).rows
            if row.document is not None
        }
    if fulltext.main_round(folder) is None:
        return {}
    state = fulltext.main_state(folder)
    kept_by_rule: set[str] = set()
    if folder.replication is not None:
        kept_by_rule = set(batch_ai.exhausted(folder, state.round.id)) | set(state.unreadable)

    def included(ref: str) -> bool:
        decision = state.final.get(ref)
        if decision is None:
            return ref in kept_by_rule
        if decision.context is DecisionContext.REPLICATION:
            return keeps(decision.value)
        return decision.value is DecisionValue.INCLUDE

    rows = {r.reference.id: r for r in retrieval.retrieval_report(folder).rows}
    return {
        ref: (rows[ref].reference, document)
        for ref in state.members
        if included(ref) and ref in rows and (document := rows[ref].document) is not None
    }


def _text(folder: ProjectFolder, document: FulltextDocument) -> PagedText | None:
    return None if document.needs_ocr else retrieval.paged_text(folder, document)


def _excerpt(
    reference: Reference, text: PagedText | None, registrations: Iterable[str]
) -> ReportExcerpt:
    pages: list[PageOfText] = []
    used = 0
    for page in () if text is None else text.body():
        if not page.text.strip() or used >= EXCERPT_CHARS:
            continue
        part = page.text[: EXCERPT_CHARS - used]
        used += len(part)
        pages.append(PageOfText(number=page.number, text=part))
    return ReportExcerpt(
        title=reference.title,
        authors=reference.authors[:12],
        year=reference.year,
        container_title=reference.container_title,
        registrations=tuple(sorted(registrations)),
        pages=tuple(pages),
    )


# --- State --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Study:
    primary: str
    reports: list[str]  # sorted, the primary among them


@dataclass(frozen=True, slots=True)
class StudyState:
    reports: list[str]  # included reports, sorted
    candidates: list[ReportCandidate]
    assessments: dict[tuple[str, str], StudyLinkAssessment]  # the latest on each pair
    decisions: dict[tuple[str, str], StudyLinkDecision]  # the latest on each pair
    studies: list[Study] = field(default_factory=list)

    @property
    def pending(self) -> list[ReportCandidate]:
        """Proposed pairs the person has not decided yet."""
        return [
            c
            for c in self.candidates
            if same_pair(c.reference_a_id, c.reference_b_id) not in self.decisions
        ]

    @property
    def without_ai(self) -> list[ReportCandidate]:
        """Proposed pairs the AI has not examined yet."""
        return [
            c
            for c in self.candidates
            if same_pair(c.reference_a_id, c.reference_b_id) not in self.assessments
        ]

    def study_of(self, reference_id: str) -> Study | None:
        return next((s for s in self.studies if reference_id in s.reports), None)


def study_state(folder: ProjectFolder, settings: ReportLinkSettings | None = None) -> StudyState:
    reports = included_reports(folder)
    texts = {ref: _text(folder, doc) for ref, (_r, doc) in reports.items()}
    reported = [
        features(reference, "" if texts[ref] is None else _whole(texts[ref]))
        for ref, (reference, _doc) in sorted(reports.items())
    ]
    with folder.engine.connect() as connection:
        assessments = latest_by_pair(studies_repo.list_assessments(connection))
        decisions_all = studies_repo.list_decisions(connection)
        choices = studies_repo.list_choices(connection)
    included = set(reports)
    decisions = {
        pair: d
        for pair, d in latest_by_pair(decisions_all).items()
        if pair[0] in included and pair[1] in included
    }
    years = {ref: reference.year for ref, (reference, _doc) in reports.items()}
    groups = group_reports(sorted(included), linked_pairs(decisions.values()))
    return StudyState(
        reports=sorted(included),
        candidates=candidate_pairs(reported, settings),
        assessments=assessments,
        decisions=decisions,
        studies=[Study(primary=primary_report(g, years, choices), reports=g) for g in groups],
    )


def _whole(text: PagedText | None) -> str:
    return "" if text is None else "\n".join(page.text for page in text.body())


# --- The AI -------------------------------------------------------------------------


def _inputs(
    folder: ProjectFolder, candidates: Sequence[ReportCandidate]
) -> list[GroupReportsInput]:
    reports = included_reports(folder)
    with folder.engine.connect() as connection:
        language = projects.get_project(connection).language
    found = []
    for c in candidates:
        a, b = reports[c.reference_a_id], reports[c.reference_b_id]
        text_a, text_b = _text(folder, a[1]), _text(folder, b[1])
        found.append(
            GroupReportsInput(
                item_id=f"{c.reference_a_id}-{c.reference_b_id}",
                language=language,
                report_a=_excerpt(a[0], text_a, features(a[0], _whole(text_a)).registrations),
                report_b=_excerpt(b[0], text_b, features(b[0], _whole(text_b)).registrations),
            )
        )
    return found


def preview_ai(
    folder: ProjectFolder,
    *,
    factory: ProviderFactory = default_provider_factory,
    settings: ReportLinkSettings | None = None,
) -> CostPreview:
    """Cost of the AI on the proposed pairs it has not examined yet."""
    pairs = study_state(folder, settings).without_ai
    return preview(folder, GROUP_REPORTS, _inputs(folder, pairs), factory=factory)


def _store(
    folder: ProjectFolder,
    candidate: ReportCandidate,
    stored: StoredCall,
    output: GroupReportsOutput,
    *,
    now: Clock,
    tool_version: str,
) -> StudyLinkAssessment:
    reports = included_reports(folder)
    texts = [_text(folder, reports[ref][1]) for ref in (candidate.reference_a_id,
                                                         candidate.reference_b_id)]  # fmt: skip

    def check(text: PagedText | None, quote: str, page: int | None) -> QuoteCheck | None:
        return None if text is None or not quote else check_quote(text.body(), quote, page)

    evidence = tuple(
        LinkEvidence(
            aspect=e.aspect,
            quote_a=e.quote_a,
            page_a=e.page_a,
            check_a=check(texts[0], e.quote_a, e.page_a),
            quote_b=e.quote_b,
            page_b=e.page_b,
            check_b=check(texts[1], e.quote_b, e.page_b),
        )
        for e in output.evidence
    )
    reviewer_id = ai_reviewer(folder, stored, now=now, tool_version=tool_version)
    with folder.write() as connection:
        moment = now()
        assessment = StudyLinkAssessment(
            id=new_ulid(moment),
            reference_a_id=candidate.reference_a_id,
            reference_b_id=candidate.reference_b_id,
            rule=candidate.rule,
            verdict=LinkVerdict(output.verdict),
            rationale=output.rationale,
            evidence=evidence,
            ai_call_id=stored.id,
            created_at=moment,
            reviewer_id=reviewer_id,
        )
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.STUDY_LINK_ASSESSED,
            subject_type="study_link_assessment",
            subject_id=assessment.id,
            summary_fr=french(
                "Reports of a same study: pair examined by the AI ({verdict})"
            ).format(verdict=output.verdict),
            tool_version=tool_version,
            payload=call_summary(stored)
            | {
                "reference_a": candidate.reference_a_id,
                "reference_b": candidate.reference_b_id,
                "rule": candidate.rule,
                "verdict": output.verdict,
            },
        )
        studies_repo.insert_assessment(connection, assessment, journal_entry_id=entry.id)
    return assessment


def run_ai(
    folder: ProjectFolder,
    *,
    batch_limit: Decimal,
    factory: ProviderFactory = default_provider_factory,
    settings: ReportLinkSettings | None = None,
    now: Clock,
    tool_version: str,
) -> AIBatchResult:
    """The AI examines the proposed pairs it has not examined yet, one call at a time,
    the project ceiling and ``batch_limit`` checked before each call (ENF-COU-02)."""
    with folder.engine.connect() as connection:
        budget = screening_repo.latest_budget(connection)
    if budget is None:
        raise BudgetNotSetError
    provider = factory(folder.ai_settings().enabled_task(GROUP_REPORTS.name))
    candidates = study_state(folder, settings).without_ai
    by_item = {f"{c.reference_a_id}-{c.reference_b_id}": c for c in candidates}
    screened, failed, stopped = 0, [], ""
    spent = Decimal(0)
    for item in _inputs(folder, candidates):
        estimate = provider.estimate_cost(GROUP_REPORTS, [item]).amount
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
                (result,) = run_task(provider, GROUP_REPORTS, [item])
            except ProviderCallError as error:
                stored = record_call(
                    folder, task=GROUP_REPORTS.name, item_id=error.item_id, call=error.call,
                    raw_response=error.raw_response, now=now, tool_version=tool_version,
                )  # fmt: skip
                spent += stored.record.cost_estimate
                continue
            stored = record_call(
                folder, task=GROUP_REPORTS.name, item_id=result.item_id, call=result.call,
                raw_response=result.raw_response, now=now, tool_version=tool_version,
            )  # fmt: skip
            spent += stored.record.cost_estimate
            if not result.output.evidence:  # pragma: no cover - the schema requires one
                record_unusable(
                    folder, stored, UnusableAnswerError("no evidence"), now=now,
                    tool_version=tool_version,
                )  # fmt: skip
                continue
            _store(folder, by_item[item.item_id], stored, result.output, now=now,
                   tool_version=tool_version)  # fmt: skip
            done = True
            break
        if done:
            screened += 1
        elif stopped:
            break
        else:
            failed.append(item.item_id)
    return AIBatchResult(screened=screened, failed=failed, stopped=stopped, spent=spent)


# --- The person ---------------------------------------------------------------------


def decide(
    folder: ProjectFolder,
    reference_a_id: str,
    reference_b_id: str,
    outcome: LinkOutcome,
    *,
    note: str = "",
    reviewer_id: str | None = None,
    now: Clock,
    tool_version: str,
) -> StudyLinkDecision:
    """The person's decision on two included reports: one study, or two; any two
    included reports may be joined, proposed by the rules or not. A new decision on a
    pair supersedes the previous one. ``reviewer_id`` names another reviewer than the
    person: the AI, whose verdict is final in a replication project (D-104)."""
    included = included_reports(folder)
    if reference_a_id == reference_b_id or not {reference_a_id, reference_b_id} <= set(included):
        raise NotIncludedError
    first, second = same_pair(reference_a_id, reference_b_id)
    with folder.write() as connection:
        moment = now()
        decision = StudyLinkDecision(
            id=new_ulid(moment),
            reference_a_id=first,
            reference_b_id=second,
            outcome=outcome,
            note=note.strip(),
            created_at=moment,
            reviewer_id=reviewer_id or folder.reviewer_id,
        )
        if outcome is LinkOutcome.SAME:
            summary = french("Reports of a same study: two reports joined")
        else:
            summary = french("Reports of a same study: two reports kept apart")
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.STUDY_LINK_DECIDED,
            subject_type="study_link_decision",
            subject_id=decision.id,
            summary_fr=summary,
            tool_version=tool_version,
            payload={
                "reference_a": first,
                "reference_b": second,
                "outcome": outcome.value,
                "note": decision.note,
            },
        )
        studies_repo.insert_decision(connection, decision, journal_entry_id=entry.id)
    return decision


def choose_primary(
    folder: ProjectFolder, reference_id: str, *, now: Clock, tool_version: str
) -> PrimaryChoice:
    """Make an included report the primary report of its study."""
    if reference_id not in included_reports(folder):
        raise NotIncludedError
    with folder.write() as connection:
        moment = now()
        choice = PrimaryChoice(
            id=new_ulid(moment),
            reference_id=reference_id,
            created_at=moment,
            reviewer_id=folder.reviewer_id,
        )
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.STUDY_PRIMARY_CHOSEN,
            subject_type="reference",
            subject_id=reference_id,
            summary_fr=french("Reports of a same study: primary report chosen"),
            tool_version=tool_version,
            payload={"reference": reference_id},
        )
        studies_repo.insert_choice(connection, choice, journal_entry_id=entry.id)
    return choice
