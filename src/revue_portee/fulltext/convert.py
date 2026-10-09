"""PDF to text by page (EF-SEL-15), with PyMuPDF (D-004, docs/03-architecture.md §2).

Each page keeps its number in the PDF; the number printed on it is recorded when the
PDF gives page labels, or when the numbers read at the top or bottom of the pages agree
with a constant shift. The bibliography is located by its heading (the last one in the
text) so that it is not sent to a model (D-102); appendices after it are kept. A PDF
with almost no text (scanned) is flagged: character recognition is not done here.
"""

import re
from collections import Counter

import pymupdf

from revue_portee.domain.fulltext import PagedText, PagePosition, TextPage
from revue_portee.i18n import gettext as _

__all__ = [
    "CONVERTER",
    "MIN_CHARS_PER_PAGE",
    "ConversionError",
    "convert_pdf",
    "locate_bibliography",
    "needs_ocr",
    "printed_labels",
]

CONVERTER = f"pymupdf {pymupdf.__version__}"
MIN_CHARS_PER_PAGE = 200  # fewer characters per page on average: a scanned PDF

_PRINTED = re.compile(
    r"^(?:page|p\.)?\s*(\d{1,4})(?:\s*(?:of|/|de|sur)\s*\d{1,4})?$", re.IGNORECASE
)
_BIBLIOGRAPHY = re.compile(
    r"^[ \t]*(?:\d{1,2}\.?[ \t]*)?(?:references|reference list|bibliography|works cited|"
    r"literature cited|références(?: bibliographiques)?|bibliographie)[ \t]*:?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_AFTER_BIBLIOGRAPHY = re.compile(
    r"^[ \t]*(?:appendix|appendices|annexe|annexes|supplementary (?:material|materials|data|"
    r"information)|supporting information)\b[^\n]{0,80}$",
    re.IGNORECASE | re.MULTILINE,
)


class ConversionError(ValueError):
    """The file cannot be read as a PDF (French message)."""


def printed_labels(pages: list[str]) -> list[str]:
    """Number printed on each page ("" when it is the PDF page number or unknown): the
    numbers read in the first or last three lines of the pages, kept only when one shift
    from the PDF numbering explains them on at least two pages and half the pages where
    a number was read."""
    shifts: Counter[int] = Counter()
    read = 0
    for index, text in enumerate(pages, start=1):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        numbers = {
            int(match.group(1))
            for line in lines[:3] + lines[-3:]
            if (match := _PRINTED.match(line))
        }
        if numbers:
            read += 1
            shifts.update({number - index for number in numbers})
    if not shifts:
        return [""] * len(pages)
    shift, agreeing = shifts.most_common(1)[0]
    if shift == 0 or agreeing < max(2, read / 2):
        return [""] * len(pages)
    return [str(index + shift) if index + shift >= 1 else "" for index in range(1, len(pages) + 1)]


def locate_bibliography(pages: list[str]) -> tuple[PagePosition | None, PagePosition | None]:
    """Start of the bibliography (its last heading in the text) and, when an appendix
    heading follows it, where the bibliography ends."""
    start: PagePosition | None = None
    for number, text in enumerate(pages, start=1):
        for match in _BIBLIOGRAPHY.finditer(text):
            start = PagePosition(page=number, offset=match.start())
    if start is None:
        return None, None
    for number, text in enumerate(pages, start=1):
        if number < start.page:
            continue
        for match in _AFTER_BIBLIOGRAPHY.finditer(text):
            if number > start.page or match.start() > start.offset:
                return start, PagePosition(page=number, offset=match.start())
    return start, None


def convert_pdf(data: bytes) -> PagedText:
    """Text of each page of the PDF ``data``."""
    # The file comes from outside (a download, an upload): any failure of the library on
    # it is reported as an unreadable PDF. PyMuPDF is only partly typed: its untyped
    # calls stay inside this function.
    try:
        document = pymupdf.open(stream=data, filetype="pdf")  # type: ignore[no-untyped-call]
    except Exception as error:  # see above
        raise ConversionError(_("The file is not a readable PDF.")) from error
    try:
        if document.needs_pass:
            raise ConversionError(_("The PDF is protected by a password."))
        texts: list[str] = []
        labels: list[str] = []
        for index in range(document.page_count):
            page = document.load_page(index)  # type: ignore[no-untyped-call]
            texts.append(str(page.get_text()))
            labels.append(str(page.get_label() or ""))
    except ConversionError:
        raise
    except Exception as error:  # see above
        raise ConversionError(_("The file is not a readable PDF.")) from error
    finally:
        document.close()  # type: ignore[no-untyped-call]
    printed = printed_labels(texts)
    pages = []
    for number, (text, label, guess) in enumerate(zip(texts, labels, printed, strict=True), 1):
        shown = label if label and label != str(number) else guess
        pages.append(TextPage(number=number, label=shown, text=text))
    start, end = locate_bibliography(texts)
    return PagedText(pages=tuple(pages), references_start=start, references_end=end)


def needs_ocr(text: PagedText) -> bool:
    """Too little text for the number of pages: a scanned PDF."""
    chars = sum(len("".join(page.text.split())) for page in text.pages)
    return chars < MIN_CHARS_PER_PAGE * max(1, len(text.pages))
