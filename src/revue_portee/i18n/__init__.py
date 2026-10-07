"""User-facing strings, externalized with Babel (ENF-LAN-03).

Message identifiers are written in English in the code and templates; the French
catalog (``locale/fr/LC_MESSAGES/messages.po``) provides the interface text. V1 ships
French only, which is the default locale. Journal summaries (``summary_fr``) always
use the French catalog through :func:`french`, whatever the interface locale.
"""

import io
from functools import cache
from importlib.resources import files

from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po
from babel.support import Translations

__all__ = ["DEFAULT_LOCALE", "DOMAIN", "french", "gettext", "ngettext", "translations"]

DOMAIN = "messages"
DEFAULT_LOCALE = "fr"


@cache
def translations(locale: str = DEFAULT_LOCALE) -> Translations:
    """Translations for ``locale``, compiled in memory from the ``.po`` catalog."""
    catalog_file = files("revue_portee.i18n") / "locale" / locale / "LC_MESSAGES" / f"{DOMAIN}.po"
    with catalog_file.open("rb") as source:
        catalog = read_po(source, locale=locale, domain=DOMAIN)
    compiled = io.BytesIO()
    write_mo(compiled, catalog, use_fuzzy=False)
    compiled.seek(0)
    return Translations(fp=compiled, domain=DOMAIN)


def gettext(message: str) -> str:
    """Translate ``message`` into the interface language."""
    return translations().gettext(message)


def ngettext(singular: str, plural: str, count: int) -> str:
    return translations().ngettext(singular, plural, count)


def french(message: str) -> str:
    """Translate ``message`` into French (journal summaries, publication exports)."""
    return translations("fr").gettext(message)
