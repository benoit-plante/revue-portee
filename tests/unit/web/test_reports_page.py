"""The « Rapports » page: flow diagram, methods section and archive (tranche 1.8)."""

import html
import re
import zipfile
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from demo import Demo, build
from revue_portee.web.app import create_app
from support import TOOL_VERSION, make_clock, new_project

BASE = "http://127.0.0.1:8000"


@pytest.fixture
def demo(tmp_path: Path) -> Iterator[Demo]:
    built = build(tmp_path)
    yield built
    built.folder.close()


def client_for(demo: Demo) -> TestClient:
    app = create_app(demo.folder, now=make_clock(), tool_version=TOOL_VERSION)
    return TestClient(app, base_url=BASE, follow_redirects=False)


def text_of(response: object) -> str:
    return html.unescape(response.text)  # type: ignore[attr-defined]


def post(client: TestClient, path: str, **data: str) -> object:
    match = re.search(r'name="csrf_token" value="([^"]+)"', text_of(client.get("/rapports")))
    assert match is not None
    return client.post(path, data={"csrf_token": match.group(1)} | data)


def test_page_shows_the_numbers_counted_by_hand(demo: Demo) -> None:
    client = client_for(demo)
    page = text_of(client.get("/rapports"))
    assert '<a href="/rapports" aria-current="page">Rapports</a>' in page
    for label, value in (
        ("Références repérées", 9),
        ("Doublons retirés", 4),
        ("Références triées", 5),
        ("Références exclues", 2),
        ("Retenues pour le texte intégral", 3),
        ("Changements de critères réévalués", 1),
    ):
        assert f'<th scope="row">{label}</th><td>{value}</td>' in page
    assert "Diagramme provisoire" not in page


def test_provisional_page_before_the_screening(tmp_path: Path) -> None:
    folder = new_project(tmp_path)
    try:
        app = create_app(folder, now=make_clock(), tool_version=TOOL_VERSION)
        page = text_of(TestClient(app, base_url=BASE).get("/rapports"))
    finally:
        folder.close()
    assert "Diagramme provisoire : le tri principal n'a pas commencé." in page


@pytest.mark.parametrize("language", ["fr", "en"])
def test_diagram_and_methods_downloads(demo: Demo, language: str) -> None:
    client = client_for(demo)
    shown = client.get(f"/rapports/diagramme?langue={language}")
    assert shown.headers["content-type"] == "image/svg+xml; charset=utf-8"
    assert "content-disposition" not in shown.headers
    assert shown.text.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    saved = client.get(f"/rapports/diagramme?langue={language}&telecharger=1")
    assert f'filename="diagramme-{language}.svg"' in saved.headers["content-disposition"]
    markdown = client.get(f"/rapports/methode?langue={language}&format=md")
    assert f'filename="methode-{language}.md"' in markdown.headers["content-disposition"]
    assert markdown.text.startswith("# Soutien à la parentalité")
    word = client.get(f"/rapports/methode?langue={language}&format=docx")
    assert word.content[:2] == b"PK"


def test_unknown_exports(demo: Demo) -> None:
    client = client_for(demo)
    assert client.get("/rapports/diagramme?langue=de").status_code == 404
    assert client.get("/rapports/methode?langue=fr&format=pdf").status_code == 404
    assert client.get("/rapports/archives/../revue.sqlite").status_code == 404
    assert client.get("/rapports/archives/archive-publique-x.zip").status_code == 404


def test_archive_written_then_downloaded(demo: Demo) -> None:
    client = client_for(demo)
    refused = post(client, "/rapports/archive", sorte="secrete")
    assert refused.status_code == 422  # type: ignore[attr-defined]
    assert "Choisissez le type d'archive." in text_of(refused)
    done = post(client, "/rapports/archive", sorte="publique")
    assert done.status_code == 303  # type: ignore[attr-defined]
    location = done.headers["location"]  # type: ignore[attr-defined]
    name = re.search(r"archive=([^#]+)", location)
    assert name is not None
    page = text_of(client.get(location))
    assert f"Archive écrite : {name.group(1)}." in page
    download = client.get(f"/rapports/archives/{name.group(1)}")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(BytesIO(download.content)).namelist()
    assert any(n.endswith("/donnees/diagramme.json") for n in names)
    complete = post(client, "/rapports/archive", sorte="complete")
    assert complete.status_code == 303  # type: ignore[attr-defined]
    assert text_of(client.get("/rapports")).count("archive-") >= 2
