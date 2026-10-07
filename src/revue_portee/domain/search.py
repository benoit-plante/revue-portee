"""Search strategy: concept blocks, terms, limits, key articles (EF-REC-01, EF-REC-05).

A strategy is a set of **concept blocks** (usually one per PCC element). The terms of a
block are combined with OR, the blocks with AND; an exclusion block is subtracted
with NOT. Each term is entered on one line with a small syntax (see
:func:`parse_term`), so that a block can be edited as plain text:

- ``parent*``, ``"soutien parental"``: free text in title and abstract (truncation
  ``*``, exact phrase between quotes);
- ``ti: parent*``, ``ab:``, ``tw:``, ``all:``, ``pt:``: another field (title, abstract,
  text words, all fields, publication type);
- ``mesh: Parenting``, ``mesh-noexp: Parenting``: MeSH descriptor, exploded or not;
- ``apa: Parenting``, ``apa+: Parenting``: APA Thesaurus descriptor (PsycINFO), not
  exploded or exploded;
- ``pubmed: …``, ``openalex: …``, ``psycinfo: …``: text copied as is in the query of
  that database only (filters, limits written in its own syntax).

Strategies are versioned like the criteria: each saved change is a new immutable
version (EF-REC-06).
"""

import re
from collections.abc import Iterable
from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from revue_portee.domain.criteria import PccElement
from revue_portee.domain.protocol import normalize_doi
from revue_portee.domain.suggestions import SuggestionOutcome

__all__ = [
    "BLOCK_CODE",
    "LANGUAGES",
    "BlockRole",
    "ConceptBlock",
    "Database",
    "DescriptorCheck",
    "KeyArticle",
    "KeyArticleKind",
    "KeyArticleSetVersion",
    "Limits",
    "QueryVersion",
    "RunKind",
    "SearchRun",
    "SearchStrategy",
    "StrategyVersion",
    "Term",
    "TermField",
    "TermKind",
    "TermSuggestion",
    "TermSuggestionKind",
    "TermSuggestionReview",
    "TermSyntaxError",
    "Translation",
    "TranslationWarning",
    "Vocabulary",
    "WarningKind",
    "format_term",
    "next_block_code",
    "parse_key_article",
    "parse_term",
]


class Database(StrEnum):
    PUBMED = "pubmed"
    OPENALEX = "openalex"
    PSYCINFO_EBSCO = "psycinfo_ebsco"

    @property
    def display_name(self) -> str:
        """Proper name of the database (not translated)."""
        return _DATABASE_NAMES[self]


_DATABASE_NAMES = {
    Database.PUBMED: "PubMed",
    Database.OPENALEX: "OpenAlex",
    Database.PSYCINFO_EBSCO: "PsycINFO (EBSCOhost)",
}


class TermKind(StrEnum):
    FREE = "free"  # free-text word or phrase
    DESCRIPTOR = "descriptor"  # controlled vocabulary heading
    RAW = "raw"  # text copied as is in one database's query


class TermField(StrEnum):
    TIAB = "tiab"
    TI = "ti"
    AB = "ab"
    TW = "tw"  # text words (PubMed); title, abstract and subjects elsewhere
    ALL = "all"
    PT = "pt"  # publication type


class Vocabulary(StrEnum):
    MESH = "mesh"
    APA = "apa"  # APA Thesaurus of Psychological Index Terms


class TermSyntaxError(ValueError):
    """A term line that cannot be read (the message names the problem, in English)."""


class Term(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: TermKind
    text: str = Field(min_length=1)
    field: TermField = TermField.TIAB  # free text only
    phrase: bool = False  # free text only: searched as an exact phrase
    vocabulary: Vocabulary | None = None  # descriptors only
    explode: bool = True  # descriptors only: include narrower headings
    database: Database | None = None  # raw text only

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.kind is TermKind.DESCRIPTOR) != (self.vocabulary is not None):
            raise ValueError("a descriptor, and only a descriptor, has a vocabulary")
        if (self.kind is TermKind.RAW) != (self.database is not None):
            raise ValueError("a raw term, and only a raw term, has a database")
        return self

    @property
    def truncated(self) -> bool:
        return self.kind is TermKind.FREE and "*" in self.text


_FIELD_PREFIXES = {f.value: f for f in TermField}
_DESCRIPTOR_PREFIXES = {
    "mesh": (Vocabulary.MESH, True),
    "mesh-noexp": (Vocabulary.MESH, False),
    "apa": (Vocabulary.APA, False),
    "apa+": (Vocabulary.APA, True),
}
_RAW_PREFIXES = {
    "pubmed": Database.PUBMED,
    "openalex": Database.OPENALEX,
    "psycinfo": Database.PSYCINFO_EBSCO,
}
_PREFIX = re.compile(r"^(?P<prefix>[a-z+-]+)\s*:\s*(?P<rest>.*)$", re.IGNORECASE)
_OPERATOR = re.compile(r"(?:^|\s)(AND|OR|NOT)(?:\s|$)")
_QUOTES = str.maketrans({"“": '"', "”": '"', "«": '"', "»": '"'})


