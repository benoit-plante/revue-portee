"""The « Synthèses vulgarisées » pages (tranche 4.1): the AI's draft in the background,
the person's revision with its readability index, and the export."""

import html
import re
from pathlib import Path

from fastapi.testclient import TestClient

from demo import build
from revue_portee.jobs.runner import BackgroundJobs
from revue_portee.web.app import LAY_JOB, create_app
from support import TOOL_VERSION
from unit.extraction.test_prefill import factory
from unit.stakeholders.test_lay_summary import PLAIN, _with_synthesis, empty, summarized

BASE = "http://127.0.0.1:8000"


def text(response: object) -> str:
    return html.unescape(response.text).replace(" ", " ")  # type: ignore[attr-defined]


def token(client: TestClient) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', text(client.get("/grille")))
    assert match is not None
    return match.group(1)


def test_draft_revision_and_export(tmp_path: Path) -> None:
    demo = _with_synthesis(tmp_path)
    try:
        jobs = BackgroundJobs()
        app = create_app(
            demo.folder, now=demo.clock, tool_version=TOOL_VERSION, jobs=jobs,
            provider_factory=factory(summarized),
        )  # fmt: skip
        client = TestClient(app, base_url=BASE, follow_redirects=False)
        assert 'href="/synthese/vulgarisation">Synthèses vulgarisées</a>' in text(
            client.get("/synthese")
        )
        listing = text(client.get("/synthese/vulgarisation"))
        assert '<a href="/synthese" aria-current="page">Synthèse</a>' in listing
        assert "<td>60 ou plus</td>" in listing
        assert client.get("/synthese/vulgarisation/enfants").status_code == 404
        url = "/synthese/vulgarisation/general"
        estimate = client.post(f"{url}/ia/estimation", data={"csrf_token": token(client)})
        assert "Demander une ébauche à l'IA (confirmer le coût)" in text(estimate)
        bad = client.post(f"{url}/ia", data={"csrf_token": token(client), "plafond": "x"})
        assert bad.status_code == 422
        started = client.post(f"{url}/ia", data={"csrf_token": token(client), "plafond": "1"})
        assert started.headers["location"] == f"{url}?ok=ia"
        jobs.wait(LAY_JOB.format(level="general"), timeout=30)
        page = text(client.get(url))
        assert PLAIN in page
        assert "Indice de lisibilité (Kandel-Moles) : 75,8, assez facile" in page
        assert "cible atteinte" in page
        assert "ébauche de l'IA, à réviser" in text(client.get("/synthese/vulgarisation"))
        empty_text = client.post(url, data={"csrf_token": token(client), "titre": "T",
                                            "texte": "  "})  # fmt: skip
        assert empty_text.status_code == 422
        recorded = client.post(
            url, data={"csrf_token": token(client), "titre": "Titre", "texte": "Le chat dort."}
        )
        assert recorded.headers["location"] == f"{url}?ok=revision"
        page = text(client.get(f"{url}?ok=revision"))
        assert "Synthèse enregistrée." in page
        assert "Votre synthèse" in page
        exported = text(client.post(f"{url}/export", data={"csrf_token": token(client)}))
        assert "Fichiers écrits dans exports : 2." in exported
    finally:
        demo.folder.close()
    assert (demo.folder.path / "exports" / "vulgarisation-general.docx").is_file()


def test_failures_and_prerequisites(tmp_path: Path) -> None:
    demo = _with_synthesis(tmp_path)
    try:
        jobs = BackgroundJobs()
        app = create_app(
            demo.folder, now=demo.clock, tool_version=TOOL_VERSION, jobs=jobs,
            provider_factory=factory(empty),
        )  # fmt: skip
        client = TestClient(app, base_url=BASE, follow_redirects=False)
        client.post("/synthese/vulgarisation/informed/ia",
                    data={"csrf_token": token(client), "plafond": "1"})  # fmt: skip
        jobs.wait(LAY_JOB.format(level="informed"), timeout=30)
        page = text(client.get("/synthese/vulgarisation/informed"))
        assert "L'IA n'a pas pu ébaucher de synthèse utilisable" in page
    finally:
        demo.folder.close()
    bare = build(tmp_path / "b")
    try:
        app = create_app(bare.folder, now=bare.clock, tool_version=TOOL_VERSION)
        client = TestClient(app, base_url=BASE, follow_redirects=False)
        assert "Activez d'abord une version de la grille" in text(
            client.get("/synthese/vulgarisation")
        )
        assert client.get("/synthese/vulgarisation/general").status_code == 404
    finally:
        bare.folder.close()
