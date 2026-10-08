"""Web page « Pilote » (tranche 1.6): budget, blind screening, AI batch, calibration table."""

import html
import re
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from revue_portee.ai.base import ModelProvider, TaskInput
from revue_portee.ai.providers.fake import FakeProvider
from revue_portee.ai.settings import AITaskConfig
from revue_portee.ai.tasks.screening import ScreenReferenceInput
from revue_portee.collect import imports
from revue_portee.domain.criteria import CriterionKind, PccElement
from revue_portee.jobs.runner import BackgroundJobs
from revue_portee.protocol import criteria
from revue_portee.screening import pilot
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.repositories import screening as screening_repo
from revue_portee.web.app import create_app
from support import TOOL_VERSION, make_clock, new_project

BASE = "http://127.0.0.1:8000"
TITLES = [
    "Housing insecurity among older adults in rural Quebec",
    "Childhood obesity and school meals",
    "Older adults and home adaptations: a qualitative study",
    "Software engineering practices in startups",
]
RATIONALE = "Raison donnée par le modèle factice."


def ris(titles: list[str]) -> bytes:
    return "\n".join(
        f"TY  - JOUR\nTI  - {title}\nAU  - Author{i}, A.\nPY  - 2021\n"
        f"JO  - Journal {i}\nAB  - This study examines {title.lower()}.\nER  - \n"
        for i, title in enumerate(titles, start=1)
    ).encode("utf-8")


