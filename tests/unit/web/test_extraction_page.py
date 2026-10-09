"""The « Extraction » pages (tranche 3.2): pre-filling by the AI in the background,
values of a study with their quotes, pages and checks."""

import html
import re
from pathlib import Path

from fastapi.testclient import TestClient

from demo import build
from revue_portee.extraction import grid
from revue_portee.jobs.runner import BackgroundJobs
from revue_portee.web.app import EXTRACTION_JOB, create_app
from support import TOOL_VERSION, make_clock
from unit.extraction.test_prefill import _with_grid, answer, factory

BASE = "http://127.0.0.1:8000"


def text(response: object) -> str:
    return html.unescape(response.text).replace(" ", " ")  # type: ignore[attr-defined]


def token(client: TestClient) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', text(client.get("/grille")))
    assert match is not None
    return match.group(1)


def test_extraction_pages(tmp_path: Path) -> None:
    demo = _with_grid(tmp_path)
    try:
        jobs = BackgroundJobs()
        app = create_app(
            demo.folder, now=make_clock(), tool_version=TOOL_VERSION, jobs=jobs,
            provider_factory=factory(answer),
        )  # fmt: skip
        client = TestClient(app, base_url=BASE, follow_redirects=False)
        page = text(client.get("/extraction"))
        assert '<a href="/extraction" aria-current="page">Extraction</a>' in page
        assert "Études à pré-remplir : 1." in page
        estimate = client.post("/extraction/ia/estimation", data={"csrf_token": token(client)})
        assert "Plafond du lot en dollars américains" in text(estimate)
        bad = client.post("/extraction/ia", data={"csrf_token": token(client), "plafond": "x"})
        assert bad.status_code == 422
        started = client.post("/extraction/ia", data={"csrf_token": token(client), "plafond": "1"})
        assert started.status_code == 303
        jobs.wait(EXTRACTION_JOB, timeout=30)
        assert jobs.error(EXTRACTION_JOB) is None
        page = text(client.get("/extraction"))
        assert "Champs vérifiés par vous : 0 sur 3." in page
        loneliness = demo.ids()["loneliness"]
        study = text(client.get(f"/extraction/{loneliness}"))
        assert "non rapporté" in study
        assert (
            "« We interviewed 24 older adults » (page 2) — trouvée, mais à une autre page" in study
        )
        assert "(l'IA indiquait la page 3)" in study
        assert "proposée par l'IA, à vérifier" in study
        assert client.get("/extraction/nope").status_code == 404
    finally:
        demo.folder.close()


def test_without_grid(tmp_path: Path) -> None:
    demo = build(tmp_path)
    try:
        app = create_app(demo.folder, now=make_clock(), tool_version=TOOL_VERSION)
        client = TestClient(app, base_url=BASE, follow_redirects=False)
        assert "Activez d'abord une version de la grille d'extraction." in text(
            client.get("/extraction")
        )
        refused = client.post("/extraction/ia/estimation", data={"csrf_token": token(client)})
        assert refused.status_code == 422
        grid.add_template(demo.folder, now=demo.clock, tool_version=TOOL_VERSION)
    finally:
        demo.folder.close()


def test_values_checked_then_exported(tmp_path: Path) -> None:
    demo = _with_grid(tmp_path)
    loneliness = demo.ids()["loneliness"]
    try:
        jobs = BackgroundJobs()
        app = create_app(
            demo.folder, now=make_clock(), tool_version=TOOL_VERSION, jobs=jobs,
            provider_factory=factory(answer),
        )  # fmt: skip
        client = TestClient(app, base_url=BASE, follow_redirects=False)
        client.post("/extraction/ia", data={"csrf_token": token(client), "plafond": "1"})
        jobs.wait(EXTRACTION_JOB, timeout=30)
        assert "Champs vérifiés par vous : 0 sur 3." in text(client.get("/extraction"))
        url = f"/extraction/{loneliness}"
        study = text(client.get(url))
        assert 'name="action" value="valider"' in study
        assert "Corriger" in study
        validated = client.post(
            f"{url}/D2", data={"csrf_token": token(client), "action": "valider"}
        )
        assert validated.status_code == 303
        assert validated.headers["location"] == f"{url}?ok=1#champ-D2"
        assert "Valeur enregistrée." in text(client.get(f"{url}?ok=1"))
        rejected = client.post(f"{url}/D1", data={"csrf_token": token(client), "action": "rejeter"})
        assert rejected.status_code == 303
        again = client.post(f"{url}/D1", data={"csrf_token": token(client), "action": "valider"})
        assert again.status_code == 422
        assert "Aucune valeur de l'IA à vérifier pour ce champ." in text(again)
        wrong = {"csrf_token": token(client), "action": "saisir", "rapporte": "oui"}
        bad_value = client.post(f"{url}/D3", data=wrong | {"valeur": "Mixte"})
        assert bad_value.status_code == 422
        assert "La valeur ne correspond pas au type du champ D3." in text(bad_value)
        bad_page = client.post(f"{url}/D3", data=wrong | {"valeur": "Quantitatif", "page": "x"})
        assert bad_page.status_code == 422
        corrected = client.post(
            f"{url}/D3",
            data=wrong | {"valeur": "Quantitatif", "citation": "living in three residences",
                          "page": "2", "note": "devis mal lu"},
        )  # fmt: skip
        assert corrected.status_code == 303
        study = text(client.get(url))
        assert 'corrigée <span class="small">— devis mal lu</span>' in study
        assert "rejetée" in study
        assert client.post(f"{url}/D9", data=wrong).status_code == 404
        assert "Champs vérifiés par vous : 3 sur 3." in text(client.get("/extraction"))
        exported = text(client.post("/extraction/export", data={"csrf_token": token(client)}))
        assert "Valeurs écrites dans exports/donnees-extraites.csv : 2." in exported
    finally:
        demo.folder.close()
    written = (demo.folder.path / "exports" / "donnees-extraites.csv").read_text(encoding="utf-8")
    assert ",D3,Devis,oui,Quantitatif,2,corrected," in written
    assert "Qualitatif" not in written


