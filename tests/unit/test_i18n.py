"""Every user-facing message used in the code or templates has a French translation."""

from importlib.resources import files
from pathlib import Path

from babel.messages.catalog import Message
from babel.messages.extract import extract_from_dir
from babel.messages.pofile import read_po

from revue_portee.i18n import DEFAULT_LOCALE, french, gettext, ngettext

SOURCE = Path(__file__).resolve().parents[2] / "src"
KEYWORDS = {"_": None, "gettext": None, "ngettext": (1, 2), "french": None}
METHODS = [
    ("**.py", "python"),
    ("revue_portee/web/templates/**.html", "jinja2"),
]


def extracted_messages() -> set[str]:
    found: set[str] = set()
    for _filename, _lineno, message, _comments, _context in extract_from_dir(
        str(SOURCE), METHODS, keywords=KEYWORDS
    ):
        found.add(message if isinstance(message, str) else message[0])
    return found


def french_catalog() -> dict[str, Message]:
    path = files("revue_portee.i18n") / "locale" / "fr" / "LC_MESSAGES" / "messages.po"
    with path.open("rb") as source:
        catalog = read_po(source, locale="fr")
    return {
        (m.id if isinstance(m.id, str) else m.id[0]): m
        for m in catalog
        if m.id and "fuzzy" not in m.flags
    }


def translations_of(message: Message) -> tuple[str, ...]:
    string = message.string
    return tuple(string) if isinstance(string, (tuple, list)) else (str(string),)


def test_every_message_is_translated() -> None:
    catalog = french_catalog()
    messages = extracted_messages()
    assert len(messages) > 50
    missing = sorted(m for m in messages if m not in catalog)
    assert missing == [], "Run pybabel extract/update (see babel.cfg) and translate."
    untranslated = sorted(m for m in messages if not all(translations_of(catalog[m])))
    assert untranslated == []


def test_catalog_has_no_obsolete_message() -> None:
    assert sorted(set(french_catalog()) - extracted_messages()) == []


def test_french_typography_in_translations() -> None:
    for message in french_catalog().values():
        for text in translations_of(message):
            for mark in (":", ";", "?", "!"):
                assert f" {mark}" not in text, f"use a no-break space before {mark!r}: {text!r}"


def test_default_interface_is_french() -> None:
    assert DEFAULT_LOCALE == "fr"
    assert gettext("Criteria") == "Critères"
    assert french("Note added to the journal") == "Note ajoutée au journal"
    assert ngettext(
        "Journal intact: {count} entry, hash chain verified.",
        "Journal intact: {count} entries, hash chain verified.",
        2,
    ).startswith("Journal intègre : {count} entrées")


def english_catalog_file() -> dict[str, Message]:
    path = files("revue_portee.i18n") / "locale" / "en" / "LC_MESSAGES" / "messages.po"
    with path.open("rb") as source:
        catalog = read_po(source, locale="en")
    return {(m.id if isinstance(m.id, str) else m.id[0]): m for m in catalog if m.id}


def test_english_catalog_is_complete_and_up_to_date() -> None:
    """ENF-LAN-03, the acceptance criterion of tranche 4.5: 100 % of the strings have an
    English translation, the one ``revue_portee.i18n.english`` builds."""
    from revue_portee.i18n.english import english

    found = english_catalog_file()
    assert set(found) == set(french_catalog())
    for key, message in found.items():
        assert all(translations_of(message)), key
        ids = [message.id] if isinstance(message.id, str) else list(message.id)
        assert list(translations_of(message)) == [english(part) for part in ids], key
        for text in translations_of(message):
            assert "«" not in text, key  # English typography
            assert " " not in text, key


def test_english_interface() -> None:
    from revue_portee.i18n import current_locale, reset_locale, set_locale

    token = set_locale("en")
    try:
        assert current_locale() == "en"
        assert gettext("Add « scoping review » to the title.") == (
            "Add “scoping review” to the title."
        )
        plural = ngettext(
            "{count} reference kept, written: {path}", "{count} references kept, written: {path}", 2
        )
        assert plural.startswith("{count} references")
        assert french("Grid version {number} in force").startswith("Version {number}")
    finally:
        reset_locale(token)
    assert current_locale() == "fr"
    unknown = set_locale("de")  # an unknown language falls back to French
    try:
        assert current_locale() == "fr"
    finally:
        reset_locale(unknown)
