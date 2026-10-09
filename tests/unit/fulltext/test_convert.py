"""PDF to text by page with PyMuPDF (EF-SEL-15): page numbers, printed numbers,
bibliography, scanned PDFs, unreadable files."""

import pytest

from revue_portee.domain.fulltext import PagePosition, QuoteCheck, check_quote
from revue_portee.fulltext.convert import (
    ConversionError,
    convert_pdf,
    locate_bibliography,
    needs_ocr,
    printed_labels,
)
from support import make_pdf

LONG = "Older adults who moved reported loneliness in the first months. " * 6


def test_text_by_page_with_quotes_found_on_their_page() -> None:
    data = make_pdf(
        [
            "Loneliness among older adults\nafter residential relocation\n" + LONG[:60],
            "Methods\nWe interviewed 24 residents\nof three seniors' residences.",
            "Results\nParticipants described a loss\nof their neighbourhood ties.",
        ]
    )
    text = convert_pdf(data)
    assert [p.number for p in text.pages] == [1, 2, 3]
    assert [p.label for p in text.pages] == ["", "", ""]
    assert check_quote(text.pages, "We interviewed 24 residents of three", 2) is QuoteCheck.AT_PAGE
    assert check_quote(text.pages, "a loss of their neighbourhood ties", 3) is QuoteCheck.AT_PAGE
    assert check_quote(text.pages, "a loss of their neighbourhood ties", 2) is (
        QuoteCheck.OTHER_PAGE
    )
    assert text.references_start is None


def test_page_labels_of_the_pdf_are_kept() -> None:
    text = convert_pdf(make_pdf(["one", "two"], first_label=233))
    assert [p.label for p in text.pages] == ["233", "234"]


def test_printed_numbers_read_with_a_constant_shift() -> None:
    pages = [f"Journal of Aging\nBody of page {i}\n{i + 46}" for i in range(1, 5)]
    pages[2] = "Table 2\nno number on this page"
    assert printed_labels(pages) == ["47", "48", "49", "50"]
    text = convert_pdf(make_pdf(pages))
    assert [p.label for p in text.pages] == ["47", "48", "49", "50"]


def test_printed_numbers_not_trusted_without_agreement() -> None:
    assert printed_labels(["Page 1 of 3\nA", "B\n2", "C\n3"]) == ["", "", ""]  # no shift
    assert printed_labels(["A\n12", "B\n40", "C\n7"]) == ["", "", ""]  # no agreement
    assert printed_labels(["A", "B"]) == ["", ""]
    assert printed_labels(["p. 1\nA", "B\n2"]) == ["", ""]


def test_shift_below_the_first_page_gives_no_label() -> None:
    # Covers numbered from the second page: the cover has no printed number.
    assert printed_labels(["Cover", "Abstract\n1", "Methods\n2", "Results\n3"]) == [
        "", "1", "2", "3",
    ]  # fmt: skip


def test_bibliography_located_by_its_last_heading() -> None:
    pages = [
        "Contents\nReferences .... 3",
        "Body\nResults",
        "Discussion\nREFERENCES\n1. Smith J. (2020)",
        "2. Doe A.\nAppendix 1: interview guide\nQuestions",
    ]
    start, end = locate_bibliography(pages)
    assert start == PagePosition(page=3, offset=len("Discussion\n"))
    assert end == PagePosition(page=4, offset=len("2. Doe A.\n"))
    text = convert_pdf(make_pdf(pages))
    assert text.references_start is not None
    assert text.references_start.page == 3
    body = " ".join(p.text for p in text.body())
    assert "Smith" not in body
    assert "Doe" not in body
    assert "interview guide" in body
    assert "Discussion" in body


def test_bibliography_headings_in_french_and_numbered() -> None:
    assert locate_bibliography(["Texte", "7. Références bibliographiques :\nA"])[0] == (
        PagePosition(page=2, offset=0)
    )
    assert locate_bibliography(["Texte\nBibliographie\nA\nAnnexe B"]) == (
        PagePosition(page=1, offset=6),
        PagePosition(page=1, offset=len("Texte\nBibliographie\nA\n")),
    )
    assert locate_bibliography(["Appendix\nText"]) == (None, None)
    # an appendix heading before the bibliography on its page does not end it
    assert locate_bibliography(["Annexe A\nReferences\nB"]) == (
        PagePosition(page=1, offset=9),
        None,
    )


def test_scanned_pdf_is_flagged() -> None:
    assert needs_ocr(convert_pdf(make_pdf(["", "12"])))
    assert not needs_ocr(convert_pdf(make_pdf([LONG.replace(". ", ".\n")])))


@pytest.mark.parametrize("data", [b"", b"<html>Sign in</html>", b"%PDF-1.7 truncated"])
def test_unreadable_files(data: bytes) -> None:
    with pytest.raises(ConversionError, match="PDF"):
        convert_pdf(data)


def test_protected_pdf() -> None:
    with pytest.raises(ConversionError, match="mot de passe"):
        convert_pdf(make_pdf(["secret"], password="pass"))
