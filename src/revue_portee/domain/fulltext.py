"""Full texts: retrieval, text by page, quotes located by page (EF-SEL-14, EF-SEL-15).

A document obtained for a reference is never changed: a better version, or one from
another source, is added and becomes the document in force (the latest one). A
reference without a document may carry notes: ``not_found`` (looked for, not found for
now) or ``not_retrievable`` (declared by the person, with a reason). Only the latter
counts as "Reports not retrieved" in the diagram (docs/10-conception-texte-integral.md
§2.1.1).

Quotes are compared on a canonical form (letters and digits only, case folded, after
NFKC), so that line breaks, hyphenation, ligatures and typographic quotes of the PDF
do not hide them.
"""

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from revue_portee.domain.references import clean_doi

__all__ = [
    "OPEN_ACCESS_ORIGINS",
    "FulltextDocument",
    "FulltextOrigin",
    "MatchKind",
    "PagePosition",
    "PagedText",
    "QuoteCheck",
    "QuoteLocation",
    "RetrievalCounts",
    "RetrievalNote",
    "RetrievalStatus",
    "TextPage",
    "UploadMatch",
    "canonical",
    "check_quote",
    "current_documents",
    "dois_in_text",
    "locate_quote",
    "match_upload",
    "retrieval_counts",
    "retrieval_statuses",
]


class FulltextOrigin(StrEnum):
    OPENALEX = "openalex"  # open access version known to OpenAlex
    UNPAYWALL = "unpaywall"
    UPLOAD = "upload"  # obtained by the team (institutional access, authors…)


OPEN_ACCESS_ORIGINS = frozenset({FulltextOrigin.OPENALEX, FulltextOrigin.UNPAYWALL})


class RetrievalStatus(StrEnum):
    NOT_SOUGHT = "not_sought"  # never looked for yet
    OBTAINED = "obtained"
    NOT_FOUND = "not_found"  # looked for automatically, not found for now
    NOT_RETRIEVABLE = "not_retrievable"  # declared by the person, with a reason


class TextPage(BaseModel):
    """Text of one page; ``number`` is the page of the PDF (1, 2…), ``label`` the
    number printed on it when it differs and could be read ("" otherwise)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    number: int = Field(ge=1)
    label: str = ""
    text: str


class PagePosition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    page: int = Field(ge=1)  # page of the PDF
    offset: int = Field(ge=0)  # characters into that page's text


class PagedText(BaseModel):
    """Text of a PDF by page, with the bibliography located when it could be found
    (``references_start`` up to ``references_end``, or the end of the text)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pages: tuple[TextPage, ...]
    references_start: PagePosition | None = None
    references_end: PagePosition | None = None

    def body(self) -> tuple[TextPage, ...]:
        """The pages without the bibliography (what may be sent to a model, D-102);
        appendices after the bibliography are kept."""
        start, end = self.references_start, self.references_end
        if start is None:
            return self.pages
        kept = []
        for page in self.pages:
            text = page.text
            cut = _offset_in(page, start)  # the bibliography starts here on this page…
            resume = len(text) if end is None else _offset_in(page, end)  # …and ends here
            kept.append(page.model_copy(update={"text": text[:cut] + text[max(cut, resume) :]}))
        return tuple(kept)


def _offset_in(page: TextPage, position: PagePosition) -> int:
    """Where ``position`` falls in the text of ``page``: its end if the position is on a
    later page, its start if on an earlier one."""
    if page.number < position.page:
        return len(page.text)
    if page.number > position.page:
        return 0
    return min(position.offset, len(page.text))


