"""What the « Grille d'extraction » page shows: field types and changed attributes."""

from revue_portee.i18n import gettext as _

__all__ = ["change_kind_labels", "changed_labels", "type_labels", "value_status_labels"]


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
        "extracted": _("extracted by the person"),
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


def change_kind_labels() -> dict[str, str]:
    return {
        "added": _("field added: studies to complete"),
        "modified": _("field modified: values to review"),
        "removed": _("field removed: values archived"),
    }
