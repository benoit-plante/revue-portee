"""Web page « Recherche » (tranche 1.3), with fake connectors and FakeProvider."""

import html
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from revue_portee.domain.search import Database, KeyArticle
from revue_portee.search import runs, strategies
from revue_portee.sources import SourceAnswer
from revue_portee.sources.http import SourceUnreachableError
from revue_portee.sources.pubmed import MeshCheck
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.web.app import create_app
from revue_portee.web.search_form import read_strategy_form
from support import TOOL_VERSION, fake_factory, make_clock, new_project

BASE = "http://127.0.0.1:8000"


@dataclass
class Source:
    database: Database
    fail: bool = False
    calls: list[str] = field(default_factory=list)

    def count(self, query: str) -> SourceAnswer:
        if self.fail:
            raise SourceUnreachableError(self.database.display_name, "api.example.test")
        self.calls.append(query)
        return SourceAnswer(count=len(query), ids=(), raw={})

    def among(self, query: str, ids: Sequence[str]) -> SourceAnswer:
        kept = tuple(i for i in ids if i != "R-2" or "parent" not in query)
        return SourceAnswer(count=len(kept), ids=kept, raw={})

    def resolve(self, article: KeyArticle) -> tuple[str | None, dict[str, Any]]:
        return f"R-{article.value}", {}


class Mesh:
    def mesh(self, heading: str) -> MeshCheck:
        found = heading == "Parenting"
        return MeshCheck(
            found=found, heading=heading if found else None, ui="D016487" if found else None, raw=()
        )


TERMS = fake_factory(
    {
        "SuggestTermsInput": lambda _item: {
            "suggestions": [
                {"block_code": "B1", "kind": "free_term", "line": "father*", "rationale": "Pères."},
                {
                    "block_code": "B1",
                    "kind": "descriptor",
                    "line": "mesh: Parent Programs",
                    "rationale": "M.",
                },
            ]
        }
    }
)


@pytest.fixture
def folder(tmp_path: Path) -> Iterator[ProjectFolder]:
    project = new_project(tmp_path)
    yield project
    project.close()


def client_for(folder: ProjectFolder, *, fail: bool = False) -> TestClient:
    app = create_app(
        folder,
        now=make_clock(),
        tool_version=TOOL_VERSION,
        provider_factory=TERMS,
        source_factory=lambda database: Source(database, fail=fail),
        descriptor_source=Mesh,
    )
    return TestClient(app, base_url=BASE, follow_redirects=False)


def text(response: Any) -> str:  # noqa: ANN401
    """Page text with entities decoded and non-breaking spaces as plain spaces."""
    return html.unescape(response.text).replace("\u00a0", " ")


def token(client: TestClient) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/recherche").text)
    assert match
    return match.group(1)


def post(client: TestClient, path: str, data: dict[str, Any]) -> Any:  # noqa: ANN401
    return client.post(path, data={"csrf_token": token(client)} | data)


STRATEGY_FORM = {
    "bloc-nouveau-libelle": "Parents",
    "bloc-nouveau-pcc": "population",
    "bloc-nouveau-role": "include",
    "bloc-nouveau-termes": "parent*\nmesh: Parenting\n\nparent*",
    "annee_debut": "2015",
    "langues": ["en", "fr"],
    "justification": "Première version",
}


def test_strategy_is_saved_and_queries_shown(folder: ProjectFolder) -> None:
    client = client_for(folder)
    page = client.get("/recherche")
    assert page.status_code == 200
    assert 'aria-current="page">Recherche' in text(page)
    response = post(client, "/recherche/strategie", STRATEGY_FORM)
    assert response.status_code == 303
    page = client.get("/recherche?enregistre=1")
    assert "Stratégie enregistrée." in text(page)
    assert '(parent*[tiab] OR "Parenting"[mh]) AND' in text(page)
    assert "english[la] OR french[la]" in text(page)
    version = strategies.current_strategy(folder)
    assert version is not None
    assert version.rationale == "Première version"
    assert [b.code for b in version.strategy.blocks] == ["B1"]
    # Second block, then removal of the first: codes are not reused.
    second = {
        "bloc-B1-libelle": "Parents",
        "bloc-B1-role": "include",
        "bloc-B1-termes": "parent*",
        "bloc-B1-retirer": "1",
        "bloc-nouveau-libelle": "Revues",
        "bloc-nouveau-role": "include",
        "bloc-nouveau-termes": '"scoping review"',
    }
    assert post(client, "/recherche/strategie", second).status_code == 303
    version = strategies.current_strategy(folder)
    assert version is not None
    assert [b.code for b in version.strategy.blocks] == ["B2"]


