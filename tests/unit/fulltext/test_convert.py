"""PDF to text by page with PyMuPDF (EF-SEL-15): page numbers, printed numbers,
bibliography, scanned PDFs, unreadable files."""

import pymupdf
import pytest

from revue_portee.domain.fulltext import (
    PagedText,
    PagePosition,
    QuoteCheck,
    TextPage,
    check_quote,
)
from revue_portee.fulltext.convert import (
    ConversionError,
    convert_pdf,
    locate_bibliography,
    merge_doubled_lines,
    needs_ocr,
    printed_labels,
    unreadable_share,
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


def test_doubled_lines_are_merged_on_a_doubled_page() -> None:
    doubled = "Background\nBackground\nDBT iswidely considered\nDBT is widely considered\n\n12\n12"
    assert merge_doubled_lines(doubled) == "Background\nDBT iswidely considered\n\n12"
    # runs of more than two, and a few pairs on a normal page, are left as they are
    filler = "\n".join(["Same line."] * 5 + ["Other."])
    assert merge_doubled_lines(filler) == filler
    table = "Table 1\nGroup\n0\n0\nMeasure\nScore\nTotal"
    assert merge_doubled_lines(table) == table
    assert merge_doubled_lines("") == ""


def test_quote_found_in_a_doubled_pdf() -> None:
    lines = [
        "Women with borderline personality",
        "disorder aged 18 to 70 years",
        "were randomly assigned",
    ]
    data = make_pdf(["\n".join(line for line in lines for _ in range(2))])
    text = convert_pdf(data)
    quote = "personality disorder aged 18 to 70 years were randomly"
    assert check_quote(text.pages, quote, 1) is QuoteCheck.AT_PAGE


def _shadowed_pdf(lines: list[str]) -> bytes:
    """A page whose text is drawn twice, the second time half a point lower and to the
    right, as some publishers' PDFs do (a "shadow" text layer)."""
    document = pymupdf.open()  # type: ignore[no-untyped-call]
    page = document.new_page()
    for number, line in enumerate(lines):
        for shift in (0.0, 0.5):
            page.insert_text((72 + shift, 72 + 14 * number + shift), line, fontsize=10)
    data = bytes(document.tobytes())  # type: ignore[no-untyped-call]
    document.close()  # type: ignore[no-untyped-call]
    return data


def test_shadow_text_is_kept_once() -> None:
    lines = ["The treatment combines weekly individual", "cognitive-behavioural psychotherapy"]
    text = convert_pdf(_shadowed_pdf(lines))
    assert text.pages[0].text.count("weekly individual") == 1
    quote = "combines weekly individual cognitive-behavioural psychotherapy"
    assert check_quote(text.pages, quote, 1) is QuoteCheck.AT_PAGE
    plain = convert_pdf(make_pdf(["\n".join(lines)]))
    assert plain.pages[0].text.count("weekly individual") == 1  # nothing drawn twice


def test_text_that_cannot_be_decoded_is_flagged() -> None:
    garbled = ")," + chr(0x19) + " " + chr(0x18) + " -- " + chr(0x15) + chr(0x0B) + "-"
    pages = (TextPage(number=1, text=(garbled + "\n") * 60),)
    assert unreadable_share(PagedText(pages=pages)) > 0.1
    assert needs_ocr(PagedText(pages=pages))
    readable = (TextPage(number=1, text=LONG),)
    assert unreadable_share(PagedText(pages=readable)) == 0.0
    assert not needs_ocr(PagedText(pages=readable))
    assert unreadable_share(PagedText(pages=(TextPage(number=1, text=" "),))) == 0.0
