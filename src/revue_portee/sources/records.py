"""Records as a database API gives them, before they become references (EF-COL-01)."""

from dataclasses import dataclass, field
from typing import Any

__all__ = ["FetchedPage", "FetchedRecord", "abstract_from_inverted_index"]


@dataclass(frozen=True, slots=True)
class FetchedRecord:
    """One record: its identifier in the source and its normalized fields (the
    fields of :class:`revue_portee.domain.references.Reference`)."""

    original_id: str
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FetchedPage:
    records: tuple[FetchedRecord, ...]
    announced: int  # records the API announces for the whole query
    next_cursor: str | None  # None after the last page
    raw: Any  # the answer as received (JSON document or XML text)


def abstract_from_inverted_index(index: dict[str, list[int]] | None) -> str:
    """OpenAlex gives abstracts as {word: [positions]}; rebuild the text."""
    if not index:
        return ""
    words: dict[int, str] = {}
    for word, positions in index.items():
        for position in positions:
            words[position] = word
    return " ".join(words[i] for i in sorted(words))
