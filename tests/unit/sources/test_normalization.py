"""Normalization of OpenAlex works, PubMed XML and Crossref works into references."""

import pytest

from recording import MASKED_EMAIL, trim_body
from revue_portee.sources.crossref import fields_from_work
from revue_portee.sources.http import SourceInvalidAnswerError
from revue_portee.sources.openalex import normalize_work
from revue_portee.sources.pubmed import parse_pubmed_xml
from revue_portee.sources.records import abstract_from_inverted_index


def test_openalex_work() -> None:
    work = {
        "id": "https://openalex.org/W42",
        "doi": "https://doi.org/10.1000/ABC",
        "display_name": "A  title",
        "publication_year": 2024,
        "authorships": [{"author": {"display_name": "Jane Doe"}}, {"author": {}}],
        "primary_location": {
            "source": {"display_name": "Journal"},
            "landing_page_url": "https://example.org/a",
        },
        "biblio": {"volume": "3", "issue": None, "first_page": "10", "last_page": "20"},
        "ids": {"pmid": "https://pubmed.ncbi.nlm.nih.gov/123"},
        "language": "en",
        "type": "article",
        "abstract_inverted_index": {"world": [1], "Hello": [0]},
    }
    record = normalize_work(work)
    assert record.original_id == "W42"
    assert record.fields == {
        "title": "A title",
        "abstract": "Hello world",
        "authors": ("Jane Doe",),
        "year": 2024,
        "container_title": "Journal",
        "volume": "3",
        "issue": "",
        "pages": "10-20",
        "doi": "10.1000/ABC",
        "pmid": "123",
        "openalex_id": "W42",
        "language": "en",
        "doc_type": "article",
        "url": "https://example.org/a",
    }
    bare = normalize_work({"id": "W1", "primary_location": None})
    assert (bare.fields["title"], bare.fields["pmid"]) == ("", "")
    assert abstract_from_inverted_index(None) == ""


XML = """<?xml version="1.0"?>
<PubmedArticleSet>
<PubmedArticle><MedlineCitation><PMID>111</PMID><Article>
  <Journal><JournalIssue><Volume>5</Volume><Issue>2</Issue>
    <PubDate><MedlineDate>2019 Spring</MedlineDate></PubDate></JournalIssue>
    <Title>Journal of Tests</Title></Journal>
  <ArticleTitle>A <i>study</i> of tests.</ArticleTitle>
  <Pagination><MedlinePgn>1-9</MedlinePgn></Pagination>
  <ELocationID EIdType="doi">10.1000/elo</ELocationID>
  <Abstract><AbstractText Label="BACKGROUND">Why.</AbstractText>
    <AbstractText>How.</AbstractText></Abstract>
  <AuthorList><Author><LastName>Doe</LastName><ForeName>Jane</ForeName></Author>
    <Author><CollectiveName>The Group</CollectiveName></Author>
    <Author><LastName>Solo</LastName></Author></AuthorList>
  <Language>eng</Language>
  <PublicationTypeList><PublicationType>Review</PublicationType></PublicationTypeList>
</Article></MedlineCitation></PubmedArticle>
<PubmedArticle><MedlineCitation><PMID>222</PMID><Article><ArticleTitle>B</ArticleTitle>
</Article></MedlineCitation><PubmedData><ArticleIdList>
<ArticleId IdType="doi">10.1000/b</ArticleId></ArticleIdList></PubmedData></PubmedArticle>
<PubmedArticle></PubmedArticle>
<PubmedBookArticle><BookDocument><PMID>333</PMID><Book><BookTitle>A Report</BookTitle>
  <PubDate><Year>2018</Year></PubDate>
  <AuthorList><Author><LastName>Roe</LastName><ForeName>Ann</ForeName></Author></AuthorList>
</Book><Language>eng</Language></BookDocument>
<PubmedBookData><ArticleIdList><ArticleId IdType="doi">10.3310/r</ArticleId></ArticleIdList>
</PubmedBookData></PubmedBookArticle>
</PubmedArticleSet>"""


def test_pubmed_articles_and_books() -> None:
    first, second, book = parse_pubmed_xml(XML)
    assert first.original_id == "111"
    assert first.fields["title"] == "A study of tests."
    assert first.fields["abstract"] == "BACKGROUND: Why.\nHow."
    assert first.fields["authors"] == ("Doe, Jane", "The Group", "Solo")
    assert (first.fields["year"], first.fields["pages"], first.fields["doi"]) == (
        2019,
        "1-9",
        "10.1000/ELO",
    )
    assert first.fields["container_title"] == "Journal of Tests"
    assert second.fields["doi"] == "10.1000/B"
    assert second.fields["year"] is None
    assert (book.original_id, book.fields["title"], book.fields["year"]) == (
        "333",
        "A Report",
        2018,
    )
    assert book.fields["authors"] == ("Roe, Ann",)
    assert book.fields["container_title"] == ""
    with pytest.raises(SourceInvalidAnswerError):
        parse_pubmed_xml("<not closed")


def test_crossref_work() -> None:
    fields = fields_from_work(
        {
            "title": ["  A   title "],
            "abstract": "<jats:p>Abstract Text here.</jats:p>",
            "author": [{"family": "Doe", "given": "J"}, {"name": "Consortium"}, {}],
            "issued": {"date-parts": [[2020]]},
            "published-print": {"date-parts": [[None]]},
            "container-title": [],
            "page": "5-9",
        }
    )
    assert fields == {
        "title": "A title",
        "abstract": "Text here.",
        "authors": ["Doe, J", "Consortium"],
        "year": 2020,
        "pages": "5-9",
    }
    assert fields_from_work({}) == {}


def test_recorded_answers_are_trimmed() -> None:
    xml = (
        "<Set><Art><AbstractText>" + "x" * 300 + " <i>a@uni.test</i></AbstractText>"
        "<ReferenceList><Ref>r</Ref></ReferenceList><Aff>b@uni.test</Aff></Art></Set>"
    )
    trimmed = trim_body("text/xml", xml)
    assert "ReferenceList" not in trimmed
    assert "uni.test" not in trimmed
    assert MASKED_EMAIL in trimmed
    assert len(trimmed) < 300
    json_body = '{"abstract_inverted_index": {"w": [1, 40]}, "abstract": "' + "y" * 300 + '"}'
    assert trim_body("application/json", json_body) == (
        '{"abstract_inverted_index": {"w": [1]}, "abstract": "' + "y" * 200 + '"}'
    )
    assert trim_body("application/json", "not json c@uni.test") == f"not json {MASKED_EMAIL}"
    assert trim_body("text/xml", "<broken") == "<broken"
