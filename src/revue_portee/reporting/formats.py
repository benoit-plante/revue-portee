"""Notation of numbers, dates and lists in publication exports (French or English)."""

from datetime import datetime
from decimal import Decimal

__all__ = ["date", "fixed", "integer", "number", "percent", "separator"]


def date(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d")


def number(value: Decimal, language: str) -> str:
    """Decimal in the notation of the export language (0,95 in French)."""
    text = str(value)
    return text.replace(".", ",") if language == "fr" else text


def integer(value: int, language: str) -> str:
    """Integer with thousands separated (1 234 in French, 1,234 in English)."""
    text = f"{value:,}"
    return text.replace(",", " ") if language == "fr" else text


def separator(language: str) -> str:
    """Separator of list items, with the French non-breaking space before « ; »."""
    return " ; " if language == "fr" else "; "


def fixed(value: float, places: int, language: str) -> str:
    """Number rounded to ``places`` decimals (0,82 in French)."""
    return number(Decimal(f"{value:.{places}f}"), language)


def percent(value: float, language: str) -> str:
    """Proportion as a percentage with one decimal (97,4 % in French, 97.4% in English)."""
    text = fixed(100 * value, 1, language)
    return f"{text} %" if language == "fr" else f"{text}%"
