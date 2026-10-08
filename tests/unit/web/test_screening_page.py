"""Web pages « Tri » (tranche 1.7): keyboard screening without the AI's decision,
batches of the AI, reconciliation, impact of a criteria change and reassessment."""

import html
import re
from collections.abc import Callable, Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from revue_portee.ai.base import ModelProvider, TaskInput
from revue_portee.ai.providers.fake import FakeBatches, FakeProvider
from revue_portee.ai.settings import AITaskConfig
from revue_portee.ai.tasks.screening import ScreenReferenceInput
from revue_portee.domain.changes import ChangeType
from revue_portee.domain.criteria import CriterionKind
from revue_portee.domain.screening import DecisionValue
from revue_portee.jobs.runner import BackgroundJobs
from revue_portee.protocol import criteria
from revue_portee.screening import main, reassessment, settings
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.web.app import create_app
from support import TOOL_VERSION, make_clock
from unit.screening.common import Clock, answer, make_project

BASE = "http://127.0.0.1:8000"
RATIONALE = "P1 et C1 évalués."  # the rationale of the fake AI reviewer


@pytest.fixture
def folder(setup: tuple[ProjectFolder, Clock]) -> ProjectFolder:
    return setup[0]


@pytest.fixture
def setup(tmp_path: Path) -> Iterator[tuple[ProjectFolder, Clock]]:
    folder, clock = make_project(tmp_path)
    yield folder, clock
    folder.close()


Responder = Callable[[TaskInput], dict[str, Any]]


@pytest.fixture
def answers() -> dict[str, Responder]:
    """The answer of the fake AI, replaced by a test when needed."""
    return {"now": answer}


@pytest.fixture
def store() -> FakeBatches:
    return FakeBatches()


@pytest.fixture
def jobs() -> BackgroundJobs:
    return BackgroundJobs()


@pytest.fixture
def client(
    folder: ProjectFolder, store: FakeBatches, jobs: BackgroundJobs, answers: dict[str, Responder]
) -> TestClient:
    def build(config: AITaskConfig) -> ModelProvider:
        return FakeProvider(
            model=str(config.model),
            responder=lambda item: answers["now"](item),
            cost_per_call=Decimal("0.002"),
            batches=store,
        )

    app = create_app(
        folder,
        now=make_clock(),
        tool_version=TOOL_VERSION,
        provider_factory=build,
        jobs=jobs,
        batch_wait=lambda _seconds: None,
        batch_poll_seconds=0,
    )
    return TestClient(app, base_url=BASE, follow_redirects=False)


def text(response: Any) -> str:  # noqa: ANN401
    return html.unescape(response.text).replace(" ", " ")


def token(client: TestClient) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/tri").text)
    assert match
    return match.group(1)


def post(client: TestClient, url: str, **data: str | list[str]) -> Any:  # noqa: ANN401
    return client.post(url, data={"csrf_token": token(client), **data})


def start(client: TestClient) -> str:
    assert post(client, "/tri/lancer", graine="5").status_code == 303
    found = re.search(r'name="reference" value="([^"]+)"', client.get("/tri/trier").text)
    assert found
    return found.group(1)


def screen_with_ai(client: TestClient, jobs: BackgroundJobs, round_id: str, back: str) -> None:
    preview = post(client, f"/tri/ia/{round_id}/estimation")
    assert preview.status_code == 200
    assert "Coût estimé (tarif des lots)" in text(preview)
    response = post(client, f"/tri/ia/{round_id}/lancer", plafond="1")
    assert response.status_code == 303
    assert response.headers["location"].startswith(back)
    jobs.wait(f"lots-{round_id}", 30)
    assert jobs.error(f"lots-{round_id}") is None


def test_start_and_screen_with_the_keyboard(client: TestClient, folder: ProjectFolder) -> None:
    page = client.get("/tri")
    assert 'aria-current="page">Tri' in page.text
    assert "Commencer le tri" in text(page)
    assert post(client, "/tri/lancer", graine="-3").status_code == 422
    first = start(client)
    screen = client.get("/tri/trier")
    assert '<script src="/statique/tri.js"' in screen.text
    assert 'aria-keyshortcuts="i"' in screen.text
    assert "<kbd>1</kbd>" in screen.text
    assert "Vos décisions : 0 sur 10." in text(screen)
    refused = post(client, "/tri/decision", reference=first, valeur="exclude")
    assert refused.status_code == 422
    assert "Citez au moins un critère" in text(refused)
    done = post(client, "/tri/decision", reference=first, valeur="exclude", criteres=["P1"])
    assert done.status_code == 303
    assert done.headers["location"] == "/tri/trier"
    after = client.get("/tri/trier")
    assert first not in after.text
    assert "Vos décisions : 1 sur 10." in text(after)
    skipped = re.search(r'id="tri-passer" href="([^"]+)"', after.text)
    assert skipped
    target = html.unescape(skipped.group(1))
    next_after_skip = client.get(target)
    assert next_after_skip.status_code == 200
    script = client.get("/statique/tri.js")
    assert script.status_code == 200
    assert "keydown" in script.text


