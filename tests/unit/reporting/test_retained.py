"""RIS and CSV of the references kept for the full text: read back by the project's
own RIS reader, field by field."""

import csv
import io
from datetime import UTC, datetime

import pytest

from revue_portee.domain.references import Reference
from revue_portee.domain.screening import (
    Decision,
    DecisionContext,
    DecisionValue,
    ReviewerKind,
    Stage,
)
from revue_portee.reporting.retained import RetainedReference, ris_type, write_csv, write_ris
from revue_portee.sources.ris import parse_ris

MOMENT = datetime(2026, 10, 8, 12, tzinfo=UTC)


def reference(**fields: object) -> Reference:
    return Reference.model_validate({"id": "R1", "created_at": MOMENT} | fields)


def kept(ref: Reference, value: DecisionValue = DecisionValue.INCLUDE) -> RetainedReference:
    decision = Decision(
        id="D1",
        reference_id=ref.id,
        stage=Stage.TITLE_ABSTRACT,
        round_id="ROUND",
        reviewer_id="P",
        value=value,
        criteria_version_id="V2",
        context=DecisionContext.REASSESSMENT,
        tool_version="test",
        created_at=MOMENT,
        reviewer_kind=ReviewerKind.HUMAN,
    )
    return RetainedReference(reference=ref, decision=decision, criteria_version=2)


FULL = reference(
    title="Housing instability and the mental health of young adults: a cohort study",
    abstract="First paragraph.\n\nSecond   paragraph,\nwrapped.",
    authors=("Tremblay, M", "Roy, P"),
    year=2021,
    container_title="Journal of Housing Studies",
    volume="12",
    issue="3",
    pages="101-115",
    doi="10.5555/DEMO.0001",
    pmid="12345678",
    openalex_id="W123",
    language="en",
    doc_type="article",
    url="https://example.org/article",
)


@pytest.mark.parametrize(
    ("doc_type", "container", "expected"),
    [
        ("JOUR", "", "JOUR"),
        ("CHAP", "", "CHAP"),
        ("article", "", "JOUR"),
        ("Book-Chapter", "", "CHAP"),
        ("dissertation", "", "THES"),
        ("preprint", "", "UNPB"),
        ("", "A journal", "JOUR"),
        ("other", "", "GEN"),
    ],
)
def test_ris_type(doc_type: str, container: str, expected: str) -> None:
    assert ris_type(reference(doc_type=doc_type, container_title=container)) == expected


def test_ris_is_read_back_by_the_project_reader() -> None:
    text = write_ris(
        [kept(FULL), kept(reference(id="R2", title="Second"), DecisionValue.UNCERTAIN)]
    )
    result = parse_ris(text)
    assert result.issues == ()
    first, second = result.records
    assert first.title == FULL.title
    assert first.authors == FULL.authors
    assert (first.year, first.container_title, first.volume, first.issue) == (
        2021,
        "Journal of Housing Studies",
        "12",
        "3",
    )
    assert first.pages == "101-115"
    assert first.doi == "10.5555/DEMO.0001"
    assert (first.language, first.url, first.doc_type) == ("en", FULL.url, "JOUR")
    # one line per value: the paragraphs of the abstract are joined
    assert first.abstract == "First paragraph. Second paragraph, wrapped."
    assert first.first("KW") == "revue-portee: include"
    assert first.first("N1") == (
        "revue-portee: R1; decision: include; criteria version: 2; PMID: 12345678; OpenAlex: W123"
    )
    assert first.first("ID") == "R1"
    # empty fields are left out
    assert second.title == "Second"
    assert second.first("KW") == "revue-portee: uncertain"
    assert set(second.tags) == {"TY", "TI", "KW", "N1", "ID"}
    assert second.doc_type == "GEN"


def test_single_page_and_empty_list() -> None:
    record = parse_ris(write_ris([kept(reference(title="T", pages="e1234"))])).records[0]
    assert (record.first("SP"), record.first("EP")) == ("e1234", "")
    assert write_ris([]) == ""


def test_csv_one_row_per_reference() -> None:
    rows = list(csv.DictReader(io.StringIO(write_csv([kept(FULL)]))))
    assert len(rows) == 1
    row = rows[0]
    assert (row["reference_id"], row["decision"], row["decision_context"]) == (
        "R1",
        "include",
        "reassessment",
    )
    assert (row["criteria_version"], row["authors"], row["year"]) == (
        "2",
        "Tremblay, M; Roy, P",
        "2021",
    )
    assert row["abstract"] == FULL.abstract  # kept as is in the CSV
    assert list(csv.reader(io.StringIO(write_csv([]))))[1:] == []
