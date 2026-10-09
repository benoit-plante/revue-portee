"""Open access sources (EF-COL-02, EF-SEL-14): Unpaywall and OpenAlex locations, PDF
downloads. Answers are written by hand from the documented formats; no network."""

from typing import Any

import httpx2
import pytest
from pydantic import SecretStr

from revue_portee.domain.references import Reference
from revue_portee.sources import OpenAccessSources
from revue_portee.sources.http import (
    NotAPdfError,
    PdfTooLargeError,
    RateLimiter,
    SourceAccessError,
    SourceUnreachableError,
    get_pdf,
)
from revue_portee.sources.openalex import OpenAlex, open_access_locations
from revue_portee.sources.records import OpenAccessLocation
from revue_portee.sources.unpaywall import Unpaywall, unpaywall_locations
from support import START

PDF = b"%PDF-1.7\n%fake\n"
URL = "https://repository.example.org/article.pdf"


def _client(*answers: httpx2.Response | Exception) -> tuple[httpx2.Client, list[httpx2.Request]]:
    seen: list[httpx2.Request] = []
    pending = list(answers)

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        answer = pending.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    return httpx2.Client(transport=httpx2.MockTransport(handler)), seen


def _no_wait() -> RateLimiter:
    return RateLimiter(0.0, sleep=lambda _: None)


def test_pdf_downloaded_after_a_redirect_and_a_retry() -> None:
    sleeps: list[float] = []
    client, seen = _client(
        httpx2.Response(503),
        httpx2.Response(302, headers={"Location": "https://cdn.example.org/a.pdf"}),
        httpx2.Response(200, content=PDF),
    )
    data = get_pdf(client, URL, limiter=_no_wait(), sleep=sleeps.append)
    assert data == PDF
    assert [str(r.url) for r in seen] == [URL, URL, "https://cdn.example.org/a.pdf"]
    assert sleeps == [1]


@pytest.mark.parametrize(
    ("answer", "error", "message"),
    [
        (httpx2.Response(403), SourceAccessError, "403"),
        (httpx2.Response(200, content=b"<html>Sign in</html>"), NotAPdfError, "pas un PDF"),
        (httpx2.ConnectError("refused"), SourceUnreachableError, "repository.example.org"),
    ],
)
def test_pdf_download_failures(
    answer: httpx2.Response | Exception, error: type[Exception], message: str
) -> None:
    client, _ = _client(answer)
    with pytest.raises(error, match=message):
        get_pdf(client, URL, limiter=_no_wait(), sleep=lambda _: None)


def test_pdf_download_gives_up_after_timeouts() -> None:
    client, seen = _client(*[httpx2.ReadTimeout("slow")] * 3)
    with pytest.raises(SourceUnreachableError):
        get_pdf(client, URL, limiter=_no_wait(), sleep=lambda _: None)
    assert len(seen) == 3


def test_pdf_too_large_and_other_schemes() -> None:
    client, _ = _client(httpx2.Response(200, content=PDF + b"x" * 100))
    with pytest.raises(PdfTooLargeError, match="Mo"):
        get_pdf(client, URL, limiter=_no_wait(), max_bytes=50)
    with pytest.raises(NotAPdfError):
        get_pdf(client, "ftp://example.org/a.pdf", limiter=_no_wait())


UNPAYWALL: dict[str, Any] = {
    "doi": "10.5555/demo.0001",
    "is_oa": True,
    "best_oa_location": {
        "url_for_pdf": "https://repository.example.org/a.pdf",
        "license": "cc-by",
        "version": "acceptedVersion",
        "host_type": "repository",
    },
    "oa_locations": [
        {"url_for_pdf": "https://repository.example.org/a.pdf", "host_type": "repository"},
        {"url_for_pdf": None, "url": "https://publisher.example.org/landing"},
        {"url_for_pdf": "https://publisher.example.org/a.pdf", "license": None,
         "version": "publishedVersion", "host_type": "publisher"},
    ],
}  # fmt: skip


