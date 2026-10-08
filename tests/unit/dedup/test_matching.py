"""Normalization and candidate pairs of deduplication (EF-COL-06), on small cases."""

from datetime import UTC, datetime
from typing import Any

import pytest

from revue_portee.dedup.matching import find_candidates, title_similarity
from revue_portee.dedup.normalize import (
    container_key,
    first_page,
    is_conference,
    is_notice,
    is_preprint,
    is_thesis,
    is_translated_title,
    normalize_text,
    surname,
    title_tokens,
)
from revue_portee.domain.dedup import DedupSettings, PairKind, Proposal
from revue_portee.domain.references import Reference

NOW = datetime(2026, 10, 8, tzinfo=UTC)
SETTINGS = DedupSettings()
ARTICLE: dict[str, Any] = {
    "title": "Housing instability and mental health of young adults: A cohort study.",
    "authors": ("Tremblay, Marie", "Roy, Paul"),
    "year": 2021,
    "container_title": "Journal of Housing Studies",
    "volume": "12",
    "issue": "3",
    "pages": "101-115",
}


def ref(ref_id: str, **fields: Any) -> Reference:  # noqa: ANN401
    return Reference(id=ref_id, created_at=NOW, **fields)


def pairs(*references: Reference) -> list[tuple[str, str, PairKind, str, Proposal]]:
    return [
        (c.reference_a, c.reference_b, c.kind, c.rule, c.proposal)
        for c in find_candidates(references, SETTINGS)
    ]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("<i>Écoute</i> des PROCHES-aidants : répit!", "ecoute des proches aidants repit"),
        ("L&rsquo;itinérance", "l itinerance"),
        ("", ""),
    ],
)
def test_normalize_text(value: str, expected: str) -> None:
    assert normalize_text(value) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Tremblay, Marie", "tremblay"),
        ("Vinet-St-Pierre, Marilou", "vinet st pierre"),
        ("Akin Ojagbemi", "ojagbemi"),
        ("Chow KKW", "chow"),
        ("O'Brien J", "o brien"),
        ("Smith-Jones AB", "smith jones"),
        ("Le Blanc KK", "le blanc"),
        ("Garcia-Lopez M", "garcia lopez"),
        ("Garcia-Lopez, M.", "garcia lopez"),
        ("Maria Garcia-Lopez", "garcia lopez"),
        ("Smith J", "smith"),
        ("Jean-Luc Picard", "picard"),
        ("Plato", "plato"),
        ("", ""),
        ("  ", ""),
        ("...", ""),
    ],
)
def test_surname(name: str, expected: str) -> None:
    assert surname(name) == expected


def test_other_normalizations() -> None:
    assert title_tokens("A study: part II") == ("a", "study", "part", "ii")
    assert first_page("278-85") == "278"
    assert first_page("e1004365") == "e1004365"
    assert first_page(" ") == ""
    assert container_key("The Lancet (London, England)") == "lancet"
    assert container_key("Journal of family psychology : JFP : journal of the APA") == (
        "journal of family psychology"
    )
    assert is_translated_title("[Housing experiences of new users].")
    assert not is_translated_title("Housing [and] health")
    assert is_notice("Correction: High-risk victims")
    assert is_notice("Supplemental Material for Thwarted belongingness")
    assert not is_notice("How families cope with housing")


def test_kinds_of_records() -> None:
    assert is_preprint(ref("1", doi="10.21203/RS.3.RS-1/V1"))
    assert is_preprint(ref("1", doc_type="preprint"))
    assert is_preprint(ref("1", container_title="medRxiv"))
    assert is_preprint(ref("1", doi="10.1101/2020.03.15.20036293"))  # medRxiv
    assert is_preprint(ref("1", doi="10.1101/123456"))  # bioRxiv, older form
    assert not is_preprint(ref("1", doi="10.1101/GR.275193.120"))  # Genome Research
    assert not is_preprint(ref("1", doi="10.1186/X", container_title="BMC Public Health"))
    assert is_thesis(ref("1", doc_type="THES"))
    assert is_thesis(ref("1", container_title="Dissertation Abstracts International"))
    assert is_thesis(ref("1", container_title="Thèse de doctorat"))
    assert not is_thesis(ref("1", container_title="These Times"))
    assert is_conference(ref("1", doc_type="CONF"))
    assert is_conference(ref("1", container_title="Conference Papers - ASA"))
    assert not is_conference(ref("1", container_title="Child Welfare"))


