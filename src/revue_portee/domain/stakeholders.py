"""Consultation of stakeholders and follow-up of their comments (EF-CON-02, EF-CON-03,
tranche 4.2), after Pollock et al. (2022): who commented, when, on what, and what was
done with each comment.

A stakeholder is recorded with a name, a role and an organisation, and nothing else
(EF-CON-03): no email, no telephone, no address. A pseudonym may stand for the name.
Comments and responses are never changed: a new response supersedes the previous one,
and the latest is in force.
"""

import datetime as dt
from collections import Counter
from collections.abc import Iterable
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

__all__ = [
    "STAKEHOLDER_FIELDS",
    "Comment",
    "CommentResponse",
    "CommentTarget",
    "ConsultationCounts",
    "ResponseAction",
    "Stakeholder",
    "consultation_counts",
    "responses_in_force",
    "stakeholder_codes",
]

# The only facts kept about a stakeholder (EF-CON-03), besides the record's own id,
# date and author.
STAKEHOLDER_FIELDS = ("name", "role", "organisation")


class Stakeholder(BaseModel):
    """A person consulted (table ``stakeholder``): name, role, organisation only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str = Field(min_length=1)  # or a pseudonym
    role: str = Field(min_length=1)  # patient partner, clinician, manager…
    organisation: str = ""
    created_at: AwareDatetime
    reviewer_id: str  # the reviewer who recorded the stakeholder


class CommentTarget(StrEnum):
    PROTOCOL = "protocol"
    CRITERIA = "criteria"
    SEARCH = "search"
    GRID = "grid"
    RESULTS = "results"
    NARRATIVE = "narrative"
    LAY_SUMMARY = "lay_summary"
    OTHER = "other"


class Comment(BaseModel):
    """A comment of a stakeholder (table ``stakeholder_comment``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    stakeholder_id: str
    target: CommentTarget
    target_detail: str = ""  # « D3 », « criteria version 2 »…
    text: str = Field(min_length=1)
    received_on: dt.date
    created_at: AwareDatetime
    reviewer_id: str


class ResponseAction(StrEnum):
    CHANGED = "changed"  # the review was changed
    NOTED = "noted"  # taken into account without a change
    DECLINED = "declined"  # not followed, with a reason
    DEFERRED = "deferred"  # left for later (another stage, another review)


class CommentResponse(BaseModel):
    """What was done with a comment (table ``comment_response``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    comment_id: str
    action: ResponseAction
    text: str = Field(min_length=1)  # what was changed, or why not
    supersedes_id: str | None = None
    created_at: AwareDatetime
    reviewer_id: str


def responses_in_force(responses: Iterable[CommentResponse]) -> dict[str, CommentResponse]:
    """The latest response to each comment."""
    found: dict[str, CommentResponse] = {}
    for response in sorted(responses, key=lambda r: (r.created_at, r.id)):
        found[response.comment_id] = response
    return found


def stakeholder_codes(stakeholders: Iterable[Stakeholder]) -> dict[str, str]:
    """A code for each stakeholder, in the order they were recorded (PP1, PP2…): what
    the public archive shows instead of the name."""
    ordered = sorted(stakeholders, key=lambda s: (s.created_at, s.id))
    return {s.id: f"PP{number}" for number, s in enumerate(ordered, start=1)}


class ConsultationCounts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    stakeholders: int
    comments: int
    answered: int
    by_target: dict[CommentTarget, int]
    by_action: dict[ResponseAction, int]
    by_role: dict[str, int]  # comments by role of their author

    @property
    def pending(self) -> int:
        return self.comments - self.answered


def consultation_counts(
    stakeholders: Iterable[Stakeholder],
    comments: Iterable[Comment],
    responses: Iterable[CommentResponse],
) -> ConsultationCounts:
    """How many stakeholders and comments, by target, by response in force and by role."""
    people = {s.id: s for s in stakeholders}
    found = list(comments)
    in_force = responses_in_force(responses)
    answered = [in_force[c.id] for c in found if c.id in in_force]
    return ConsultationCounts(
        stakeholders=len(people),
        comments=len(found),
        answered=len(answered),
        by_target=dict(Counter(c.target for c in found)),
        by_action=dict(Counter(r.action for r in answered)),
        by_role=dict(
            Counter(people[c.stakeholder_id].role for c in found if c.stakeholder_id in people)
        ),
    )