def test_screening_shows_no_ai_decision(
    client: TestClient, jobs: BackgroundJobs, folder: ProjectFolder
) -> None:
    start(client)
    round_id = str(main.main_round(folder).id)  # type: ignore[union-attr]
    settings.set_budget(folder, Decimal(5), now=make_clock(), tool_version=TOOL_VERSION)
    screen_with_ai(client, jobs, round_id, "/tri")
    state = main.main_state(folder, round_id)
    assert len(state.ai) == 10
    overview = text(client.get("/tri"))
    assert "Décisions de l'IA" in overview
    # the AI has decided every reference, but its decision is not shown while screening
    for priority in ("", "?priorite=1"):
        page = text(client.get(f"/tri/trier{priority}"))
        assert RATIONALE not in page
        assert "probabilité d'inclusion" not in page
    progress = client.get(f"/tri/ia/{round_id}/etat")
    assert progress.headers["HX-Refresh"] == "true"


def test_reconciliation_shows_the_ai_only_then(
    client: TestClient, jobs: BackgroundJobs, folder: ProjectFolder
) -> None:
    start(client)
    round_id = str(main.main_round(folder).id)  # type: ignore[union-attr]
    settings.set_budget(folder, Decimal(5), now=make_clock(), tool_version=TOOL_VERSION)
    screen_with_ai(client, jobs, round_id, "/tri")
    ai = main.main_state(folder, round_id).ai
    # the human keeps everything: each AI exclusion is a disagreement
    while (ref := main.next_reference(folder, round_id)) is not None:
        assert post(client, "/tri/decision", reference=ref, valeur="include").status_code == 303
    expected = [r for r in main.main_state(folder, round_id).members
                if ai[r].value is DecisionValue.EXCLUDE]  # fmt: skip
    assert expected
    overview = text(client.get("/tri"))
    assert f"Réconcilier les désaccords ({len(expected)})" in overview
    page = client.get("/tri/reconciliation")
    assert RATIONALE in text(page)
    assert f"Désaccords restants : {len(expected)}." in text(page)
    shown = re.search(r'name="reference" value="([^"]+)"', page.text)
    assert shown
    assert shown.group(1) == expected[0]
    agreeing = next(r for r in ai if r not in expected)
    wrong = post(client, "/tri/reconciliation", reference=agreeing, valeur="include")
    assert wrong.status_code == 422
    final = post(
        client, "/tri/reconciliation", reference=expected[0], valeur="exclude", criteres=["P1"]
    )
    assert final.status_code == 303
    assert main.main_state(folder, round_id).final[expected[0]].value is DecisionValue.EXCLUDE
    assert f"Désaccords restants : {len(expected) - 1}." in text(client.get("/tri/reconciliation"))


def broad(item: TaskInput) -> dict[str, Any]:
    assert isinstance(item, ScreenReferenceInput)
    output = answer(item)
    output["decision"] = "include"
    output["inclusion_probability"] = 0.95
    output["assessments"] = [
        {
            "code": a["code"],
            "status": "not_met" if a["code"] == "X1" else "met",
            "evidence_quote": "",
        }
        for a in output["assessments"]
    ]
    return output


def test_impact_and_reassessment_pages(
    client: TestClient,
    jobs: BackgroundJobs,
    folder: ProjectFolder,
    answers: dict[str, Responder],
) -> None:
    start(client)
    round_id = str(main.main_round(folder).id)  # type: ignore[union-attr]
    clock = make_clock()
    while (ref := main.next_reference(folder, round_id)) is not None:
        post(client, "/tri/decision", reference=ref, valeur="exclude", criteres=["P1"])
    assert "Aucun changement de critères" in text(client.get("/tri"))
    criteria.update_criterion(
        folder, "P1", kind=CriterionKind.INCLUSION, text="Adults (18 and over).",
        now=clock, tool_version=TOOL_VERSION,
    )  # fmt: skip
    criteria.activate_draft(
        folder, rationale="Population élargie.", qualifications={"P1": ChangeType.BROADENING},
        now=clock, tool_version=TOOL_VERSION,
    )  # fmt: skip
    overview = text(client.get("/tri"))
    assert "Analyser l'impact de la version 2" in overview
    response = post(client, "/tri/impact")
    assert response.status_code == 303
    url = response.headers["location"]
    summary = text(client.get(url))
    assert "Réévaluation 1 : version 1 à 2 des critères" in summary
    assert "élargissement" in summary
    impact_id = url.rsplit("/", 1)[-1]
    state = reassessment.reassessment_state(folder, impact_id)
    assert len(state.members) == 10
    settings.set_budget(folder, Decimal(5), now=clock, tool_version=TOOL_VERSION)
    answers["now"] = broad
    screen_with_ai(client, jobs, state.round.id, url)
    page = client.get(url)
    assert "Décision de l'IA avec la nouvelle version" in text(page)
    assert "À vérifier : 10 sur 10." in text(page)
    shown = re.search(r'name="reference" value="([^"]+)"', page.text)
    assert shown
    assert post(client, url, reference=shown.group(1), valeur="include").status_code == 303
    finish = post(client, f"{url}/terminer")
    assert finish.status_code == 422  # nine decisions left to verify
    for ref in reassessment.reassessment_state(folder, impact_id).queue:
        assert (
            post(client, url, reference=ref, valeur="exclude", criteres=["C1"]).status_code == 303
        )
    assert post(client, f"{url}/terminer").status_code == 303
    assert "Réévaluation terminée et consignée au journal." in text(client.get(url))
    assert client.get("/tri/reevaluation/nope").status_code == 404


def test_pages_before_the_screening(client: TestClient) -> None:
    assert client.get("/tri/trier").status_code == 404
    assert client.get("/tri/reconciliation").status_code == 404
    assert post(client, "/tri/impact").status_code == 404
    assert client.get("/tri/ia/nope/etat").status_code == 404
