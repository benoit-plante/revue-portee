"""AI suggestions for the PCC framing and their human review (EF-CAD-02).

The AI (task ``suggest_pcc``) proposes reformulations, secondary questions and PCC
wordings. Each suggestion is then accepted, modified or rejected explicitly; the choice
is recorded with the AI call that produced the suggestion, and an accepted or modified
suggestion creates a new framing version in the same transaction.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection

from revue_portee.ai.base import TaskResult
from revue_portee.ai.providers import ProviderFactory
from revue_portee.ai.tasks import SUGGEST_PCC, SuggestPccInput, SuggestPccOutput
from revue_portee.domain.ids import new_ulid
from revue_portee.domain.journal import EntryType
from revue_portee.domain.suggestions import (
    AISuggestion,
    SuggestionOutcome,
    SuggestionReview,
    apply_suggestion,
)
from revue_portee.i18n import french
from revue_portee.i18n import gettext as _
from revue_portee.protocol import ai_assist
from revue_portee.protocol.ai_assist import CostPreview, call_summary, default_provider_factory
from revue_portee.protocol.framing import save_framing_in
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import ai as ai_repo
from revue_portee.storage.repositories import framing as framing_repo
from revue_portee.storage.repositories import journal, projects
from revue_portee.storage.repositories.ai import StoredCall

__all__ = [
    "AlreadyReviewedError",
    "MissingTextError",
    "NoFramingError",
    "SuggestionView",
    "UnknownSuggestionError",
    "list_suggestions",
    "preview_suggestions",
    "request_suggestions",
    "review_suggestion",
]

Clock = Callable[[], datetime]


class NoFramingError(LookupError):
    def __init__(self) -> None:
        super().__init__(_("Save the main question before asking the AI for suggestions."))


class UnknownSuggestionError(LookupError):
    def __init__(self, suggestion_id: str) -> None:
        super().__init__(_("Unknown suggestion: {id}.").format(id=suggestion_id))


class AlreadyReviewedError(ValueError):
    def __init__(self) -> None:
        super().__init__(_("This suggestion has already been reviewed."))


class MissingTextError(ValueError):
    def __init__(self) -> None:
        super().__init__(_("A modified suggestion needs a text."))


@dataclass(frozen=True, slots=True)
class SuggestionView:
    suggestion: AISuggestion
    review: SuggestionReview | None
    model_returned: str


def _input(connection: Connection) -> SuggestPccInput:
    current = framing_repo.latest_framing_version(connection)
    if current is None:
        raise NoFramingError
    framing = current.framing
    return SuggestPccInput(
        item_id=current.id,
        language=projects.get_project(connection).language,
        question=framing.question,
        population=framing.population,
        concept=framing.concept,
        context=framing.context,
        secondary_questions=framing.secondary_questions,
    )


def preview_suggestions(
    folder: ProjectFolder, *, factory: ProviderFactory = default_provider_factory
) -> CostPreview:
    """Estimated cost of asking for suggestions on the current framing."""
    with folder.engine.connect() as connection:
        item = _input(connection)
    return ai_assist.preview(folder, SUGGEST_PCC, [item], factory=factory)


def request_suggestions(
    folder: ProjectFolder,
    *,
    now: Clock,
    tool_version: str,
    factory: ProviderFactory = default_provider_factory,
) -> list[AISuggestion]:
    """Ask the AI for suggestions on the current framing and record them."""
    with folder.engine.connect() as connection:
        item = _input(connection)
    received: list[AISuggestion] = []

    def store(
        connection: Connection, stored: StoredCall, result: TaskResult[SuggestPccOutput]
    ) -> None:
        moment = now()
        suggestions = [
            AISuggestion(
                id=new_ulid(moment),
                ai_call_id=stored.id,
                position=position,
                kind=suggestion.kind,
                text=suggestion.text.strip(),
                rationale=suggestion.rationale.strip(),
                created_at=moment,
            )
            for position, suggestion in enumerate(result.output.suggestions)
        ]
        ai_repo.insert_suggestions(connection, suggestions)
        journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.FRAMING_SUGGESTIONS_RECEIVED,
            subject_type="ai_call",
            subject_id=stored.id,
            summary_fr=french("{count} AI suggestions received for the framing").format(
                count=len(suggestions)
            ),
            tool_version=tool_version,
            payload=call_summary(stored)
            | {
                "framing_version_id": item.item_id,
                "suggestions": [
                    {"id": s.id, "kind": s.kind.value, "text": s.text, "rationale": s.rationale}
                    for s in suggestions
                ],
            },
        )
        received.extend(suggestions)

    ai_assist.run_and_record(
        folder,
        SUGGEST_PCC,
        [item],
        on_result=store,
        now=now,
        tool_version=tool_version,
        factory=factory,
    )
    return received


def list_suggestions(folder: ProjectFolder) -> list[SuggestionView]:
    """Every suggestion received, oldest first, with its review if any."""
    with folder.engine.connect() as connection:
        suggestions = ai_repo.list_suggestions(connection)
        reviews = ai_repo.list_reviews(connection)
        models = {
            call.id: call.record.model_returned
            for call in ai_repo.list_calls(connection, task=SUGGEST_PCC.name)
        }
    return [
        SuggestionView(
            suggestion=s, review=reviews.get(s.id), model_returned=models.get(s.ai_call_id, "")
        )
        for s in suggestions
    ]


def review_suggestion(
    folder: ProjectFolder,
    suggestion_id: str,
    outcome: SuggestionOutcome,
    *,
    text: str = "",
    now: Clock,
    tool_version: str,
) -> SuggestionReview:
    """Record the human decision on a suggestion and apply it to the framing.

    A "modified" suggestion whose text is unchanged is recorded as accepted.
    """
    with folder.write() as connection:
        suggestion = ai_repo.get_suggestion(connection, suggestion_id)
        if suggestion is None:
            raise UnknownSuggestionError(suggestion_id)
        if suggestion_id in ai_repo.list_reviews(connection):
            raise AlreadyReviewedError
        final_text = ""
        if outcome is SuggestionOutcome.ACCEPTED:
            final_text = suggestion.text
        elif outcome is SuggestionOutcome.MODIFIED:
            final_text = text.strip()
            if not final_text:
                raise MissingTextError
            if final_text == suggestion.text:
                outcome = SuggestionOutcome.ACCEPTED
        moment = now()
        framing_version_id = None
        if outcome is not SuggestionOutcome.REJECTED:
            current = framing_repo.latest_framing_version(connection)
            if current is None:
                raise NoFramingError
            version = save_framing_in(
                connection,
                folder,
                apply_suggestion(current.framing, suggestion.kind, final_text),
                moment=moment,
                tool_version=tool_version,
                payload={"suggestion_id": suggestion.id},
            )
            framing_version_id = version.id
        review = SuggestionReview(
            id=new_ulid(moment),
            suggestion_id=suggestion.id,
            outcome=outcome,
            final_text=final_text,
            reviewer_id=folder.reviewer_id,
            created_at=moment,
            framing_version_id=framing_version_id,
        )
        summaries = {
            SuggestionOutcome.ACCEPTED: french("AI suggestion accepted"),
            SuggestionOutcome.MODIFIED: french("AI suggestion modified then accepted"),
            SuggestionOutcome.REJECTED: french("AI suggestion rejected"),
        }
        entry = journal.append_entry(
            connection,
            now=moment,
            actor_reviewer_id=folder.reviewer_id,
            entry_type=EntryType.FRAMING_SUGGESTION_REVIEWED,
            subject_type="ai_suggestion",
            subject_id=suggestion.id,
            summary_fr=summaries[outcome],
            tool_version=tool_version,
            payload={
                "ai_call_id": suggestion.ai_call_id,
                "kind": suggestion.kind.value,
                "outcome": outcome.value,
                "proposed_text": suggestion.text,
                "final_text": final_text,
                "framing_version_id": framing_version_id,
            },
        )
        ai_repo.insert_review(connection, review, journal_entry_id=entry.id)
        return review