class FulltextDocument(BaseModel):
    """A PDF obtained for a reference, stored in ``textes/<sha256>.pdf`` with its text
    by page in ``textes/<sha256>.pages.json``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    reference_id: str
    origin: FulltextOrigin
    url: str = ""  # where it was downloaded (never in the public archive)
    license: str = ""  # as declared by the source, e.g. cc-by
    version: str = ""  # e.g. publishedVersion, acceptedVersion
    host_type: str = ""  # publisher or repository
    filename: str = ""  # name of the uploaded file
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_count: int = Field(ge=0)
    text_chars: int = Field(ge=0)  # characters of text found (0: scanned PDF)
    needs_ocr: bool  # too little text: character recognition is required
    references_page: int | None = None  # page where the bibliography starts
    converter: str  # library and version, e.g. "pymupdf 1.28.2"
    raw_dir: str = ""  # raw answers of the sources asked (brut/sources/<id>)
    created_at: AwareDatetime
    reviewer_id: str

    @property
    def open_access(self) -> bool:
        return self.origin in OPEN_ACCESS_ORIGINS


class RetrievalNote(BaseModel):
    """A reference left without a text: not found automatically, or declared not
    retrievable by the person (with the reason)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    reference_id: str
    status: RetrievalStatus
    reason: str = ""
    raw_dir: str = ""
    created_at: AwareDatetime
    reviewer_id: str


def _order(item: FulltextDocument | RetrievalNote) -> tuple[AwareDatetime, str]:
    return item.created_at, item.id


def current_documents(documents: Iterable[FulltextDocument]) -> dict[str, FulltextDocument]:
    """The document in force of each reference: the latest one added."""
    current: dict[str, FulltextDocument] = {}
    for document in sorted(documents, key=_order):
        current[document.reference_id] = document
    return current


def retrieval_statuses(
    sought: Iterable[str],
    documents: Iterable[FulltextDocument],
    notes: Iterable[RetrievalNote],
) -> dict[str, RetrievalStatus]:
    """Status of each sought reference: obtained as soon as it has a document (a text
    found after a note wins over it), otherwise the latest note, otherwise not sought."""
    with_document = {d.reference_id for d in documents}
    latest: dict[str, RetrievalStatus] = {}
    for note in sorted(notes, key=_order):
        latest[note.reference_id] = note.status
    return {
        ref: RetrievalStatus.OBTAINED
        if ref in with_document
        else latest.get(ref, RetrievalStatus.NOT_SOUGHT)
        for ref in dict.fromkeys(sought)
    }


class RetrievalCounts(BaseModel):
    """Numbers of the retrieval of full texts, over the references sought."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sought: int
    obtained: int
    open_access: int  # obtained from an open access source (OpenAlex, Unpaywall)
    uploaded: int
    not_sought: int
    not_found: int
    not_retrievable: int
    needs_ocr: int  # obtained, but without text: character recognition required

    @property
    def open_access_share(self) -> float | None:
        """Share of the sought references found in open access (criterion of tranche
        2.1); None when nothing is sought."""
        return self.open_access / self.sought if self.sought else None

    @property
    def started(self) -> bool:
        return self.not_sought < self.sought


def retrieval_counts(
    sought: Sequence[str],
    documents: Iterable[FulltextDocument],
    notes: Iterable[RetrievalNote],
) -> RetrievalCounts:
    """Counts by status; a reference counts by the origin of its document in force.
    Documents and notes of references no longer sought are ignored."""
    wanted = set(sought)
    documents = [d for d in documents if d.reference_id in wanted]
    statuses = retrieval_statuses(sought, documents, [n for n in notes if n.reference_id in wanted])
    current = current_documents(documents).values()
    by_status = {s: sum(1 for v in statuses.values() if v is s) for s in RetrievalStatus}
    return RetrievalCounts(
        sought=len(statuses),
        obtained=by_status[RetrievalStatus.OBTAINED],
        open_access=sum(1 for d in current if d.open_access),
        uploaded=sum(1 for d in current if d.origin is FulltextOrigin.UPLOAD),
        not_sought=by_status[RetrievalStatus.NOT_SOUGHT],
        not_found=by_status[RetrievalStatus.NOT_FOUND],
        not_retrievable=by_status[RetrievalStatus.NOT_RETRIEVABLE],
        needs_ocr=sum(1 for d in current if d.needs_ocr),
    )


# --- Quotes located by page -----------------------------------------------------------


def canonical(text: str) -> str:
    """Letters and digits only, case folded, after NFKC (ligatures, full-width forms)."""
    return "".join(c for c in unicodedata.normalize("NFKC", text).casefold() if c.isalnum())


class QuoteCheck(StrEnum):
    AT_PAGE = "at_page"  # found on the page given
    OTHER_PAGE = "other_page"  # found, but only on other pages
    NOT_FOUND = "not_found"


class QuoteLocation(BaseModel):
    """Pages of the PDF where a quote was found; a quote over a page break counts for
    every page it touches."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pages: tuple[tuple[int, ...], ...]  # one tuple of pages per occurrence

    @property
    def found(self) -> bool:
        return bool(self.pages)

    @property
    def first_page(self) -> int | None:
        return self.pages[0][0] if self.pages else None


