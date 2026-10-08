"""Candidate duplicate pairs, in two stages (EF-COL-06).

1. **Identifiers**: references sharing a normalized DOI, a PMID or an OpenAlex
   identifier are duplicates, unless their titles or their other identifiers disagree
   (then a person decides).
2. **Approximate matching**: references sharing a blocking key (beginning of the
   title, first author and year and first page, journal and volume and first page) are
   compared field by field; the weighted similarity is the pair's score. Pairs at or
   above ``auto_from`` are duplicates, pairs between ``review_from`` and ``auto_from``
   go to a person, others are left apart.

Some pairs are never grouped automatically, whatever their score: different DOIs or
PMIDs, a title that only PubMed's translation gives, different numbers in the
titles, different years or first pages, no first author to compare. Two versions of
one work (a preprint and the article, a thesis or a conference paper and the article,
an article published twice) are a pair of kind ``version``, always left to a person.
A correction, a retraction or a comment is never paired with the record it concerns.

Pure functions: the same references and thresholds always give the same pairs
(ENF-REP-01).
"""

import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from itertools import combinations

from rapidfuzz import fuzz

from revue_portee.dedup.normalize import (
    container_key,
    first_page,
    is_conference,
    is_notice,
    is_preprint,
    is_thesis,
    is_translated_title,
    normalize_text,
    surname,
)
from revue_portee.domain.dedup import (
    ALGORITHM_VERSION,
    DedupSettings,
    PairKind,
    Proposal,
)
from revue_portee.domain.references import Reference

__all__ = ["ALGORITHM_VERSION", "Candidate", "find_candidates", "title_similarity"]

# Weights of the compared fields; a field unknown on either side is left out.
WEIGHTS = {"title": 0.55, "author": 0.15, "year": 0.10, "venue": 0.10, "place": 0.10}
# Keys shared by more references than this are too common to pair everything in them.
MAX_BLOCK = 400
_NUMBER = re.compile(r"\d+")
_ROMAN = re.compile(r"\b(?:i{1,3}|iv|v|vi{1,3}|ix|x)\b")


@dataclass(frozen=True, slots=True)
class Candidate:
    """A pair of references, ``reference_a`` < ``reference_b``, with why it was made."""

    reference_a: str
    reference_b: str
    kind: PairKind
    rule: str
    score: float
    proposal: Proposal
    details: dict[str, float | str | None] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _Prepared:
    ref: Reference
    title: str
    tokens: tuple[str, ...]
    translated: bool
    notice: bool
    author: str
    coauthors: frozenset[str]
    page: str
    volume: str
    venue: str
    preprint: bool
    thesis: bool
    conference: bool


def _prepare(ref: Reference) -> _Prepared:
    title = normalize_text(ref.title)
    return _Prepared(
        ref=ref,
        title=title,
        tokens=tuple(title.split()),
        translated=is_translated_title(ref.title),
        notice=is_notice(ref.title),
        author=surname(ref.authors[0]) if ref.authors else "",
        coauthors=frozenset(surname(a) for a in ref.authors[:3]) - {""},
        page=first_page(ref.pages),
        volume=normalize_text(ref.volume),
        venue=container_key(ref.container_title),
        preprint=is_preprint(ref),
        thesis=is_thesis(ref),
        conference=is_conference(ref),
    )


def title_similarity(a: Sequence[str], b: Sequence[str]) -> float:
    """Similarity of two normalized titles (token tuples), 0 to 1.

    A title that is the beginning of the other (a truncated title, a subtitle left out)
    counts as 0.95."""
    score = fuzz.ratio(" ".join(a), " ".join(b)) / 100
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) >= 3 and tuple(long[: len(short)]) == tuple(short):
        score = max(score, 0.95)
    return score


def _numbers(tokens: Sequence[str]) -> set[str]:
    text = " ".join(tokens)
    return set(_NUMBER.findall(text)) | set(_ROMAN.findall(text))


