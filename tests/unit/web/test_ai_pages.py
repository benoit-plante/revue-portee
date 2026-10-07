"""Web pages of tranche 1.2: AI suggestions, qualification, protocol (FakeProvider only)."""

import io
import re
from collections.abc import Iterator, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

import docx
import pytest
from fastapi.testclient import TestClient

from revue_portee.ai.base import CostEstimate, TaskInput, TaskSpec
from revue_portee.ai.settings import AITaskConfig
from revue_portee.domain.criteria import CriterionKind, PccElement
from revue_portee.domain.framing import Framing
from revue_portee.protocol import criteria, framing, suggestions
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.web.app import create_app, money
from support import TOOL_VERSION, fake_factory, make_clock, new_project

BASE = "http://127.0.0.1:8000"
FACTORY = fake_factory(
    {
        "SuggestPccInput": lambda _item: {
            "suggestions": [
                {
                    "kind": "reformulation",
                    "text": "Quelles interventions existent ?",
                    "rationale": "Plus ouvert.",
                },
                {"kind": "concept", "text": "Soutien parental", "rationale": "Plus précis."},
            ]
        },
        "QualifyChangeInput": lambda _item: {
            "change_type": "broadening",
            "confidence": 0.8,
            "rationale": "Tranche d'âge élargie.",
        },
    }
)


@pytest.fixture
def folder(tmp_path: Path) -> Iterator[ProjectFolder]:
    project = new_project(tmp_path)
    yield project
    project.close()


def client_for(folder: ProjectFolder, factory: Any = FACTORY) -> TestClient:  # noqa: ANN401
    app = create_app(folder, now=make_clock(), tool_version=TOOL_VERSION, provider_factory=factory)
    return TestClient(app, base_url=BASE, follow_redirects=False)


@pytest.fixture
def client(folder: ProjectFolder) -> TestClient:
    return client_for(folder)


def text_of(response: Any) -> str:  # noqa: ANN401
    import html

    return html.unescape(response.text)


def token(client: TestClient) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', text_of(client.get("/cadrage")))
    assert match is not None
    return match.group(1)


def post(client: TestClient, path: str, **data: str) -> Any:  # noqa: ANN401
    return client.post(path, data={"csrf_token": token(client)} | data)


def frame(folder: ProjectFolder) -> None:
    framing.save_framing(
        folder,
        Framing(question="Quelles interventions ?", population="Parents"),
        now=make_clock(),
        tool_version=TOOL_VERSION,
    )


def test_money_uses_french_notation() -> None:
    assert money(Decimal("0.0123"), "USD") == "0,0123 USD"


def test_cost_is_shown_before_the_call(client: TestClient, folder: ProjectFolder) -> None:
    assert "Enregistrez d'abord la question principale." in text_of(client.get("/cadrage"))
    frame(folder)
    page = text_of(client.get("/cadrage"))
    assert "Demander des suggestions à l'IA…" in page
    estimate = post(client, "/cadrage/suggestions/estimation")
    assert estimate.status_code == 200
    shown = text_of(estimate)
    assert "Coût estimé avant l'appel" in shown
    assert "0,0000 USD" in shown
    model = folder.ai_settings().enabled_task("suggest_pcc").model
    assert f"fake — {model}" in shown
    assert "Interroger l'IA (confirmer le coût)" in shown
    assert suggestions.list_suggestions(folder) == []  # nothing called yet


