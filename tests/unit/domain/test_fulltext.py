"""Full texts: statuses, counts, text without the bibliography, quotes located by page,
uploaded files matched to references (pure functions, counts made by hand)."""

from datetime import UTC, datetime, timedelta

import pytest

from revue_portee.domain.fulltext import (
    FulltextDocument,
    FulltextOrigin,
    MatchKind,
    PagedText,
    PagePosition,
    QuoteCheck,
    RetrievalCounts,
    RetrievalNote,
    RetrievalStatus,
    TextPage,
    canonical,
    check_quote,
    current_documents,
    dois_in_text,
    locate_quote,
    match_upload,
    retrieval_counts,
    retrieval_statuses,
)

T0 = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


def _document(
    ref: str, origin: FulltextOrigin, minute: int, *, ocr: bool = False
) -> FulltextDocument:
    return FulltextDocument(
        id=f"D{minute:02d}",
        reference_id=ref,
        origin=origin,
        sha256=f"{minute:064x}",
        page_count=3,
        text_chars=0 if ocr else 9000,
        needs_ocr=ocr,
        converter="pymupdf test",
        created_at=T0 + timedelta(minutes=minute),
        reviewer_id="R",
    )


def _note(ref: str, status: RetrievalStatus, minute: int) -> RetrievalNote:
    return RetrievalNote(
        id=f"N{minute:02d}",
        reference_id=ref,
        status=status,
        reason="raison",
        created_at=T0 + timedelta(minutes=minute),
        reviewer_id="R",
    )


def test_statuses_documents_win_over_notes_and_the_latest_note_counts() -> None:
    documents = [_document("a", FulltextOrigin.OPENALEX, 5)]
    notes = [
        _note("a", RetrievalStatus.NOT_FOUND, 1),  # found later: obtained
        _note("b", RetrievalStatus.NOT_FOUND, 2),
        _note("b", RetrievalStatus.NOT_RETRIEVABLE, 3),  # latest note of b
        _note("c", RetrievalStatus.NOT_RETRIEVABLE, 4),
        _note("c", RetrievalStatus.NOT_FOUND, 6),  # looked for again: latest note of c
    ]
    assert retrieval_statuses(["a", "b", "c", "d", "a"], documents, notes) == {
        "a": RetrievalStatus.OBTAINED,
        "b": RetrievalStatus.NOT_RETRIEVABLE,
        "c": RetrievalStatus.NOT_FOUND,
        "d": RetrievalStatus.NOT_SOUGHT,
    }


def test_the_latest_document_is_in_force() -> None:
    first = _document("a", FulltextOrigin.UNPAYWALL, 1)
    second = _document("a", FulltextOrigin.UPLOAD, 2)
    assert current_documents([second, first]) == {"a": second}


def test_counts_made_by_hand() -> None:
    # Six references sought: a and b in open access, c uploaded after an open access
    # version (counts as uploaded), d not found, e declared not retrievable, f never
    # looked for; g is no longer sought and is ignored. b has no text (scanned).
    documents = [
        _document("a", FulltextOrigin.OPENALEX, 1),
        _document("b", FulltextOrigin.UNPAYWALL, 2, ocr=True),
        _document("c", FulltextOrigin.UNPAYWALL, 3),
        _document("c", FulltextOrigin.UPLOAD, 4),
        _document("g", FulltextOrigin.UPLOAD, 5),
    ]
    notes = [
        _note("d", RetrievalStatus.NOT_FOUND, 6),
        _note("e", RetrievalStatus.NOT_RETRIEVABLE, 7),
        _note("g", RetrievalStatus.NOT_RETRIEVABLE, 8),
    ]
    counts = retrieval_counts(["a", "b", "c", "d", "e", "f"], documents, notes)
    assert counts == RetrievalCounts(
        sought=6,
        obtained=3,
        open_access=2,
        uploaded=1,
        not_sought=1,
        not_found=1,
        not_retrievable=1,
        needs_ocr=1,
    )
    assert counts.open_access_share == pytest.approx(2 / 6)
    assert counts.started


def test_counts_with_nothing_sought() -> None:
    counts = retrieval_counts([], [], [])
    assert counts.open_access_share is None
    assert not counts.started


def _pages(*texts: str) -> tuple[TextPage, ...]:
    return tuple(TextPage(number=i, text=t) for i, t in enumerate(texts, start=1))