def test_title_similarity() -> None:
    a = title_tokens("In their own words: Exploring family pathways to housing instability")
    assert title_similarity(title_tokens("In Their Own Words."), a) == 0.95
    assert title_similarity(a, a) == 1.0
    assert title_similarity(title_tokens("Reflections"), title_tokens("Reflections from X")) < 0.9


def test_same_doi_is_an_automatic_duplicate() -> None:
    a = ref("A", doi="10.1/X", **ARTICLE)
    b = ref("B", doi="10.1/X", **ARTICLE | {"title": ARTICLE["title"].upper()})
    assert pairs(b, a) == [("A", "B", PairKind.IDENTIFIER, "doi", Proposal.DUPLICATE)]


def test_same_identifier_with_other_identifiers_differing_goes_to_a_person() -> None:
    a = ref("A", pmid="123", doi="10.1/X", **ARTICLE)
    b = ref("B", pmid="123", doi="10.1/Y", **ARTICLE)
    (found,) = find_candidates([a, b], SETTINGS)
    assert (found.rule, found.proposal) == ("pmid_other_identifiers_differ", Proposal.REVIEW)
    assert found.details["not_automatic"] == "different_doi"


def test_same_identifier_with_different_titles_goes_to_a_person() -> None:
    a = ref("A", pmid="123", **ARTICLE)
    b = ref("B", pmid="123", **ARTICLE | {"title": "Something else entirely"})
    c = ref("C", openalex_id="W1", **ARTICLE)
    d = ref("D", openalex_id="W1", **ARTICLE)
    assert pairs(a, b, c, d) == [
        ("A", "B", PairKind.IDENTIFIER, "pmid_title_differs", Proposal.REVIEW),
        ("A", "C", PairKind.FUZZY, "similarity", Proposal.DUPLICATE),
        ("A", "D", PairKind.FUZZY, "similarity", Proposal.DUPLICATE),
        ("C", "D", PairKind.IDENTIFIER, "openalex", Proposal.DUPLICATE),
    ]


@pytest.mark.parametrize(
    "change",
    [
        {"title": "HOUSING INSTABILITY AND MENTAL HEALTH OF YOUNG ADULTS: A COHORT STUDY"},
        {"title": "Housing instability and mental health of young adults."},
        {"title": "<i>Housing</i> instability and mental health of young adults - a cohort study"},
        {"authors": ("Tremblay M", "Roy P")},
        {"year": 2020, "volume": "", "issue": "", "pages": ""},
        {"container_title": "journal of housing studies (online)"},
    ],
)
def test_variants_of_one_record_are_grouped(change: dict[str, Any]) -> None:
    a = ref("A", doi="10.1/X", **ARTICLE)
    b = ref("B", **ARTICLE | change)
    assert pairs(a, b) == [("A", "B", PairKind.FUZZY, "similarity", Proposal.DUPLICATE)]


def test_accents_and_translated_titles() -> None:
    fr = {
        "title": "L'itinérance des aînés : une étude qualitative",
        "authors": ("Bélanger, Éric",),
        "year": 2019,
        "container_title": "Santé mentale au Québec",
        "volume": "44",
        "pages": "33-50",
    }
    a = ref("A", **fr)
    b = ref("B", **fr | {"title": "L'itinerance des aines : une etude qualitative"})
    c = ref("C", **fr | {"title": "[Homelessness of older adults: a qualitative study]."})
    found = pairs(a, b, c)
    assert ("A", "B", PairKind.FUZZY, "similarity", Proposal.DUPLICATE) in found
    assert ("A", "C", PairKind.FUZZY, "translated_title", Proposal.REVIEW) in found
    # a translated title with a different page: not even shown
    d = ref("D", **fr | {"title": "[Something]", "pages": "51-60"})
    assert [p for p in pairs(a, d)] == []


def test_versions_of_one_work_are_left_to_a_person() -> None:
    article = ref("A", doi="10.1186/S1", **ARTICLE)
    preprint = ref(
        "B",
        **ARTICLE | {"container_title": "Research Square", "volume": "", "pages": ""},
        doi="10.21203/RS.3.RS-9/V1",
    )
    thesis = ref(
        "C",
        **ARTICLE
        | {"year": 2019, "container_title": "Dissertation Abstracts International", "pages": ""},
        doc_type="THES",
    )
    elsewhere = ref("D", doi="10.9/OTHER", **ARTICLE | {"container_title": "Annals of Family"})
    found = pairs(article, preprint, thesis, elsewhere)
    assert ("A", "B", PairKind.VERSION, "preprint", Proposal.REVIEW) in found
    assert ("A", "C", PairKind.VERSION, "thesis", Proposal.REVIEW) in found
    assert ("A", "D", PairKind.VERSION, "co_publication", Proposal.REVIEW) in found
    assert all(p[4] is Proposal.REVIEW for p in found)


