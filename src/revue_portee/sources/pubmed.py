"""PubMed through the NCBI E-utilities (EF-REC-02, EF-REC-04, EF-REC-05).

Requests carry ``tool`` and ``email`` as the NCBI asks; without an NCBI key the limit
is 3 requests per second. Raw answers are returned with the results, to be stored in
the project (docs/03-architecture.md §8).
"""

import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx2
from pydantic import SecretStr

from revue_portee.domain.references import clean_doi
from revue_portee.domain.search import Database, KeyArticle, KeyArticleKind
from revue_portee.i18n import gettext as _
from revue_portee.sources.http import (
    RateLimiter,
    SourceAnswer,
    SourceError,
    SourceInvalidAnswerError,
    chunks,
    get_json,
    get_text,
    merge_answers,
)
from revue_portee.sources.records import FetchedPage, FetchedRecord

__all__ = [
    "EUTILS",
    "MAX_RECORDS",
    "PAGE_SIZE",
    "MeshCheck",
    "PubMed",
    "TooManyRecordsError",
    "databank_accessions",
    "parse_pubmed_xml",
]

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
SERVICE = "PubMed (E-utilities)"
TOOL = "revue-portee"
# Identifiers per request, to keep the URL short (GET requests).
MAX_UIDS = 200
PAGE_SIZE = 200
# PubMed gives at most 10,000 records of one search (E-utilities, since 2022).
MAX_RECORDS = 10_000


class TooManyRecordsError(SourceError):
    def __init__(self, count: int) -> None:
        super().__init__(
            _(
                "PubMed announces {count} records, but gives at most 10,000 per query: "
                "split the search (for example by publication years) before collecting."
            ).format(count=count)
        )


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

    def _history(self, query: str) -> tuple[str, str, int]:
        raw = get_json(
            self._client,
            EUTILS + "esearch.fcgi",
            self._params(db="pubmed", term=query, retmax="0", usehistory="y"),
            service=SERVICE,
            limiter=self._limiter,
        )
        result = raw.get("esearchresult", {})
        webenv, key = result.get("webenv"), result.get("querykey")
        if not webenv or not key:
            raise SourceInvalidAnswerError(SERVICE)
        return str(webenv), str(key), int(result.get("count", 0))

    def fetch(self, query: str, cursor: str | None) -> FetchedPage:
        """One page of the records retrieved by ``query``; ``cursor`` None for the first.

        The cursor holds the history server session (WebEnv) and the next position;
        when the session has expired, the search is run again and the collection
        continues at the same position."""
        state = json.loads(cursor) if cursor else {}
        retstart = int(state.get("retstart", 0))
        if not state:
            webenv, key, count = self._history(query)
            if count > MAX_RECORDS:
                raise TooManyRecordsError(count)
        else:
            webenv, key, count = state["webenv"], state["query_key"], int(state["count"])
        params = self._params(
            db="pubmed",
            query_key=key,
            WebEnv=webenv,
            retstart=str(retstart),
            retmax=str(PAGE_SIZE),
            retmode="xml",
        )
        text = get_text(
            self._client, EUTILS + "efetch.fcgi", params, service=SERVICE, limiter=self._limiter
        )
        if _is_error(text) and state:  # expired session: search again
            webenv, key, count = self._history(query)
            params.update(query_key=key, WebEnv=webenv)
            text = get_text(
                self._client,
                EUTILS + "efetch.fcgi",
                params,
                service=SERVICE,
                limiter=self._limiter,
            )
        if _is_error(text):  # never taken for the end of the results
            raise SourceInvalidAnswerError(SERVICE)
        records = parse_pubmed_xml(text)
        following = retstart + PAGE_SIZE
        if not records and retstart < count:  # an empty page before the end: an error
            raise SourceInvalidAnswerError(SERVICE)
        next_cursor = (
            json.dumps({"webenv": webenv, "query_key": key, "count": count, "retstart": following})
            if following < count
            else None
        )
        return FetchedPage(records=records, announced=count, next_cursor=next_cursor, raw=text)


def _is_error(text: str) -> bool:
    return "<ERROR>" in text[:2000]


def _text(element: ET.Element | None) -> str:
    return "" if element is None else " ".join("".join(element.itertext()).split())


def _authors(container: ET.Element | None) -> tuple[str, ...]:
    names = []
    for author in [] if container is None else container.findall("Author"):
        collective = _text(author.find("CollectiveName"))
        last, fore = _text(author.find("LastName")), _text(author.find("ForeName"))
        name = collective or (f"{last}, {fore}" if last and fore else last)
        if name:
            names.append(name)
    return tuple(names)


