"""The « Déclaration » page (tranche 4.3): the PRISMA-ScR checklist filled from the
project, and its export in French and English."""

import html
import re
from pathlib import Path

from fastapi.testclient import TestClient

from demo import build_extracted
from revue_portee.web.app import create_app
from support import TOOL_VERSION

BASE = "http://127.0.0.1:8000"


def text(response: object) -> str:
    return html.unescape(response.text).replace(" ", " ")  # type: ignore[attr-defined]


def token(client: TestClient) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', text(client.get("/declaration")))
    assert match is not None
    return match.group(1)


def test_declaration_page(tmp_path: Path) -> None:
    demo = build_extracted(tmp_path)
    try:
        app = create_app(demo.folder, now=demo.clock, tool_version=TOOL_VERSION)
        client = TestClient(app, base_url=BASE, follow_redirects=False)
        page = text(client.get("/declaration"))
        assert '<a href="/declaration" aria-current="page">Déclaration</a>' in page
        assert '<option value="prisma-scr-2018" selected>PRISMA-ScR 2018</option>' in page
        assert "Éléments avec une proposition : 14 sur 22." in page
        assert '12 <span class="small">(facultatif)</span>' in page
        assert "À compléter par l'équipe." in page
        assert client.get("/declaration?liste=prisma-2099").status_code == 404
        for language, expected in (
            ("fr", "prisma-scr-2018-fr.md"),
            ("en", "prisma-scr-2018-en.md"),
        ):
            exported = client.post(
                "/declaration/export",
                data={"csrf_token": token(client), "liste": "prisma-scr-2018", "langue": language},
            )
            assert "Fichiers écrits dans exports : 2." in text(exported)
            assert (demo.folder.path / "exports" / expected).is_file()
        refused = client.post("/declaration/export",
                              data={"csrf_token": token(client), "langue": "de"})  # fmt: skip
        assert refused.status_code == 404
        unknown = client.post("/declaration/export",
                              data={"csrf_token": token(client), "liste": "x"})  # fmt: skip
        assert unknown.status_code == 404
    finally:
        demo.folder.close()
    english = (demo.folder.path / "exports" / "prisma-scr-2018-en.md").read_text(encoding="utf-8")
    assert "Items with a proposal: 14 of 22." in english
