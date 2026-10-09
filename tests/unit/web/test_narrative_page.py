"""The « Synthèse narrative » pages (tranche 3.6): the AI's draft in the background,
the person's revision, each sentence resting on included studies, and the export."""

import html
import re
from pathlib import Path

from fastapi.testclient import TestClient

from demo import build, build_extracted
from revue_portee.jobs.runner import BackgroundJobs
from revue_portee.web.app import NARRATIVE_JOB, create_app
from support import TOOL_VERSION
from unit.extraction.test_prefill import factory
from unit.synthesis.test_narrative import AI_TEXT, drafted, unknown_key

BASE = "http://127.0.0.1:8000"


def text(response: object) -> str:
    return html.unescape(response.text).replace(" ", " ")  # type: ignore[attr-defined]


def token(client: TestClient) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', text(client.get("/grille")))
    assert match is not None
    return match.group(1)


def test_draft_then_revision(tmp_path: Path) -> None:
    demo = build_extracted(tmp_path)
    ref = demo.ids()["loneliness"]
    try:
        jobs = BackgroundJobs()
        app = create_app(
            demo.folder, now=demo.clock, tool_version=TOOL_VERSION, jobs=jobs,
            provider_factory=factory(drafted),
        )  # fmt: skip
        client = TestClient(app, base_url=BASE, follow_redirects=False)
        assert '<a href="/synthese/narratif">Synthèse narrative</a>' in text(
            client.get("/synthese")
        )
        listing = text(client.get("/synthese/narratif"))
        assert '<a href="/synthese" aria-current="page">Synthèse</a>' in listing
        assert "D1 — Devis</a></th>\n      <td>1</td>\n      <td>—</td>" in listing
        page = text(client.get("/synthese/narratif/D1"))
        assert f'<a href="/extraction/{ref}">' in page
        assert client.get("/synthese/narratif/D9").status_code == 404
        estimate = client.post("/synthese/narratif/D1/ia/estimation",
                               data={"csrf_token": token(client)})  # fmt: skip
        assert "Demander une ébauche à l'IA (confirmer le coût)" in text(estimate)
        bad = client.post("/synthese/narratif/D1/ia", data={"csrf_token": token(client),
                                                           "plafond": "x"})  # fmt: skip
        assert bad.status_code == 422
        started = client.post(
            "/synthese/narratif/D1/ia", data={"csrf_token": token(client), "plafond": "1"}
        )
        assert started.headers["location"] == "/synthese/narratif/D1?ok=ia"
        jobs.wait(NARRATIVE_JOB.format(code="D1"), timeout=30)
        assert jobs.error(NARRATIVE_JOB.format(code="D1")) is None
        page = text(client.get("/synthese/narratif/D1"))
        assert "Ébauche de l'IA non révisée" in page
        assert AI_TEXT in page
        assert "ébauche de l'IA, à réviser" in text(client.get("/synthese/narratif"))
        form = {"csrf_token": token(client), "nombre": "3", "phrase-0": "Une étude qualitative.",
                "etudes-0": ref, "phrase-1": "", "phrase-2": "Sans étude."}  # fmt: skip
        refused = client.post("/synthese/narratif/D1", data=form)
        assert refused.status_code == 422
        assert "Chaque phrase doit reposer sur au moins une étude (phrase 3)." in text(refused)
        empty = client.post(
            "/synthese/narratif/D1",
            data={"csrf_token": token(client), "nombre": "1", "phrase-0": ""},
        )
        assert empty.status_code == 422
        del form["phrase-2"]
        recorded = client.post("/synthese/narratif/D1", data=form)
        assert recorded.headers["location"] == "/synthese/narratif/D1?ok=revision"
        page = text(client.get("/synthese/narratif/D1?ok=revision"))
        assert "Synthèse enregistrée." in page
        assert "Votre synthèse" in page
        assert "<td>révisée</td>" in text(client.get("/synthese/narratif"))
        exported = text(client.post("/synthese/narratif/export",
                                    data={"csrf_token": token(client)}))  # fmt: skip
        assert "Fichiers écrits dans exports/synthese : 2." in exported
    finally:
        demo.folder.close()
    markdown = (demo.folder.path / "exports" / "synthese" / "narratif-fr.md").read_text(
        encoding="utf-8"
    )
    assert "Une étude qualitative (" in markdown
    assert AI_TEXT not in markdown


def test_failed_draft_and_errors(tmp_path: Path) -> None:
    demo = build_extracted(tmp_path)
    try:
        jobs = BackgroundJobs()
        app = create_app(
            demo.folder, now=demo.clock, tool_version=TOOL_VERSION, jobs=jobs,
            provider_factory=factory(unknown_key),
        )  # fmt: skip
        client = TestClient(app, base_url=BASE, follow_redirects=False)
        client.post("/synthese/narratif/D2/ia", data={"csrf_token": token(client), "plafond": "1"})
        jobs.wait(NARRATIVE_JOB.format(code="D2"), timeout=30)
        page = text(client.get("/synthese/narratif/D2"))
        assert "L'IA n'a pas pu ébaucher de synthèse utilisable" in page
        assert client.post("/synthese/narratif/D9", data={"csrf_token": token(client)}
                           ).status_code == 404  # fmt: skip
    finally:
        demo.folder.close()


def test_without_grid(tmp_path: Path) -> None:
    demo = build(tmp_path)
    try:
        app = create_app(demo.folder, now=demo.clock, tool_version=TOOL_VERSION)
        client = TestClient(app, base_url=BASE, follow_redirects=False)
        assert "Activez d'abord une version de la grille d'extraction." in text(
            client.get("/synthese/narratif")
        )
        assert client.get("/synthese/narratif/D1").status_code == 404
    finally:
        demo.folder.close()
