"""Comparative test of PDF text extraction by page (tranche 2.1, docs/03-architecture.md
§2): PyMuPDF, the default, against pypdf and pdfplumber.

Criterion of the roadmap: on 30 test PDFs, the right page number for at least 98% of
the quotes checked. Until the AI quotes full texts (tranche 2.2), the quotes are
passages of eight words drawn at random, with a recorded seed, from the text of a page
as one of the *other* libraries reads it; each library is then asked where the passage
is (``check_quote``). A library scores when it finds the passage on the page it was
drawn from. The test thus measures whether the libraries agree on the page of a
passage, through differences of reading order, hyphenation and ligatures.

pypdf and pdfplumber are development dependencies, used only here. The report names
the PDFs by their SHA-256 digest only and quotes no text (copyright).
"""

import hashlib
import io
import random
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from revue_portee.domain.fulltext import QuoteCheck, TextPage, check_quote
from revue_portee.fulltext.convert import CONVERTER, ConversionError, convert_pdf
from revue_portee.i18n import gettext as _

__all__ = [
    "EXTRACTORS",
    "QUOTE_WORDS",
    "TARGET",
    "BenchmarkResult",
    "ExtractorScore",
    "PdfResult",
    "draw_quotes",
    "pdf_files",
    "report_markdown",
    "run_benchmark",
]

QUOTE_WORDS = 8
QUOTES_PER_PAGE = 3
TARGET = 0.98
Extractor = Callable[[bytes], list[str]]


def _pymupdf(data: bytes) -> list[str]:
    return [page.text for page in convert_pdf(data).pages]


def _pypdf(data: bytes) -> list[str]:
    import pypdf  # development dependency, used only by this test

    reader = pypdf.PdfReader(io.BytesIO(data))
    return [page.extract_text() or "" for page in reader.pages]


def _pdfplumber(data: bytes) -> list[str]:
    import pdfplumber  # development dependency, used only by this test

    with pdfplumber.open(io.BytesIO(data)) as document:
        return [page.extract_text() or "" for page in document.pages]


EXTRACTORS: dict[str, Extractor] = {
    "pymupdf": _pymupdf,
    "pypdf": _pypdf,
    "pdfplumber": _pdfplumber,
}


def _pages(texts: Sequence[str]) -> list[TextPage]:
    return [TextPage(number=n, text=t) for n, t in enumerate(texts, start=1)]


def draw_quotes(
    texts: Sequence[str], rng: random.Random, *, per_page: int = QUOTES_PER_PAGE
) -> list[tuple[int, str]]:
    """Up to ``per_page`` passages of eight consecutive words from each page, with the
    page they come from."""
    quotes = []
    for number, text in enumerate(texts, start=1):
        words = text.split()
        starts = range(len(words) - QUOTE_WORDS + 1)
        for start in rng.sample(starts, min(per_page, len(starts))):
            quotes.append((number, " ".join(words[start : start + QUOTE_WORDS])))
    return quotes


@dataclass
class ExtractorScore:
    checked: int = 0
    at_page: int = 0
    other_page: int = 0
    not_found: int = 0

    def add(self, check: QuoteCheck) -> None:
        self.checked += 1
        if check is QuoteCheck.AT_PAGE:
            self.at_page += 1
        elif check is QuoteCheck.OTHER_PAGE:
            self.other_page += 1
        else:
            self.not_found += 1

    @property
    def rate(self) -> float | None:
        return self.at_page / self.checked if self.checked else None


@dataclass
class PdfResult:
    sha256: str
    pages: int
    scores: dict[str, ExtractorScore] = field(default_factory=dict)
    error: str = ""  # the PDF could not be read by every library


@dataclass
class BenchmarkResult:
    seed: int
    generated_at: datetime
    pdfs: list[PdfResult]
    converter: str = CONVERTER

    def total(self, extractor: str) -> ExtractorScore:
        total = ExtractorScore()
        for pdf in self.pdfs:
            score = pdf.scores.get(extractor)
            if score is not None:
                total.checked += score.checked
                total.at_page += score.at_page
                total.other_page += score.other_page
                total.not_found += score.not_found
        return total


