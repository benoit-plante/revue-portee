"""What the « Tri » pages show: the main screening, reconciliation and reassessment."""

from revue_portee.domain.changes import ChangeType
from revue_portee.i18n import gettext as _

__all__ = ["KEYS", "change_type_labels", "context_labels", "skip_list"]

# Keyboard shortcuts of the screening form (ENF-PER-02); digits toggle the criteria.
KEYS = {"include": "i", "exclude": "e", "uncertain": "d", "skip": "p"}


def change_type_labels() -> dict[str, str]:
    return {
        ChangeType.BROADENING.value: _("broadening"),
        ChangeType.NARROWING.value: _("narrowing"),
        ChangeType.CLARIFICATION.value: _("clarification"),
        ChangeType.ADDED.value: _("added criterion"),
        ChangeType.REMOVED.value: _("removed criterion"),
    }


def context_labels() -> dict[str, str]:
    return {
        "independent": _("independent"),
        "reconciliation": _("reconciliation"),
        "reassessment": _("reassessment"),
        "audit": _("audit"),
    }


def skip_list(text: str, *, limit: int = 50) -> list[str]:
    """References skipped for now (``passer`` in the address), at most ``limit``."""
    return [part for part in text.split(",") if part.isalnum()][:limit]