def _abstract(container: ET.Element | None) -> str:
    parts = []
    for part in [] if container is None else container.findall("AbstractText"):
        text, label = _text(part), part.get("Label")
        if text:
            parts.append(f"{label}: {text}" if label else text)
    return "\n".join(parts)


def _year(*elements: ET.Element | None) -> int | None:
    for element in elements:
        match = re.search(r"(1[0-9]{3}|20[0-9]{2})", _text(element))
        if match:
            return int(match.group(1))
    return None


def parse_pubmed_xml(text: str) -> tuple[FetchedRecord, ...]:
    """Records of an EFetch answer (journal articles and books)."""
    try:
        root = ET.fromstring(text)  # noqa: S314 - NCBI answer; expat guards entity expansion
    except ET.ParseError as error:
        raise SourceInvalidAnswerError(SERVICE) from error
    records = []
    for article in root.iter("PubmedArticle"):
        citation = article.find("MedlineCitation")
        if citation is None:
            continue
        body = citation.find("Article")
        journal = None if body is None else body.find("Journal")
        issue = None if journal is None else journal.find("JournalIssue")
        date = None if issue is None else issue.find("PubDate")
        pmid = _text(citation.find("PMID"))
        doi = next(
            (
                _text(i)
                for i in article.iterfind("PubmedData/ArticleIdList/ArticleId")
                if i.get("IdType") == "doi"
            ),
            "",
        )
        if not doi and body is not None:
            doi = next(
                (_text(e) for e in body.iterfind("ELocationID") if e.get("EIdType") == "doi"), ""
            )
        records.append(
            FetchedRecord(
                original_id=pmid,
                fields={
                    "title": _text(None if body is None else body.find("ArticleTitle")),
                    "abstract": _abstract(None if body is None else body.find("Abstract")),
                    "authors": _authors(None if body is None else body.find("AuthorList")),
                    "year": _year(
                        None if date is None else date.find("Year"),
                        None if date is None else date.find("MedlineDate"),
                    ),
                    "container_title": _text(None if journal is None else journal.find("Title")),
                    "volume": _text(None if issue is None else issue.find("Volume")),
                    "issue": _text(None if issue is None else issue.find("Issue")),
                    "pages": _text(None if body is None else body.find("Pagination/MedlinePgn")),
                    "doi": clean_doi(doi),
                    "pmid": pmid,
                    "language": _text(None if body is None else body.find("Language")),
                    "doc_type": _text(
                        None if body is None else body.find("PublicationTypeList/PublicationType")
                    ),
                },
            )
        )
    for book in root.iter("PubmedBookArticle"):
        document = book.find("BookDocument")
        if document is None:
            continue
        pmid = _text(document.find("PMID"))
        title = _text(document.find("ArticleTitle")) or _text(document.find("Book/BookTitle"))
        doi = next(
            (
                _text(i)
                for i in book.iterfind("PubmedBookData/ArticleIdList/ArticleId")
                if i.get("IdType") == "doi"
            ),
            "",
        )
        records.append(
            FetchedRecord(
                original_id=pmid,
                fields={
                    "title": title,
                    "abstract": _abstract(document.find("Abstract")),
                    "authors": _authors(document.find("AuthorList"))
                    or _authors(document.find("Book/AuthorList")),
                    "year": _year(document.find("Book/PubDate/Year")),
                    "container_title": _text(document.find("Book/BookTitle"))
                    if document.find("ArticleTitle") is not None
                    else "",
                    "doi": clean_doi(doi),
                    "pmid": pmid,
                    "language": _text(document.find("Language")),
                    "doc_type": "Book",
                },
            )
        )
    return tuple(r for r in records if r.original_id)


def databank_accessions(
    text: str, databank: str = "ClinicalTrials.gov"
) -> dict[str, frozenset[str]]:
    """Accession numbers of ``databank`` (the trial registry) given by PubMed for each
    record of an EFetch answer (``DataBankList``), by PMID."""
    try:
        root = ET.fromstring(text)  # noqa: S314 - NCBI answer; expat guards entity expansion
    except ET.ParseError as error:
        raise SourceInvalidAnswerError(SERVICE) from error
    found: dict[str, frozenset[str]] = {}
    for article in root.iter("PubmedArticle"):
        pmid = _text(article.find("MedlineCitation/PMID"))
        numbers = {
            _text(number).upper()
            for bank in article.iterfind("MedlineCitation/Article/DataBankList/DataBank")
            if _text(bank.find("DataBankName")) == databank
            for number in bank.iterfind("AccessionNumberList/AccessionNumber")
        }
        if pmid:
            found[pmid] = frozenset(n for n in numbers if n)
    return found
