"""References: identifiers and enrichment that never replaces a field (EF-COL-02)."""

from datetime import UTC, datetime

import pytest

from revue_portee.domain.references import (
    Enrichment,
    Reference,
    clean_doi,
    clean_pmid,
    merged,
    missing_fields,
)

NOW = datetime(2026, 10, 8, tzinfo=UTC)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("10.1037/fam0001410", "10.1037/FAM0001410"),
        ("https://doi.org/10.7202/1069916ar", "10.7202/1069916AR"),
        ("doi:10.1000/xyz.1.", "10.1000/XYZ.1"),
        ("See (10.1000/abc);", "10.1000/ABC"),
        ("", ""),
        ("no doi here", ""),
    ],
)
def test_clean_doi(value: str, expected: str) -> None:
    assert clean_doi(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("33276576", "33276576"), ("PMID: 42", "42"), ("0123", ""), ("abc", "")],
)
def test_clean_pmid(value: str, expected: str) -> None:
    assert clean_pmid(value) == expected


def test_merged_fills_only_missing_fields_oldest_first() -> None:
    reference = Reference(id="R1", title="Kept title", year=2018, created_at=NOW)
    assert missing_fields(reference) == (
        "abstract",
        "authors",
        "container_title",
        "volume",
        "issue",
        "pages",
    )
    first = Enrichment(
        id="E1",
        reference_id="R1",
        fields={"title": "Other title", "authors": ["Doe, Jane"], "volume": "6"},
        raw_dir="brut/sources/X",
        created_at=NOW,
    )
    second = Enrichment(
        id="E2",
        reference_id="R1",
        fields={"volume": "7", "pages": "1-9", "unknown": "x"},
        raw_dir="brut/sources/Y",
        created_at=NOW,
    )
    result = merged(reference, [first, second])
    assert result.title == "Kept title"
    assert result.authors == ("Doe, Jane",)
    assert (result.volume, result.pages, result.year) == ("6", "1-9", 2018)
    assert merged(reference, []) is reference
