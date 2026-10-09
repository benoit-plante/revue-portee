"""PDF to text by page (EF-SEL-15), with PyMuPDF (D-004, docs/03-architecture.md §2).

Each page keeps its number in the PDF; the number printed on it is recorded when the
PDF gives page labels, or when the numbers read at the top or bottom of the pages agree
with a constant shift. The bibliography is located by its heading (the last one in the
text) so that it is not sent to a model (D-102); appendices after it are kept. A PDF
with almost no text (scanned) is flagged: character recognition is not done here.

Conversion 2 (essai-screen-fulltext-v1, docs/resultats/):

- some PDFs draw their text twice (a "shadow" layer under the visible one), which cut
  the quotes of the AI in two: a piece of text drawn again at the same place (within
  two points) is kept once, and on a page where most lines come in pairs, the pairs
  are merged;
- a text made mostly of control or unassigned characters (a font without a table of
  its characters) cannot be read: it is flagged like a scanned PDF.

The number of the conversion is part of ``CONVERTER``: a text converted before keeps
its text, and a new conversion is added as a new document.
"""

import re
import unicodedata
from collections import Counter
from typing import Any

import pymupdf

from revue_portee.domain.fulltext import PagedText, PagePosition, TextPage, canonical
from revue_portee.i18n import gettext as _

__all__ = [
    "CONVERSION",
    "CONVERTER",
    "DOUBLED_SHARE",
    "MAX_UNREADABLE_SHARE",
    "MIN_CHARS_PER_PAGE",
    "SHADOW_TOLERANCE",
    "ConversionError",
    "convert_pdf",
    "locate_bibliography",
    "merge_doubled_lines",
    "needs_ocr",
    "printed_labels",
    "unreadable_share",
]

CONVERSION = 2  # version of the conversion rules of this module
CONVERTER = f"pymupdf {pymupdf.__version__}, conversion {CONVERSION}"
DOUBLED_SHARE = 0.6  # share of lines in pairs from which a page is taken as doubled
MIN_CHARS_PER_PAGE = 200  # fewer characters per page on average: a scanned PDF
MAX_UNREADABLE_SHARE = 0.1  # more control or unassigned characters: text not decodable
SHADOW_TOLERANCE = 2.0  # points: the same text drawn again this close is a shadow

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


def _key(line: str) -> str:
    return canonical(line)


def merge_doubled_lines(text: str) -> str:
    """``text`` without the repeats of a doubled page. Lines are compared on their
    letters and digits, case folded; a doubled page holds its lines in pairs (A A B B…).
    When at least 60 % of the lines with text belong to such pairs, each pair keeps one
    line. Longer runs of a same line (a table, a filler) are left as they are, and so is
    a page with a few repeats."""
    lines = text.split("\n")
    runs: list[list[str]] = []  # consecutive lines with the same key
    keys: list[str] = []
    for line in lines:
        key = _key(line)
        if runs and key and key == keys[-1]:
            runs[-1].append(line)
        else:
            runs.append([line])
            keys.append(key)
    filled = sum(len(run) for run, key in zip(runs, keys, strict=True) if key)
    paired = sum(2 for run, key in zip(runs, keys, strict=True) if key and len(run) == 2)
    if not filled or paired < DOUBLED_SHARE * filled:
        return text
    return "\n".join(
        line
        for run, key in zip(runs, keys, strict=True)
        for line in (run[:1] if key and len(run) == 2 else run)
    )


def _page_text(page: Any) -> str:  # noqa: ANN401 - a PyMuPDF page (partly typed)
    """Text of a page, a span drawn again at the same place (a shadow layer) kept once;
    the text of the library as it is when no span is drawn twice."""
    plain = str(page.get_text())
    seen: dict[str, list[tuple[float, float]]] = {}
    lines: list[str] = []
    dropped = 0
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            kept = []
            for span in line.get("spans", []):
                text = str(span.get("text", ""))
                x, y = (float(v) for v in span.get("origin", (0.0, 0.0)))
                places = seen.setdefault(text, [])
                if text.strip() and any(
                    abs(x - px) < SHADOW_TOLERANCE and abs(y - py) < SHADOW_TOLERANCE
                    for px, py in places
                ):
                    dropped += 1
                    continue
                places.append((x, y))
                kept.append(text)
            if kept:
                lines.append("".join(kept))
    return plain if dropped == 0 else "\n".join(lines) + "\n"


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
            texts.append(merge_doubled_lines(_page_text(page)))
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


def unreadable_share(text: PagedText) -> float:
    """Share of the characters (spaces aside) that are control, private or unassigned
    characters, or the replacement character: text that could not be decoded."""
    chars = [c for page in text.pages for c in page.text if not c.isspace()]
    if not chars:
        return 0.0
    bad = sum(1 for c in chars if c == "\ufffd" or unicodedata.category(c) in ("Cc", "Co", "Cn"))
    return bad / len(chars)


def needs_ocr(text: PagedText) -> bool:
    """No readable text: too little for the number of pages (a scanned PDF), or text
    that cannot be decoded."""
    chars = sum(len("".join(page.text.split())) for page in text.pages)
    too_little = chars < MIN_CHARS_PER_PAGE * max(1, len(text.pages))
    return too_little or unreadable_share(text) > MAX_UNREADABLE_SHARE
