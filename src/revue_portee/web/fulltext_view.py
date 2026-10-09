"""What the « Textes intégraux » page shows: statuses, origins and match kinds."""

from revue_portee.i18n import gettext as _

__all__ = ["JOB", "match_labels", "origin_labels", "status_labels"]

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


def match_labels() -> dict[str, str]:
    return {
        "doi_in_filename": _("DOI in the file name"),
        "doi_in_text": _("DOI in the text"),
        "title": _("title"),
    }
