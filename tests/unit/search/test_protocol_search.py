"""The protocol reports the search strategy (sections and Appendix II, EF-CAD-06)."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from revue_portee.domain.search import (
    BlockRole,
    ConceptBlock,
    Database,
    KeyArticle,
    Limits,
    SearchStrategy,
    parse_term,
)
from revue_portee.protocol.document import protocol_document
from revue_portee.reporting.document import Code, render_docx, render_markdown
from revue_portee.search import runs, strategies
from revue_portee.sources import SourceAnswer
from support import TOOL_VERSION, make_clock, new_project


class Counter:
    database = Database.PUBMED

    def count(self, query: str) -> SourceAnswer:
        return SourceAnswer(count=12345, ids=(), raw={})

    def among(self, query: str, ids: Sequence[str]) -> SourceAnswer:  # pragma: no cover
        return SourceAnswer(count=0, ids=(), raw={})

    def resolve(self, article: KeyArticle) -> tuple[str | None, dict[str, Any]]:  # pragma: no cover
        return None, {}


STRATEGY = SearchStrategy(
    blocks=(
        ConceptBlock(code="B1", label="Parents", terms=(parse_term("parent*"),)),
        ConceptBlock(code="B2", label="Revues", terms=(parse_term('"scoping review"'),)),
        ConceptBlock(
            code="B3", label="Animaux", role=BlockRole.EXCLUDE, terms=(parse_term("rat*"),)
        ),
    ),
    limits=Limits(year_from=2015, year_to=2025, languages=("en", "fr")),
)


def test_search_sections_and_appendix(tmp_path: Path) -> None:
    clock = make_clock()
    folder = new_project(tmp_path, clock)
    try:
        empty = render_markdown(
            protocol_document(folder, language="fr", now=clock, tool_version=TOOL_VERSION)
        )
        assert "À compléter : stratégie de recherche complète" in empty.replace(" ", " ")
        strategies.save_strategy(folder, STRATEGY, now=clock, tool_version=TOOL_VERSION)
        runs.count_results(
            folder,
            Database.PUBMED,
            now=clock,
            tool_version=TOOL_VERSION,
            factory=lambda _: Counter(),
        )
        french = protocol_document(folder, language="fr", now=clock, tool_version=TOOL_VERSION)
        text = render_markdown(french).replace(" ", " ")
        assert "repose sur 3 blocs de concepts" in text
        assert "par AND (Parents, Revues)" in text
        assert "retirées par NOT : Animaux." in text
        assert (
            "Limites : années de publication de 2015 à 2025 ; langues : anglais, français." in text
        )
        assert "- PubMed (2026-" in text
        assert ") : 12 345" in text  # thousands separated by a non-breaking space
        assert "```\n(parent*[tiab]) AND" in text
        codes = [b.text for b in french.blocks if isinstance(b, Code)]
        assert len(codes) == 3  # PubMed, OpenAlex, PsycINFO
        english = render_markdown(
            protocol_document(folder, language="en", now=clock, tool_version=TOOL_VERSION)
        )
        assert "built from 3 concept blocks" in english
        assert "PubMed (2026-" in english
        assert ": 12,345" in english
        assert render_docx(french)[:2] == b"PK"
    finally:
        folder.close()
