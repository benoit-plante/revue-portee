"""The English interface (ENF-LAN-03, tranche 4.5): the language is chosen by the person,
kept in a cookie, and every page follows it: words, typography and numbers."""

import html
import re
from pathlib import Path

from fastapi.testclient import TestClient

from demo import build_extracted
from revue_portee.i18n import current_locale
from revue_portee.web.app import LOCALE_COOKIE, create_app
from support import TOOL_VERSION

BASE = "http://127.0.0.1:8000"


def text(response: object) -> str:
    return html.unescape(response.text)  # type: ignore[attr-defined]


def token(page: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', page)
    assert match is not None
    return match.group(1)


def test_switch_to_english_and_back(tmp_path: Path) -> None:
    demo = build_extracted(tmp_path)
    try:
        app = create_app(demo.folder, now=demo.clock, tool_version=TOOL_VERSION)
        client = TestClient(app, base_url=BASE, follow_redirects=False)
        french = text(client.get("/synthese"))
        assert '<html lang="fr">' in french
        assert ">Synthèse</a>" in french
        assert "100,0 %" in french  # D1 « Qualitatif »: 1 of 1 study
        assert 'value="en" lang="en" class="link">English</button>' in french
        switched = client.post(
            "/langue", data={"csrf_token": token(french), "langue": "en", "retour": "/synthese"}
        )
        assert switched.status_code == 303
        assert switched.headers["location"] == "/synthese"
        assert client.cookies.get(LOCALE_COOKIE) == "en"
        english = text(client.get("/synthese"))
        assert '<html lang="en">' in english
        assert '<a href="/synthese" aria-current="page">Synthesis</a>' in english
        assert "Included studies: 1." in english
        assert "100.0%" in english
        assert " :" not in english
        assert "«" not in english
        # the AI's page, with its quotes and colons, and the journal stays in French
        study = text(client.get(f"/extraction/{demo.ids()['loneliness']}"))
        assert "Data extraction" in study
        assert "not reported" in study
        assert 'value="fr" lang="fr" class="link">Français</button>' in english
        outside = client.post(
            "/langue", data={"csrf_token": token(english), "langue": "fr",
                             "retour": "//example.org/"},
        )  # fmt: skip
        assert outside.headers["location"] == "/"  # never outside the application
        assert client.cookies.get(LOCALE_COOKIE) == "fr"
        assert '<html lang="fr">' in text(client.get("/synthese"))
        odd = client.post("/langue", data={"csrf_token": token(english), "langue": "de"})
        assert odd.status_code == 303
        assert client.cookies.get(LOCALE_COOKIE) == "fr"  # an unknown language: French
    finally:
        demo.folder.close()
    assert current_locale() == "fr"  # the requests did not change the default