def test_suggestions_are_reviewed_one_by_one(client: TestClient, folder: ProjectFolder) -> None:
    frame(folder)
    done = post(client, "/cadrage/suggestions")
    assert (done.status_code, done.headers["location"]) == (303, "/cadrage#suggestions")
    page = text_of(client.get("/cadrage"))
    assert "Reformulation de la question" in page
    assert "Justification de l'IA : Plus ouvert." in page
    assert "Proposée par fake-model-2026-10-07" in page
    first, second = (v.suggestion for v in suggestions.list_suggestions(folder))

    accepted = post(client, f"/cadrage/suggestions/{first.id}", decision="accepted")
    assert accepted.headers["location"] == f"/cadrage#suggestion-{first.id}"
    modified = post(
        client,
        f"/cadrage/suggestions/{second.id}",
        decision="modified",
        texte="Soutien aux parents",
    )
    assert modified.status_code == 303
    current = framing.current_framing(folder)
    assert current is not None
    assert current.framing.question == "Quelles interventions existent ?"
    assert current.framing.concept == "Soutien aux parents"
    page = text_of(client.get("/cadrage"))
    assert "Acceptée" in page
    assert "Modifiée, puis acceptée" in page

    again = post(client, f"/cadrage/suggestions/{first.id}", decision="rejected")
    assert again.status_code == 422
    assert "déjà été examinée" in text_of(again)
    unknown = post(client, "/cadrage/suggestions/inconnue", decision="rejected")
    assert unknown.status_code == 404


def test_modified_suggestion_needs_text(client: TestClient, folder: ProjectFolder) -> None:
    frame(folder)
    post(client, "/cadrage/suggestions")
    first = suggestions.list_suggestions(folder)[0].suggestion
    refused = post(client, f"/cadrage/suggestions/{first.id}", decision="modified", texte=" ")
    assert refused.status_code == 422
    assert "Une suggestion modifiée doit avoir un texte." in text_of(refused)


def test_errors_are_shown_on_the_page(client: TestClient, folder: ProjectFolder) -> None:
    no_framing = post(client, "/cadrage/suggestions/estimation")
    assert no_framing.status_code == 422
    assert "Enregistrez la question principale avant" in text_of(no_framing)
    assert post(client, "/cadrage/suggestions").status_code == 422


class Failing:
    name = "fake"

    def supports(self, task: TaskSpec[Any, Any]) -> bool:
        return True

    def estimate_cost(self, task: TaskSpec[Any, Any], inputs: Sequence[TaskInput]) -> CostEstimate:
        return CostEstimate(input_tokens=0, output_tokens=0, amount=Decimal(0))

    def run(self, task: TaskSpec[Any, Any], inputs: Sequence[TaskInput]) -> Iterator[Any]:
        from datetime import UTC, datetime

        from revue_portee.ai.base import AICallRecord, ProviderCallError

        call = AICallRecord(
            provider="fake",
            model_requested="fake-model",
            model_returned="fake-model",
            prompt_template_id=task.prompt.template_id,
            prompt_template_version=task.prompt.version,
            prompt_sha256="0" * 64,
            input_tokens=0,
            output_tokens=0,
            cost_estimate=Decimal(0),
            latency_ms=0,
            status="error",
            error_code="APIConnectionError",
            created_at=datetime(2026, 10, 7, tzinfo=UTC),
        )
        raise ProviderCallError("L'API d'Anthropic est injoignable.", item_id="x", call=call)


def test_failed_call_is_reported(folder: ProjectFolder) -> None:
    frame(folder)

    def factory(_config: AITaskConfig) -> Failing:
        return Failing()

    response = post(client_for(folder, factory), "/cadrage/suggestions")
    assert response.status_code == 502
    assert "L'API d'Anthropic est injoignable." in text_of(response)


def qualify_setup(folder: ProjectFolder) -> None:
    clock = make_clock()
    criteria.add_criterion(
        folder, pcc_element=PccElement.POPULATION, kind=CriterionKind.INCLUSION,
        text="Parents d'enfants de 0 à 12 ans", now=clock, tool_version=TOOL_VERSION,
    )  # fmt: skip
    criteria.activate_draft(folder, rationale="", now=clock, tool_version=TOOL_VERSION)
    criteria.update_criterion(
        folder, "P1", kind=CriterionKind.INCLUSION, text="Parents d'enfants de 0 à 17 ans",
        now=clock, tool_version=TOOL_VERSION,
    )  # fmt: skip


