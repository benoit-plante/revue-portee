"""HTTP helper: retries, clear errors, rate limiting; connector parameters."""

import httpx2
import pytest
from pydantic import SecretStr

from revue_portee.domain.search import KeyArticle, KeyArticleKind
from revue_portee.sources.http import (
    RateLimiter,
    SourceAccessError,
    SourceUnreachableError,
    get_json,
    make_client,
)
from revue_portee.sources.openalex import OpenAlex
from revue_portee.sources.pubmed import PubMed

URL = "https://api.example.test/works"


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


def test_retries_on_429_then_succeeds() -> None:
    sleeps: list[float] = []
    client, seen = _client(
        httpx2.Response(429), httpx2.Response(503), httpx2.Response(200, json={"ok": 1})
    )
    result = get_json(client, URL, {}, service="Test", limiter=_no_wait(), sleep=sleeps.append)
    assert result == {"ok": 1}
    assert len(seen) == 3
    assert sleeps == [1, 2]


def test_gives_up_after_the_retries() -> None:
    client, _ = _client(*[httpx2.Response(500)] * 3)
    with pytest.raises(SourceAccessError, match="500"):
        get_json(
            client, URL, {}, service="Test", limiter=_no_wait(), retries=2, sleep=lambda _: None
        )


def test_client_error_is_not_retried() -> None:
    client, seen = _client(httpx2.Response(403))
    with pytest.raises(SourceAccessError, match="Test") as raised:
        get_json(client, URL, {"api_key": "DUMMY"}, service="Test", limiter=_no_wait())
    assert len(seen) == 1
    assert "DUMMY" not in str(raised.value)


def test_blocked_domain_is_named() -> None:
    client, _ = _client(httpx2.ConnectError("refused"))
    with pytest.raises(SourceUnreachableError, match=r"api\.example\.test"):
        get_json(client, URL, {}, service="Test", limiter=_no_wait())


def test_timeouts_are_retried_then_reported() -> None:
    client, seen = _client(httpx2.ReadTimeout("slow"), httpx2.ReadTimeout("slow"))
    with pytest.raises(SourceUnreachableError):
        get_json(
            client, URL, {}, service="Test", limiter=_no_wait(), retries=1, sleep=lambda _: None
        )
    assert len(seen) == 2


def test_rate_limiter_spaces_requests() -> None:
    now = [10.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    limiter = RateLimiter(0.5, clock=lambda: now[0], sleep=sleep)
    limiter.wait()
    now[0] += 0.2
    limiter.wait()
    now[0] += 1.0
    limiter.wait()
    assert sleeps == [pytest.approx(0.3)]


def test_make_client_identifies_the_tool() -> None:
    with make_client() as client:
        assert client.headers["User-Agent"].startswith("revue-portee/")


def test_keys_are_sent_only_when_configured() -> None:
    client, seen = _client(
        httpx2.Response(200, json={"esearchresult": {"count": "3", "idlist": []}}),
        httpx2.Response(200, json={"meta": {"count": 0}, "results": []}),
    )
    key = SecretStr("DUMMY")
    PubMed(client, email=SecretStr("contact@example.org"), api_key=key, limiter=_no_wait()).count(
        "x"
    )
    OpenAlex(client, api_key=key, limiter=_no_wait()).count("x")
    assert seen[0].url.params["api_key"] == "DUMMY"
    assert seen[0].url.params["tool"] == "revue-portee"
    assert seen[1].url.params["api_key"] == "DUMMY"


def test_resolution_by_title_and_pmid_and_empty_lists() -> None:
    client, seen = _client(
        httpx2.Response(200, json={"esearchresult": {"count": "2", "idlist": ["1", "2"]}}),
        httpx2.Response(200, json={"esearchresult": {"count": "1", "idlist": ["42"]}}),
        httpx2.Response(
            200, json={"meta": {"count": 1}, "results": [{"id": "https://openalex.org/W7"}]}
        ),
        httpx2.Response(
            200, json={"meta": {"count": 1}, "results": [{"id": "https://openalex.org/W8"}]}
        ),
    )
    pubmed = PubMed(client, email=SecretStr("contact@example.org"), limiter=_no_wait())
    openalex = OpenAlex(client, limiter=_no_wait())
    title = KeyArticle(kind=KeyArticleKind.TITLE, value='Parenting, "programs" for fathers')
    pmid = KeyArticle(kind=KeyArticleKind.PMID, value="42")
    assert pubmed.resolve(title)[0] is None  # two matches: ambiguous
    assert pubmed.resolve(pmid)[0] == "42"
    assert openalex.resolve(title)[0] == "W7"
    assert openalex.resolve(pmid)[0] == "W8"
    assert seen[2].url.params["filter"] == 'title.search.exact:"Parenting programs for fathers"'
    assert seen[3].url.params["filter"] == "pmid:42"
    assert pubmed.among("x", []).ids == ()
    assert openalex.among("x", []).ids == ()
    assert len(seen) == 4


def test_mesh_lookup_without_exact_name() -> None:
    client, _ = _client(
        httpx2.Response(200, json={"esearchresult": {"count": "1", "idlist": ["9"]}}),
        httpx2.Response(
            200,
            json={
                "result": {"uids": ["9"], "9": {"ds_meshterms": ["Parenting"], "ds_meshui": "D1"}}
            },
        ),
    )
    check = PubMed(client, email=SecretStr("contact@example.org"), limiter=_no_wait()).mesh(
        "Parent"
    )
    assert not check.found
    assert len(check.raw) == 2
