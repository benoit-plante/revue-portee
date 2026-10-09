"""Rules that propose reports of a same study (EF-SEL-17): registration numbers, shared
authors and words, close titles; studies and pair recall counted by hand."""

from datetime import UTC, datetime

from revue_portee.dedup.reports import (
    LinkRule,
    ReportLinkSettings,
    candidate_pairs,
    evaluate_pairs,
    features,
    group_reports,
    registrations,
)
from revue_portee.domain.references import Reference

T0 = datetime(2026, 10, 9, tzinfo=UTC)


def _ref(ref: str, title: str, authors: tuple[str, ...], abstract: str = "") -> Reference:
    return Reference(id=ref, title=title, authors=authors, abstract=abstract, created_at=T0)


def test_registration_numbers() -> None:
    text = (
        "Registered at ClinicalTrials.gov (NCT 01234567) and ISRCTN12345678; ACTRN12615000123456;"
        " ChiCTR-IOR-17012345; DRKS00012345; NTR4567; UMIN000012345; IRCT20150101012345N1; "
        "CTRI/2018/02/012345; PACTR201801002345678; EudraCT number: 2014-001234-56; nct00000000"
    )
    assert registrations(text) == {
        "NCT01234567", "ISRCTN12345678", "ACTRN12615000123456", "ChiCTRIOR-17012345",
        "DRKS00012345", "NTR4567", "UMIN000012345", "IRCT20150101012345N1",
        "CTRI2018/02/012345", "PACTR201801002345678", "EudraCT2014-001234-56", "NCT00000000",
    }  # fmt: skip
    assert registrations("Published 2014-001234-56 without the registry name") == frozenset()


ABSTRACT = (
    "Dialectical behaviour therapy for women with borderline personality disorder in "
    "Amsterdam: twelve months of weekly individual sessions and skills groups."
)


def test_candidates_counted_by_hand() -> None:
    dbt = "Dialectical behaviour therapy in a Dutch sample"
    schema = "Schema therapy for borderline personality disorder: a randomised trial"
    schema_us = "Schema therapy for borderline personality disorder - a randomized trial"
    vdb = ("van den Bosch, L", "Verheul R")
    reports = [
        # a and b: the same registration number (in the text of b only)
        features(_ref("a", dbt, ("Linehan, M",), "NCT01234567")),
        features(_ref("b", "Long-term follow-up of a trial", ("Smith J",)), text="NCT01234567"),
        # c and d: two shared authors and many shared words
        features(_ref("c", "Main results in Amsterdam", vdb, ABSTRACT)),
        features(
            _ref("d", "Costs in Amsterdam", ("Louise van den Bosch", "Roel Verheul"), ABSTRACT)
        ),
        # e and f: close titles, no shared author
        features(_ref("e", schema, ("Giesen-Bloo J",))),
        features(_ref("f", schema_us, ("Arntz A",))),
        # g and h: different registration numbers, even with the same title: never paired
        features(_ref("g", "Mentalization-based treatment", ("Bateman A",), "ISRCTN11111111")),
        features(_ref("h", "Mentalization-based treatment", ("Bateman A",), "ISRCTN22222222")),
    ]
    found = {(c.reference_a_id, c.reference_b_id): c for c in candidate_pairs(reports)}
    assert set(found) == {("a", "b"), ("c", "d"), ("e", "f")}
    assert found["a", "b"].rule == LinkRule.REGISTRATION
    assert found["a", "b"].shared_registrations == ("NCT01234567",)
    assert found["c", "d"].rule == LinkRule.AUTHORS
    assert found["c", "d"].shared_authors == ("bosch", "verheul")
    assert found["e", "f"].rule == LinkRule.TITLE
    stricter = ReportLinkSettings(
        min_shared_authors=3, single_author_overlap=1.0, min_title_similarity=0.99
    )
    assert {(c.reference_a_id, c.reference_b_id) for c in candidate_pairs(reports, stricter)} == {
        ("a", "b")
    }
    untitled = [features(_ref("x", "", ("A, B",))), features(_ref("y", "", ("C, D",)))]
    assert candidate_pairs(untitled) == []


def test_studies_from_links() -> None:
    groups = group_reports(
        ["e", "a", "b", "c", "d"], [("b", "a"), ("c", "d"), ("d", "b"), ("z", "a")]
    )
    assert groups == [["a", "b", "c", "d"], ["e"]]
    assert group_reports(["a"], [("a", "a")]) == [["a"]]


def test_pair_recall_and_precision_by_hand() -> None:
    # studies: S1 = a, b, c (3 pairs); S2 = d, e (1 pair); S3 = f
    study_of = {"a": "S1", "b": "S1", "c": "S1", "d": "S2", "e": "S2", "f": "S3"}
    evaluation = evaluate_pairs([("b", "a"), ("a", "c"), ("d", "e"), ("e", "f")], study_of)
    assert (evaluation.true_pairs, evaluation.proposed, evaluation.found) == (4, 4, 3)
    assert evaluation.recall == 0.75
    assert evaluation.precision == 0.75
    assert evaluation.missed == [("b", "c")]
    empty = evaluate_pairs([], {"a": "S1"})
    assert (empty.recall, empty.precision) == (None, None)
