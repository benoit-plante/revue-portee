"""Normalized forms of the fields compared by deduplication (EF-COL-06).

Pure functions. Titles lose markup, accents, case and punctuation; author names are
reduced to the first author's surname, whatever the format the database used
("Surname, Given", "Given Surname" or "Surname GK").
"""

import html
import re
import unicodedata

from revue_portee.domain.references import Reference

__all__ = [
    "PREPRINT_DOI_PREFIXES",
    "container_key",
    "first_page",
    "is_conference",
    "is_notice",
    "is_preprint",
    "is_thesis",
    "is_translated_title",
    "normalize_text",
    "surname",
    "title_tokens",
]

_TAGS = re.compile(r"<[^>]{1,40}>")
_NON_WORD = re.compile(r"[^a-z0-9]+")

# DOI prefixes of preprint servers: Research Square, bioRxiv and medRxiv, PsyArXiv,
# SocArXiv, OSF Preprints, SSRN, arXiv, Preprints.org, Authorea, EdArXiv, TechRxiv.
PREPRINT_DOI_PREFIXES = (
    "10.21203/",
    "10.1101/",
    "10.31234/",
    "10.31235/",
    "10.31219/",
    "10.2139/",
    "10.48550/",
    "10.20944/",
    "10.22541/",
    "10.35542/",
    "10.36227/",
)
_PREPRINT_VENUES = re.compile(r"rxiv|research square|ssrn|preprint", re.IGNORECASE)
_THESIS = re.compile(r"dissertation|\bthes[ei]s\b|\bthèses?\b", re.IGNORECASE)
_CONFERENCE = re.compile(r"conference|proceedings|congress|symposium|meeting", re.IGNORECASE)
# Titles of records that are about another publication, not the publication itself.
_NOTICE = re.compile(
    r"\b(correction|corrigendum|corrigenda|erratum|errata|retraction|retracted|"
    r"expression of concern|respond|response to|reply|comment on|commentary on|"
    r"letter to the editor|recommendation of|supplementa(?:l|ry) materials?)\b",
    re.IGNORECASE,
)


def normalize_text(value: str) -> str:
    """Lower case, without markup, accents or punctuation; words separated by a space."""
    text = _TAGS.sub(" ", html.unescape(value))
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(_NON_WORD.sub(" ", text).split())


def title_tokens(title: str) -> tuple[str, ...]:
    return tuple(normalize_text(title).split())


def is_translated_title(title: str) -> bool:
    """PubMed gives the English translation of a title in brackets."""
    text = title.strip().rstrip(".")
    return text.startswith("[") and text.endswith("]")


def is_notice(title: str) -> bool:
    """A correction, retraction, comment or reply: a record about another one."""
    return _NOTICE.search(title) is not None


def surname(author: str) -> str:
    """Normalized surname of an author name in any of the usual formats."""
    text = author.strip()
    if not text:
        return ""
    if "," in text:
        return normalize_text(text.split(",", 1)[0])
    words = normalize_text(text).split()
    if not words:
        return ""
    # "Chow KK" or "Smith J": the surname comes first, followed by initials.
    if len(words) > 1 and all(len(w) <= 3 and w.isalpha() for w in words[1:]):
        original = text.split()
        if all(w.isupper() or len(w) == 1 for w in original[1:]):
            return words[0]
    return words[-1]


def first_page(pages: str) -> str:
    text = pages.strip().lower()
    if not text:
        return ""
    return re.split(r"\s*[-\u2013\u2014]\s*", text, maxsplit=1)[0]


def container_key(container: str) -> str:
    """Journal name without the subtitles and places PubMed adds, and without "the"."""
    text = re.sub(r"\([^)]*\)", " ", container)  # "(London, England)", "(1982)"
    text = text.split(" : ", 1)[0].split(": ", 1)[0]
    words = normalize_text(text).split()
    if words and words[0] == "the":
        words = words[1:]
    return " ".join(words)


def is_preprint(value: Reference) -> bool:
    if value.doc_type.lower() in ("preprint", "posted-content"):
        return True
    if value.doi.lower().startswith(PREPRINT_DOI_PREFIXES):
        return True
    return _PREPRINT_VENUES.search(value.container_title) is not None


def is_thesis(value: Reference) -> bool:
    doc_type = value.doc_type.lower()
    return doc_type in ("thes", "dissertation") or _THESIS.search(value.container_title) is not None


def is_conference(value: Reference) -> bool:
    doc_type = value.doc_type.lower()
    if doc_type in ("conf", "cpaper", "abst", "proceedings-article"):
        return True
    return _CONFERENCE.search(value.container_title) is not None