def test_unpaywall_locations_best_first_without_repeats() -> None:
    assert unpaywall_locations(UNPAYWALL) == [
        OpenAccessLocation(URL.replace("article", "a"), "cc-by", "acceptedVersion", "repository"),
        OpenAccessLocation(
            "https://publisher.example.org/a.pdf", "", "publishedVersion", "publisher"
        ),
    ]
    assert unpaywall_locations({"is_oa": False, "best_oa_location": None}) == []


def test_unpaywall_connector() -> None:
    client, seen = _client(httpx2.Response(200, json=UNPAYWALL), httpx2.Response(404))
    unpaywall = Unpaywall(client, email=SecretStr("contact@example.org"), limiter=_no_wait())
    found, raw = unpaywall.locations("10.5555/DEMO.0001")
    assert len(found) == 2
    assert raw == UNPAYWALL
    assert seen[0].url.path == "/v2/10.5555/demo.0001"
    assert seen[0].url.params["email"] == "contact@example.org"
    assert unpaywall.locations("10.5555/UNKNOWN") == ([], {"status": 404})
    unpaywall.close()


def test_unpaywall_other_errors_are_raised() -> None:
    client, _ = _client(httpx2.Response(401))
    unpaywall = Unpaywall(client, email=SecretStr("contact@example.org"), limiter=_no_wait())
    with pytest.raises(SourceAccessError):
        unpaywall.locations("10.5555/DEMO.0001")


WORK: dict[str, Any] = {
    "id": "https://openalex.org/W1",
    "best_oa_location": {
        "is_oa": True,
        "pdf_url": "https://www.example.org/pmc/a.pdf",
        "license": "cc-by",
        "version": "publishedVersion",
        "source": {"type": "repository"},
    },
    "locations": [
        {"is_oa": False, "pdf_url": "https://publisher.example.org/paywalled.pdf"},
        {"is_oa": True, "pdf_url": None, "landing_page_url": "https://example.org"},
        {"is_oa": True, "pdf_url": "https://www.example.org/pmc/a.pdf"},
        {"is_oa": True, "pdf_url": "https://journal.example.org/a.pdf",
         "source": {"type": "journal"}},
    ],
}  # fmt: skip


def test_openalex_locations() -> None:
    assert open_access_locations(WORK) == [
        OpenAccessLocation(
            "https://www.example.org/pmc/a.pdf", "cc-by", "publishedVersion", "repository"
        ),
        OpenAccessLocation("https://journal.example.org/a.pdf", "", "", "publisher"),
    ]


def test_openalex_connector_by_id_then_doi() -> None:
    client, seen = _client(
        httpx2.Response(200, json={"results": [WORK]}),
        httpx2.Response(200, json={"results": []}),
    )
    openalex = OpenAlex(client, limiter=_no_wait())
    found, _raw = openalex.locations(openalex_id="W1", doi="10.5555/X")
    assert len(found) == 2
    assert seen[0].url.params["filter"] == "openalex:W1"
    assert seen[0].url.params["select"] == "id,best_oa_location,locations"
    assert openalex.locations(doi="10.5555/X") == ([], {"results": []})
    assert seen[1].url.params["filter"] == "doi:10.5555/x"
    assert openalex.locations() == ([], {})
    assert len(seen) == 2


class _Fake:
    def __init__(self) -> None:
        self.closed = False

    def locations(self, *args: str, **kwargs: str) -> tuple[list[OpenAccessLocation], Any]:
        return [], {"asked": [*args, *kwargs.values()]}

    def close(self) -> None:
        self.closed = True


def test_open_access_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONTACT_EMAIL", "contact@example.org")
    sources = OpenAccessSources()
    sources.close()
    fakes = {"_openalex": _Fake(), "_unpaywall": _Fake()}
    for name, fake in fakes.items():
        setattr(sources, name, fake)
    client, _ = _client(httpx2.Response(200, content=PDF))
    sources._files = client  # no network in tests
    sources._limiter = _no_wait()
    reference = Reference(id="R", doi="10.5555/X", openalex_id="W1", created_at=START)
    assert sources.openalex(reference) == ([], {"asked": ["W1", "10.5555/X"]})
    assert sources.unpaywall("10.5555/X") == ([], {"asked": ["10.5555/X"]})
    assert sources.download(URL) == PDF
    sources.close()
    assert all(fake.closed for fake in fakes.values())
