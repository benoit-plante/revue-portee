"""User-facing strings, externalized with Babel (ENF-LAN-03).

Message identifiers are written in English in the code and templates. The French
catalog (``locale/fr/LC_MESSAGES/messages.po``) gives the French interface, the default;
the English catalog (``locale/en/...``, tranche 4.5) gives the English interface, the
identifiers with English typography (“quotation marks”), kept complete by
:mod:`revue_portee.i18n.english`. The interface language is set for each request
(:func:`set_locale`); journal summaries (``summary_fr``) always use the French catalog
through :func:`french`, whatever the interface language.
"""

import io
from collections.abc import Callable
from contextvars import ContextVar, Token
from functools import cache
from importlib.resources import files

from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po
from babel.support import Translations

__all__ = [
    "DEFAULT_LOCALE",
    "DOMAIN",
    "EXPORT_LANGUAGES",
    "INTERFACE_LOCALES",
    "current_locale",
    "french",
    "gettext",
    "ngettext",
    "reset_locale",
    "set_locale",
    "translations",
    "translator",
]

DOMAIN = "messages"
DEFAULT_LOCALE = "fr"
# Languages of the interface (ENF-LAN-03) and of the publication exports (ENF-LAN-04).
INTERFACE_LOCALES = ("fr", "en")
EXPORT_LANGUAGES = ("fr", "en")

_locale: ContextVar[str] = ContextVar("revue_portee_locale", default=DEFAULT_LOCALE)


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


def current_locale() -> str:
    """The language of the interface for the current request (French by default)."""
    return _locale.get()


def set_locale(locale: str) -> Token[str]:
    """Use ``locale`` for the interface until :func:`reset_locale`; an unknown locale
    falls back to the default."""
    return _locale.set(locale if locale in INTERFACE_LOCALES else DEFAULT_LOCALE)


def reset_locale(token: Token[str]) -> None:
    _locale.reset(token)


def gettext(message: str) -> str:
    """Translate ``message`` into the interface language."""
    return translations(current_locale()).gettext(message)


def ngettext(singular: str, plural: str, count: int) -> str:
    return translations(current_locale()).ngettext(singular, plural, count)


def french(message: str) -> str:
    """Translate ``message`` into French (journal summaries, publication exports)."""
    return translations("fr").gettext(message)


def translator(language: str) -> Callable[[str], str]:
    """Translation function for a publication export in ``language`` (fr or en)."""
    if language not in EXPORT_LANGUAGES:
        raise ValueError(f"unsupported export language: {language}")
    return translations(language).gettext
