"""Reports of a same study: candidate pairs by rules (EF-SEL-17, tranche 2.3).

Two included reports are proposed as reports of one study when:

- they cite the same trial registration number (ClinicalTrials.gov, ISRCTN, ANZCTR,
  ChiCTR, DRKS, Netherlands Trial Register, UMIN, IRCT, CTRI, PACTR, EudraCT); two
  reports citing only different numbers are never proposed;
- or they share at least ``min_shared_authors`` author surnames and a few words of their
  titles and abstracts (``min_text_overlap``), or one surname and many words
  (``single_author_overlap``);
- or their titles are close (``min_title_similarity``).

The default settings were chosen on a development set (PubMed records of psychotherapy
trials, 2015 to 2019, labelled by their ClinicalTrials.gov number): recall of the true
pairs 0.969 (docs/resultats/). They are tested once on a held-out set.

The rules are generous on purpose: they propose, the AI examines each pair in the texts
and a person decides (``screening.studies``). A study is a group of reports joined by
the links in force; nothing is deleted. Pure functions.
"""

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import combinations

from pydantic import BaseModel, ConfigDict, Field

from revue_portee.dedup.matching import title_similarity
from revue_portee.dedup.normalize import normalize_text, surname, title_tokens
from revue_portee.domain.references import Reference

__all__ = [
    "LinkRule",
    "PairEvaluation",
    "ReportCandidate",
    "ReportFeatures",
    "ReportLinkSettings",
    "candidate_pairs",
    "evaluate_pairs",
    "features",
    "group_reports",
    "registrations",
]

_REGISTRIES = (
    ("NCT", re.compile(r"\bNCT\s?(0\d{7})\b", re.IGNORECASE)),
    ("ISRCTN", re.compile(r"\bISRCTN\s?(\d{8})\b", re.IGNORECASE)),
    ("ACTRN", re.compile(r"\bACTRN\s?(\d{14})\b", re.IGNORECASE)),
    ("ChiCTR", re.compile(r"\bChiCTR[-\s]?((?:[A-Z]{2,4}-)?\d{6,12})\b", re.IGNORECASE)),
    ("DRKS", re.compile(r"\bDRKS\s?(\d{8})\b", re.IGNORECASE)),
    ("NTR", re.compile(r"\bNTR\s?(\d{3,5})\b", re.IGNORECASE)),
    ("UMIN", re.compile(r"\bUMIN\s?(\d{9})\b", re.IGNORECASE)),
    ("IRCT", re.compile(r"\bIRCT\s?(\d{6,14}N\d{1,3})\b", re.IGNORECASE)),
    ("CTRI", re.compile(r"\bCTRI/(\d{4}/\d{2,3}/\d{6})\b", re.IGNORECASE)),
    ("PACTR", re.compile(r"\bPACTR\s?(\d{15,16})\b", re.IGNORECASE)),
    ("EudraCT", re.compile(r"\bEudraCT[^0-9]{0,20}(\d{4}-\d{6}-\d{2})\b", re.IGNORECASE)),
)
# Words too common in reports to tell two studies apart.
_COMMON_WORDS = (
    "a an and are as at be by for from in is of on or the to with was were this that these "
    "study trial randomised randomized controlled results patients participants effect "
    "effects between versus vs using among after during their who than which group groups "
    "treatment intervention outcome outcomes analysis method methods background conclusion "
    "conclusions objective objectives aim aims design setting"
)
_COMMON = frozenset(_COMMON_WORDS.split())


def registrations(text: str) -> frozenset[str]:
    """Trial registration numbers written in ``text``, normalized (``NCT01234567``)."""
    found = set()
    for name, pattern in _REGISTRIES:
        for match in pattern.finditer(text):
            found.add(name + match.group(1).upper().replace(" ", ""))
    return frozenset(found)


class ReportLinkSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    min_shared_authors: int = Field(default=2, ge=1)
    min_text_overlap: float = Field(default=0.03, ge=0, le=1)  # Jaccard of the words
    single_author_overlap: float = Field(default=0.12, ge=0, le=1)  # with one author only
    min_title_similarity: float = Field(default=0.85, ge=0, le=1)


@dataclass(frozen=True, slots=True)
class ReportFeatures:
    reference_id: str
    surnames: frozenset[str]
    words: frozenset[str]  # distinctive words of the title and abstract
    title: tuple[str, ...]
    registrations: frozenset[str]


