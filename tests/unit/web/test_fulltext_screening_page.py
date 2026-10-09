"""The full-text screening pages (tranche 2.2): pilot, mode chosen at the start, blind
screening and reconciliation, assisted screening with the AI's quotes and pages."""

import html
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from demo import (
    AI_FT,
    Demo,
    _factory,
    broaden_and_reassess,
    create,
    deduplicate,
    reconcile,
    retrieve_texts,
    screen,
)
from revue_portee.jobs.runner import BackgroundJobs
from revue_portee.screening import fulltext
from revue_portee.web.app import create_app
from support import TOOL_VERSION, make_clock

BASE = "http://127.0.0.1:8000"


@pytest.fixture
def demo(tmp_path: Path) -> Iterator[Demo]:
    """The demonstration up to the full texts obtained (two texts)."""
    built = create(tmp_path)
    deduplicate(built)
    screen(built)
    reconcile(built)
    broaden_and_reassess(built)
    retrieve_texts(built)
    yield built
    built.folder.close()


def setup(demo: Demo) -> tuple[TestClient, BackgroundJobs]:
    jobs = BackgroundJobs()
    app = create_app(
        demo.folder,
        now=make_clock(),
        tool_version=TOOL_VERSION,
        provider_factory=_factory(AI_FT),
        jobs=jobs,
    )
    return TestClient(app, base_url=BASE, follow_redirects=False), jobs


def text(response: object) -> str:
    """The page, its non-breaking spaces read as spaces."""
    return html.unescape(response.text).replace(" ", " ")  # type: ignore[attr-defined]


def token(client: TestClient) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', text(client.get("/textes/tri")))
    assert match is not None
    return match.group(1)


def post(client: TestClient, path: str, **data: str) -> object:
    return client.post(path, data={"csrf_token": token(client)} | data)


def run_ai(client: TestClient, jobs: BackgroundJobs, round_id: str) -> None:
    estimate = post(client, f"/textes/tri/{round_id}/ia/estimation")
    assert "Plafond du lot en dollars américains" in text(estimate)
    started = post(client, f"/textes/tri/{round_id}/ia", plafond="1,00")
    assert started.status_code == 303  # type: ignore[attr-defined]
    jobs.wait(f"texte-ia-{round_id}", timeout=30)
    assert jobs.error(f"texte-ia-{round_id}") is None


def decide(client: TestClient, round_id: str, ref: str, value: str, *codes: str) -> object:
    data = {"csrf_token": token(client), "reference": ref, "valeur": value}
    return client.post(f"/textes/tri/{round_id}/decision", data=data | {"criteres": list(codes)})


def test_pilot_then_blind_screening_and_reconciliation(demo: Demo) -> None:
    client, jobs = setup(demo)
    ids = demo.ids()
    page = text(client.get("/textes/tri"))
    assert '<a href="/textes" aria-current="page">Textes intégraux</a>' in page
    assert "2 textes obtenus." in page
    assert post(client, "/textes/tri/pilote").status_code == 303  # type: ignore[attr-defined]
    trial = fulltext.pilot_round(demo.folder)
    assert trial is not None
    # blind pilot: the text by page, no AI shown
    first = text(client.get(f"/textes/tri/{trial.id}/trier"))
    assert "Tri à l'aveugle : la décision de l'IA n'est pas affichée." in first
    assert "Page 2" in first
    assert decide(client, trial.id, ids["housing"], "exclude").status_code == 422  # type: ignore[attr-defined]
    assert decide(client, trial.id, ids["housing"], "exclude", "P1").status_code == 303  # type: ignore[attr-defined]
    assert decide(client, trial.id, ids["loneliness"], "include").status_code == 303  # type: ignore[attr-defined]
    assert "Aucun texte à trier" in text(client.get(f"/textes/tri/{trial.id}/trier"))
    run_ai(client, jobs, trial.id)
    page = text(client.get("/textes/tri"))
    assert "Essai pilote terminé." in page
    # the main round, blind; the AI on it; then a disagreement
    assert post(client, "/textes/tri/commencer", mode="").status_code == 422  # type: ignore[attr-defined]
    assert post(client, "/textes/tri/commencer", mode="blind").status_code == 303  # type: ignore[attr-defined]
    started = fulltext.main_round(demo.folder)
    assert started is not None
    run_ai(client, jobs, started.id)
    page = text(client.get("/textes/tri"))
    assert "Mode : double tri à l'aveugle." in page
    assert decide(client, started.id, ids["housing"], "include").status_code == 303  # type: ignore[attr-defined]
    reconciliation = text(client.get("/textes/tri/reconciliation"))
    assert "Désaccords restants : 1." in reconciliation
    assert "« A cohort of 1,200 adolescents aged 14 to 17 » (page 2) — trouvée à cette page" in (
        reconciliation
    )
    data = {"csrf_token": token(client), "reference": ids["housing"], "valeur": "exclude"}
    final = client.post("/textes/tri/reconciliation", data=data | {"criteres": ["P1"]})
    assert final.status_code == 303
    assert "Aucun désaccord à réconcilier." in text(client.get("/textes/tri/reconciliation?ok=1"))
    assert (
        client.post("/textes/tri/reconciliation", data={"csrf_token": token(client)}).status_code
        == 422
    )
    diagram = text(client.get("/rapports/diagramme?langue=fr"))
    assert "Rapports évalués pour l'admissibilité (n = 2)" in diagram


