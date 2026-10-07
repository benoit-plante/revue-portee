"""OpenAlex works API (EF-REC-04, EF-REC-05).

The key, when configured, is sent as ``api_key``; in the cloud environment the network
proxy adds it itself (D-021). Each count costs a little of the daily allowance.
"""

from collections.abc import Sequence
from typing import Any

import httpx2
from pydantic import SecretStr

from revue_portee.domain.search import Database, KeyArticle, KeyArticleKind
from revue_portee.sources.http import RateLimiter, SourceAnswer, get_json

__all__ = ["WORKS", "OpenAlex"]

WORKS = "https://api.openalex.org/works"
SERVICE = "OpenAlex"


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
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._limiter = limiter or RateLimiter(0.1)

    def _works(self, filter_value: str, per_page: int) -> SourceAnswer:
        params = {"filter": filter_value, "per-page": str(per_page), "select": "id"}
        if self._api_key is not None:
            params["api_key"] = self._api_key.get_secret_value()
        raw = get_json(self._client, WORKS, params, service=SERVICE, limiter=self._limiter)
        ids = tuple(_short(work["id"]) for work in raw.get("results", []) if work.get("id"))
        return SourceAnswer(count=int(raw.get("meta", {}).get("count", 0)), ids=ids, raw=raw)

    def count(self, filter_value: str) -> SourceAnswer:
        return self._works(filter_value, 1)

    def among(self, filter_value: str, work_ids: Sequence[str]) -> SourceAnswer:
        """Which of ``work_ids`` the filter retrieves."""
        if not work_ids:
            return SourceAnswer(count=0, ids=(), raw={})
        joined = "|".join(work_ids)
        return self._works(f"openalex:{joined},{filter_value}", min(200, len(work_ids)))

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
