"""What the « Textes intégraux » page shows: statuses, origins and match kinds."""

from revue_portee.i18n import gettext as _

__all__ = ["JOB", "check_labels", "match_labels", "mode_labels", "origin_labels",
           "status_labels"]  # fmt: skip

# Key of the background job that looks for open access versions (one at a time).
JOB = "textes-libres"


def status_labels() -> dict[str, str]:
    return {
        "not_sought": _("not looked for yet"),
        "obtained": _("obtained"),
        "not_found": _("not found in open access"),
        "not_retrievable": _("not retrievable"),
    }


def origin_labels() -> dict[str, str]:
    return {
        "openalex": _("open access (OpenAlex)"),
        "unpaywall": _("open access (Unpaywall)"),
        "upload": _("added by the team"),
    }


def check_labels() -> dict[str, str]:
    """Result of the check of a quote of the AI in the text."""
    return {
        "at_page": _("found at this page"),
        "other_page": _("found, but on another page"),
        "not_found": _("not found in the text"),
    }


def mode_labels() -> dict[str, str]:
    return {"blind": _("blind double screening"), "assisted": _("assisted screening")}


def match_labels() -> dict[str, str]:
    return {
        "doi_in_filename": _("DOI in the file name"),
        "doi_in_text": _("DOI in the text"),
        "title": _("title"),
    }
