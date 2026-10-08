"""RIS import on excerpts of six real exports, and malformed files (EF-COL-03).

The excerpts (``tests/fixtures/ris/``) keep the exact line format of the exports
(line ends, spacing, wrapped values); abstracts are cut short because the repository
is public. Full exports (4,189 records) were also read without loss during the tranche.
"""

import re
from pathlib import Path

import pytest

from revue_portee.domain.references import IssueKind
from revue_portee.sources.ris import detect_database, parse_ris

FIXTURES = Path(__file__).parents[2] / "fixtures" / "ris"

EXPORTS = {
    "psycinfo-ebscohost.ris": "APA PsycInfo (EBSCOhost)",
    "cinahl-ebscohost.ris": "CINAHL Complete (EBSCOhost)",
    "eric-ebscohost.ris": "ERIC (EBSCOhost)",
    "socindex-ebscohost.ris": "SocINDEX (EBSCOhost)",
    "pubmed.ris": "PubMed",
    "erudit.ris": "Érudit",
}


def read(name: str) -> str:
    return (FIXTURES / name).read_bytes().decode("utf-8")


@pytest.mark.parametrize(("name", "database"), EXPORTS.items())
def test_every_record_of_real_exports_is_recognized(name: str, database: str) -> None:
    text = read(name)
    assert ("\r\n" in text) == name.startswith(("cinahl", "eric", "socindex"))  # bytes kept
    expected = len(re.findall(r"^TY  -", text, flags=re.MULTILINE))  # independent count
    assert expected == len(re.findall(r"^ER  -", text, flags=re.MULTILINE))
    result = parse_ris(text)
    assert result.total == expected
    assert len(result.records) == expected
    assert result.issues == ()
    assert result.database_counts == {database: expected}
    assert all(r.title or r.doi for r in result.records)


def test_ebscohost_record() -> None:
    first = parse_ris(read("psycinfo-ebscohost.ris")).records[0]
    assert first.title.startswith("Neighborhood child-friendliness and parenting strategies")
    assert first.authors[:2] == ("Wang, Yilin", "Screene, Canice")
    assert first.doi == "10.1037/FAM0001410"
    assert (first.year, first.container_title) == (2026, "Journal of Family Psychology")
    assert (first.volume, first.issue, first.pages) == ("40", "3", "377-387")
    assert first.accession == "2026-69056-001"
    assert first.pmid == ""


def test_pubmed_record_and_missing_title() -> None:
    records = parse_ris(read("pubmed.ris")).records
    first = records[0]
    assert first.pmid == "33276576"
    assert first.container_title.startswith("International journal of environmental research")
    assert first.title.startswith("Indoor Exposure to Selected Air Pollutants")
    assert "  " not in first.title  # double spaces of the export collapsed
    untitled = [r for r in records if not r.title]
    assert untitled  # real records without title: left to the Crossref enrichment
    assert all(r.doi and not r.container_title for r in untitled)


def test_erudit_wrapped_values_two_abstracts_and_doi_url() -> None:
    records = parse_ris(read("erudit.ris")).records
    first = records[0]
    assert first.title == "À chacun son cirque !"
    assert first.doi == "10.7202/1069916AR"  # from https://doi.org/…
    assert first.abstract.count("\n\n") == 1  # French and English abstracts kept
    assert (first.year, first.language, first.doc_type) == (2020, "FR", "JOUR")
    wrapped = [r for r in records if "psychique" in r.title]
    assert wrapped
    assert wrapped[0].title.endswith("pédopsychiatrie.")
    assert "  " not in wrapped[0].title


def test_constructed_malformed_file() -> None:
    text = "\r\n".join(
        [
            "﻿Provider: test export",  # before any record
            "TY  - JOUR",
            "TI  - A complete record",
            "AU  - Doe, Jane",
            "PY  - 2021///",
            "SP  - 5",
            "EP  - 5",
            "M3  - doi:10.1000/XYZ.1.",
            "ER  - ",
            "TY  - JOUR",  # empty record
            "ER  -",
            "ER  -",  # ER outside a record
            "TY - JOUR",  # one space only before the dash
            "T1 - A record the next TY interrupts",
            "TY  - JOUR",
            "T2  - Journal only, no title",
            "  wrapped journal line",
            "",
        ]
    )
    result = parse_ris(text)
    assert result.total == 4
    assert [r.title for r in result.records] == [
        "A complete record",
        "A record the next TY interrupts",
    ]
    complete = result.records[0]
    assert (complete.year, complete.pages, complete.doi) == (2021, "5", "10.1000/XYZ.1")
    assert [(i.kind, i.line, i.record) for i in result.issues] == [
        (IssueKind.BAD_LINE, 1, None),
        (IssueKind.EMPTY, 10, 2),
        (IssueKind.NO_TYPE, 12, None),
        (IssueKind.UNTERMINATED, 15, 3),
        (IssueKind.EMPTY, 15, 4),
        (IssueKind.UNTERMINATED, 17, 4),
    ]
    assert result.issues[0].text == "Provider: test export"


def test_database_names() -> None:
    def record(**tags: str) -> object:
        return parse_ris(
            "TY  - JOUR\nTI  - T\n" + "".join(f"{k}  - {v}\n" for k, v in tags.items())
        ).records[0]

    assert detect_database(record(DB="ERIC", DP="EBSCOhost")) == "ERIC (EBSCOhost)"  # type: ignore[arg-type]
    assert detect_database(record(DB="Érudit", DP="Érudit: www.erudit.org")) == "Érudit"  # type: ignore[arg-type]
    assert detect_database(record(DB="PubMed")) == "PubMed"  # type: ignore[arg-type]
    assert detect_database(record()) == ""  # type: ignore[arg-type]
