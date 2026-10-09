"""Test of the rules that propose reports of a same study: set labelled by the
ClinicalTrials.gov number PubMed gives, read and written as CSV, measured by hand."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from revue_portee.cli.main import app
from revue_portee.collect.study_benchmark import (
    StudyRecord,
    build_set,
    read_set,
    report_markdown,
    run_test,
    write_set,
)
from revue_portee.sources.pubmed import databank_accessions
from revue_portee.sources.records import FetchedPage
from support import START

XML = """<?xml version="1.0"?>
<PubmedArticleSet>
 <PubmedArticle><MedlineCitation><PMID>1</PMID><Article>
  <DataBankList><DataBank><DataBankName>ClinicalTrials.gov</DataBankName>
   <AccessionNumberList><AccessionNumber>nct01234567</AccessionNumber></AccessionNumberList>
  </DataBank><DataBank><DataBankName>ISRCTN</DataBankName>
   <AccessionNumberList><AccessionNumber>ISRCTN12345678</AccessionNumber></AccessionNumberList>
  </DataBank></DataBankList></Article></MedlineCitation></PubmedArticle>
 <PubmedArticle><MedlineCitation><PMID>2</PMID><Article/></MedlineCitation></PubmedArticle>
</PubmedArticleSet>"""

ABSTRACT = "Dialectical behaviour therapy for women with borderline personality disorder."
RECORDS = [
    # one trial in three reports: a and b share the registration, c shares authors and words
    StudyRecord("a", "NCT1", "Main results", ("Verheul R", "Bosch L"), 2003, "BJP",
                ABSTRACT + " NCT01234567"),
    StudyRecord("b", "NCT1", "Follow-up", ("Smith J",), 2005, "BRAT", "NCT01234567"),
    StudyRecord("c", "NCT1", "Costs", ("Verheul R", "van den Bosch L"), 2006, "J", ABSTRACT),
    # another trial, unrelated
    StudyRecord("d", "NCT2", "Exercise in older adults", ("Lee K",), 2010, "J", "Walking."),
]  # fmt: skip


def test_registry_numbers_given_by_pubmed() -> None:
    assert databank_accessions(XML) == {"1": frozenset({"NCT01234567"}), "2": frozenset()}
    assert databank_accessions(XML, "ISRCTN") == {
        "1": frozenset({"ISRCTN12345678"}),
        "2": frozenset(),
    }


def test_measure_counted_by_hand(tmp_path: Path) -> None:
    path = tmp_path / "jeu.csv"
    path.write_text(write_set(RECORDS), encoding="utf-8")
    records = read_set(path)
    assert records == RECORDS
    test = run_test("jeu", records, now=START)
    # true pairs: (a, b), (a, c), (b, c); proposed: (a, b) by registration, (a, c) by
    # authors; (b, c) missed
    assert (test.records, test.studies, test.studies_with_several) == (4, 2, 1)
    e = test.evaluation
    assert (e.true_pairs, e.proposed, e.found) == (3, 2, 2)
    assert e.missed == [("b", "c")]
    assert test.by_rule == {"authors": (1, 1), "registration": (1, 1)}
    report = report_markdown(test, role="développement")
    assert "| **Rappel** | **66.7%** |" in report
    assert "développement" in report
    assert "Dialectical" not in report  # numbers only


def test_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "jeu.csv"
    path.write_text(write_set(RECORDS), encoding="utf-8")
    out = tmp_path / "rapports"
    result = CliRunner().invoke(app, ["banc-etudes", str(path), "--sortie", str(out)])
    assert result.exit_code == 0, result.output
    assert "rappel 0.667" in result.output
    assert (out / "etudes-jeu.md").is_file()
    assert CliRunner().invoke(app, ["banc-etudes", str(tmp_path / "x.csv")]).exit_code == 1
    monkeypatch.delenv("CONTACT_EMAIL", raising=False)
    missing = CliRunner().invoke(
        app, ["jeu-etudes", "psychotherapy[mh]", "--sortie", str(tmp_path / "s.csv")]
    )
    assert missing.exit_code == 1
    assert "CONTACT_EMAIL" in missing.output


class _Pages:
    """PubMed answering two pages from recorded XML (no network)."""

    def __init__(self, pages: list[str]) -> None:
        self.pages = pages

    def fetch(self, query: str, cursor: str | None) -> FetchedPage:
        number = 0 if cursor is None else int(cursor)
        following = str(number + 1) if number + 1 < len(self.pages) else None
        raw = self.pages[number]
        return FetchedPage(records=(), announced=2, next_cursor=following, raw=raw)


def test_set_built_from_pubmed_pages() -> None:
    page = XML.replace("<Article>", "<Article><ArticleTitle>Main results</ArticleTitle>", 1)
    seen: list[int] = []
    records = build_set(_Pages([page, page]), "q", limit=10, progress=seen.append)  # type: ignore[arg-type]
    assert [(r.pmid, r.study, r.title) for r in records] == [
        ("1", "NCT01234567", "Main results")
    ] * 2
    assert seen == [2, 4]
    assert len(build_set(_Pages([page, page]), "q", limit=1)) == 1  # type: ignore[arg-type]
