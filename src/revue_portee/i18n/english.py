"""The English catalog of the interface (ENF-LAN-03, tranche 4.5).

Message identifiers are written in English, so the English text is the identifier with
English typography: « quoted » becomes “quoted”. The catalog is rebuilt from the
identifiers of the French catalog, which tests keep complete; run after updating the
French catalog::

    uv run python -m revue_portee.i18n.english
"""

import re
from pathlib import Path

from babel.messages.catalog import Catalog
from babel.messages.pofile import read_po, write_po

__all__ = ["CATALOGS", "english", "english_catalog", "main"]

CATALOGS = Path(__file__).parent / "locale"
_FRENCH_QUOTES = re.compile("«[\\s  ]*(.*?)[\\s  ]*»", re.DOTALL)


def english(text: str) -> str:
    """``text`` with English quotation marks instead of French guillemets."""
    return _FRENCH_QUOTES.sub("“\\1”", text)


def english_catalog(french: Catalog) -> Catalog:
    """The English catalog of the identifiers of ``french``."""
    catalog = Catalog(locale="en", domain=french.domain, project="revue-portee",
                      fuzzy=False)  # fmt: skip
    for message in french:
        if not message.id:
            continue
        if isinstance(message.id, tuple | list):
            text: str | tuple[str, ...] = tuple(english(part) for part in message.id)
        else:
            text = english(message.id)
        catalog.add(message.id, text, context=message.context)
    return catalog


def main() -> None:  # pragma: no cover - a maintenance command
    with (CATALOGS / "fr" / "LC_MESSAGES" / "messages.po").open("rb") as source:
        french = read_po(source, locale="fr")
    target = CATALOGS / "en" / "LC_MESSAGES" / "messages.po"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as output:
        write_po(output, english_catalog(french), width=100, sort_output=True,
                 no_location=True, omit_header=False)  # fmt: skip


if __name__ == "__main__":  # pragma: no cover
    main()
