"""Versioned prompt templates and the hash of the rendered prompt."""

import pytest
from jinja2 import UndefinedError

from revue_portee.ai.prompts import PromptTemplate, load_template
from revue_portee.ai.tasks import (
    QUALIFY_CRITERION_CHANGE,
    SUGGEST_PCC,
    CriterionSnapshot,
    QualifyChangeInput,
    SuggestPccInput,
)


@pytest.mark.parametrize("task", [SUGGEST_PCC, QUALIFY_CRITERION_CHANGE])
def test_each_task_has_a_versioned_template(task: object) -> None:
    template = load_template(task.prompt.template_id)  # type: ignore[attr-defined]
    assert template.task == task.name  # type: ignore[attr-defined]
    assert template.version == task.prompt.version  # type: ignore[attr-defined]
    assert template.changelog[-1]["version"] == template.version


def test_suggestion_prompt_contains_the_framing_and_the_language() -> None:
    item = SuggestPccInput(
        item_id="f1",
        language="fr",
        question="Quelles interventions ?",
        population="Parents",
        secondary_questions=("Quels résultats ?",),
    )
    prompt = load_template("suggest_pcc").render(item)
    assert "ISO 639-1 code: fr" in prompt.system
    assert "Main question: Quelles interventions ?" in prompt.user
    assert "Concept: (not specified)" in prompt.user
    assert "- Quels résultats ?" in prompt.user
    assert "f1" not in prompt.user  # identifiers are not sent to the model


def test_hash_changes_with_any_part_of_the_prompt() -> None:
    def render(question: str, language: str = "fr") -> str:
        item = SuggestPccInput(item_id="x", language=language, question=question)
        return load_template("suggest_pcc").render(item).sha256

    assert render("Q ?") == render("Q ?")
    assert render("Q ?") != render("Q2 ?")
    assert render("Q ?") != render("Q ?", "en")


def test_qualification_prompt_shows_both_states() -> None:
    item = QualifyChangeInput(
        item_id="P1",
        language="en",
        code="P1",
        pcc_element="population",
        before=CriterionSnapshot(kind="inclusion", text="Parents"),
        after=CriterionSnapshot(kind="exclusion", text="Parents", examples=("a", "b")),
    )
    user = load_template("qualify_criterion_change").render(item).user
    assert "Criterion P1 (PCC element: population)" in user
    assert "- Kind: inclusion" in user
    assert "- Kind: exclusion" in user
    assert "- Examples: a | b" in user


def test_missing_values_are_errors() -> None:
    template = PromptTemplate(
        id="t", version="1", task="t", system_source="{{ missing }}", user_source=""
    )
    with pytest.raises(UndefinedError):
        template.render(SuggestPccInput(item_id="x", language="fr", question="Q ?"))


def test_template_id_must_match_its_folder() -> None:
    with pytest.raises(FileNotFoundError):
        load_template("does_not_exist")