def test_assisted_screening_shows_the_ai_first(demo: Demo) -> None:
    client, jobs = setup(demo)
    ids = demo.ids()
    post(client, "/textes/tri/pilote")
    trial = fulltext.pilot_round(demo.folder)
    assert trial is not None
    post(client, "/textes/tri/commencer", mode="assisted")
    started = fulltext.main_round(demo.folder)
    assert started is not None
    refused = post(client, f"/textes/tri/{started.id}/ia", plafond="1")
    assert "Terminez d'abord l'essai pilote" in text(refused)
    assert "un texte attend que l'IA l'ait trié" in text(
        client.get(f"/textes/tri/{started.id}/trier")
    )
    decide(client, trial.id, ids["housing"], "exclude", "P1")
    decide(client, trial.id, ids["loneliness"], "include")
    run_ai(client, jobs, trial.id)
    run_ai(client, jobs, started.id)
    # both texts are decided by the pilot: show one of them on demand
    page = text(client.get(f"/textes/tri/{started.id}/trier?ref={ids['loneliness']}"))
    assert "Tri assisté : l'évaluation de l'IA est affichée avant votre décision." in page
    assert "« living in three residences » (page 1) — trouvée, mais à une autre page" in page
    assert "« This is an original research article » (page 1) — introuvable dans le texte" in page
    assert 'name="criteres" value="C1" checked' not in page  # nothing preselected
    assert decide(client, started.id, ids["loneliness"], "exclude", "C1").status_code == 303  # type: ignore[attr-defined]
    page = text(client.get("/textes/tri"))
    assert "Décisions qui conservent ou excluent comme l'IA : 0 sur 1." in page
    assert client.get("/textes/tri/reconciliation").status_code == 200


def test_errors(demo: Demo, tmp_path: Path) -> None:
    client, _jobs = setup(demo)
    assert client.get("/textes/tri/nope/trier").status_code == 404
    assert post(client, "/textes/tri/nope/ia/estimation").status_code == 404  # type: ignore[attr-defined]
    assert post(client, "/textes/tri/nope/ia", plafond="1").status_code == 404  # type: ignore[attr-defined]
    assert client.get("/textes/tri/reconciliation").status_code == 404
    post(client, "/textes/tri/pilote")
    trial = fulltext.pilot_round(demo.folder)
    assert trial is not None
    assert post(client, f"/textes/tri/{trial.id}/ia", plafond="non").status_code == 422  # type: ignore[attr-defined]
    missing = client.post(
        f"/textes/tri/{trial.id}/decision",
        data={"csrf_token": token(client), "reference": demo.ids()["housing"]},
    )
    assert missing.status_code == 422
    assert post(client, "/textes/tri/commencer", mode="blind").status_code == 303  # type: ignore[attr-defined]
    assert post(client, "/textes/tri/commencer", mode="blind").status_code == 422  # type: ignore[attr-defined]
    assert post(client, "/textes/tri/ajouter").status_code == 303  # type: ignore[attr-defined]