def _balanced(text: str) -> bool:
    depth = 0
    for char in text:
        depth += {"(": 1, ")": -1}.get(char, 0)
        if depth < 0:
            return False
    return depth == 0 and text.count('"') % 2 == 0


def parse_term(line: str) -> Term:
    """Read one term line (see the module documentation)."""
    text = " ".join(line.translate(_QUOTES).split())
    if not text:
        raise TermSyntaxError("empty term")
    prefix, rest = "", text
    match = _PREFIX.match(text)
    if match and match.group("prefix").lower() in (
        _FIELD_PREFIXES.keys() | _DESCRIPTOR_PREFIXES.keys() | _RAW_PREFIXES.keys()
    ):
        prefix, rest = match.group("prefix").lower(), match.group("rest").strip()
    if not rest:
        raise TermSyntaxError("a prefix needs a term")
    if prefix in _RAW_PREFIXES:
        if not _balanced(rest):
            raise TermSyntaxError("unbalanced parentheses or quotes")
        return Term(kind=TermKind.RAW, text=rest, database=_RAW_PREFIXES[prefix])
    if prefix in _DESCRIPTOR_PREFIXES:
        heading = rest.strip('"').strip()
        if not heading or '"' in heading:
            raise TermSyntaxError("invalid descriptor")
        vocabulary, explode = _DESCRIPTOR_PREFIXES[prefix]
        return Term(kind=TermKind.DESCRIPTOR, text=heading, vocabulary=vocabulary, explode=explode)
    phrase = len(rest) >= 2 and rest.startswith('"') and rest.endswith('"')
    words = rest[1:-1].strip() if phrase else rest
    if not words or '"' in words or any(c in words for c in "()[]"):
        raise TermSyntaxError("quotes, parentheses and brackets are not allowed in a term")
    if _OPERATOR.search(words):
        raise TermSyntaxError("one term per line: use separate lines instead of AND, OR, NOT")
    return Term(
        kind=TermKind.FREE,
        text=words,
        field=_FIELD_PREFIXES.get(prefix, TermField.TIAB),
        phrase=phrase or " " in words,
    )


def format_term(term: Term) -> str:
    """The line that :func:`parse_term` reads back into ``term``."""
    if term.kind is TermKind.RAW:
        prefix = next(k for k, v in _RAW_PREFIXES.items() if v is term.database)
        return f"{prefix}: {term.text}"
    if term.kind is TermKind.DESCRIPTOR:
        prefix = next(
            k for k, v in _DESCRIPTOR_PREFIXES.items() if v == (term.vocabulary, term.explode)
        )
        return f"{prefix}: {term.text}"
    words = f'"{term.text}"' if term.phrase else term.text
    return words if term.field is TermField.TIAB else f"{term.field.value}: {words}"


class BlockRole(StrEnum):
    INCLUDE = "include"  # combined with AND
    EXCLUDE = "exclude"  # subtracted with NOT


BLOCK_CODE = re.compile(r"^B(?P<number>[1-9][0-9]*)$")