def test_pilot_pages(tmp_path: Path) -> None:
    demo = _with_grid(tmp_path)
    loneliness = demo.ids()["loneliness"]
    try:
        jobs = BackgroundJobs()
        app = create_app(
            demo.folder, now=make_clock(), tool_version=TOOL_VERSION, jobs=jobs,
            provider_factory=factory(answer),
        )  # fmt: skip
        client = TestClient(app, base_url=BASE, follow_redirects=False)
        client.post("/extraction/ia", data={"csrf_token": token(client), "plafond": "1"})
        jobs.wait(EXTRACTION_JOB, timeout=30)
        refused = client.post(
            "/extraction/pilote", data={"csrf_token": token(client), "taille": "0"}
        )
        assert refused.status_code == 422
        started = client.post(
            "/extraction/pilote", data={"csrf_token": token(client), "taille": "5"}
        )
        assert started.headers["location"] == "/extraction?ok=pilote"
        page = text(client.get("/extraction?ok=pilote"))
        assert "Études du pilote tirées : extrayez-les sans l'IA." in page
        assert "0 études extraites sur 1." in page
        assert "Pilote : à extraire sans l'IA." in page
        url = f"/extraction/{loneliness}"
        study = text(client.get(url))
        assert "Cette étude fait partie du pilote d'extraction" in study
        assert "We interviewed" not in study
        assert 'value="valider"' not in study
        give = {"csrf_token": token(client), "action": "saisir"}
        client.post(f"{url}/D1", data=give | {"rapporte": "non"})
        client.post(f"{url}/D2", data=give | {"rapporte": "oui", "valeur": "24"})
        client.post(f"{url}/D3", data=give | {"rapporte": "oui", "valeur": "Quantitatif"})
        page = text(client.get("/extraction"))
        assert "1 études extraites sur 1." in page
        assert "Concordance de l'IA avec votre extraction" in page
        assert "<td>1</td><td>0</td><td>0 %</td>" in page  # D3
        assert "Tirer les études d'un nouveau pilote" in page
        study = text(client.get(url))
        assert "Cette étude fait partie du pilote" not in study
        assert "extraite par la personne" in study
    finally:
        demo.folder.close()


def test_grid_change_followed(tmp_path: Path) -> None:
    from unit.extraction.test_impact import _changed

    demo = _changed(tmp_path)
    loneliness = demo.ids()["loneliness"]
    try:
        app = create_app(demo.folder, now=demo.clock, tool_version=TOOL_VERSION)
        client = TestClient(app, base_url=BASE, follow_redirects=False)
        page = text(client.get("/extraction"))
        assert "Changements de la grille depuis la version 1" in page
        assert "<td>champ ajouté : études à compléter</td><td>1</td><td>1</td>" in page
        assert "<td>champ retiré : valeurs archivées</td><td>1</td><td>—</td>" in page
        assert "dans l'export) : 1." in page
        assert "Champs vérifiés par vous : 0 sur 3. À revoir : 1." in page
        url = f"/extraction/{loneliness}"
        study = text(client.get(url))
        assert "À revoir : donnée selon une définition antérieure du champ." in study
        confirm = {"csrf_token": token(client), "action": "confirmer"}
        assert client.post(f"{url}/D2", data=confirm).status_code == 303
        again = client.post(f"{url}/D2", data=confirm)
        assert again.status_code == 422
        assert "Aucune valeur de votre part à confirmer pour ce champ." in text(again)
        page = text(client.get("/extraction"))
        assert "<td>champ modifié : valeurs à revoir</td><td>1</td><td>0</td>" in page
        assert "Champs vérifiés par vous : 1 sur 3." in page
    finally:
        demo.folder.close()
