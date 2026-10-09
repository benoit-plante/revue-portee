"""What the « Grille d'extraction » page shows: field types and changed attributes."""

from revue_portee.i18n import gettext as _

__all__ = ["changed_labels", "type_labels", "value_status_labels"]


def type_labels() -> dict[str, str]:
    return {
        "text": _("text"),
        "number": _("number"),
        "single_choice": _("single choice"),
        "multiple_choice": _("multiple choice"),
        "hierarchical": _("hierarchical category"),
        "boolean": _("yes or no"),
        "date": _("date"),
    }


def value_status_labels() -> dict[str, str]:
    return {
        "proposed": _("proposed by the AI, to check"),
        "validated": _("validated"),
        "corrected": _("corrected"),
        "rejected": _("rejected"),
    }


def changed_labels() -> dict[str, str]:
    return {
        "label": _("name"),
        "type": _("type"),
        "definition": _("definition"),
        "guidance": _("guidance"),
        "examples": _("examples"),
        "choices": _("choices"),
    }
