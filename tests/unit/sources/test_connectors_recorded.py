"""PubMed and OpenAlex connectors against recorded answers (tests/cassettes/)."""

import httpx2
import pytest
from pydantic import SecretStr

from revue_portee.domain.search import KeyArticle, KeyArticleKind
from revue_portee.sources.http import RateLimiter
from revue_portee.sources.openalex import OpenAlex
from revue_portee.sources.pubmed import PubMed

pytestmark = pytest.mark.cassette

# A scoping review indexed in both databases (BMC Palliative Care, 2026).
DOI = "10.1186/s12904-026-02174-1"


def _pubmed(client: httpx2.Client, email: SecretStr) -> PubMed:
    return PubMed(client, email=email, limiter=RateLimiter(0.4))


def test_pubmed_count(http_cassette: httpx2.Client, contact_email: SecretStr) -> None:
    answer = _pubmed(http_cassette, contact_email).count('"scoping review"[ti] AND parent*[tiab]')
    assert answer.count > 100
    assert answer.ids == ()


def test_pubmed_mesh_heading_exists(http_cassette: httpx2.Client, contact_email: SecretStr) -> None:
    check = _pubmed(http_cassette, contact_email).mesh("parenting")
    assert check.found
    assert check.heading == "Parenting"
    assert check.ui == "D016487"


def test_pubmed_mesh_heading_absent(http_cassette: httpx2.Client, contact_email: SecretStr) -> None:
    check = _pubmed(http_cassette, contact_email).mesh("Parenting Programs")
    assert not check.found
    assert check.heading is None


def test_pubmed_resolve_and_among(http_cassette: httpx2.Client, contact_email: SecretStr) -> None:
    pubmed = _pubmed(http_cassette, contact_email)
    pmid, _ = pubmed.resolve(KeyArticle(kind=KeyArticleKind.DOI, value=DOI))
    assert pmid is not None
    assert pubmed.among('"scoping review"[tiab]', [pmid]).ids == (pmid,)
    assert pubmed.among('"randomized controlled trial"[ti]', [pmid]).ids == ()


def test_openalex_count(http_cassette: httpx2.Client) -> None:
    answer = OpenAlex(http_cassette).count(
        'title_and_abstract.search.exact:"scoping review" AND parent*'
    )
    assert answer.count > 100


def test_openalex_resolve_and_among(http_cassette: httpx2.Client) -> None:
    openalex = OpenAlex(http_cassette)
    work, _ = openalex.resolve(KeyArticle(kind=KeyArticleKind.DOI, value=DOI))
    assert work is not None
    assert work.startswith("W")
    found = openalex.among('title_and_abstract.search.exact:"scoping review"', [work])
    assert found.ids == (work,)
    missing = openalex.among('title_and_abstract.search.exact:"randomized controlled"', [work])
    assert missing.ids == ()