def features(reference: Reference, text: str = "") -> ReportFeatures:
    """What the rules compare of a report; ``text`` is its full text when there is one
    (registration numbers are often only in it)."""
    words = normalize_text(f"{reference.title} {reference.abstract}").split()
    return ReportFeatures(
        reference_id=reference.id,
        # The last word of the surname: "van den Bosch" and "Bosch" are the same author.
        surnames=frozenset(s.split()[-1] for s in (surname(a) for a in reference.authors) if s),
        words=frozenset(w for w in words if len(w) > 2 and w not in _COMMON),
        title=title_tokens(reference.title),
        registrations=registrations(f"{reference.title}\n{reference.abstract}\n{text}"),
    )


class LinkRule:
    REGISTRATION = "registration"
    AUTHORS = "authors"
    TITLE = "title"


class ReportCandidate(BaseModel):
    """A pair of reports proposed as reports of one study, with the rule and the
    elements shared (for the person and the AI)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reference_a_id: str
    reference_b_id: str
    rule: str
    shared_registrations: tuple[str, ...] = ()
    shared_authors: tuple[str, ...] = ()
    text_overlap: float = 0.0
    title_similarity: float = 0.0


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a or b else 0.0


def _candidate(
    a: ReportFeatures, b: ReportFeatures, settings: ReportLinkSettings
) -> ReportCandidate | None:
    shared_registrations = sorted(a.registrations & b.registrations)
    if a.registrations and b.registrations and not shared_registrations:
        return None  # two different trials
    shared_authors = tuple(sorted(a.surnames & b.surnames))
    overlap = round(_jaccard(a.words, b.words), 3)
    similarity = round(title_similarity(a.title, b.title), 3) if a.title and b.title else 0.0
    if shared_registrations:
        rule = LinkRule.REGISTRATION
    elif (
        len(shared_authors) >= settings.min_shared_authors and overlap >= settings.min_text_overlap
    ) or (shared_authors and overlap >= settings.single_author_overlap):
        rule = LinkRule.AUTHORS
    elif similarity >= settings.min_title_similarity:
        rule = LinkRule.TITLE
    else:
        return None
    first, second = sorted((a.reference_id, b.reference_id))
    return ReportCandidate(
        reference_a_id=first,
        reference_b_id=second,
        rule=rule,
        shared_registrations=tuple(shared_registrations),
        shared_authors=shared_authors,
        text_overlap=overlap,
        title_similarity=similarity,
    )


def candidate_pairs(
    reports: Sequence[ReportFeatures], settings: ReportLinkSettings | None = None
) -> list[ReportCandidate]:
    """Every pair of reports the rules propose, sorted by identifiers."""
    chosen = settings or ReportLinkSettings()
    found = [
        candidate
        for a, b in combinations(reports, 2)
        if (candidate := _candidate(a, b, chosen)) is not None
    ]
    return sorted(found, key=lambda c: (c.reference_a_id, c.reference_b_id))


def group_reports(
    reference_ids: Iterable[str], links: Iterable[tuple[str, str]]
) -> list[list[str]]:
    """Studies: the reports joined by ``links``, each group sorted, groups sorted by
    their first report; a report without a link is a study of its own."""
    parent = {ref: ref for ref in reference_ids}

    def root(ref: str) -> str:
        while parent[ref] != ref:
            parent[ref] = parent[parent[ref]]
            ref = parent[ref]
        return ref

    for a, b in links:
        if a in parent and b in parent:
            ra, rb = root(a), root(b)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
    groups: dict[str, list[str]] = defaultdict(list)
    for ref in parent:
        groups[root(ref)].append(ref)
    return sorted((sorted(g) for g in groups.values()), key=lambda g: g[0])


@dataclass(frozen=True, slots=True)
class PairEvaluation:
    """Pairs proposed against the pairs of a reference standard (reports grouped by
    study)."""

    true_pairs: int
    proposed: int
    found: int  # true pairs proposed
    missed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def recall(self) -> float | None:
        return self.found / self.true_pairs if self.true_pairs else None

    @property
    def precision(self) -> float | None:
        return self.found / self.proposed if self.proposed else None


def evaluate_pairs(
    proposed: Iterable[tuple[str, str]], study_of: Mapping[str, str]
) -> PairEvaluation:
    """Recall and precision of ``proposed`` pairs against ``study_of`` (report: study)."""
    by_study: dict[str, list[str]] = defaultdict(list)
    for ref, study in study_of.items():
        by_study[study].append(ref)
    truth = {
        tuple(sorted(pair)) for refs in by_study.values() for pair in combinations(sorted(refs), 2)
    }
    asked = {tuple(sorted(pair)) for pair in proposed}
    found = truth & asked
    return PairEvaluation(
        true_pairs=len(truth),
        proposed=len(asked),
        found=len(found),
        missed=sorted(truth - asked),  # type: ignore[arg-type]
    )
