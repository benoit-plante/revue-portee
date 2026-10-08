"""Web page « Collecte » (tranche 1.4): background collection, RIS import, Crossref."""

import html
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from revue_portee.collect import enrichment
from revue_portee.domain.search import ConceptBlock, SearchStrategy, parse_term
from revue_portee.jobs.runner import BackgroundJobs
from revue_portee.search import strategies
from revue_portee.sources.http import SourceUnreachableError
from revue_portee.sources.records import FetchedPage, FetchedRecord
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.web.app import create_app
from support import TOOL_VERSION, make_clock, new_project

BASE = "http://127.0.0.1:8000"
FIXTURES = Path(__file__).parents[2] / "fixtures" / "ris"


class TwoPages:
    """Gives two pages; the first collection loses the network before page 2."""

    database: Any = None
    failed = False

    def fetch(self, query: str, cursor: str | None) -> FetchedPage:
        if cursor and not TwoPages.failed:
            TwoPages.failed = True
            raise SourceUnreachableError("OpenAlex", "api.openalex.org")
        page = int(cursor or 0)
        return FetchedPage(
            records=(FetchedRecord(original_id=f"W{page}", fields={"title": f"T{page}"}),),
            announced=2,
            next_cursor=None if page else "1",
            raw={"page": page},
        )


class NoCrossref:
    def work(self, doi: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        return None, {"status": 404}


@pytest.fixture
def folder(tmp_path: Path) -> Iterator[ProjectFolder]:
    project = new_project(tmp_path)
    strategies.save_strategy(
        project,
        SearchStrategy(
            blocks=(ConceptBlock(code="B1", label="P", terms=(parse_term("parent*"),)),)
        ),
        now=make_clock(),
        tool_version=TOOL_VERSION,
    )
    yield project
    project.close()


def text(response: Any) -> str:  # noqa: ANN401
    return html.unescape(response.text).replace(" ", " ")


def setup_client(folder: ProjectFolder) -> tuple[TestClient, BackgroundJobs]:
    jobs = BackgroundJobs()
    app = create_app(
        folder,
        now=make_clock(),
        tool_version=TOOL_VERSION,
        collector_factory=lambda _: TwoPages(),
        crossref_source=NoCrossref,
        jobs=jobs,
    )
    return TestClient(app, base_url=BASE, follow_redirects=False), jobs


def token(client: TestClient) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/collecte").text)
    assert match
    return match.group(1)


def test_collection_in_background_with_resumption(folder: ProjectFolder) -> None:
    TwoPages.failed = False
    client, jobs = setup_client(folder)
    page = client.get("/collecte")
    assert page.status_code == 200
    assert 'aria-current="page">Collecte' in page.text
    assert "parent*" in text(page)
    response = client.post("/collecte/lancer/openalex", data={"csrf_token": token(client)})
    assert response.status_code == 303
    [run_id] = jobs.keys()
    jobs.wait(run_id, 10)
    body = text(client.get("/collecte"))
    assert "Interrompue" in body
    assert "api.openalex.org" in body
    resume = client.post(f"/collecte/reprendre/{run_id}", data={"csrf_token": token(client)})
    assert resume.status_code == 303
    jobs.wait(run_id, 10)
    body = text(client.get("/collecte/etat"))
    assert "notices : 2 sur 2 (pages : 2)" in body
    assert "Références enregistrées : 2" in body  # counts refreshed with the progress
    assert "Terminée" in body
    again = client.post(f"/collecte/reprendre/{run_id}", data={"csrf_token": token(client)})
    assert again.status_code == 422
    assert (
        client.post("/collecte/reprendre/inconnu", data={"csrf_token": token(client)}).status_code
        == 404
    )
    assert (
        client.post("/collecte/lancer/zzz", data={"csrf_token": token(client)}).status_code == 404
    )
    TwoPages.failed = False  # this one is interrupted: it stays open
    first = client.post("/collecte/lancer/openalex", data={"csrf_token": token(client)})
    assert first.status_code == 303
    [_, open_run] = jobs.keys()
    jobs.wait(open_run, 10)
    twice = client.post("/collecte/lancer/openalex", data={"csrf_token": token(client)})
    assert twice.status_code == 422
    assert "n'est pas terminée" in text(twice)
    refused = client.post("/collecte/lancer/psycinfo_ebsco", data={"csrf_token": token(client)})
    assert refused.status_code == 422


def test_ris_import_and_crossref(folder: ProjectFolder) -> None:
    client, jobs = setup_client(folder)
    content = (FIXTURES / "eric-ebscohost.ris").read_bytes()
    response = client.post(
        "/collecte/import",
        data={"csrf_token": token(client), "base": ""},
        files={"fichier": ("eric.ris", content, "application/x-research-info-systems")},
    )
    assert response.status_code == 303
    page = text(client.get("/collecte?importe=1"))
    assert "Fichier importé." in page
    assert "— ERIC (EBSCOhost) — notices : 25" in page
    duplicate = client.post(
        "/collecte/import",
        data={"csrf_token": token(client)},
        files={"fichier": ("copie.ris", content, "text/plain")},
    )
    assert duplicate.status_code == 422
    assert "a déjà été importé le" in text(duplicate)
    broken = client.post(
        "/collecte/import",
        data={"csrf_token": token(client), "base": "APA PsycInfo (Ovid)"},
        files={
            "fichier": (
                "ovid.ris",
                b"TY  - JOUR\nTI  - T\nER  -\nTY  - JOUR\nER  -\n",
                "text/plain",
            )
        },
    )
    assert broken.status_code == 303
    page = text(client.get("/collecte"))
    assert "Problèmes trouvés : 1" in page
    assert "notice vide, non importée" in page
    assert client.post("/collecte/import", data={"csrf_token": token(client)}).status_code == 422
    expected = len(enrichment.enrichment_candidates(folder))
    assert expected > 0
    assert f"Notices à compléter : {expected}" in page
    client.post("/collecte/crossref", data={"csrf_token": token(client)})
    jobs.wait("crossref", 10)
    assert "Notices à compléter : 0" in text(client.get("/collecte"))