@pytest.fixture
def folder(tmp_path: Path) -> Iterator[ProjectFolder]:
    clock = make_clock()
    project = new_project(tmp_path, clock)
    for element, kind, text in (
        (PccElement.POPULATION, CriterionKind.INCLUSION, "Older adults (65 and over)."),
        (PccElement.CONCEPT, CriterionKind.INCLUSION, "Housing or living conditions."),
    ):
        criteria.add_criterion(
            project, pcc_element=element, kind=kind, text=text, now=clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
    criteria.activate_draft(project, rationale="", now=clock, tool_version=TOOL_VERSION)
    imports.import_ris(
        project, "demo.ris", ris(TITLES), database="PubMed", now=clock, tool_version=TOOL_VERSION
    )
    yield project
    project.close()


def answer(item: TaskInput) -> dict[str, Any]:
    assert isinstance(item, ScreenReferenceInput)
    keep = "older" in item.reference.title.lower()
    status = "met" if keep else "not_met"
    return {
        "assessments": [
            {"code": "P1", "status": status, "evidence_quote": "older adults" if keep else ""},
            {"code": "C1", "status": status, "evidence_quote": ""},
        ],
        "decision": "include" if keep else "exclude",
        "inclusion_probability": 0.9 if keep else 0.02,
        "rationale": RATIONALE,
        "decisive_criteria": ["P1"],
    }


def factory(config: AITaskConfig) -> ModelProvider:
    return FakeProvider(
        model=str(config.model),
        model_returned="fake-screener-2026-10-08",
        responder=answer,
        cost_per_call=Decimal("0.001"),
    )


def text(response: Any) -> str:  # noqa: ANN401
    return html.unescape(response.text).replace(" ", " ")


@pytest.fixture
def jobs() -> BackgroundJobs:
    return BackgroundJobs()


@pytest.fixture
def client(folder: ProjectFolder, jobs: BackgroundJobs) -> TestClient:
    app = create_app(
        folder, now=make_clock(), tool_version=TOOL_VERSION, provider_factory=factory, jobs=jobs
    )
    return TestClient(app, base_url=BASE, follow_redirects=False)


def token(client: TestClient) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/pilote").text)
    assert match
    return match.group(1)


def post(client: TestClient, url: str, **data: str | list[str]) -> Any:  # noqa: ANN401
    return client.post(url, data={"csrf_token": token(client), **data})


def draw(client: TestClient) -> str:
    response = post(client, "/pilote/lancer", taille="4", graine="7")
    assert response.status_code == 303
    return str(response.headers["location"]).removeprefix("/pilote/")


def screen_with_ai(client: TestClient, jobs: BackgroundJobs, round_id: str) -> None:
    assert post(client, "/pilote/budget", montant="5").status_code == 303
    preview = post(client, f"/pilote/{round_id}/ia/estimation")
    assert preview.status_code == 200
    assert "Coût estimé" in text(preview)
    assert 'name="plafond" value="0,01"' in preview.text  # 4 * 0.001 * 1.25, rounded up
    response = post(client, f"/pilote/{round_id}/ia", plafond="0,01")
    assert response.status_code == 303
    jobs.wait(f"pilote-{round_id}", 30)


def test_budget_is_required_and_validated(client: TestClient) -> None:
    page = client.get("/pilote")
    assert page.status_code == 200
    assert 'aria-current="page">Pilote' in page.text
    assert "Aucun budget pour l'instant" in text(page)
    assert post(client, "/pilote/budget", montant="-2").status_code == 422
    response = post(client, "/pilote/budget", montant="12,50")
    assert response.status_code == 303
    assert "12,50 $ US" in text(client.get("/pilote")) or "12,50" in text(client.get("/pilote"))
    round_id = draw(client)
    assert round_id in client.get("/pilote").text


def test_ai_batch_needs_a_budget(client: TestClient, jobs: BackgroundJobs) -> None:
    round_id = draw(client)
    response = post(client, f"/pilote/{round_id}/ia", plafond="1")
    assert response.status_code == 422
    assert "budget" in text(response).lower()
    assert not jobs.keys()


def test_human_screening_is_blind(
    client: TestClient, jobs: BackgroundJobs, folder: ProjectFolder
) -> None:
    round_id = draw(client)
    screen_with_ai(client, jobs, round_id)
    with folder.engine.connect() as connection:
        assert len(screening_repo.list_decisions(connection, round_id=round_id)) == 4
    page = client.get(f"/pilote/{round_id}")
    # Every AI decision exists, but none is shown before the human decides (EF-SEL-02).
    assert RATIONALE not in text(page)
    assert "Aucune décision de votre part" in text(page)
    state = pilot.pilot_state(folder, round_id)
    first = state.next_reference
    assert first is not None
    title = state.references[first].title
    assert title in text(page)

    excluded = post(client, f"/pilote/{round_id}/decision", reference=first, valeur="exclude")
    assert excluded.status_code == 422  # an exclusion cites a criterion (EF-SEL-12)
    decided = post(
        client, f"/pilote/{round_id}/decision", reference=first, valeur="include", criteres=["P1"]
    )
    assert decided.status_code == 303
    after = text(client.get(f"/pilote/{round_id}"))
    assert after.count(RATIONALE) == 1  # only the decided reference shows the AI
    second = pilot.pilot_state(folder, round_id).next_reference
    assert second is not None
    assert second != first


def test_calibration_table_and_thresholds(
    client: TestClient, jobs: BackgroundJobs, folder: ProjectFolder
) -> None:
    round_id = draw(client)
    screen_with_ai(client, jobs, round_id)
    state = pilot.pilot_state(folder, round_id)
    for ref_id in state.round.reference_ids:
        keep = "older" in state.references[ref_id].title.lower()
        data: dict[str, str | list[str]] = {"reference": ref_id}
        data |= {"valeur": "include"} if keep else {"valeur": "exclude", "criteres": ["P1"]}
        assert post(client, f"/pilote/{round_id}/decision", **data).status_code == 303
    page = text(client.get(f"/pilote/{round_id}"))
    assert "Table d'étalonnage" in page
    assert "100,0 %" in page  # agreement and sensitivity
    assert "Vous avez trié toutes les références" in page

    assert post(client, f"/pilote/{round_id}/etalonnage").status_code == 303
    assert "Étalonnage ajusté" in text(client.get(f"/pilote/{round_id}?decide=2"))

    missing = post(
        client, f"/pilote/{round_id}/seuils", exclure="0,05", inclure="0,6", cible="0,95", motif=""
    )
    assert missing.status_code == 422
    wrong = post(
        client, f"/pilote/{round_id}/seuils", exclure="0,7", inclure="0,6", cible="0,95", motif="x"
    )
    assert wrong.status_code == 422
    fixed = post(
        client,
        f"/pilote/{round_id}/seuils",
        exclure="0,05",
        inclure="0,6",
        cible="0,95",
        motif="Sensibilité de 100 % sur le pilote.",
        etalonne="1",
    )
    assert fixed.status_code == 303
    with folder.engine.connect() as connection:
        setting = screening_repo.latest_threshold(connection, pilot.STAGE)
    assert setting is not None
    assert setting.thresholds.exclude_below == pytest.approx(0.05)
    assert setting.calibration_id is not None


def test_unknown_round_and_progress(client: TestClient, jobs: BackgroundJobs) -> None:
    assert client.get("/pilote/inconnu").status_code == 404
    round_id = draw(client)
    progress = client.get(f"/pilote/{round_id}/etat")
    assert progress.status_code == 200
    assert progress.headers["HX-Refresh"] == "true"


def test_drawing_needs_criteria(tmp_path: Path) -> None:
    project = new_project(tmp_path / "vide")
    try:
        app = create_app(project, now=make_clock(), tool_version=TOOL_VERSION)
        client = TestClient(app, base_url=BASE, follow_redirects=False)
        assert "Activez une version des critères" in text(client.get("/pilote"))
        assert post(client, "/pilote/lancer", taille="0").status_code == 422
        response = post(client, "/pilote/lancer", taille="5")
        assert response.status_code == 422
    finally:
        project.close()
