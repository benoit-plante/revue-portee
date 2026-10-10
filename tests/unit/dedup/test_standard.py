"""Matching the included studies of a published review to references (tranche 3.8)."""

from revue_portee.dedup.standard import match_studies
from revue_portee.domain.references import Reference
from revue_portee.domain.replication import StandardStudy
from support import START


def _ref(ref_id: str, title: str, *, doi: str = "", pmid: str = "") -> Reference:
    return Reference(id=ref_id, title=title, doi=doi, pmid=pmid, created_at=START)


REFERENCES = [
    _ref("r1", "Brisk walking groups and anxiety in older adults", doi="10.5555/FICT.0001"),
    _ref("r1d", "Brisk walking groups and anxiety in older adults", doi="10.5555/FICT.0001"),
    _ref("r2", "Nordic walking in long-term care residents", pmid="12345"),
    _ref("r3", "Neighbourhood strolls and wellbeing in retirement"),
    _ref("r4", "Walking"),
]


def test_match_by_doi_pmid_then_title() -> None:
    studies = [
        StandardStudy(study_id="A", doi="10.5555/FICT.0001"),
        StandardStudy(study_id="B", doi="10.5555/FICT.9999", pmid="12345"),
        StandardStudy(study_id="C", title="Neighbourhood strolls and well-being in retirement"),
        StandardStudy(
            study_id="D",
            citation="Cote H. Neighbourhood strolls and wellbeing in retirement. Rev. 2017.",
        ),
        StandardStudy(study_id="E", citation="Someone. Walking. 2010.", in_search=False),
    ]
    match = match_studies(studies, REFERENCES)
    assert match.references("A") == ("r1", "r1d")  # both duplicates
    assert match.rule == {"A": "doi", "B": "pmid", "C": "title", "D": "title"}
    assert match.references("B") == ("r2",)
    assert match.references("C") == ("r3",)
    assert match.references("D") == ("r3",)
    # A one-word title is never looked for in a citation.
    assert match.unmatched == ("E",)
    assert match.references("E") == ()
