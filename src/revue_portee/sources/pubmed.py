"""PubMed through the NCBI E-utilities (EF-REC-02, EF-REC-04, EF-REC-05).

Requests carry ``tool`` and ``email`` as the NCBI asks; without an NCBI key the limit
is 3 requests per second. Raw answers are returned with the results, to be stored in
the project (docs/03-architecture.md §8).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx2
from pydantic import SecretStr

from revue_portee.domain.search import Database, KeyArticle, KeyArticleKind
from revue_portee.sources.http import RateLimiter, SourceAnswer, chunks, get_json, merge_answers

__all__ = ["EUTILS", "MeshCheck", "PubMed"]

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
SERVICE = "PubMed (E-utilities)"
TOOL = "revue-portee"
# Identifiers per request, to keep the URL short (GET requests).
MAX_UIDS = 200


@dataclass(frozen=True, slots=True)
class MeshCheck:
    """Result of looking a heading up in MeSH: ``heading`` is the official name."""

    found: bool
    heading: str | None
    ui: str | None
    raw: tuple[dict[str, Any], ...]


class PubMed:
    database = Database.PUBMED

    def __init__(
        self,
        client: httpx2.Client,
        *,
        email: SecretStr,
        api_key: SecretStr | None = None,
        limiter: RateLimiter | None = None,
        owns_client: bool = False,
    ) -> None:
        self._client = client
        self._owns_client = owns_client
        self._email = email
        self._api_key = api_key
        interval = 0.11 if api_key is not None else 0.34
        self._limiter = limiter or RateLimiter(interval)

    def close(self) -> None:
        """Close the HTTP client if this connector created it."""
        if self._owns_client:
            self._client.close()

    def _params(self, **params: str) -> dict[str, str]:
        base = {"tool": TOOL, "email": self._email.get_secret_value(), "retmode": "json"}
        if self._api_key is not None:
            base["api_key"] = self._api_key.get_secret_value()
        return base | params

    def _esearch(self, database: str, term: str, retmax: int) -> SourceAnswer:
        raw = get_json(
            self._client,
            EUTILS + "esearch.fcgi",
            self._params(db=database, term=term, retmax=str(retmax)),
            service=SERVICE,
            limiter=self._limiter,
        )
        result = raw.get("esearchresult", {})
        return SourceAnswer(
            count=int(result.get("count", 0)), ids=tuple(result.get("idlist", ())), raw=raw
        )

    def count(self, query: str) -> SourceAnswer:
        """Number of records found by ``query`` (no identifiers returned)."""
        return self._esearch("pubmed", query, 0)

    def among(self, query: str, pmids: Sequence[str]) -> SourceAnswer:
        """Which of ``pmids`` ``query`` retrieves."""
        if not pmids:
            return SourceAnswer(count=0, ids=(), raw={})
        answers = []
        for part in chunks(pmids, MAX_UIDS):
            uids = " OR ".join(f"{pmid}[uid]" for pmid in part)
            answers.append(self._esearch("pubmed", f"({query}) AND ({uids})", len(part)))
        return merge_answers(answers)

    def resolve(self, article: KeyArticle) -> tuple[str | None, dict[str, Any]]:
        """PMID of a key article, or None if PubMed has no single match."""
        if article.kind is KeyArticleKind.PMID:
            answer = self._esearch("pubmed", f"{article.value}[uid]", 1)
        elif article.kind is KeyArticleKind.DOI:
            answer = self._esearch("pubmed", f'"{article.value}"[doi]', 2)
        else:
            title = article.value.replace('"', " ")
            answer = self._esearch("pubmed", f'"{title}"[ti]', 2)
        return (answer.ids[0] if len(answer.ids) == 1 else None), answer.raw

    def mesh(self, heading: str) -> MeshCheck:
        """Look ``heading`` up in MeSH; found only if it is an official descriptor name."""
        name = heading.replace('"', " ").strip()
        search = self._esearch("mesh", f'"{name}"[MeSH Terms]', 5)
        if not search.ids:
            return MeshCheck(found=False, heading=None, ui=None, raw=(search.raw,))
        summary = get_json(
            self._client,
            EUTILS + "esummary.fcgi",
            self._params(db="mesh", id=",".join(search.ids)),
            service=SERVICE,
            limiter=self._limiter,
        )
        result = summary.get("result", {})
        for uid in result.get("uids", []):
            item = result.get(uid, {})
            terms = item.get("ds_meshterms", [])
            if terms and terms[0].casefold() == name.casefold():
                return MeshCheck(
                    found=True,
                    heading=terms[0],
                    ui=item.get("ds_meshui"),
                    raw=(search.raw, summary),
                )
        return MeshCheck(found=False, heading=None, ui=None, raw=(search.raw, summary))