def test_records_about_another_record_are_never_paired() -> None:
    a = ref("A", **ARTICLE)
    b = ref("B", **ARTICLE | {"title": "Correction: " + ARTICLE["title"]})
    assert pairs(a, b) == []
    # the article's own title has a word of a reply: the correction still stays apart
    title = "Nurses' response to patient aggression in emergency departments"
    c = ref("C", **ARTICLE | {"title": title})
    d = ref("D", **ARTICLE | {"title": "Correction: " + title})
    e = ref("E", **ARTICLE | {"title": title.upper()})
    assert pairs(c, d, e) == [("C", "E", PairKind.FUZZY, "similarity", Proposal.DUPLICATE)]


def test_the_pronoun_i_is_not_a_number() -> None:
    a = ref("A", **ARTICLE | {"title": "What I learned from caring for older adults"})
    b = ref("B", **ARTICLE | {"title": "What learned from caring for older adults"})
    (found,) = find_candidates([a, b], SETTINGS)
    assert "different_numbers" not in str(found.details.get("not_automatic", ""))
    c = ref("C", **ARTICLE | {"title": "Guidelines for housing, part II"})
    d = ref("D", **ARTICLE | {"title": "Guidelines for housing, part III"})
    assert "different_numbers" in str(find_candidates([c, d], SETTINGS)[0].details)


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"title": ARTICLE["title"] + " Part 2"}, "different_numbers"),
        ({"authors": ("Gagnon, Luc",)}, "first_author"),
        ({"authors": ()}, "first_author"),
        ({"year": 2015}, "year"),
        ({"pages": "201-215"}, "first_page"),
    ],
)
def test_uncertain_pairs_go_to_a_person(change: dict[str, Any], reason: str) -> None:
    a = ref("A", **ARTICLE)
    b = ref("B", **ARTICLE | change)
    found = find_candidates([a, b], SETTINGS)
    assert [c.proposal for c in found] == [Proposal.REVIEW]
    assert reason in str(found[0].details.get("not_automatic", ""))


def test_different_dois_in_the_same_journal_go_to_a_person() -> None:
    a = ref("A", doi="10.1002/EHF2.12005", **ARTICLE)
    b = ref("B", doi="10.1002/2055-5822.12005", **ARTICLE)
    found = find_candidates([a, b], SETTINGS)
    assert [(c.kind, c.proposal) for c in found] == [(PairKind.FUZZY, Proposal.REVIEW)]
    assert found[0].details["not_automatic"] == "different_doi"


def test_distinct_works_with_the_same_title_are_left_apart() -> None:
    a = ref("A", **ARTICLE)
    b = ref(
        "B",
        **ARTICLE
        | {"authors": ("Gagnon, Luc",), "year": 2009, "container_title": "Other", "volume": "3"},
    )
    assert pairs(a, b) == []


def test_thresholds_decide_between_automatic_review_and_nothing() -> None:
    a = ref("A", **ARTICLE)
    b = ref("B", **ARTICLE | {"title": "Housing insecurity and wellbeing of young adults"})
    score = find_candidates([a, b], DedupSettings(review_from=0, auto_from=0))[0].score
    strict = DedupSettings(review_from=score, auto_from=1)
    assert [c.proposal for c in find_candidates([a, b], strict)] == [Proposal.REVIEW]
    lenient = DedupSettings(review_from=0, auto_from=score)
    assert find_candidates([a, b], lenient)[0].details["not_automatic"] == "title"
    assert find_candidates([a, b], DedupSettings(review_from=1, auto_from=1)) == []


def test_results_do_not_depend_on_the_order_of_references() -> None:
    refs = [
        ref("A", doi="10.1/X", **ARTICLE),
        ref("B", **ARTICLE),
        ref("C", **ARTICLE | {"year": 2015}),
        ref("D", **ARTICLE | {"title": "Other subject", "authors": ("Gagnon, L",)}),
    ]
    assert find_candidates(refs, SETTINGS) == find_candidates(list(reversed(refs)), SETTINGS)


def test_settings_are_validated() -> None:
    with pytest.raises(ValueError, match="review_from"):
        DedupSettings(review_from=0.9, auto_from=0.8)
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        DedupSettings(review_from=-0.1)
