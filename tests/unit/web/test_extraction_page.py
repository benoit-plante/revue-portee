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
        assert "Champs rapportés : 2 sur 3." in page
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
