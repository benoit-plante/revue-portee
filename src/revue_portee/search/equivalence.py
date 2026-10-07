"""Syntactic equivalence of two queries (EF-REC-03 acceptance tests).

A query is parsed into a boolean tree, then normalized so that differences without
effect disappear:

- spacing, case, straight or curly quotes, redundant parentheses;
- order of the operands of OR and AND (both commutative);
- ``A NOT B`` read as ``A AND (NOT B)``, so that the position of NOT among the AND
  operands does not matter;
- field tag synonyms (``[tiab]`` = ``[Title/Abstract]``, ``[mh]`` = ``[Mesh]`` =
  ``[MeSH Terms]``, ``[pdat]`` = ``[dp]``…);
- EBSCOhost field codes distributed over a group (``TI ( a OR b )`` = ``TI a OR TI b``),
  and ``TI x OR AB x`` read as one title-and-abstract term.

Queries are read left to right, without operator precedence, as PubMed does.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "Syntax",
    "equivalent",
    "normalize",
    "parse",
]


class Syntax(StrEnum):
    PUBMED = "pubmed"
    EBSCO = "ebsco"


@dataclass(frozen=True, slots=True)
class Leaf:
    text: str
    field: str  # canonical field, "" when untagged


@dataclass(frozen=True, slots=True)
class Range:
    field: str
    start: str
    end: str


@dataclass(frozen=True, slots=True)
class Not:
    operand: "Node"


@dataclass(frozen=True, slots=True)
class Or:
    operands: frozenset["Node"]


@dataclass(frozen=True, slots=True)
class And:
    operands: frozenset["Node"]


type Node = Leaf | Range | Not | Or | And


_PUBMED_FIELDS = {
    "tiab": "tiab",
    "title/abstract": "tiab",
    "ti": "ti",
    "title": "ti",
    "ab": "ab",
    "abstract": "ab",
    "tw": "tw",
    "text word": "tw",
    "all": "all",
    "all fields": "all",
    "mh": "mh",
    "mesh": "mh",
    "mesh terms": "mh",
    "mh:noexp": "mh:noexp",
    "mesh:noexp": "mh:noexp",
    "mesh terms:noexp": "mh:noexp",
    "majr": "majr",
    "pt": "pt",
    "publication type": "pt",
    "la": "la",
    "lang": "la",
    "language": "la",
    "dp": "dp",
    "pdat": "dp",
    "date - publication": "dp",
    "uid": "uid",
    "filter": "filter",
    "sb": "filter",
}
_EBSCO_FIELDS = {"TI", "AB", "DE", "MH", "MM", "SU", "TX", "KW", "PT", "PZ", "PO", "LA", "XB"}
# Typographic quotes and apostrophes, as published, read as their plain forms.
_QUOTES = str.maketrans({"\u201c": '"', "\u201d": '"', "\u201e": '"', "\u2019": "'", "\u2018": "'"})
_TOKEN = re.compile(
    r"""\s*(?:
        (?P<lparen>\() | (?P<rparen>\)) |
        (?P<tag>\[[^\]]*\]) |
        "(?P<phrase>[^"]*)" |
        (?P<word>[^\s()"\[]+)
    )""",
    re.VERBOSE,
)


class _Parser:
    def __init__(self, text: str, syntax: Syntax) -> None:
        self.syntax = syntax
        self.tokens: list[tuple[str, str]] = []
        position = 0
        text = text.translate(_QUOTES).strip()
        while position < len(text):
            match = _TOKEN.match(text, position)
            if match is None or match.end() == position:
                if text[position:].strip():
                    raise ValueError(
                        f"cannot read the query at: {text[position : position + 20]!r}"
                    )
                break
            kind = match.lastgroup
            assert kind is not None  # noqa: S101 - one group always matches
            self.tokens.append((kind, match.group(kind)))
            position = match.end()
        self.index = 0

    def peek(self) -> tuple[str, str] | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def take(self) -> tuple[str, str]:
        token = self.tokens[self.index]
        self.index += 1
        return token

    def operator(self) -> str | None:
        token = self.peek()
        if token is None or token[0] != "word":
            return None
        word = token[1] if self.syntax is Syntax.PUBMED else token[1].upper()
        return word if word in {"AND", "OR", "NOT"} else None

    def expression(self) -> Node:
        node = self.unary()
        while (operator := self.operator()) is not None:
            self.take()
            right = self.unary()
            if operator == "OR":
                node = Or(frozenset({node, right}))
            elif operator == "AND":
                node = And(frozenset({node, right}))
            else:
                node = And(frozenset({node, Not(right)}))
        return node

    def unary(self) -> Node:
        token = self.peek()
        if (
            self.syntax is Syntax.EBSCO
            and token is not None
            and token[0] == "word"
            and token[1] in _EBSCO_FIELDS
            and self.index + 1 < len(self.tokens)
        ):
            self.take()
            return _with_field(self.primary(), token[1].lower())
        return self.primary()

    def primary(self) -> Node:
        token = self.peek()
        if token is None:
            raise ValueError("unexpected end of query")
        if token[0] == "lparen":
            self.take()
            node = self.expression()
            if self.peek() is None or self.take()[0] != "rparen":
                raise ValueError("missing closing parenthesis")
            return node
        return self.term()

    def term(self) -> Node:
        words: list[str] = []
        while (token := self.peek()) is not None and token[0] in {"word", "phrase"}:
            if token[0] == "word" and (self.operator() is not None or token[1] == ":"):
                break
            if self.syntax is Syntax.EBSCO and token[0] == "word" and token[1] in _EBSCO_FIELDS:
                break
            words.append(self.take()[1])
        if not words:
            raise ValueError(f"a term was expected, not {self.peek()}")
        field = ""
        if (token := self.peek()) is not None and token[0] == "tag":
            tag = " ".join(self.take()[1][1:-1].lower().split())
            field = _PUBMED_FIELDS.get(tag, tag)
        leaf = Leaf(_text(" ".join(words)), field)
        if (token := self.peek()) is not None and token == ("word", ":"):
            self.take()
            end = self.term()
            if not isinstance(end, Leaf):
                raise ValueError("invalid range")
            return Range(field or end.field, leaf.text, end.text)
        return leaf


def _text(value: str) -> str:
    text = " ".join(value.lower().split())
    return re.sub(r"\s+\+$", "+", text)


def _with_field(node: Node, field: str) -> Node:
    """Apply an EBSCOhost field code to the untagged terms of ``node``."""
    if isinstance(node, Leaf):
        return node if node.field else Leaf(node.text, field)
    if isinstance(node, Not):
        return Not(_with_field(node.operand, field))
    if isinstance(node, Or | And):
        return type(node)(frozenset(_with_field(child, field) for child in node.operands))
    return node


def parse(text: str, syntax: Syntax) -> Node:
    parser = _Parser(text, syntax)
    node = parser.expression()
    if parser.peek() is not None:
        raise ValueError(f"unexpected {parser.peek()}")
    return node


def normalize(node: Node) -> Node:
    """Canonical form: flattened AND and OR, title + abstract pairs merged."""
    if isinstance(node, Not):
        return Not(normalize(node.operand))
    if isinstance(node, Or | And):
        kind = type(node)
        flat: set[Node] = set()
        for child in (normalize(c) for c in node.operands):
            if isinstance(child, kind):
                flat |= child.operands
            else:
                flat.add(child)
        if kind is Or:
            flat = _merge_title_abstract(flat)
        return next(iter(flat)) if len(flat) == 1 else kind(frozenset(flat))
    return node


def _merge_title_abstract(operands: set[Node]) -> set[Node]:
    leaves = {(n.text, n.field) for n in operands if isinstance(n, Leaf)}
    merged = set(operands)
    for text, field in leaves:
        if field == "ti" and (text, "ab") in leaves:
            merged -= {Leaf(text, "ti"), Leaf(text, "ab")}
            merged.add(Leaf(text, "tiab"))
    return merged


def equivalent(first: str, second: str, syntax: Syntax) -> bool:
    return normalize(parse(first, syntax)) == normalize(parse(second, syntax))
