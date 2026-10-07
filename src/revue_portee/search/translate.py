"""Translation of a search strategy into the syntax of each database (EF-REC-03).

Pure and deterministic (ENF-REP-01): the same strategy always gives the same text,
terms in the order they were entered. What a database cannot express is left out and
reported as a warning, never silently.

- **PubMed**: ``"phrase"[tiab]``, ``word*[ti]``, ``"Heading"[mh]`` (``[mh:noexp]``),
  publication date ``[dp]`` and language ``[la]`` limits.
- **OpenAlex**: one ``title_and_abstract.search.exact`` filter (no stemming, so that
  truncation works) holding the boolean expression, plus ``from_publication_date``,
  ``to_publication_date`` and ``language`` filters. Controlled vocabularies and field
  restrictions do not exist there.
- **PsycINFO (EBSCOhost)**: ``TI ( … ) OR AB ( … )`` for title and abstract,
  ``DE "Heading"`` (``"Heading+"`` exploded) for the APA Thesaurus, ``LA`` for languages.
  Publication years are set with the interface limiter.
"""

from collections.abc import Sequence

from revue_portee.domain.search import (
    LANGUAGES,
    ConceptBlock,
    Database,
    SearchStrategy,
    Term,
    TermField,
    TermKind,
    Translation,
    TranslationWarning,
    Vocabulary,
    WarningKind,
    format_term,
)

__all__ = [
    "OPENALEX_SEARCH_FILTER",
    "Translation",
    "TranslationWarning",
    "WarningKind",
    "translate",
]

OPENALEX_SEARCH_FILTER = "title_and_abstract.search.exact"


def _quoted(term: Term) -> str:
    return f'"{term.text}"' if term.phrase else term.text


# --- PubMed ---------------------------------------------------------------------------

_PUBMED_TAGS = {
    TermField.TIAB: "tiab",
    TermField.TI: "ti",
    TermField.AB: "ab",
    TermField.TW: "tw",
    TermField.ALL: "all",
    TermField.PT: "pt",
}


def _pubmed_term(term: Term, block: str, warnings: list[TranslationWarning]) -> str | None:
    if term.kind is TermKind.RAW:
        return f"({term.text})"
    if term.kind is TermKind.DESCRIPTOR:
        if term.vocabulary is not Vocabulary.MESH:
            warnings.append(_warning(WarningKind.DESCRIPTOR_NOT_SUPPORTED, block, term))
            return None
        return f'"{term.text}"[{"mh" if term.explode else "mh:noexp"}]'
    return f"{_quoted(term)}[{_PUBMED_TAGS[term.field]}]"


def _pubmed_limits(strategy: SearchStrategy) -> str:
    limits = strategy.limits
    parts = []
    if limits.year_from or limits.year_to:
        start, end = limits.year_from or 1800, limits.year_to or 3000
        parts.append(f'("{start}"[dp] : "{end}"[dp])')
    if limits.languages:
        names = [f"{LANGUAGES[code].lower()}[la]" for code in limits.languages]
        parts.append(f"({' OR '.join(names)})")
    return " AND ".join(parts)


# --- PsycINFO (EBSCOhost) -------------------------------------------------------------


def _ebsco_free(term: Term) -> str:
    return _quoted(term)


def _ebsco_block(block: ConceptBlock, warnings: list[TranslationWarning]) -> str | None:
    title: list[str] = []
    abstract: list[str] = []
    others: list[str] = []
    for term in block.terms_for(Database.PSYCINFO_EBSCO):
        if term.kind is TermKind.RAW:
            others.append(f"({term.text})")
        elif term.kind is TermKind.DESCRIPTOR:
            if term.vocabulary is not Vocabulary.APA:
                warnings.append(_warning(WarningKind.DESCRIPTOR_NOT_SUPPORTED, block.code, term))
                continue
            others.append(f'DE "{term.text}{"+" if term.explode else ""}"')
        elif term.field in (TermField.TIAB, TermField.TI):
            title.append(_ebsco_free(term))
            if term.field is TermField.TIAB:
                abstract.append(_ebsco_free(term))
        elif term.field is TermField.AB:
            abstract.append(_ebsco_free(term))
        elif term.field is TermField.PT:
            others.append(f"PT {_ebsco_free(term)}")
        else:  # text words and all fields: the default fields of EBSCOhost
            others.append(_ebsco_free(term))
    parts = []
    if title:
        parts.append(f"TI ( {' OR '.join(title)} )")
    if abstract:
        parts.append(f"AB ( {' OR '.join(abstract)} )")
    parts += others
    return " OR ".join(parts) if parts else None