def test_body_leaves_out_the_bibliography_and_keeps_the_appendix() -> None:
    text = PagedText(
        pages=_pages("Intro\nResults", "Discussion\nReferences\n1. A", "2. B\nAppendix A\nTable"),
        references_start=PagePosition(page=2, offset=11),
        references_end=PagePosition(page=3, offset=5),
    )
    assert [p.text for p in text.body()] == ["Intro\nResults", "Discussion\n", "Appendix A\nTable"]


def test_body_without_end_runs_to_the_end_and_on_the_same_page() -> None:
    pages = _pages("Intro", "Body References 1. A", "2. B")
    to_end = PagedText(pages=pages, references_start=PagePosition(page=2, offset=5))
    assert [p.text for p in to_end.body()] == ["Intro", "Body ", ""]
    same_page = PagedText(
        pages=pages,
        references_start=PagePosition(page=2, offset=5),
        references_end=PagePosition(page=2, offset=16),
    )
    assert [p.text for p in same_page.body()] == ["Intro", "Body 1. A", "2. B"]
    assert PagedText(pages=pages).body() == pages


def test_canonical_form() -> None:
    assert canonical("Well-\nknown « ﬁndings »,  ÉTÉ") == "wellknownfindingsété"


def test_quotes_located_by_page() -> None:
    pages = _pages(
        "Methods. We recruited older adults living alone.",
        "The interviews were analysed thema-\ntically. Older adults",
        "living alone reported « loneliness ».",
    )
    assert locate_quote(pages, "analysed thematically").pages == ((2,),)
    over_break = locate_quote(pages, "older adults living alone")
    assert over_break.pages == ((1,), (2, 3))
    assert over_break.first_page == 1
    assert check_quote(pages, "reported “loneliness”", 3) is QuoteCheck.AT_PAGE
    assert check_quote(pages, "older adults living alone", 3) is QuoteCheck.AT_PAGE
    assert check_quote(pages, "analysed thematically", 1) is QuoteCheck.OTHER_PAGE
    assert check_quote(pages, "analysed thematically", None) is QuoteCheck.OTHER_PAGE
    assert check_quote(pages, "a randomised trial", 2) is QuoteCheck.NOT_FOUND
    assert check_quote(pages, " … ", 2) is QuoteCheck.NOT_FOUND
    assert not locate_quote(pages, "").found
    assert locate_quote(pages, "").first_page is None


def test_quote_on_a_page_without_text() -> None:
    pages = _pages("First page text", "", "third")
    assert locate_quote(pages, "text third").pages == ((1, 3),)


def test_dois_in_text() -> None:
    text = "doi: 10.1186/s12889-020-1.  See https://doi.org/10.1016/J.X.2020.01.002), "
    text += "10.1186/S12889-020-1"
    assert dois_in_text(text) == ["10.1186/S12889-020-1", "10.1016/J.X.2020.01.002"]


DOIS = {"r1": "10.1186/s12889-020-08001-1", "r2": "10.1016/j.ssmph.2021.100", "r3": ""}
TITLES = {
    "r1": "Loneliness among older adults after residential relocation",
    "r2": "Community gardens and wellbeing in public housing",
    "r3": "Editorial",
}


def test_match_by_doi_in_the_file_name() -> None:
    match = match_upload("10.1186_s12889-020-08001-1.pdf", "", DOIS, TITLES)
    assert (match.reference_id, match.kind) == ("r1", MatchKind.DOI_IN_FILENAME)


def test_match_by_the_first_doi_of_a_reference_in_the_text() -> None:
    text = "Cites 10.9999/other first. https://doi.org/10.1016/j.ssmph.2021.100 Received"
    match = match_upload("article.pdf", text, DOIS, TITLES)
    assert (match.reference_id, match.kind) == ("r2", MatchKind.DOI_IN_TEXT)


def test_match_by_title() -> None:
    text = "RESEARCH\nLoneliness among older adults after\nresidential relocation\nA. Author"
    match = match_upload("scan 12.pdf", text, DOIS, TITLES)
    assert (match.reference_id, match.kind) == ("r1", MatchKind.TITLE)


def test_no_match_when_ambiguous_or_short() -> None:
    assert match_upload("x.pdf", "Editorial", DOIS, TITLES).reference_id is None
    both = "Loneliness among older adults after residential relocation and community "
    both += "gardens and wellbeing in public housing"
    assert match_upload("x.pdf", both, DOIS, TITLES).reference_id is None
    twice = {"a": "10.1/abcdefgh", "b": "10.1/ABCDEFGH"}
    assert match_upload("10.1_abcdefgh.pdf", "", twice, {}).reference_id is None
    assert match_upload("x.pdf", "see 10.1/abcdefgh", twice, {}).reference_id is None
