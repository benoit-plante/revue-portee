"""What the « Consultation » page shows: targets of comments and responses."""

from revue_portee.i18n import gettext as _

__all__ = ["action_labels", "target_labels"]


def target_labels() -> dict[str, str]:
    return {
        "protocol": _("protocol"),
        "criteria": _("eligibility criteria"),
        "search": _("search strategy"),
        "grid": _("extraction grid"),
        "results": _("results, tables and maps"),
        "narrative": _("narrative synthesis"),
        "lay_summary": _("plain-language summary"),
        "other": _("other"),
    }


def action_labels() -> dict[str, str]:
    return {
        "changed": _("the review was changed"),
        "noted": _("taken into account without a change"),
        "declined": _("not followed"),
        "deferred": _("left for later"),
    }