def test_invalid_terms_are_shown_with_the_typed_text(folder: ProjectFolder) -> None:
    client = client_for(folder)
    data = STRATEGY_FORM | {"bloc-nouveau-termes": "parent*\na AND b", "annee_fin": "20x"}
    response = post(client, "/recherche/strategie", data)
    assert response.status_code == 422
    assert "Bloc « Parents », ligne « a AND b »" in text(response)
    assert "quatre chiffres" in text(response)
    assert "a AND b</textarea>" in text(response)
    assert strategies.current_strategy(folder) is None
    empty = post(client, "/recherche/strategie", {"bloc-nouveau-termes": ""})
    assert empty.status_code == 422


def test_counts_descriptors_key_articles_and_sensitivity(folder: ProjectFolder) -> None:
    client = client_for(folder)
    post(client, "/recherche/strategie", STRATEGY_FORM)
    assert post(client, "/recherche/comptes/pubmed", {}).status_code == 303
    page = client.get("/recherche")
    assert "Compté le" in text(page)
    assert (
        client.post(
            "/recherche/comptes/psycinfo_ebsco", data={"csrf_token": token(client)}
        ).status_code
        == 404
    )
    assert post(client, "/recherche/descripteurs", {}).status_code == 303
    assert "existe (D016487)" in text(client.get("/recherche"))
    bad = post(client, "/recherche/articles-cles", {"articles": "1\ncourt"})
    assert bad.status_code == 422
    assert "« court »" in text(bad)
    assert post(client, "/recherche/articles-cles", {"articles": "1\n2"}).status_code == 303
    assert post(client, "/recherche/sensibilite/openalex", {}).status_code == 303
    page = client.get("/recherche")
    assert "Articles clés retrouvés : 1 sur 2" in text(page)
    assert "PMID 2" in text(page)
    checks = runs.sensitivity_checks(folder)
    assert checks[0][1].result.missed[0].responsible == ("B1",)


def test_unreachable_service_is_reported(folder: ProjectFolder) -> None:
    client = client_for(folder, fail=True)
    post(client, "/recherche/strategie", STRATEGY_FORM)
    response = post(client, "/recherche/comptes/openalex", {})
    assert response.status_code == 502
    assert "api.example.test" in text(response)


def test_term_suggestions_flow(folder: ProjectFolder) -> None:
    client = client_for(folder)
    assert "Enregistrez au moins un bloc" in text(client.get("/recherche"))
    post(client, "/recherche/strategie", STRATEGY_FORM)
    preview = post(client, "/recherche/suggestions/estimation", {})
    assert preview.status_code == 200
    assert "Coût estimé" in text(preview)
    assert post(client, "/recherche/suggestions", {}).status_code == 303
    page = client.get("/recherche")
    ids = re.findall(r'id="suggestion-([0-9A-Z]{26})"', page.text)
    assert len(ids) == 2
    assert "pas encore vérifié" in text(page)
    accepted = post(client, f"/recherche/suggestions/{ids[0]}", {"decision": "accepted"})
    assert accepted.status_code == 303
    again = post(client, f"/recherche/suggestions/{ids[0]}", {"decision": "accepted"})
    assert again.status_code == 422
    bad = post(client, f"/recherche/suggestions/{ids[1]}", {"decision": "modified", "terme": "(x"})
    assert bad.status_code == 422
    assert (
        post(client, "/recherche/suggestions/inconnue", {"decision": "accepted"}).status_code == 404
    )
    version = strategies.current_strategy(folder)
    assert version is not None
    assert version.number == 2


def test_form_reader_keeps_unknown_fields_out() -> None:
    form = read_strategy_form(
        {"bloc-x-termes": "a", "bloc-B1-termes": "a", "bloc-B1-pcc": "zz"}, ["xx"]
    )
    assert form.strategy is None
    assert any("choix" in e for e in form.errors)
