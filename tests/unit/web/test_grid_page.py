"""The « Grille d'extraction » page (tranche 3.1): starting grid, fields added,
modified and removed in a draft, activation with a rationale, history and changes."""

import html
import re
from pathlib import Path

from fastapi.testclient import TestClient

from revue_portee.web.app import create_app
from support import TOOL_VERSION, make_clock, new_project

BASE = "http://127.0.0.1:8000"


def text(response: object) -> str:
    return html.unescape(response.text).replace(" ", " ")  # type: ignore[attr-defined]


def post(client: TestClient, path: str, **data: str) -> object:
    match = re.search(r'name="csrf_token" value="([^"]+)"', text(client.get("/grille")))
    assert match is not None
    return client.post(path, data={"csrf_token": match.group(1)} | data)


def test_grid_page(tmp_path: Path) -> None:
    folder = new_project(tmp_path)
    try:
        app = create_app(folder, now=make_clock(), tool_version=TOOL_VERSION)
        client = TestClient(app, base_url=BASE, follow_redirects=False)
        page = text(client.get("/grille"))
        assert '<a href="/grille" aria-current="page">Grille</a>' in page
        assert "Aucune version de la grille n'est encore en vigueur." in page
        assert post(client, "/grille/modele").status_code == 303  # type: ignore[attr-defined]
        page = text(client.get("/grille?ok=modele"))
        assert "Champs de la grille de départ ajoutés au brouillon." in page
        assert "Taille de l'échantillon" in page
        added = post(
            client, "/grille/ajouter", libelle="Financement", type="single_choice",
            choix="Public\nPrivé\n\nAucun", definition="Source du financement.",
        )  # fmt: skip
        assert added.status_code == 303  # type: ignore[attr-defined]
        bad = post(client, "/grille/ajouter", libelle="Devis", type="single_choice", choix="Un")
        assert bad.status_code == 422  # type: ignore[attr-defined]
        assert "au moins deux choix distincts" in text(bad)
        removed = post(client, "/grille/D11/retirer")
        assert removed.status_code == 303  # type: ignore[attr-defined]
        unknown = post(client, "/grille/D99/retirer")
        assert unknown.status_code == 422  # type: ignore[attr-defined]
        assert post(client, "/grille/activer").status_code == 303  # type: ignore[attr-defined]
        page = text(client.get("/grille?ok=activation"))
        assert "La nouvelle version de la grille est en vigueur." in page
        assert "Version 1, en vigueur depuis" in page
        modified = post(
            client, "/grille/D12/modifier", libelle="Financement", type="multiple_choice",
            choix="Public\nPrivé\nAucun\nInconnu", definition="Source du financement.",
        )  # fmt: skip
        assert modified.status_code == 303  # type: ignore[attr-defined]
        refused = post(client, "/grille/activer", justification=" ")
        assert refused.status_code == 422  # type: ignore[attr-defined]
        assert "Une nouvelle version de la grille exige une justification." in text(refused)
        page = text(client.get("/grille"))
        assert "Modifié : D12 (type, choix)" in page
        done = post(client, "/grille/activer", justification="Plusieurs sources de financement.")
        assert done.status_code == 303  # type: ignore[attr-defined]
        page = text(client.get("/grille"))
        assert "Plusieurs sources de financement." in page  # history
        assert post(client, "/grille/abandonner").status_code == 422  # type: ignore[attr-defined]
        post(client, "/grille/ajouter", libelle="Année", type="number")
        assert post(client, "/grille/abandonner").status_code == 303  # type: ignore[attr-defined]
        assert "Brouillon abandonné." in text(client.get("/grille?ok=abandon"))
    finally:
        folder.close()
