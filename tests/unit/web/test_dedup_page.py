"""Web page « Doublons » (tranche 1.5): numbers, pairs side by side, undoing groupings."""

import html
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from revue_portee.collect import deduplication, imports
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.web import dedup_view
from revue_portee.web.app import create_app
from support import TOOL_VERSION, make_clock, new_project

BASE = "http://127.0.0.1:8000"
DEMO = Path(__file__).parents[2] / "fixtures" / "dedup"


@pytest.fixture
def folder(tmp_path: Path) -> Iterator[ProjectFolder]:
    project = new_project(tmp_path)
    yield project
    project.close()


def load_demo(folder: ProjectFolder) -> None:
    clock = make_clock()
    for name, database in (
        ("demo-psycinfo.ris", "APA PsycInfo (EBSCOhost)"),
        ("demo-cinahl.ris", "CINAHL (EBSCOhost)"),
        ("demo-pubmed.ris", "PubMed"),
    ):
        imports.import_ris(
            folder,
            name,
            (DEMO / name).read_bytes(),
            database=database,
            now=clock,
            tool_version=TOOL_VERSION,
        )


def text(response: Any) -> str:  # noqa: ANN401
    return html.unescape(response.text).replace(" ", " ")


def client_for(folder: ProjectFolder) -> TestClient:
    app = create_app(folder, now=make_clock(), tool_version=TOOL_VERSION)
    return TestClient(app, base_url=BASE, follow_redirects=False)


def token(client: TestClient) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/doublons").text)
    assert match
    return match.group(1)


def test_page_without_references(folder: ProjectFolder) -> None:
    client = client_for(folder)
    page = client.get("/doublons")
    assert page.status_code == 200
    assert 'aria-current="page">Doublons' in page.text
    assert "Aucune référence pour l'instant" in text(page)
    response = client.post("/doublons/lancer", data={"csrf_token": token(client)})
    assert response.status_code == 422
    assert "aucune référence à dédoublonner" in text(response)


def test_run_review_and_undo(folder: ProjectFolder) -> None:
    load_demo(folder)
    client = client_for(folder)
    response = client.post(
        "/doublons/lancer",
        data={"csrf_token": token(client), "review_from": "0,75", "auto_from": "0,93"},
    )
    assert response.status_code == 303
    body = text(client.get("/doublons?fait=1"))
    assert "Dédoublonnage effectué." in body
    assert "Doublons retirés</th><td>3" in body
    assert "Références après dédoublonnage</th><td>6" in body
    assert "Paires encore à examiner : 1." in body
    assert "seuils 0,75 et 0,93" in body
    assert "Non regroupées automatiquement : premier auteur différent ou absent." in body
    assert 'class="differs"' in body  # the authors differ
    state = deduplication.dedup_state(folder)
    (pending,) = state.pending
    decided = client.post(
        "/doublons/paire",
        data={
            "csrf_token": token(client),
            "reference_a": pending.reference_a_id,
            "reference_b": pending.reference_b_id,
            "outcome": "not_duplicate",
        },
    )
    assert decided.status_code == 303
    assert decided.headers["location"] == "/doublons#paires"
    body = text(client.get("/doublons"))
    assert "Aucune paire à examiner." in body
    assert "gardées séparées le" in body
    # undo an automatic grouping from the list of groups
    a, b = sorted(state.links)[0]
    undone = client.post(
        "/doublons/paire",
        data={
            "csrf_token": token(client),
            "reference_a": a,
            "reference_b": b,
            "outcome": "not_duplicate",
            "retour": "groupes",
        },
    )
    assert undone.headers["location"] == "/doublons#groupes"
    assert (a, b) not in deduplication.dedup_state(folder).links
    regroup = client.post(
        "/doublons/paire",
        data={
            "csrf_token": token(client),
            "reference_a": a,
            "reference_b": b,
            "outcome": "duplicate",
            "retour": "ailleurs",
        },
    )
    assert regroup.headers["location"] == "/doublons#paires"
    assert (a, b) in deduplication.dedup_state(folder).links


def test_invalid_requests(folder: ProjectFolder) -> None:
    load_demo(folder)
    client = client_for(folder)
    bad = client.post(
        "/doublons/lancer",
        data={"csrf_token": token(client), "review_from": "0,95", "auto_from": "0,9"},
    )
    assert bad.status_code == 422
    assert "Les seuils doivent être des nombres de 0 à 1" in text(bad)
    unreadable = client.post(
        "/doublons/lancer", data={"csrf_token": token(client), "review_from": "beaucoup"}
    )
    assert unreadable.status_code == 422
    unknown = client.post(
        "/doublons/paire",
        data={"csrf_token": token(client), "reference_a": "A", "reference_b": "B", "outcome": "x"},
    )
    assert unknown.status_code == 422
    not_a_pair = client.post(
        "/doublons/paire",
        data={
            "csrf_token": token(client),
            "reference_a": "A",
            "reference_b": "B",
            "outcome": "duplicate",
        },
    )
    assert not_a_pair.status_code == 422
    assert "ne forment pas une paire" in text(not_a_pair)
    assert client.post("/doublons/lancer", data={"csrf_token": "faux"}).status_code == 403


def test_groups_are_shown_page_by_page(folder: ProjectFolder) -> None:
    load_demo(folder)
    client = client_for(folder)
    client.post("/doublons/lancer", data={"csrf_token": token(client)})
    body = text(client.get("/doublons?page=7"))  # beyond the last page: the last one
    assert "Groupes : 2 ; doublons : 3." in body
    assert "Principale :" in body
    assert "automatique, même DOI" in body
    groups = deduplication.dedup_state(folder).groups
    assert dedup_view.page_of(groups * 30, 2) == ((groups * 30)[50:60], 2)
    assert dedup_view.parse_threshold(" ", 0.5) == 0.5