def locate_quote(pages: Sequence[TextPage], quote: str) -> QuoteLocation:
    """Every occurrence of ``quote`` in ``pages``, with the pages it spans."""
    target = canonical(quote)
    if not target:
        return QuoteLocation(pages=())
    texts = [canonical(page.text) for page in pages]
    whole = "".join(texts)
    ends: list[int] = []  # canonical offset where each page ends
    total = 0
    for text in texts:
        total += len(text)
        ends.append(total)
    occurrences = []
    start = whole.find(target)
    while start != -1:
        stop = start + len(target)
        spanned = tuple(
            page.number
            for page, end, text in zip(pages, ends, texts, strict=True)
            if text and end - len(text) < stop and start < end
        )
        occurrences.append(spanned)
        start = whole.find(target, start + 1)
    return QuoteLocation(pages=tuple(occurrences))


def check_quote(pages: Sequence[TextPage], quote: str, page: int | None) -> QuoteCheck:
    """Whether ``quote`` is on the PDF page ``page``, elsewhere, or nowhere."""
    location = locate_quote(pages, quote)
    if not location.found:
        return QuoteCheck.NOT_FOUND
    if page is not None and any(page in spanned for spanned in location.pages):
        return QuoteCheck.AT_PAGE
    return QuoteCheck.OTHER_PAGE


# --- Uploaded files matched to references -----------------------------------------------

_DOI = re.compile(r"\b10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)
_TRAILING = ".,;:)]}'"
MIN_TITLE_CHARS = 20  # shorter titles ("Editorial") are not matched on their own


def dois_in_text(text: str) -> list[str]:
    """DOIs written in ``text``, normalized, in their order of appearance."""
    found = []
    for match in _DOI.finditer(text):
        doi = clean_doi(match.group(0).rstrip(_TRAILING))
        if doi and doi not in found:
            found.append(doi)
    return found


class MatchKind(StrEnum):
    DOI_IN_FILENAME = "doi_in_filename"
    DOI_IN_TEXT = "doi_in_text"
    TITLE = "title"


class UploadMatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reference_id: str | None
    kind: MatchKind | None = None


def _single(found: Iterable[str]) -> str | None:
    distinct = set(found)
    return distinct.pop() if len(distinct) == 1 else None


def match_upload(
    filename: str,
    first_pages: str,
    dois: Mapping[str, str],
    titles: Mapping[str, str],
) -> UploadMatch:
    """Reference of an uploaded PDF: by the DOI in its name (where ``/`` may have been
    replaced), then the first DOI of a reference in its first pages, then a title of at
    least 20 characters found in them. ``dois`` and ``titles`` map reference ids to the
    DOI and title of the references sought; an ambiguous match gives no reference."""
    name = canonical(filename)
    by_doi: dict[str, list[str]] = {}
    for ref, doi in dois.items():
        if key := clean_doi(doi):
            by_doi.setdefault(key, []).append(ref)
    in_name = _single(
        ref for doi, refs in by_doi.items() if len(canonical(doi)) >= 8 and canonical(doi) in name
        for ref in refs
    )  # fmt: skip
    if in_name is not None:
        return UploadMatch(reference_id=in_name, kind=MatchKind.DOI_IN_FILENAME)
    for doi in dois_in_text(first_pages):
        if doi in by_doi:
            in_text = _single(by_doi[doi])
            if in_text is not None:
                return UploadMatch(reference_id=in_text, kind=MatchKind.DOI_IN_TEXT)
            break
    text = canonical(first_pages)
    by_title = _single(
        ref for ref, title in titles.items()
        if len(key := canonical(title)) >= MIN_TITLE_CHARS and key in text
    )  # fmt: skip
    if by_title is not None:
        return UploadMatch(reference_id=by_title, kind=MatchKind.TITLE)
    return UploadMatch(reference_id=None)
