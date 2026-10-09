"""Bibliographic source connectors (docs/03-architecture.md §8).

Services only know :class:`SearchSource`; they receive a :data:`SourceFactory` so that
tests can substitute connectors replaying recorded answers.
"""

from collections.abc import Callable, Sequence
from typing import Any, Protocol

from revue_portee.config.secrets import SecretName, get_optional_secret, get_secret
from revue_portee.domain.references import Reference
from revue_portee.domain.search import Database, KeyArticle
from revue_portee.i18n import gettext as _
from revue_portee.sources.crossref import Crossref
from revue_portee.sources.http import RateLimiter, SourceAnswer, SourceError, get_pdf, make_client
from revue_portee.sources.openalex import OpenAlex
from revue_portee.sources.pubmed import PubMed
from revue_portee.sources.records import OpenAccessLocation
from revue_portee.sources.unpaywall import Unpaywall

__all__ = [
    "OpenAccessSources",
    "SearchSource",
    "SourceAnswer",
    "SourceError",
    "SourceFactory",
    "UnsupportedDatabaseError",
    "close_source",
    "default_crossref",
    "default_source_factory",
]


class SearchSource(Protocol):
    @property
    def database(self) -> Database: ...

    def count(self, query: str) -> SourceAnswer: ...

    def among(self, query: str, ids: Sequence[str]) -> SourceAnswer: ...

    def resolve(self, article: KeyArticle) -> tuple[str | None, dict[str, Any]]: ...


class UnsupportedDatabaseError(SourceError):
    def __init__(self, database: Database) -> None:
        super().__init__(
            _("{database} has no API: run the query in its interface.").format(
                database=database.display_name
            )
        )


SourceFactory = Callable[[Database], SearchSource]


def default_source_factory(database: Database) -> SearchSource:
    """Connector for the real service (contact address and keys from the environment)."""
    if database is Database.PUBMED:
        return PubMed(make_client(), email=get_secret(SecretName.CONTACT_EMAIL), owns_client=True)
    if database is Database.OPENALEX:
        return OpenAlex(
            make_client(),
            api_key=get_optional_secret(SecretName.OPENALEX_API_KEY),
            owns_client=True,
        )
    raise UnsupportedDatabaseError(database)


def default_crossref() -> Crossref:
    """Crossref connector for the real service (contact address from the environment)."""
    return Crossref(make_client(), email=get_secret(SecretName.CONTACT_EMAIL), owns_client=True)


def close_source(source: object) -> None:
    """Release a connector's HTTP client (connectors given by tests have none)."""
    close = getattr(source, "close", None)
    if callable(close):
        close()


class OpenAccessSources:
    """OpenAlex and Unpaywall for the open access versions of a work, and the download
    of their PDFs (one request a second to the hosts of the files)."""

    def __init__(self) -> None:
        self._openalex = OpenAlex(
            make_client(),
            api_key=get_optional_secret(SecretName.OPENALEX_API_KEY),
            owns_client=True,
        )
        self._unpaywall = Unpaywall(
            make_client(), email=get_secret(SecretName.CONTACT_EMAIL), owns_client=True
        )
        self._files = make_client(timeout=60.0)
        self._limiter = RateLimiter(1.0)

    def openalex(self, reference: Reference) -> tuple[list[OpenAccessLocation], dict[str, Any]]:
        return self._openalex.locations(openalex_id=reference.openalex_id, doi=reference.doi)

    def unpaywall(self, doi: str) -> tuple[list[OpenAccessLocation], dict[str, Any]]:
        return self._unpaywall.locations(doi)

    def download(self, url: str) -> bytes:
        return get_pdf(self._files, url, limiter=self._limiter)

    def close(self) -> None:
        self._openalex.close()
        self._unpaywall.close()
        self._files.close()
