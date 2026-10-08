"""Crossref works API, to fill missing fields of references by DOI (EF-COL-02).

The "polite" pool is used (``mailto`` = contact address): 10 requests per second for
single records, at most three at a time (conditions of December 2025,
docs/01-etat-de-l-art.md §6).
"""

import re
from typing import Any
from urllib.parse import quote

import httpx2
from pydantic import SecretStr

from revue_portee.sources.http import RateLimiter, SourceAccessError, get_json

__all__ = ["MAX_CONCURRENCY", "WORKS", "Crossref", "fields_from_work"]

WORKS = "https://api.crossref.org/works/"
SERVICE = "Crossref"
MAX_CONCURRENCY = 3
_TAGS = re.compile(r"<[^>]+>")


class Crossref:
    def __init__(
        self,
        client: httpx2.Client,
        *,
        email: SecretStr,
        limiter: RateLimiter | None = None,
        owns_client: bool = False,
    ) -> None:
        self._client = client
        self._email = email
        self._limiter = limiter or RateLimiter(0.1)
        self._owns_client = owns_client

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def work(self, doi: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """The Crossref record of ``doi`` (None when Crossref does not know it) and the
        raw answer."""
        try:
            raw = get_json(
                self._client,
                WORKS + quote(doi.lower(), safe="/"),
                {"mailto": self._email.get_secret_value()},
                service=SERVICE,
                limiter=self._limiter,
            )
        except SourceAccessError as error:
            if error.status == 404:
                return None, {"status": 404}
            raise
        message = raw.get("message")
        return (message if isinstance(message, dict) else None), raw


def _first(values: Any) -> str:  # noqa: ANN401 - JSON value
    if isinstance(values, list) and values:
        return " ".join(str(values[0]).split())
    return ""


def fields_from_work(work: dict[str, Any]) -> dict[str, str | int | list[str]]:
    """Reference fields of a Crossref work (only those it gives)."""
    fields: dict[str, str | int | list[str]] = {}
    if title := _first(work.get("title")):
        fields["title"] = title
    if abstract := " ".join(_TAGS.sub(" ", str(work.get("abstract") or "")).split()):
        fields["abstract"] = abstract.removeprefix("Abstract ").strip()
    authors = []
    for author in work.get("author") or []:
        family, given = author.get("family"), author.get("given")
        name = f"{family}, {given}" if family and given else family or author.get("name")
        if name:
            authors.append(str(name))
    if authors:
        fields["authors"] = authors
    for key in ("published-print", "published-online", "issued"):
        parts = (work.get(key) or {}).get("date-parts") or [[]]
        if parts and parts[0] and isinstance(parts[0][0], int):
            fields["year"] = parts[0][0]
            break
    if container := _first(work.get("container-title")):
        fields["container_title"] = container
    for name, key in (("volume", "volume"), ("issue", "issue"), ("pages", "page")):
        if value := str(work.get(key) or "").strip():
            fields[name] = value
    return fields