def test_qualification_with_the_ai(client: TestClient, folder: ProjectFolder) -> None:
    qualify_setup(folder)
    page = text_of(client.get("/criteres"))
    assert "Qualifier les changements" in page
    assert 'name="qualification-P1" value="broadening" required' in page
    estimate = post(client, "/criteres/qualification/estimation")
    assert "Coût estimé avant l'appel" in text_of(estimate)
    assert post(client, "/criteres/qualification").headers["location"] == "/criteres#qualification"
    page = text_of(client.get("/criteres"))
    assert "Proposition de l'IA : élargissement (confiance 0,80)." in page
    assert 'value="broadening" required\n                 checked' in page

    invalid = post(client, "/criteres/activer", justification="Ados", **{"qualification-P1": "x"})
    assert invalid.status_code == 422
    activated = post(
        client, "/criteres/activer", justification="Ados", **{"qualification-P1": "broadening"}
    )
    assert activated.headers["location"] == "/criteres/versions/2"
    version = text_of(client.get("/criteres/versions/2"))
    assert "Changements qualifiés" in version
    assert "P1 : élargissement (proposé par l'IA, confirmé par le réviseur)" in version


def test_nothing_to_qualify_is_explained(client: TestClient, folder: ProjectFolder) -> None:
    response = post(client, "/criteres/qualification/estimation")
    assert response.status_code == 422
    assert "aucun critère modifié à qualifier" in text_of(response)
    assert post(client, "/criteres/qualification").status_code == 422


def test_protocol_page_text_and_registration(client: TestClient, folder: ProjectFolder) -> None:
    page = client.get("/protocole")
    assert page.status_code == 200
    shown = text_of(page)
    assert "Protocole de la revue" in shown
    assert 'aria-current="page">Protocole' in shown
    assert "PETERS-07" in shown

    saved = post(client, "/protocole/texte", funding="Aucun financement.", background="")
    assert saved.headers["location"] == "/protocole?enregistre=1#texte"
    shown = text_of(client.get("/protocole?enregistre=1"))
    assert "Texte du protocole enregistré." in shown
    assert ">Aucun financement.</textarea>" in shown

    no_date = post(client, "/protocole/enregistrement", doi="10.17605/OSF.IO/ABCDE", date="")
    assert no_date.status_code == 422
    assert "Saisissez la date" in text_of(no_date)
    bad = post(client, "/protocole/enregistrement", doi="osf", date="2026-10-01")
    assert bad.status_code == 422
    assert 'value="osf"' in text_of(bad)
    done = post(client, "/protocole/enregistrement", doi="10.17605/osf.io/abcde", date="2026-10-01")
    assert done.status_code == 303
    assert "DOI 10.17605/OSF.IO/ABCDE" in text_of(client.get("/protocole"))

    qualify_setup(folder)
    assert "sera un écart au protocole" in text_of(client.get("/criteres"))
    post(client, "/criteres/activer", justification="Ados", **{"qualification-P1": "broadening"})
    assert "écart au protocole" in text_of(client.get("/criteres"))
    assert "Écart au protocole enregistré" in text_of(client.get("/criteres/versions/2"))


@pytest.mark.parametrize("language", ["fr", "en"])
def test_protocol_downloads(client: TestClient, language: str) -> None:
    markdown = client.get(f"/protocole/telecharger?langue={language}&format=md")
    assert markdown.status_code == 200
    assert markdown.headers["content-type"] == "text/markdown; charset=utf-8"
    assert f'filename="protocole-{language}.md"' in markdown.headers["content-disposition"]
    assert markdown.text.startswith("# Soutien à la parentalité")
    word = client.get(f"/protocole/telecharger?langue={language}&format=docx")
    assert word.status_code == 200
    assert word.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert docx.Document(io.BytesIO(word.content)).core_properties.language == language


def test_unknown_download(client: TestClient) -> None:
    assert client.get("/protocole/telecharger?langue=de&format=md").status_code == 404
    assert client.get("/protocole/telecharger?langue=fr&format=pdf").status_code == 404
