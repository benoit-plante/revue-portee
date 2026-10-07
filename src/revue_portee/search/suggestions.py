"""AI suggestions of search terms and their human review (EF-REC-02).

The AI (task ``suggest_terms``) proposes free-text terms and descriptors for each block
of the current strategy. Each suggestion is then accepted, modified or rejected; an
accepted or modified suggestion adds the term to its block, which creates a new strategy
version in the same transaction. MeSH headings, suggested or not, are checked with the
E-utilities by ``search.runs.check_descriptors``.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection

from revue_portee.ai.base import TaskResult
from revue_portee.ai.providers import ProviderFactory
from revue_portee.ai.tasks import (
    SUGGEST_TERMS,
    BlockSnapshot,
    SuggestTermsInput,
    SuggestTermsOutput,
)
from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.domain.search import (
    StrategyVersion,
    TermSuggestion,
    TermSuggestionReview,
    TermSyntaxError,
    format_term,
    parse_term,
)
from revue_portee.domain.suggestions import SuggestionOutcome
from revue_portee.i18n import french
from revue_portee.i18n import gettext as _
from revue_portee.protocol import ai_assist
from revue_portee.protocol.ai_assist import CostPreview, call_summary, default_provider_factory
from revue_portee.search.strategies import save_strategy_in
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import ai as ai_repo
from revue_portee.storage.repositories import framing as framing_repo
from revue_portee.storage.repositories import journal, projects
from revue_portee.storage.repositories import search as search_repo
from revue_portee.storage.repositories.ai import StoredCall

__all__ = [
    "AlreadyReviewedError",
    "BlockGoneError",
    "InvalidTermError",
    "NoStrategyError",
    "TermSuggestionView",
    "UnknownSuggestionError",
    "list_term_suggestions",
    "preview_term_suggestions",
    "request_term_suggestions",
    "review_term_suggestion",
]

Clock = Callable[[], datetime]


class NoStrategyError(LookupError):
    def __init__(self) -> None:
        super().__init__(_("Save at least one concept block before asking the AI for terms."))


class UnknownSuggestionError(LookupError):
    def __init__(self, suggestion_id: str) -> None:
        super().__init__(_("Unknown suggestion: {id}.").format(id=suggestion_id))


class AlreadyReviewedError(ValueError):
    def __init__(self) -> None:
        super().__init__(_("This suggestion has already been reviewed."))


class BlockGoneError(LookupError):
    def __init__(self, code: str) -> None:
        super().__init__(_("Block {code} no longer exists in the strategy.").format(code=code))


class InvalidTermError(ValueError):
    def __init__(self, detail: str) -> None:
        super().__init__(_("Invalid term: {detail}").format(detail=detail))


@dataclass(frozen=True, slots=True)
class TermSuggestionView:
    suggestion: TermSuggestion
    review: TermSuggestionReview | None
    model_returned: str


def _input(connection: Connection) -> tuple[StrategyVersion, SuggestTermsInput]:
    version = search_repo.latest_strategy_version(connection)
    if version is None or not version.strategy.blocks:
        raise NoStrategyError
    framing = framing_repo.latest_framing_version(connection)
    blocks = tuple(
        BlockSnapshot(
            item_id=block.code,
            code=block.code,
            label=block.label,
            pcc_element="" if block.pcc_element is None else block.pcc_element.value,
            role=block.role.value,
            terms=tuple(format_term(t) for t in block.terms),
        )
        for block in version.strategy.blocks
    )
    return version, SuggestTermsInput(
        item_id=version.id,
        language=projects.get_project(connection).language,
        question="" if framing is None else framing.framing.question,
        population="" if framing is None else framing.framing.population,
        concept="" if framing is None else framing.framing.concept,
        context="" if framing is None else framing.framing.context,
        blocks=blocks,
    )


def preview_term_suggestions(
    folder: ProjectFolder, *, factory: ProviderFactory = default_provider_factory
) -> CostPreview:
    with folder.engine.connect() as connection:
        _version, item = _input(connection)
    return ai_assist.preview(folder, SUGGEST_TERMS, [item], factory=factory)


def request_term_suggestions(
    folder: ProjectFolder,
    *,
    now: Clock,
    tool_version: str,
    factory: ProviderFactory = default_provider_factory,
) -> list[TermSuggestion]:
    """Ask the AI for terms for the blocks of the current strategy and record them.

    Proposals for an unknown block, in an invalid syntax or already in their block are
    left out; their number is recorded in the journal."""
    with folder.engine.connect() as connection:
        version, item = _input(connection)
    received: list[TermSuggestion] = []

    def store(
        connection: Connection, stored: StoredCall, result: TaskResult[SuggestTermsOutput]
    ) -> None:
        moment = now()
        existing = {
            b.code: {format_term(t).casefold() for t in b.terms} for b in version.strategy.blocks
        }
        suggestions: list[TermSuggestion] = []
        left_out = 0
        for proposal in result.output.suggestions:
            try:
                line = format_term(parse_term(proposal.line))
            except (TermSyntaxError, ValueError):
                left_out += 1
                continue
            known = existing.get(proposal.block_code)
            if known is None or line.casefold() in known:
                left_out += 1
                continue
            known.add(line.casefold())
            suggestions.append(
                TermSuggestion(
                    id=new_ulid(moment),
                    ai_call_id=stored.id,
                    strategy_version_id=version.id,
                    position=len(suggestions),
                    block_code=proposal.block_code,
                    kind=proposal.kind,
                    line=line,
                    rationale=proposal.rationale.strip(),
                    created_at=moment,
                )
            )
        search_repo.insert_term_suggestions(connection, suggestions)
        journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.SEARCH_TERMS_SUGGESTED,
            subject_type="ai_call",
            subject_id=stored.id,
            summary_fr=french("{count} AI term suggestions received").format(
                count=len(suggestions)
            ),
            tool_version=tool_version,
            payload=call_summary(stored)
            | {
                "strategy_version_id": version.id,
                "left_out": left_out,
                "suggestions": [
                    {
                        "id": s.id,
                        "block": s.block_code,
                        "kind": s.kind.value,
                        "line": s.line,
                        "rationale": s.rationale,
                    }
                    for s in suggestions
                ],
            },
        )
        received.extend(suggestions)

    ai_assist.run_and_record(
        folder,
        SUGGEST_TERMS,
        [item],
        on_result=store,
        now=now,
        tool_version=tool_version,
        factory=factory,
    )
    return received


def list_term_suggestions(folder: ProjectFolder) -> list[TermSuggestionView]:
    with folder.engine.connect() as connection:
        suggestions = search_repo.list_term_suggestions(connection)
        reviews = search_repo.list_term_reviews(connection)
        models = {
            call.id: call.record.model_returned or ""
            for call in ai_repo.list_calls(connection, task=SUGGEST_TERMS.name)
        }
    return [
        TermSuggestionView(
            suggestion=s, review=reviews.get(s.id), model_returned=models.get(s.ai_call_id, "")
        )
        for s in suggestions
    ]


def review_term_suggestion(
    folder: ProjectFolder,
    suggestion_id: str,
    outcome: SuggestionOutcome,
    *,
    line: str = "",
    now: Clock,
    tool_version: str,
) -> TermSuggestionReview:
    """Record the human decision and, unless rejected, add the term to its block.

    A "modified" suggestion whose line is unchanged is recorded as accepted."""
    with folder.write() as connection:
        suggestion = search_repo.get_term_suggestion(connection, suggestion_id)
        if suggestion is None:
            raise UnknownSuggestionError(suggestion_id)
        if suggestion_id in search_repo.list_term_reviews(connection):
            raise AlreadyReviewedError
        final_line = ""
        if outcome is SuggestionOutcome.ACCEPTED:
            final_line = suggestion.line
        elif outcome is SuggestionOutcome.MODIFIED:
            try:
                final_line = format_term(parse_term(line))
            except (TermSyntaxError, ValueError) as error:
                raise InvalidTermError(str(error)) from error
            if final_line == suggestion.line:
                outcome = SuggestionOutcome.ACCEPTED
        moment = now()
        created_version_id = None
        if outcome is not SuggestionOutcome.REJECTED:
            current = search_repo.latest_strategy_version(connection)
            block = None if current is None else current.strategy.block(suggestion.block_code)
            if current is None or block is None:
                raise BlockGoneError(suggestion.block_code)
            term = parse_term(final_line)
            if term not in block.terms:
                updated = block.model_copy(update={"terms": (*block.terms, term)})
                strategy = current.strategy.model_copy(
                    update={
                        "blocks": tuple(
                            updated if b.code == block.code else b for b in current.strategy.blocks
                        )
                    }
                )
                version = save_strategy_in(
                    connection,
                    folder,
                    strategy,
                    rationale=french("AI term suggestion accepted"),
                    moment=moment,
                    tool_version=tool_version,
                    payload={"suggestion_id": suggestion.id},
                )
                created_version_id = version.id
        review = TermSuggestionReview(
            id=new_ulid(moment),
            suggestion_id=suggestion.id,
            outcome=outcome,
            final_line=final_line,
            reviewer_id=folder.reviewer_id,
            created_at=moment,
            strategy_version_id=created_version_id,
        )
        summaries = {
            SuggestionOutcome.ACCEPTED: french("AI term suggestion accepted"),
            SuggestionOutcome.MODIFIED: french("AI term suggestion modified then accepted"),
            SuggestionOutcome.REJECTED: french("AI term suggestion rejected"),
        }
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.SEARCH_TERM_SUGGESTION_REVIEWED,
            subject_type="term_suggestion",
            subject_id=suggestion.id,
            summary_fr=summaries[outcome],
            tool_version=tool_version,
            payload={
                "ai_call_id": suggestion.ai_call_id,
                "block": suggestion.block_code,
                "kind": suggestion.kind.value,
                "outcome": outcome.value,
                "proposed_line": suggestion.line,
                "final_line": final_line,
                "strategy_version_id": created_version_id,
            },
        )
        search_repo.insert_term_review(connection, review, journal_entry_id=entry.id)
        return review
