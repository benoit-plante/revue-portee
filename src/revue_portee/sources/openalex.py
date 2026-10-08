"""OpenAlex works API (EF-REC-04, EF-REC-05).

The key, when configured, is sent as ``api_key``; in the cloud environment the network
proxy adds it itself (D-021). Each count costs a little of the daily allowance.
"""

from collections.abc import Sequence
from typing import Any

import httpx2
from pydantic import SecretStr

from revue_portee.domain.references import clean_doi
from revue_portee.domain.search import Database, KeyArticle, KeyArticleKind
from revue_portee.i18n import gettext as _
from revue_portee.sources.http import (
    RateLimiter,
    SourceAccessError,
    SourceAnswer,
    SourceError,
    chunks,
    get_json,
    merge_answers,
)
from revue_portee.sources.records import FetchedPage, FetchedRecord, abstract_from_inverted_index

__all__ = ["PAGE_SIZE", "WORKS", "OpenAlex", "OpenAlexKeyError", "normalize_work"]

WORKS = "https://api.openalex.org/works"
SERVICE = "OpenAlex"
# OpenAlex accepts at most 100 values in one OR filter (and 200 results per page).
MAX_OR_VALUES = 100
PAGE_SIZE = 200
_FIELDS = (
    "id,doi,display_name,publication_year,authorships,primary_location,biblio,ids,"
    "language,type,abstract_inverted_index"
)


class OpenAlexKeyError(SourceError):
    """OpenAlex refuses the request (401 or 403): the key is missing or invalid."""

    def __init__(self, status: int) -> None:
        super().__init__(
            _(
                "OpenAlex refused the request (HTTP error {status}): check the key "
                "OPENALEX_API_KEY (required by OpenAlex unless the network proxy adds it). "
                "The OpenAlex collection is stopped."
            ).format(status=status)
        )


def _short(openalex_id: str) -> str:
    return openalex_id.rsplit("/", 1)[-1]


class OpenAlex:
    database = Database.OPENALEX

    def __init__(
        self,
        client: httpx2.Client,
        *,
        api_key: SecretStr | None = None,
        limiter: RateLimiter | None = None,
        owns_client: bool = False,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._limiter = limiter or RateLimiter(0.1)
        self._owns_client = owns_client

    def close(self) -> None:
        """Close the HTTP client if this connector created it."""
        if self._owns_client:
            self._client.close()

    def _get(self, params: dict[str, str]) -> Any:  # noqa: ANN401 - JSON document
        if self._api_key is not None:
            params["api_key"] = self._api_key.get_secret_value()
        try:
            return get_json(self._client, WORKS, params, service=SERVICE, limiter=self._limiter)
        except SourceAccessError as error:
            if error.status in (401, 403):
                raise OpenAlexKeyError(error.status) from error
            raise

    def _works(self, filter_value: str, per_page: int) -> SourceAnswer:
        raw = self._get({"filter": filter_value, "per-page": str(per_page), "select": "id"})
        ids = tuple(_short(work["id"]) for work in raw.get("results", []) if work.get("id"))
        return SourceAnswer(count=int(raw.get("meta", {}).get("count", 0)), ids=ids, raw=raw)

    def count(self, filter_value: str) -> SourceAnswer:
        return self._works(filter_value, 1)

    def among(self, filter_value: str, work_ids: Sequence[str]) -> SourceAnswer:
        """Which of ``work_ids`` the filter retrieves."""
        if not work_ids:
            return SourceAnswer(count=0, ids=(), raw={})
        return merge_answers(
            [
                self._works(f"openalex:{'|'.join(part)},{filter_value}", len(part))
                for part in chunks(work_ids, MAX_OR_VALUES)
            ]
        )

    def resolve(self, article: KeyArticle) -> tuple[str | None, dict[str, Any]]:
        """OpenAlex work of a key article, or None if there is no single match."""
        if article.kind is KeyArticleKind.DOI:
            answer = self._works(f"doi:{article.value.lower()}", 2)
        elif article.kind is KeyArticleKind.PMID:
            answer = self._works(f"pmid:{article.value}", 2)
        else:
            title = " ".join(article.value.replace(",", " ").replace('"', " ").split())
            answer = self._works(f'title.search.exact:"{title}"', 2)
        return (answer.ids[0] if len(answer.ids) == 1 else None), answer.raw

    def fetch(self, filter_value: str, cursor: str | None) -> FetchedPage:
        """One page of the works retrieved by the filter; ``cursor`` None for the first."""
        raw = self._get(
            {
                "filter": filter_value,
                "per-page": str(PAGE_SIZE),
                "cursor": cursor or "*",
                "select": _FIELDS,
            }
        )
        results = raw.get("results", [])
        meta = raw.get("meta", {})
        next_cursor = meta.get("next_cursor") if results else None
        return FetchedPage(
            records=tuple(normalize_work(work) for work in results if work.get("id")),
            announced=int(meta.get("count", 0)),
            next_cursor=next_cursor,
            raw=raw,
        )


def normalize_work(work: dict[str, Any]) -> FetchedRecord:
    """Fields of a reference from an OpenAlex work."""
    location = work.get("primary_location") or {}
    source = location.get("source") or {}
    biblio = work.get("biblio") or {}
    ids = work.get("ids") or {}
    first, last = biblio.get("first_page") or "", biblio.get("last_page") or ""
    pages = f"{first}-{last}" if first and last and first != last else first
    pmid = str(ids.get("pmid") or "").rsplit("/", 1)[-1]
    return FetchedRecord(
        original_id=_short(work["id"]),
        fields={
            "title": " ".join((work.get("display_name") or "").split()),
            "abstract": abstract_from_inverted_index(work.get("abstract_inverted_index")),
            "authors": tuple(
                name
                for a in work.get("authorships") or []
                if (name := (a.get("author") or {}).get("display_name"))
            ),
            "year": work.get("publication_year"),
            "container_title": source.get("display_name") or "",
            "volume": str(biblio.get("volume") or ""),
            "issue": str(biblio.get("issue") or ""),
            "pages": str(pages),
            "doi": clean_doi(work.get("doi") or ""),
            "pmid": pmid if pmid.isdigit() else "",
            "openalex_id": _short(work["id"]),
            "language": work.get("language") or "",
            "doc_type": work.get("type") or "",
            "url": location.get("landing_page_url") or "",
        },
    )
