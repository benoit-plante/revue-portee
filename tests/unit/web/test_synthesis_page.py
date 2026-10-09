"""The « Synthèse » page (tranche 3.5): frequency tables, evidence map, gaps commented
and exports, on the demonstration extracted by hand."""

import html
import re
from pathlib import Path

from fastapi.testclient import TestClient

from demo import build, build_extracted
from revue_portee.web.app import create_app
from support import TOOL_VERSION

BASE = "http://127.0.0.1:8000"


def text(response: object) -> str:
    return html.unescape(response.text).replace(" ", " ")  # type: ignore[attr-defined]


def token(client: TestClient) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', text(client.get("/grille")))
    assert match is not None
    return match.group(1)


def test_synthesis_page(tmp_path: Path) -> None:
    demo = build_extracted(tmp_path)
    try:
        app = create_app(demo.folder, now=demo.clock, tool_version=TOOL_VERSION)
        client = TestClient(app, base_url=BASE, follow_redirects=False)
        page = text(client.get("/synthese"))
        assert '<a href="/synthese" aria-current="page">Synthèse</a>' in page
        assert "Études incluses : 1." in page
        assert '<tr><th scope="row">Qualitatif</th><td>1</td><td>100,0 %</td></tr>' in page
        assert "<svg" not in page
        same = client.get("/synthese?lignes=D1&colonnes=D1")
        assert same.status_code == 422
        assert "Choisissez deux champs différents." in text(same)
        assert client.get("/synthese?lignes=D1&colonnes=D9").status_code == 404
        shown = text(client.get("/synthese?lignes=D1&colonnes=D2&seuil=1"))
        assert shown.count("<circle ") == 1
        assert shown.count('name="ligne"') == 9  # 8 empty cells and 1 sparse
        commented = client.post(
            "/synthese/lacune",
            data={"csrf_token": token(client), "lignes": "D1", "colonnes": "D2", "seuil": "1",
                  "ligne": "Mixte", "colonne": "Hôpital", "commentaire": "Aucune étude mixte"},
        )  # fmt: skip
        assert commented.status_code == 303
        assert commented.headers["location"] == "/synthese?lignes=D1&colonnes=D2&seuil=1#lacunes"
        shown = text(client.get(commented.headers["location"]))
        assert ">Aucune étude mixte</textarea>" in shown
        unknown = {"csrf_token": token(client), "lignes": "D1", "colonnes": "D2",
                   "ligne": "Autre", "colonne": "Hôpital"}  # fmt: skip
        assert client.post("/synthese/lacune", data=unknown).status_code == 404
        exported = text(
            client.post(
                "/synthese/export",
                data={"csrf_token": token(client), "lignes": "D1", "colonnes": "D2"},
            )
        )
        assert "Fichiers écrits dans exports/synthese : 9." in exported
        tables_only = text(client.post("/synthese/export", data={"csrf_token": token(client)}))
        assert "Fichiers écrits dans exports/synthese : 5." in tables_only
    finally:
        demo.folder.close()
    assert (demo.folder.path / "exports" / "synthese" / "carte-D1-D2-fr.html").is_file()


def test_without_grid(tmp_path: Path) -> None:
    demo = build(tmp_path)
    try:
        app = create_app(demo.folder, now=demo.clock, tool_version=TOOL_VERSION)
        client = TestClient(app, base_url=BASE, follow_redirects=False)
        assert "Activez d'abord une version de la grille d'extraction." in text(
            client.get("/synthese")
        )
        refused = client.post("/synthese/export", data={"csrf_token": token(client)})
        assert refused.status_code == 422
    finally:
        demo.folder.close()