class ConceptBlock(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(pattern=BLOCK_CODE.pattern)
    label: str = Field(min_length=1)
    pcc_element: PccElement | None = None
    role: BlockRole = BlockRole.INCLUDE
    terms: tuple[Term, ...] = ()

    def terms_for(self, database: Database) -> tuple[Term, ...]:
        """Terms that apply to ``database`` (raw text of other databases left out)."""
        return tuple(t for t in self.terms if t.kind is not TermKind.RAW or t.database is database)


def next_block_code(used: Iterable[str]) -> str:
    """Next block code; codes are never reused, like criterion codes."""
    numbers = [int(m.group("number")) for code in used if (m := BLOCK_CODE.match(code))]
    return f"B{max(numbers, default=0) + 1}"


# Languages offered as limits: ISO 639-1 code -> name used by PubMed and PsycINFO.
LANGUAGES: dict[str, str] = {
    "en": "English",
    "fr": "French",
    "es": "Spanish",
    "de": "German",
    "pt": "Portuguese",
    "it": "Italian",
}


class Limits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    year_from: int | None = Field(default=None, ge=1800, le=2100)
    year_to: int | None = Field(default=None, ge=1800, le=2100)
    languages: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _valid(self) -> Self:
        if self.year_from and self.year_to and self.year_from > self.year_to:
            raise ValueError("the first year comes after the last year")
        unknown = [code for code in self.languages if code not in LANGUAGES]
        if unknown:
            raise ValueError(f"unknown languages: {unknown}")
        return self

    @property
    def empty(self) -> bool:
        return self.year_from is None and self.year_to is None and not self.languages


class SearchStrategy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    blocks: tuple[ConceptBlock, ...] = ()
    limits: Limits = Limits()

    @model_validator(mode="after")
    def _unique_codes(self) -> Self:
        codes = [b.code for b in self.blocks]
        if len(codes) != len(set(codes)):
            raise ValueError("block codes must be unique")
        return self

    def block(self, code: str) -> ConceptBlock | None:
        return next((b for b in self.blocks if b.code == code), None)

    @property
    def included(self) -> tuple[ConceptBlock, ...]:
        return tuple(b for b in self.blocks if b.role is BlockRole.INCLUDE and b.terms)

    @property
    def excluded(self) -> tuple[ConceptBlock, ...]:
        return tuple(b for b in self.blocks if b.role is BlockRole.EXCLUDE and b.terms)


class StrategyVersion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    number: int = Field(ge=1)
    created_at: AwareDatetime
    author_id: str
    rationale: str = ""
    strategy: SearchStrategy


class KeyArticleKind(StrEnum):
    DOI = "doi"
    PMID = "pmid"
    TITLE = "title"


class KeyArticle(BaseModel):
    """An article the search must retrieve (sensitivity test, EF-REC-05)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: KeyArticleKind
    value: str = Field(min_length=1)

    @property
    def label(self) -> str:
        return f"{self.kind.value.upper()} {self.value}"


_PMID = re.compile(r"^(?:pmid\s*:?\s*)?(?P<pmid>[1-9][0-9]{0,8})$", re.IGNORECASE)


def parse_key_article(line: str) -> KeyArticle:
    """A DOI, a PMID (digits, optionally after "PMID:") or else a title (10+ characters)."""
    text = " ".join(line.split())
    if match := _PMID.match(text):
        return KeyArticle(kind=KeyArticleKind.PMID, value=match.group("pmid"))
    try:
        return KeyArticle(kind=KeyArticleKind.DOI, value=normalize_doi(text))
    except ValueError:
        pass
    if len(text) < 10:
        raise ValueError("not a DOI, a PMID or a title")
    return KeyArticle(kind=KeyArticleKind.TITLE, value=text)


class KeyArticleSetVersion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    number: int = Field(ge=1)
    created_at: AwareDatetime
    author_id: str
    articles: tuple[KeyArticle, ...]


# --- Translated queries (the translators are in search/translate.py) ----------------


class WarningKind(StrEnum):
    DESCRIPTOR_NOT_SUPPORTED = "descriptor_not_supported"  # vocabulary absent there
    FIELD_WIDENED = "field_widened"  # field not available: searched more broadly
    PUBLICATION_TYPE_NOT_SUPPORTED = "publication_type_not_supported"
    COMMA_REMOVED = "comma_removed"  # OpenAlex filters cannot hold commas
    EMPTY_BLOCK = "empty_block"
    YEARS_IN_INTERFACE = "years_in_interface"  # limit to set in the database interface


class TranslationWarning(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: WarningKind
    block: str | None = None  # block code
    term: str | None = None  # the term line concerned
    detail: str = ""


class Translation(BaseModel):
    """The query of one database, with the query of each block alone (for counts and
    for the sensitivity test) and the warnings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    database: Database
    text: str  # the complete query (for OpenAlex: the value of the "filter" parameter)
    blocks: dict[str, str]  # block code -> query of that block alone
    limits: str = ""  # the limits alone ("" when none)
    warnings: tuple[TranslationWarning, ...] = ()


# --- Stored records ---------------------------------------------------------------


class QueryVersion(BaseModel):
    """The query generated for one database from one strategy version (EF-REC-06)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    strategy_version_id: str
    created_at: AwareDatetime
    translation: Translation
    generated_by: str = "translator"
    edited: bool = False

    @property
    def database(self) -> Database:
        return self.translation.database


class RunKind(StrEnum):
    COUNT = "count"
    SENSITIVITY = "sensitivity"


class SearchRun(BaseModel):
    """One execution of a query against a database API; raw answers in ``raw_dir``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    query_id: str
    kind: RunKind
    executed_at: AwareDatetime
    result_count: int | None  # total of the complete query (None for a sensitivity test)
    block_counts: dict[str, int] = Field(default_factory=dict)
    raw_dir: str
    reviewer_id: str


class DescriptorCheck(BaseModel):
    """Whether a controlled-vocabulary heading exists (EF-REC-04)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    created_at: AwareDatetime
    vocabulary: Vocabulary
    heading: str
    found: bool
    official_heading: str | None = None
    descriptor_ui: str | None = None
    raw_dir: str
    reviewer_id: str


class TermSuggestionKind(StrEnum):
    FREE_TERM = "free_term"  # synonym, variant, truncation, phrase
    DESCRIPTOR = "descriptor"  # MeSH or APA Thesaurus heading


class TermSuggestion(BaseModel):
    """A term proposed by the AI for one block (EF-REC-02), in the term syntax."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    ai_call_id: str
    strategy_version_id: str
    position: int = Field(ge=0)
    block_code: str = Field(pattern=BLOCK_CODE.pattern)
    kind: TermSuggestionKind
    line: str = Field(min_length=1)
    rationale: str
    created_at: AwareDatetime

    @property
    def term(self) -> Term:
        return parse_term(self.line)


class TermSuggestionReview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    suggestion_id: str
    outcome: SuggestionOutcome
    final_line: str
    reviewer_id: str
    created_at: AwareDatetime
    strategy_version_id: str | None = None  # version created by this review
