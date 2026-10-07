"""Protocol models (DOI, free text, checklists) and framing suggestions."""

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from revue_portee.domain.framing import Framing
from revue_portee.domain.protocol import (
    Checklist,
    ChecklistItem,
    OsfForm,
    OsfItem,
    ProtocolRegistration,
    ProtocolSection,
    ProtocolText,
    normalize_doi,
)
from revue_portee.domain.suggestions import (
    SuggestionKind,
    SuggestionOutcome,
    SuggestionReview,
    apply_suggestion,
)

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "value",
    [
        "10.17605/OSF.IO/ABCDE",
        "10.17605/osf.io/abcde",
        " https://doi.org/10.17605/OSF.IO/ABCDE ",
        "http://doi.org/10.17605/osf.io/abcde",
        "https://dx.doi.org/10.17605/OSF.IO/ABCDE",
        "doi:10.17605/OSF.IO/ABCDE",
    ],
)
def test_doi_is_normalized(value: str) -> None:
    assert normalize_doi(value) == "10.17605/OSF.IO/ABCDE"


@pytest.mark.parametrize("value", ["", "osf.io/abcde", "10.1/x", "10.17605/", "11.1234/x"])
def test_invalid_doi(value: str) -> None:
    with pytest.raises(ValueError, match="not a DOI"):
        normalize_doi(value)


def test_registration_normalizes_its_doi() -> None:
    registration = ProtocolRegistration(
        id="r",
        doi="https://doi.org/10.17605/osf.io/abcde",
        registered_on=date(2026, 10, 1),
        criteria_version_id=None,
        created_at=NOW,
        reviewer_id="h",
    )
    assert registration.doi == "10.17605/OSF.IO/ABCDE"


def test_protocol_text_keeps_free_text_sections_only() -> None:
    text = ProtocolText(
        sections={ProtocolSection.FUNDING: "  Aucun.  ", ProtocolSection.BACKGROUND: "   "}
    )
    assert text.sections == {ProtocolSection.FUNDING: "Aucun."}
    assert text.text(ProtocolSection.BACKGROUND) == ""
    with pytest.raises(ValidationError, match="not free-text sections"):
        ProtocolText(sections={ProtocolSection.TITLE: "Titre"})


def test_checklist_ids_are_unique() -> None:
    item = ChecklistItem(id="A", section=ProtocolSection.TITLE, en="Title", fr="Titre")
    assert item.label("fr") == "Titre"
    assert item.label("en") == "Title"
    with pytest.raises(ValidationError, match="unique"):
        Checklist(id="c", version="1", source="s", verified=True, items=(item, item))


def test_osf_items_are_numbered_in_order() -> None:
    first = OsfItem(id="GSRRF-1", en="Title", fr="Titre")
    second = OsfItem(id="GSRRF-2", en="Contributors", fr="Contributeurs")
    assert second.label("fr") == "Contributeurs"
    OsfForm(id="o", version="1", source="s", verified=True, items=(first, second))
    with pytest.raises(ValidationError, match="numbered"):
        OsfForm(id="o", version="1", source="s", verified=True, items=(second, first))


FRAMING = Framing(question="Q ?", population="Parents", secondary_questions=("S1 ?",))


def test_apply_reformulation_and_elements() -> None:
    assert apply_suggestion(FRAMING, SuggestionKind.REFORMULATION, " Q2 ? ").question == "Q2 ?"
    assert apply_suggestion(FRAMING, SuggestionKind.POPULATION, "Tuteurs").population == "Tuteurs"
    assert apply_suggestion(FRAMING, SuggestionKind.CONCEPT, "Soutien").concept == "Soutien"
    assert apply_suggestion(FRAMING, SuggestionKind.CONTEXT, "École").context == "École"


def test_secondary_question_is_added_once() -> None:
    added = apply_suggestion(FRAMING, SuggestionKind.SECONDARY_QUESTION, "S2 ?")
    assert added.secondary_questions == ("S1 ?", "S2 ?")
    assert apply_suggestion(added, SuggestionKind.SECONDARY_QUESTION, "S2 ?") == added


def test_applied_suggestion_needs_text() -> None:
    with pytest.raises(ValueError, match="needs a text"):
        apply_suggestion(FRAMING, SuggestionKind.CONCEPT, "  ")


def test_review_text_matches_outcome() -> None:
    common = {"id": "r", "suggestion_id": "s", "reviewer_id": "h", "created_at": NOW}
    SuggestionReview(outcome=SuggestionOutcome.REJECTED, **common)  # type: ignore[arg-type]
    SuggestionReview(outcome=SuggestionOutcome.ACCEPTED, final_text="x", **common)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        SuggestionReview(outcome=SuggestionOutcome.REJECTED, final_text="x", **common)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        SuggestionReview(outcome=SuggestionOutcome.MODIFIED, **common)  # type: ignore[arg-type]
