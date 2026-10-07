"""Translation of concept blocks for PubMed, OpenAlex and PsycINFO (EF-REC-03)."""

from revue_portee.domain.search import (
    BlockRole,
    ConceptBlock,
    Database,
    Limits,
    SearchStrategy,
    WarningKind,
    parse_term,
)
from revue_portee.search.translate import OPENALEX_SEARCH_FILTER, translate


def block(code: str, *lines: str, role: BlockRole = BlockRole.INCLUDE) -> ConceptBlock:
    return ConceptBlock(code=code, label=code, role=role, terms=tuple(parse_term(x) for x in lines))


MIXED = SearchStrategy(
    blocks=(
        block(
            "B1",
            "parent*",
            '"parenting program"',
            "ti:father*",
            "ab:mother*",
            "tw:caregiver",
            "all:family",
            "mesh:Parenting",
            "mesh-noexp:Fathers",
            "apa+:Parenting",
            "apa:Parent Training",
        ),
        block(
            "B2", "pt:Review", "pubmed: review[pt]", "openalex: type:review", "psycinfo: PZ Review"
        ),
        block("B3", "rat*", role=BlockRole.EXCLUDE),
        block("B4"),  # no term yet
    ),
    limits=Limits(year_from=2015, year_to=2025, languages=("en", "fr")),
)


def kinds(translation: object) -> list[tuple[WarningKind, str | None]]:
    return [(w.kind, w.block) for w in translation.warnings]  # type: ignore[attr-defined]


def test_pubmed() -> None:
    result = translate(MIXED, Database.PUBMED)
    assert result.blocks["B1"] == (
        'parent*[tiab] OR "parenting program"[tiab] OR father*[ti] OR mother*[ab]'
        ' OR caregiver[tw] OR family[all] OR "Parenting"[mh] OR "Fathers"[mh:noexp]'
    )
    assert result.blocks["B2"] == "Review[pt] OR (review[pt])"
    assert result.limits == '("2015"[dp] : "2025"[dp]) AND (english[la] OR french[la])'
    assert result.text == (
        f"({result.blocks['B1']}) AND ({result.blocks['B2']}) AND {result.limits} NOT (rat*[tiab])"
    )
    assert kinds(result) == [
        (WarningKind.DESCRIPTOR_NOT_SUPPORTED, "B1"),
        (WarningKind.DESCRIPTOR_NOT_SUPPORTED, "B1"),
        (WarningKind.EMPTY_BLOCK, "B4"),
    ]


def test_openalex() -> None:
    result = translate(MIXED, Database.OPENALEX)
    expression = 'parent* OR "parenting program" OR father* OR mother* OR caregiver OR family'
    assert result.blocks["B1"] == f"{OPENALEX_SEARCH_FILTER}:{expression}"
    assert result.limits == (
        "from_publication_date:2015-01-01,to_publication_date:2025-12-31,language:en|fr"
    )
    assert result.text == (
        f"{OPENALEX_SEARCH_FILTER}:({expression}) NOT (rat*),{result.limits},type:review"
    )
    assert result.blocks["B2"] == "type:review"  # its raw filter, for the sensitivity test
    assert (WarningKind.FIELD_WIDENED, "B1") in kinds(result)
    assert (WarningKind.PUBLICATION_TYPE_NOT_SUPPORTED, "B2") in kinds(result)
    assert kinds(result).count((WarningKind.DESCRIPTOR_NOT_SUPPORTED, "B1")) == 4


def test_openalex_commas_are_removed() -> None:
    strategy = SearchStrategy(blocks=(block("B1", '"health, mental"'),))
    result = translate(strategy, Database.OPENALEX)
    assert result.text == f'{OPENALEX_SEARCH_FILTER}:("health mental")'
    assert kinds(result) == [(WarningKind.COMMA_REMOVED, "B1")]


def test_psycinfo() -> None:
    result = translate(MIXED, Database.PSYCINFO_EBSCO)
    assert result.blocks["B1"] == (
        'TI ( parent* OR "parenting program" OR father* ) OR AB ( parent*'
        ' OR "parenting program" OR mother* ) OR caregiver OR family'
        ' OR DE "Parenting+" OR DE "Parent Training"'
    )
    assert result.blocks["B2"] == "PT Review OR (PZ Review)"
    assert result.limits == "(LA English OR LA French)"
    assert (WarningKind.YEARS_IN_INTERFACE, None) in kinds(result)
    assert kinds(result).count((WarningKind.DESCRIPTOR_NOT_SUPPORTED, "B1")) == 2


def test_limits_alone_and_open_ranges() -> None:
    strategy = SearchStrategy(limits=Limits(year_to=2020, languages=("de",)))
    assert translate(strategy, Database.PUBMED).text == (
        '("1800"[dp] : "2020"[dp]) AND (german[la])'
    )
    assert translate(strategy, Database.PSYCINFO_EBSCO).text == "LA German"
    assert translate(strategy, Database.OPENALEX).text == (
        "to_publication_date:2020-12-31,language:de"
    )
    assert translate(SearchStrategy(), Database.OPENALEX).text == ""


def test_openalex_raw_filters_of_exclusion_blocks_are_left_out() -> None:
    strategy = SearchStrategy(
        blocks=(
            block("B1", "parent*", "openalex: has_abstract:true"),
            block("B2", "rat*", "openalex: type:review", role=BlockRole.EXCLUDE),
        )
    )
    result = translate(strategy, Database.OPENALEX)
    assert result.text == (f"{OPENALEX_SEARCH_FILTER}:(parent*) NOT (rat*),has_abstract:true")
    assert result.blocks == {
        "B1": f"{OPENALEX_SEARCH_FILTER}:parent*,has_abstract:true",
        "B2": f"{OPENALEX_SEARCH_FILTER}:rat*",
    }
    assert kinds(result) == [(WarningKind.RAW_FILTER_IN_EXCLUSION, "B2")]


def test_exclusion_blocks_alone_give_no_query() -> None:
    strategy = SearchStrategy(blocks=(block("B1", "child*", role=BlockRole.EXCLUDE),))
    for database in Database:
        result = translate(strategy, database)
        assert result.text == ""
        assert (WarningKind.EXCLUSION_WITHOUT_INCLUSION, None) in kinds(result)
    with_limits = strategy.model_copy(update={"limits": Limits(year_from=2020)})
    assert translate(with_limits, Database.PUBMED).text == (
        '("2020"[dp] : "3000"[dp]) NOT (child*[tiab])'
    )