def _blocking_keys(p: _Prepared) -> set[str]:
    keys = set()
    if len(p.tokens) >= 2 and not p.translated:
        keys.add("t:" + " ".join(p.tokens[:4]))
        keys.add("s:" + " ".join(sorted(sorted(p.tokens, key=lambda t: (-len(t), t))[:3])))
        if len(p.tokens) >= 6:
            keys.add("e:" + " ".join(p.tokens[-4:]))
    if p.author and p.ref.year is not None and p.page:
        keys.add(f"a:{p.author}|{p.ref.year}|{p.page}")
    if p.venue and p.volume and p.page:
        keys.add(f"v:{' '.join(p.venue.split()[:3])}|{p.volume}|{p.page}")
    return keys


def _ordered(a: _Prepared, b: _Prepared) -> tuple[_Prepared, _Prepared]:
    return (a, b) if a.ref.id < b.ref.id else (b, a)


def _features(a: _Prepared, b: _Prepared) -> dict[str, float | None]:
    title = None if a.translated or b.translated else title_similarity(a.tokens, b.tokens)
    author: float | None = None
    if a.author and b.author:
        if a.author == b.author:
            author = 1.0
        elif (
            fuzz.ratio(a.author, b.author) >= 85
            or a.author in b.coauthors
            or b.author in a.coauthors
        ):
            author = 0.5  # a spelling variant, or the authors in another order
        else:
            author = 0.0
    year: float | None = None
    if a.ref.year is not None and b.ref.year is not None:
        gap = abs(a.ref.year - b.ref.year)
        year = 1.0 if gap == 0 else (0.5 if gap == 1 else 0.0)
    venue = None
    if a.venue and b.venue:
        venue = fuzz.token_set_ratio(a.venue, b.venue) / 100
    agreements = [x == y for x, y in ((a.volume, b.volume), (a.page, b.page)) if x and y]
    place = None if not agreements else sum(agreements) / len(agreements)
    return {"title": title, "author": author, "year": year, "venue": venue, "place": place}


def _score(features: dict[str, float | None]) -> float:
    known = {k: v for k, v in features.items() if v is not None}
    total = sum(WEIGHTS[k] for k in known)
    return 0.0 if total == 0 else round(sum(WEIGHTS[k] * v for k, v in known.items()) / total, 4)


def _version(a: _Prepared, b: _Prepared) -> str:
    """Why two records may be two versions of one work, or ""."""
    if a.preprint != b.preprint:
        return "preprint"
    if a.thesis != b.thesis:
        return "thesis"
    if a.conference != b.conference:
        return "conference"
    return ""


def _identifier_rule(a: Reference, b: Reference) -> str:
    if a.doi and a.doi == b.doi:
        return "doi"
    if a.pmid and a.pmid == b.pmid:
        return "pmid"
    if a.openalex_id and a.openalex_id == b.openalex_id:
        return "openalex"
    return ""


def _conflicts(a: Reference, b: Reference) -> list[str]:
    found = []
    if a.doi and b.doi and a.doi != b.doi:
        found.append("different_doi")
    if a.pmid and b.pmid and a.pmid != b.pmid:
        found.append("different_pmid")
    if a.openalex_id and b.openalex_id and a.openalex_id != b.openalex_id:
        found.append("different_openalex_id")
    return found


def _identifier_candidate(a: _Prepared, b: _Prepared, rule: str) -> Candidate:
    features = _features(a, b)
    title = features["title"]
    details: dict[str, float | str | None] = {**features, "identifier": rule}
    conflicts = _conflicts(a.ref, b.ref)
    if conflicts:  # e.g. the same PMID, but two DOIs
        details["not_automatic"] = ", ".join(conflicts)
        return Candidate(
            a.ref.id,
            b.ref.id,
            PairKind.IDENTIFIER,
            f"{rule}_other_identifiers_differ",
            _score(features),
            Proposal.REVIEW,
            details,
        )
    agree = title is None or title >= 0.6 or _contained(a.tokens, b.tokens)
    if agree and a.notice == b.notice:
        return Candidate(
            a.ref.id, b.ref.id, PairKind.IDENTIFIER, rule, 1.0, Proposal.DUPLICATE, details
        )
    return Candidate(
        a.ref.id,
        b.ref.id,
        PairKind.IDENTIFIER,
        f"{rule}_title_differs",
        _score(features),
        Proposal.REVIEW,
        details,
    )


