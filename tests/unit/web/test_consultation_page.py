"""The « Consultation » page (tranche 4.2): stakeholders, comments and responses."""

import html
import re
from pathlib import Path

from fastapi.testclient import TestClient

from revue_portee.web.app import create_app
from support import TOOL_VERSION, make_clock, new_project

BASE = "http://127.0.0.1:8000"


def text(response: object) -> str:
    return html.unescape(response.text).replace(" ", " ")  # type: ignore[attr-defined]


def token(client: TestClient) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', text(client.get("/consultation")))
    assert match is not None
    return match.group(1)


def test_consultation_page(tmp_path: Path) -> None:
    folder = new_project(tmp_path)
    try:
        app = create_app(folder, now=make_clock(), tool_version=TOOL_VERSION)
        client = TestClient(app, base_url=BASE, follow_redirects=False)
        page = text(client.get("/consultation"))
        assert '<a href="/consultation" aria-current="page">Consultation</a>' in page
        assert "Aucun commentaire pour l'instant." in page
        assert 'action="/consultation/commentaires"' not in page  # no stakeholder yet
        refused = client.post(
            "/consultation/parties-prenantes",
            data={"csrf_token": token(client), "nom": "A", "role": " "},
        )
        assert refused.status_code == 422
        added = client.post(
            "/consultation/parties-prenantes",
            data={"csrf_token": token(client), "nom": "Mireille", "role": "patiente partenaire"},
        )
        assert added.headers["location"] == "/consultation?ok=personne"
        page = text(client.get("/consultation?ok=personne"))
        assert "Partie prenante ajoutée." in page
        person = re.search(r'<option value="([0-9A-Z]{26})">PP1 — Mireille', page)
        assert person is not None
        base = {"csrf_token": token(client), "partie": person.group(1), "cible": "criteria",
                "recu_le": "2026-10-02", "texte": "Trop restrictif."}  # fmt: skip
        for wrong in ({"cible": "x"}, {"texte": " "}, {"partie": "X"}):
            assert client.post("/consultation/commentaires", data=base | wrong).status_code == 422
        recorded = client.post("/consultation/commentaires", data=base)
        assert recorded.headers["location"] == "/consultation?ok=commentaire"
        page = text(client.get("/consultation"))
        assert "PP1 (patiente partenaire) — critères d'admissibilité — 2026-10-02" in page
        assert "En attente d'une suite." in page
        comment = re.search(r'action="/consultation/commentaires/([0-9A-Z]{26})/suite"', page)
        assert comment is not None
        url = f"/consultation/commentaires/{comment.group(1)}/suite"
        answer = {"csrf_token": token(client), "suite": "noted", "texte": "Gardé pour la suite."}
        assert client.post(url, data=answer | {"suite": "x"}).status_code == 422
        assert client.post(url, data=answer | {"texte": " "}).status_code == 422
        unknown = client.post("/consultation/commentaires/X/suite", data=answer)
        assert unknown.status_code == 404
        assert client.post(url, data=answer).status_code == 303
        page = text(client.get("/consultation"))
        assert "<strong>pris en compte sans modification</strong> : Gardé pour la suite." in page
        assert "en attente d'une suite : 0." in page
        exported = text(client.post("/consultation/export", data={"csrf_token": token(client)}))
        assert "Suivi écrit dans exports/suivi-commentaires.csv." in exported
    finally:
        folder.close()
