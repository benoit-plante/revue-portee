import html
import re
from collections.abc import Iterator
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from revue_portee.domain.journal import EntryType
from revue_portee.protocol import notes
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.web.app import create_app
from support import TOOL_VERSION, make_clock, new_project

BASE = "http://127.0.0.1:8000"


@pytest.fixture
def folder(tmp_path: Path) -> Iterator[ProjectFolder]:
    project = new_project(tmp_path)
    yield project
    project.close()


@pytest.fixture
def client(folder: ProjectFolder) -> TestClient:
    app = create_app(folder, now=make_clock(), tool_version=TOOL_VERSION)
    return TestClient(app, base_url=BASE, follow_redirects=False)


def html_text(response: object) -> str:
    """Response body with HTML entities decoded (apostrophes are escaped by Jinja)."""
    return html.unescape(response.text)  # type: ignore[attr-defined]  # type: ignore[attr-defined]


def token(client: TestClient, path: str = "/cadrage") -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html_text(client.get(path)))
    assert match is not None
    return match.group(1)


def post(client: TestClient, path: str, **data: str) -> object:
    return client.post(path, data={"csrf_token": token(client)} | data)


SIX = [
    ("population", "inclusion", "Parents ou tuteurs d'enfants de 0 à 12 ans"),
    ("population", "exclusion", "Enfants avec un trouble du spectre de l'autisme"),
    ("concept", "inclusion", "Intervention de soutien à la parentalité"),
    ("concept", "inclusion", "Résultat sur la santé mentale de l'enfant"),
    ("context", "inclusion", "Services communautaires ou de première ligne"),
    ("other", "exclusion", "Langue autre que le français ou l'anglais"),
]


def test_home_redirects_to_framing(client: TestClient) -> None:
    response = client.get("/")
    assert (response.status_code, response.headers["location"]) == (303, "/cadrage")


def test_framing_page_is_french_and_saves(client: TestClient, folder: ProjectFolder) -> None:
    page = client.get("/cadrage")
    assert page.status_code == 200
    assert "Cadrage de la question de recherche" in html_text(page)
    assert 'lang="fr"' in html_text(page)
    response = post(
        client,
        "/cadrage",
        question="Quelles interventions ?",
        population="Parents",
        concept="Soutien",
        contexte="Communautaire",
        questions_secondaires="Quels résultats ?\n\nQuels contextes ?",
    )
    assert response.status_code == 303  # type: ignore[attr-defined]
    saved = html_text(client.get("/cadrage?enregistre=1"))
    assert "Cadrage enregistré." in saved
    assert "Quels résultats ?\nQuels contextes ?" in saved
    assert notes.journal_entries(folder)[-1].entry_type == EntryType.FRAMING_UPDATED


def test_framing_requires_a_question(client: TestClient) -> None:
    response = post(client, "/cadrage", question="  ")
    assert response.status_code == 422  # type: ignore[attr-defined]
    assert "La question principale est obligatoire." in html_text(response)


def test_criteria_workflow_to_version_2(client: TestClient, folder: ProjectFolder) -> None:
    assert "Aucune version des critères n'est encore en vigueur." in html_text(
        client.get("/criteres")
    )
    assert post(client, "/criteres/brouillon").status_code == 303  # type: ignore[attr-defined]
    for element, kind, text in SIX:
        response = post(
            client, "/criteres/brouillon/ajouter", element=element, nature=kind, texte=text,
            exemples="Exemple A\nExemple B",
        )  # fmt: skip
        assert response.status_code == 303  # type: ignore[attr-defined]
    response = post(client, "/criteres/activer", justification="")
    assert response.headers["location"] == "/criteres/versions/1"  # type: ignore[attr-defined]
    page = html_text(client.get("/criteres"))
    for code in ("P1", "P2", "C1", "C2", "CTX1", "X1"):
        assert f"<code>{code}</code>" in page

    # Editing a criterion of the version in force starts version 2.
    form = html_text(client.get("/criteres/brouillon/P1"))
    assert "la version en vigueur reste inchangée" in form
    post(
        client,
        "/criteres/brouillon/P1",
        nature="inclusion",
        texte="Parents d'enfants de 0 à 17 ans",
    )
    page = html_text(client.get("/criteres"))
    assert "Brouillon de la version 2" in page
    assert "Modifié\u00a0: P1" in page

    refused = post(client, "/criteres/activer", justification=" ")
    assert refused.status_code == 422  # type: ignore[attr-defined]
    assert "Une justification est obligatoire" in html_text(refused)
    unqualified = post(client, "/criteres/activer", justification="Inclure les adolescents")
    assert unqualified.status_code == 422  # type: ignore[attr-defined]
    assert "Confirmez le type de changement" in html_text(unqualified)
    done = client.post(
        "/criteres/activer",
        data={
            "csrf_token": token(client),
            "justification": "Inclure les adolescents",
            "qualification-P1": "broadening",
        },
    )
    assert done.headers["location"] == "/criteres/versions/2"

    version_1 = html_text(client.get("/criteres/versions/1"))
    assert "0 à 12 ans" in version_1
    assert "remplacée" in version_1
    diff = html_text(client.get("/criteres/differentiel?de=1&a=2"))
    assert "Différences entre la version 1 et la version 2" in diff
    assert "modifié\u00a0: Libellé" in diff
    assert "0 à 17 ans" in diff
    assert notes.verify_journal(folder).valid