def _ebsco_limits(strategy: SearchStrategy, warnings: list[TranslationWarning]) -> str:
    limits = strategy.limits
    if limits.year_from or limits.year_to:
        years = f"{limits.year_from or '…'}-{limits.year_to or '…'}"
        warnings.append(TranslationWarning(kind=WarningKind.YEARS_IN_INTERFACE, detail=years))
    if not limits.languages:
        return ""
    names = [f"LA {LANGUAGES[code]}" for code in limits.languages]
    return f"({' OR '.join(names)})" if len(names) > 1 else names[0]


# --- OpenAlex -------------------------------------------------------------------------


def _openalex_term(term: Term, block: str, warnings: list[TranslationWarning]) -> str | None:
    if term.kind is TermKind.DESCRIPTOR:
        warnings.append(_warning(WarningKind.DESCRIPTOR_NOT_SUPPORTED, block, term))
        return None
    if term.field is TermField.PT:
        warnings.append(_warning(WarningKind.PUBLICATION_TYPE_NOT_SUPPORTED, block, term))
        return None
    if term.field is not TermField.TIAB:
        warnings.append(_warning(WarningKind.FIELD_WIDENED, block, term))
    text = _quoted(term)
    if "," in text:
        warnings.append(_warning(WarningKind.COMMA_REMOVED, block, term))
        text = " ".join(text.replace(",", " ").split())
    return text


def _openalex_limits(strategy: SearchStrategy) -> list[str]:
    limits = strategy.limits
    parts = []
    if limits.year_from:
        parts.append(f"from_publication_date:{limits.year_from}-01-01")
    if limits.year_to:
        parts.append(f"to_publication_date:{limits.year_to}-12-31")
    if limits.languages:
        parts.append("language:" + "|".join(limits.languages))
    return parts


# --- Common ---------------------------------------------------------------------------


def _warning(kind: WarningKind, block: str, term: Term) -> TranslationWarning:
    return TranslationWarning(kind=kind, block=block, term=format_term(term))


def _combine(included: Sequence[str], excluded: Sequence[str], limits: str) -> str:
    query = " AND ".join(f"({text})" for text in included)
    if limits:
        query = f"{query} AND {limits}" if query else limits
    for text in excluded:
        query = f"{query} NOT ({text})"
    return query


def translate(strategy: SearchStrategy, database: Database) -> Translation:
    """The query of ``strategy`` in the syntax of ``database``."""
    warnings: list[TranslationWarning] = []
    blocks: dict[str, str] = {}
    for block in strategy.blocks:
        if database is Database.PSYCINFO_EBSCO:
            text = _ebsco_block(block, warnings)
        else:
            translate_term = _pubmed_term if database is Database.PUBMED else _openalex_term
            raw_terms = [
                t for t in block.terms_for(database)
                if not (database is Database.OPENALEX and t.kind is TermKind.RAW)
            ]  # fmt: skip
            texts = [x for t in raw_terms if (x := translate_term(t, block.code, warnings))]
            text = " OR ".join(texts) if texts else None
        if text:
            blocks[block.code] = text
        else:
            warnings.append(TranslationWarning(kind=WarningKind.EMPTY_BLOCK, block=block.code))
    included = [blocks[b.code] for b in strategy.included if b.code in blocks]
    excluded = [blocks[b.code] for b in strategy.excluded if b.code in blocks]
    if database is Database.OPENALEX:
        expression = _combine(included, excluded, "")
        filters = [f"{OPENALEX_SEARCH_FILTER}:{expression}"] if expression else []
        extra = _openalex_limits(strategy) + [
            t.text for b in strategy.blocks for t in b.terms_for(database) if t.kind is TermKind.RAW
        ]
        return Translation(
            database=database,
            text=",".join(filters + extra),
            blocks={code: f"{OPENALEX_SEARCH_FILTER}:{text}" for code, text in blocks.items()},
            limits=",".join(_openalex_limits(strategy)),
            warnings=tuple(warnings),
        )
    limits = (
        _pubmed_limits(strategy)
        if database is Database.PUBMED
        else _ebsco_limits(strategy, warnings)
    )
    return Translation(
        database=database,
        text=_combine(included, excluded, limits),
        blocks=blocks,
        limits=limits,
        warnings=tuple(warnings),
    )