def _contained(a: Sequence[str], b: Sequence[str]) -> bool:
    """One title is entirely made of words of the other (a title cut by a database)."""
    short, long = (set(a), set(b)) if len(a) <= len(b) else (set(b), set(a))
    return len(short) >= 2 and short <= long


def _fuzzy_candidate(a: _Prepared, b: _Prepared, settings: DedupSettings) -> Candidate | None:
    if a.notice != b.notice:
        return None
    features = _features(a, b)
    score = _score(features)
    details: dict[str, float | str | None] = dict(features)
    title, author = features["title"], features["author"]
    same_work = (title is not None and title >= 0.9) and (author or 0) >= 0.5
    version = _version(a, b)
    conflicts = _conflicts(a.ref, b.ref)
    if version and (same_work or score >= settings.review_from):
        details["version"] = version
        return Candidate(
            a.ref.id, b.ref.id, PairKind.VERSION, version, score, Proposal.REVIEW, details
        )
    if (
        "different_doi" in conflicts
        and same_work
        and author == 1.0
        and (features["venue"] or 0) < 0.8
    ):
        details["version"] = "co_publication"
        return Candidate(
            a.ref.id, b.ref.id, PairKind.VERSION, "co_publication", score, Proposal.REVIEW, details
        )
    if title is None:  # only a translation of the title: the rest must agree fully
        complete = author == 1.0 and features["year"] == 1.0 and features["place"] == 1.0
        if complete and (features["venue"] or 0) >= 0.8:
            return Candidate(
                a.ref.id,
                b.ref.id,
                PairKind.FUZZY,
                "translated_title",
                score,
                Proposal.REVIEW,
                details,
            )
        return None
    if score < settings.review_from:
        return None
    reasons = list(conflicts)
    if _numbers(a.tokens) != _numbers(b.tokens):
        reasons.append("different_numbers")
    if title < 0.9:
        reasons.append("title")
    if author != 1.0:
        reasons.append("first_author")
    if features["year"] == 0.0:
        reasons.append("year")
    if a.volume and b.volume and a.volume == b.volume and a.page and b.page and a.page != b.page:
        reasons.append("first_page")
    if reasons:
        details["not_automatic"] = ", ".join(reasons)
    automatic = score >= settings.auto_from and not reasons
    return Candidate(
        a.ref.id,
        b.ref.id,
        PairKind.FUZZY,
        "similarity",
        score,
        Proposal.DUPLICATE if automatic else Proposal.REVIEW,
        details,
    )


def _identifier_groups(prepared: Sequence[_Prepared]) -> Iterable[tuple[_Prepared, _Prepared]]:
    for name in ("doi", "pmid", "openalex_id"):
        by: dict[str, list[_Prepared]] = defaultdict(list)
        for p in prepared:
            value = getattr(p.ref, name)
            if value:
                by[value].append(p)
        for members in by.values():
            yield from combinations(members, 2)


def find_candidates(references: Sequence[Reference], settings: DedupSettings) -> list[Candidate]:
    """Every candidate pair of ``references``, ordered by reference identifiers."""
    prepared = [_prepare(r) for r in sorted(references, key=lambda r: r.id)]
    found: dict[tuple[str, str], Candidate] = {}
    for x, y in _identifier_groups(prepared):
        a, b = _ordered(x, y)
        key = (a.ref.id, b.ref.id)
        if key not in found:
            found[key] = _identifier_candidate(a, b, _identifier_rule(a.ref, b.ref))
    blocks: dict[str, list[_Prepared]] = defaultdict(list)
    for p in prepared:
        for block_key in _blocking_keys(p):
            blocks[block_key].append(p)
    compared: set[tuple[str, str]] = set(found)
    for members in blocks.values():
        if len(members) < 2 or len(members) > MAX_BLOCK:
            continue
        for x, y in combinations(members, 2):
            a, b = _ordered(x, y)
            key = (a.ref.id, b.ref.id)
            if key in compared:
                continue
            compared.add(key)
            candidate = _fuzzy_candidate(a, b, settings)
            if candidate is not None:
                found[key] = candidate
    return [found[key] for key in sorted(found)]