def _score(data: bytes, rng: random.Random) -> PdfResult:
    sha256 = hashlib.sha256(data).hexdigest()
    try:
        texts = {name: extract(data) for name, extract in EXTRACTORS.items()}
    except ConversionError as error:
        return PdfResult(sha256=sha256, pages=0, error=str(error))
    except Exception as error:  # a library failing on a file is a result
        return PdfResult(sha256=sha256, pages=0, error=type(error).__name__)
    counts = {len(t) for t in texts.values()}
    if len(counts) != 1:
        return PdfResult(sha256=sha256, pages=max(counts), error="page counts differ")
    result = PdfResult(sha256=sha256, pages=counts.pop())
    drawn = {name: draw_quotes(t, rng) for name, t in texts.items()}
    for name, candidate in texts.items():
        pages = _pages(candidate)
        score = ExtractorScore()
        for source, quotes in drawn.items():
            if source == name:
                continue
            for page, quote in quotes:
                score.add(check_quote(pages, quote, page))
        result.scores[name] = score
    return result


def run_benchmark(files: Sequence[Path], *, seed: int, now: datetime) -> BenchmarkResult:
    """Score every library on the PDFs ``files`` (sorted by digest, then drawn with
    ``seed``, so that the same files give the same quotes)."""
    contents = sorted((p.read_bytes() for p in files), key=lambda d: hashlib.sha256(d).digest())
    rng = random.Random(seed)  # noqa: S311 - reproducible draw, not security
    return BenchmarkResult(seed=seed, generated_at=now, pdfs=[_score(d, rng) for d in contents])


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


def report_markdown(result: BenchmarkResult) -> str:
    """Report in French, for ``docs/resultats/``."""
    read = [p for p in result.pdfs if not p.error]
    lines = [
        "# Essai comparatif de l'extraction du texte par page",
        "",
        f"- Date : {result.generated_at:%Y-%m-%d}; outil : {result.converter}",
        f"- PDF : {len(result.pdfs)} (lus par les trois bibliothèques : {len(read)}); "
        f"pages : {sum(p.pages for p in read)}",
        f"- Passages : {QUOTE_WORDS} mots consécutifs, jusqu'à {QUOTES_PER_PAGE} par page et "
        f"par bibliothèque, tirés avec la graine {result.seed} dans le texte lu par les deux "
        "autres bibliothèques",
        f"- Critère de la tranche 2.1 : bon numéro de page pour au moins {TARGET:.0%} des "
        "passages vérifiés",
        "",
        "| Bibliothèque | Passages | Bonne page | Autre page | Introuvables | Taux |",
        "|---|---|---|---|---|---|",
    ]
    for name in EXTRACTORS:
        t = result.total(name)
        lines.append(
            f"| {name} | {t.checked} | {t.at_page} | {t.other_page} | {t.not_found} "
            f"| {_percent(t.rate)} |"
        )
    rates = [s.rate for p in read for s in [p.scores["pymupdf"]] if s.rate is not None]
    lines += [
        "",
        f"PyMuPDF, médiane par PDF : {_percent(statistics.median(rates) if rates else None)}; "
        f"plus faible : {_percent(min(rates) if rates else None)}.",
        "",
        "## Par PDF",
        "",
        "| PDF (SHA-256, début) | Pages | PyMuPDF | pypdf | pdfplumber | Remarque |",
        "|---|---|---|---|---|---|",
    ]
    for pdf in result.pdfs:
        cells = [_percent(pdf.scores[n].rate) if n in pdf.scores else "—" for n in EXTRACTORS]
        lines.append(f"| {pdf.sha256[:12]} | {pdf.pages} | {' | '.join(cells)} | {pdf.error} |")
    lines += [
        "",
        "## Lecture",
        "",
        "Un passage introuvable vient le plus souvent d'un ordre de lecture différent (colonnes, "
        "encadrés, notes) : il chevauche alors deux blocs que l'autre bibliothèque lit "
        "séparément. Un passage trouvé à une autre page signale une erreur de page. Ce test "
        "mesure l'accord entre bibliothèques, pas encore les citations du modèle : il sera "
        "repris avec les citations de l'IA au tri du texte intégral (tranche 2.2).",
        "",
    ]
    return "\n".join(lines)


def pdf_files(paths: Sequence[Path]) -> list[Path]:
    """The PDFs named, folders expanded (``*.pdf``, sorted)."""
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found += sorted(p for p in path.iterdir() if p.suffix.lower() == ".pdf")
        elif path.is_file():
            found.append(path)
        else:
            raise FileNotFoundError(_("File not found: {path}").format(path=path))
    return found
