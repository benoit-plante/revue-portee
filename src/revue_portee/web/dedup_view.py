"""What the « Doublons » page shows of pairs and groups (tranche 1.5)."""

from collections.abc import Sequence
from dataclasses import dataclass

from revue_portee.collect.deduplication import DedupState
from revue_portee.dedup.groups import Group
from revue_portee.dedup.normalize import normalize_text
from revue_portee.domain.dedup import DedupSettings, DuplicatePair, PairDecision
from revue_portee.domain.references import Reference
from revue_portee.i18n import gettext as _

__all__ = [
    "GROUPS_PER_PAGE",
    "PAIRS_SHOWN",
    "GroupLink",
    "PairRow",
    "group_links",
    "pair_rows",
    "parse_threshold",
    "reason_labels",
    "rule_labels",
]

PAIRS_SHOWN = 25
GROUPS_PER_PAGE = 50


def rule_labels() -> dict[str, str]:
    return {
        "doi": _("same DOI"),
        "pmid": _("same PMID"),
        "openalex": _("same OpenAlex identifier"),
        "doi_title_differs": _("same DOI, but different titles"),
        "pmid_title_differs": _("same PMID, but different titles"),
        "openalex_title_differs": _("same OpenAlex identifier, but different titles"),
        "doi_other_identifiers_differ": _("same DOI, but other identifiers differ"),
        "pmid_other_identifiers_differ": _("same PMID, but other identifiers differ"),
        "openalex_other_identifiers_differ": _(
            "same OpenAlex identifier, but other identifiers differ"
        ),
        "similarity": _("similar fields"),
        "translated_title": _(
            "title translated by PubMed; same first author, year, journal and pages"
        ),
        "preprint": _("a preprint and another version of the work"),
        "thesis": _("a thesis and another version of the work"),
        "conference": _("a conference paper and another version of the work"),
        "co_publication": _("the same work published in two journals"),
    }


def reason_labels() -> dict[str, str]:
    """Why a pair was not grouped automatically."""
    return {
        "different_doi": _("different DOIs"),
        "different_pmid": _("different PMIDs"),
        "different_openalex_id": _("different OpenAlex identifiers"),
        "different_numbers": _("different numbers in the titles"),
        "title": _("titles less similar"),
        "first_author": _("different or missing first author"),
        "year": _("years more than one apart"),
        "first_page": _("different first pages in the same volume"),
    }


@dataclass(frozen=True, slots=True)
class PairRow:
    label: str
    a: str
    b: str
    differs: bool


def _authors(ref: Reference) -> str:
    shown = "; ".join(ref.authors[:6])
    return shown + (" …" if len(ref.authors) > 6 else "")


def pair_rows(a: Reference, b: Reference, sources: dict[str, str]) -> list[PairRow]:
    """The fields of two references side by side; ``differs`` once normalized."""
    fields = (
        (_("Title"), a.title, b.title),
        (_("Authors"), _authors(a), _authors(b)),
        (_("Year"), str(a.year or ""), str(b.year or "")),
        (_("Journal or book"), a.container_title, b.container_title),
        (_("Volume (issue)"), _volume(a), _volume(b)),
        (_("Pages"), a.pages, b.pages),
        (_("DOI"), a.doi, b.doi),
        (_("PMID"), a.pmid, b.pmid),
        (_("OpenAlex"), a.openalex_id, b.openalex_id),
        (_("Type"), a.doc_type, b.doc_type),
        (_("Source"), sources.get(a.id, ""), sources.get(b.id, "")),
    )
    return [
        PairRow(label, x, y, normalize_text(x) != normalize_text(y))
        for label, x, y in fields
        if x or y
    ]


def _volume(ref: Reference) -> str:
    if ref.issue:
        return f"{ref.volume} ({ref.issue})".strip()
    return ref.volume


@dataclass(frozen=True, slots=True)
class GroupLink:
    reference_a: str
    reference_b: str
    pair: DuplicatePair | None
    decision: PairDecision | None


def group_links(group: Group, state: DedupState) -> list[GroupLink]:
    """The links in force inside a group, with what made each one."""
    members = set(group.members)
    return [
        GroupLink(a, b, state.pairs.get((a, b)), state.decisions.get((a, b)))
        for a, b in sorted(state.links)
        if a in members and b in members
    ]


def parse_threshold(value: str, default: float) -> float:
    """A threshold typed with a decimal point or a comma; ValueError if unreadable."""
    text = value.strip().replace(",", ".")
    if not text:
        return default
    return float(text)


def default_settings(state: DedupState) -> DedupSettings:
    return state.run.settings if state.run is not None else DedupSettings()


def page_of(groups: Sequence[Group], page: int) -> tuple[list[Group], int]:
    """The groups of page ``page`` (1-based) and the number of pages."""
    pages = max(1, -(-len(groups) // GROUPS_PER_PAGE))
    page = min(max(1, page), pages)
    start = (page - 1) * GROUPS_PER_PAGE
    return list(groups[start : start + GROUPS_PER_PAGE]), pages