def test_remove_and_discard(client: TestClient) -> None:
    post(client, "/criteres/brouillon/ajouter", element="population", nature="inclusion", texte="A")
    post(client, "/criteres/brouillon/ajouter", element="concept", nature="inclusion", texte="B")
    assert post(client, "/criteres/brouillon/P1/retirer").status_code == 303  # type: ignore[attr-defined]
    assert "<code>P1</code>" not in html_text(client.get("/criteres"))
    assert post(client, "/criteres/abandonner").status_code == 303  # type: ignore[attr-defined]
    assert "Commencer les critères" in html_text(client.get("/criteres"))


def test_form_errors(client: TestClient) -> None:
    empty = post(client, "/criteres/brouillon/ajouter", element="population", nature="inclusion")
    assert empty.status_code == 422  # type: ignore[attr-defined]
    no_draft = post(client, "/criteres/activer", justification="x")
    assert no_draft.status_code == 404  # type: ignore[attr-defined]
    assert "Il n'y a aucun brouillon des critères." in html_text(no_draft)
    post(client, "/criteres/brouillon")
    nothing = post(client, "/criteres/activer", justification="")
    assert "Ajoutez au moins un critère" in html_text(nothing)
    assert client.get("/criteres/brouillon/P9").status_code == 404
    assert client.get("/criteres/versions/7").status_code == 404
    assert client.get("/criteres/differentiel?de=1&a=2").status_code == 404
    assert post(client, "/criteres/brouillon/P9", nature="inclusion", texte="x").status_code == 404  # type: ignore[attr-defined]
    assert post(client, "/criteres/brouillon/P9/retirer").status_code == 404  # type: ignore[attr-defined]


def test_journal_page_and_notes(client: TestClient) -> None:
    page = html_text(client.get("/journal"))
    assert "Journal intègre\u00a0: 1 entrée, chaîne d'empreintes vérifiée." in page
    assert post(client, "/journal/notes", note="Réunion d'équipe du 7 octobre").status_code == 303  # type: ignore[attr-defined]
    page = html_text(client.get("/journal"))
    assert "Réunion d'équipe du 7 octobre" in page
    assert "Journal intègre\u00a0: 2 entrées" in page
    assert post(client, "/journal/notes", note=" ").status_code == 422  # type: ignore[attr-defined]


def test_writes_require_the_form_token(client: TestClient) -> None:
    for path in ("/cadrage", "/criteres/brouillon", "/journal/notes"):
        missing = client.post(path, data={"question": "x", "note": "x"})
        assert missing.status_code == 403
        assert "Jeton de formulaire invalide" in html_text(missing)
        wrong = client.post(path, data={"csrf_token": "forged", "note": "x"})
        assert wrong.status_code == 403


def test_foreign_host_and_origin_are_refused(client: TestClient) -> None:
    assert client.get("/cadrage", headers={"host": "attacker.example"}).status_code == 400
    forged = client.post(
        "/journal/notes",
        data={"csrf_token": token(client), "note": "x"},
        headers={"origin": "https://attacker.example"},
    )
    assert forged.status_code == 403
    local = client.post(
        "/journal/notes",
        data={"csrf_token": token(client), "note": "ok"},
        headers={"origin": BASE},
    )
    assert local.status_code == 303


def test_static_files_are_served(client: TestClient) -> None:
    assert client.get("/statique/app.css").status_code == 200
    assert client.get("/statique/vendor/htmx-2.0.11.min.js").status_code == 200


class _FormAudit(HTMLParser):
    """Collects what keyboard and screen-reader use depends on."""

    def __init__(self) -> None:
        super().__init__()
        self.labels: set[str] = set()
        self.fields: list[tuple[str, str | None]] = []
        self.wrapped_depth = 0
        self.positive_tabindex = False
        self.skip_link = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "label":
            if attributes.get("for"):
                self.labels.add(str(attributes["for"]))
            else:
                self.wrapped_depth += 1
        visible_field = (
            tag in {"input", "textarea", "select"} and attributes.get("type") != "hidden"
        )
        if visible_field and not self.wrapped_depth:
            self.fields.append((tag, attributes.get("id")))
        tabindex = attributes.get("tabindex")
        if tabindex and int(tabindex) > 0:
            self.positive_tabindex = True
        if tag == "a" and attributes.get("href") == "#contenu":
            self.skip_link = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "label" and self.wrapped_depth:
            self.wrapped_depth -= 1


@pytest.mark.parametrize("path", ["/cadrage", "/criteres", "/journal", "/criteres/brouillon/P1"])
def test_pages_are_usable_with_the_keyboard(client: TestClient, path: str) -> None:
    post(client, "/criteres/brouillon/ajouter", element="population", nature="inclusion", texte="A")
    audit = _FormAudit()
    audit.feed(html_text(client.get(path)))
    unlabeled = [field for field in audit.fields if field[1] not in audit.labels]
    assert unlabeled == []
    assert audit.skip_link
    assert not audit.positive_tabindex


def test_htmx_shows_error_responses(client: TestClient) -> None:
    # hx-boost would otherwise drop the 4xx pages that carry form errors (checked in
    # Chromium: without this setting, « La question principale est obligatoire. » never shows).
    page = client.get("/cadrage").text
    match = re.search(r"<meta name=\"htmx-config\" content='([^']+)'>", page)
    assert match is not None
    import json

    rules = json.loads(match.group(1))["responseHandling"]
    assert {"code": "[45]..", "swap": True, "error": True} in rules
