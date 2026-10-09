"""The « Textes intégraux » page (tranche 2.1): open access in the background, uploads
one by one or as a set, texts declared not retrievable, text by page."""

import html
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from demo import (
    NOT_RETRIEVABLE,
    Demo,
    DemoFinder,
    broaden_and_reassess,
    build,
    create,
    deduplicate,
    reconcile,
    screen,
)
from revue_portee.jobs.runner import BackgroundJobs
from revue_portee.web import fulltext_view
from revue_portee.web.app import create_app
from support import TOOL_VERSION, make_clock, make_pdf, new_project

BASE = "http://127.0.0.1:8000"
CAREGIVERS = "Family caregivers of older adults living in rural areas: A qualitative study"


@pytest.fixture
def screened(tmp_path: Path) -> Iterator[Demo]:
    """The demonstration up to the end of the title and abstract screening."""
    demo = create(tmp_path)
    deduplicate(demo)
    screen(demo)
    reconcile(demo)
    broaden_and_reassess(demo)
    yield demo
    demo.folder.close()


def setup(demo: Demo) -> tuple[TestClient, BackgroundJobs]:
    jobs = BackgroundJobs()
    app = create_app(
        demo.folder,
        now=make_clock(),
        tool_version=TOOL_VERSION,
        open_access_finder=lambda: DemoFinder(demo.ids()),
        jobs=jobs,
    )
    return TestClient(app, base_url=BASE, follow_redirects=False), jobs


def text(response: object) -> str:
    return html.unescape(response.text)  # type: ignore[attr-defined]


def token(client: TestClient) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', text(client.get("/textes")))
    assert match is not None
    return match.group(1)


def row(page: str, label: str) -> str:
    match = re.search(rf'<th scope="row">{label}</th><td>([^<]*)</td>', page)
    assert match is not None, label
    return match.group(1)


def test_open_access_then_declaration_counted_by_hand(screened: Demo) -> None:
    client, jobs = setup(screened)
    page = text(client.get("/textes"))
    assert '<a href="/textes" aria-current="page">Textes intégraux</a>' in page
    assert (row(page, "Références recherchées"), row(page, "Pas encore cherchés")) == ("3", "3")
    assert "responsabilité de l'équipe" in page
    started = client.post("/textes/libres", data={"csrf_token": token(client)})
    assert started.status_code == 303
    jobs.wait(fulltext_view.JOB, timeout=30)
    assert jobs.error(fulltext_view.JOB) is None
    page = text(client.get("/textes/etat"))
    assert row(page, "Textes obtenus") == "2"
    assert row(page, "dont en libre accès").startswith("2 (66,7")
    assert row(page, "Non trouvés en libre accès") == "1"
    caregivers = screened.ids()["caregivers"]
    declared = client.post(
        f"/textes/{caregivers}/introuvable",
        data={"csrf_token": token(client), "raison": NOT_RETRIEVABLE},
    )
    assert declared.status_code == 303
    page = text(client.get("/textes?declare=1"))
    assert "Texte déclaré introuvable." in page
    assert row(page, "Déclarés introuvables") == "1"
    assert NOT_RETRIEVABLE in page
    # the diagram now counts the report not retrieved
    reports = text(client.get("/rapports/diagramme?langue=fr"))
    assert "Rapports non obtenus (n = 1)" in reports
    empty = client.post(
        f"/textes/{caregivers}/introuvable", data={"csrf_token": token(client), "raison": " "}
    )
    assert empty.status_code == 422


def test_text_by_page_and_pdf(tmp_path: Path) -> None:
    demo = build(tmp_path)
    try:
        client, _jobs = setup(demo)
        loneliness = demo.ids()["loneliness"]
        page = text(client.get(f"/textes/{loneliness}"))
        pdf = client.get(f"/textes/{loneliness}/pdf")
        missing = client.get(f"/textes/{demo.ids()['caregivers']}")
        csv = client.get("/textes/manquants.csv")
    finally:
        demo.folder.close()
    assert "Page 2" in page
    assert "We interviewed 24 older adults" in page
    assert "contient la bibliographie" in page  # page 3
    assert "libre accès (OpenAlex)" in page
    assert pdf.content.startswith(b"%PDF-")
    assert missing.status_code == 404
    assert csv.headers["content-disposition"] == 'attachment; filename="textes-manquants.csv"'
    assert NOT_RETRIEVABLE in csv.text


def test_uploads(tmp_path: Path) -> None:
    demo = build(tmp_path)
    try:
        client, _jobs = setup(demo)
        caregivers = demo.ids()["caregivers"]
        many = client.post(
            "/textes/televerser",
            data={"csrf_token": token(client)},
            files=[
                ("fichiers", ("aidants.pdf", make_pdf([CAREGIVERS]), "application/pdf")),
                ("fichiers", ("autre.pdf", make_pdf(["Something else"]), "application/pdf")),
                ("fichiers", ("casse.pdf", b"%PDF-1.4 broken", "application/pdf")),
            ],
        )  # fmt: skip
        assert many.status_code == 200
        page = text(many)
        assert "Ajouté : aidants.pdf (trouvé par titre)" in page
        assert "Aucune référence trouvée, l'ajouter depuis sa ligne ci-dessous : autre.pdf" in page
        assert "casse.pdf : Le fichier n'est pas un PDF lisible." in page
        one = client.post(
            f"/textes/{caregivers}/televerser",
            data={"csrf_token": token(client)},
            files={"fichier": ("v2.pdf", make_pdf(["Published version"]), "application/pdf")},
        )
        assert one.status_code == 303
        assert "Texte ajouté." in text(client.get("/textes?ajoute=1"))
        gardens = demo.ids()["gardens"]  # excluded: not sought
        refused = client.post(
            f"/textes/{gardens}/televerser",
            data={"csrf_token": token(client)},
            files={"fichier": ("x.pdf", make_pdf(["x"]), "application/pdf")},
        )
        assert refused.status_code == 422
        none = client.post("/textes/televerser", data={"csrf_token": token(client)})
        assert none.status_code == 422
        no_file = client.post(
            f"/textes/{caregivers}/televerser", data={"csrf_token": token(client)}
        )
        assert no_file.status_code == 422
        page = text(client.get("/textes"))
    finally:
        demo.folder.close()
    assert row(page, "dont ajoutés par l'équipe") == "1"


def test_page_before_the_screening(tmp_path: Path) -> None:
    folder = new_project(tmp_path)
    try:
        app = create_app(folder, now=make_clock(), tool_version=TOOL_VERSION)
        page = text(TestClient(app, base_url=BASE).get("/textes"))
    finally:
        folder.close()
    assert "Aucune référence n'est encore retenue pour le texte intégral" in page
