"""Comparative test of the extraction by page: passages drawn with a seed, each library
scored on the passages read by the others, report without any text of the PDFs."""

import random
from pathlib import Path

import pytest

from revue_portee.domain.fulltext import QuoteCheck
from revue_portee.fulltext.page_benchmark import (
    EXTRACTORS,
    ExtractorScore,
    draw_quotes,
    pdf_files,
    report_markdown,
    run_benchmark,
)
from support import START, make_pdf


def test_passages_of_eight_words_drawn_with_a_seed() -> None:
    texts = [" ".join(f"w{i}" for i in range(10)), "too short to quote", ""]
    first = draw_quotes(texts, random.Random(1))  # noqa: S311 - reproducible draw
    assert first == draw_quotes(texts, random.Random(1))  # noqa: S311
    assert len(first) == 3  # three starts possible on page 1, none on pages 2 and 3
    assert {page for page, _quote in first} == {1}
    assert all(len(quote.split()) == 8 for _page, quote in first)


def test_score_counts_by_hand() -> None:
    score = ExtractorScore()
    for check in (QuoteCheck.AT_PAGE, QuoteCheck.AT_PAGE, QuoteCheck.OTHER_PAGE,
                  QuoteCheck.NOT_FOUND):  # fmt: skip
        score.add(check)
    assert (score.checked, score.at_page, score.other_page, score.not_found) == (4, 2, 1, 1)
    assert score.rate == 0.5
    assert score.found_rate == 2 / 3
    assert ExtractorScore().rate is None
    assert ExtractorScore().found_rate is None


def test_benchmark_on_generated_pdfs(tmp_path: Path) -> None:
    page = "\n".join(" ".join(f"alpha{i}{j}" for j in range(8)) for i in range(6))
    good = tmp_path / "good.pdf"
    good.write_bytes(make_pdf([page, page.replace("alpha", "beta")]))
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4 broken")
    result = run_benchmark(pdf_files([tmp_path]), seed=7, now=START)
    read = [p for p in result.pdfs if not p.error]
    assert len(result.pdfs) == 2
    assert len(read) == 1
    assert read[0].pages == 2
    for name in EXTRACTORS:
        total = result.total(name)
        assert total.checked == 12  # 3 passages a page, 2 pages, from each of 2 others
        assert total.rate == 1.0
    report = report_markdown(result)
    assert "| pymupdf | 12 | 12 | 0 | 0 | 100.0% | 100.0% |" in report
    assert "graine 7" in report
    assert "alpha" not in report  # no text of the PDFs


def test_files_must_exist(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        pdf_files([tmp_path / "absent.pdf"])
