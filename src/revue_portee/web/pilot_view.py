"""What the « Pilote » pages show of rounds, decisions and the calibration table."""

from decimal import ROUND_UP, Decimal

from revue_portee.ai.base import CostEstimate
from revue_portee.i18n import current_locale
from revue_portee.i18n import gettext as _

__all__ = [
    "assessment_labels",
    "batch_ceiling",
    "parse_amount",
    "parse_probability",
    "percent",
    "stopped_labels",
    "value_labels",
]


def value_labels() -> dict[str, str]:
    return {"include": _("Include"), "exclude": _("Exclude"), "uncertain": _("Uncertain")}


def assessment_labels() -> dict[str, str]:
    return {"met": _("met"), "not_met": _("not met"), "cannot_tell": _("cannot tell")}


def stopped_labels() -> dict[str, str]:
    return {
        "project_budget": _("the budget of the project is reached"),
        "batch_budget": _("the ceiling of the batch is reached"),
    }


def percent(value: float | None) -> str:
    """A percentage in the notation of the interface, or a dash without a value."""
    if value is None:
        return "—"
    text = f"{value * 100:.1f}"
    if current_locale() == "fr":
        return text.replace(".", ",") + " %"
    return text + "%"


def parse_amount(text: str) -> Decimal:
    """An amount typed with a point or a comma; ValueError if not a positive number."""
    try:
        amount = Decimal(text.strip().replace(",", ".").replace(" ", "").replace(" ", ""))
    except ArithmeticError as error:
        raise ValueError(text) from error
    if not amount.is_finite() or amount <= 0:
        raise ValueError(text)
    return amount


def parse_probability(text: str) -> float:
    value = float(text.strip().replace(",", "."))
    if not 0 <= value <= 1:
        raise ValueError(text)
    return value


def batch_ceiling(estimate: CostEstimate) -> Decimal:
    """Ceiling proposed for a batch: the estimate plus a quarter, rounded up to the cent
    (the estimate is already the most expensive case), at least one cent."""
    proposed = (estimate.amount * Decimal("1.25")).quantize(Decimal("0.01"), ROUND_UP)
    return max(Decimal("0.01"), proposed)
