"""Matching the included studies of a published review to references (tranche 3.8).

Each study of the reference standard (``domain.replication.StandardStudy``) is matched
to the references that carry its DOI, else its PMID, else its title, with the rules of
the deduplication: normalized identifiers, and titles compared by ``title_similarity``
at or above the threshold of automatic grouping. A study without a title column is
matched by a reference title (four words at least) found in its full citation. A study
may match several references (duplicates); a study matched by none is listed.

Pure function: the same studies and references always give the same matches.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from revue_portee.dedup.matching import title_similarity
from revue_portee.dedup.normalize import normalize_text, title_tokens
from revue_portee.domain.dedup import DedupSettings
from revue_portee.domain.references import Reference
from revue_portee.domain.replication import StandardStudy

__all__ = ["MIN_CITATION_WORDS", "StandardMatch", "match_studies"]

# A title looked for in a citation needs this many words, not to match a short title.
MIN_CITATION_WORDS = 4


@dataclass(frozen=True, slots=True)
class StandardMatch:
    by_study: dict[str, tuple[str, ...]] = field(default_factory=dict)  # reference ids
    rule: dict[str, str] = field(default_factory=dict)  # "doi", "pmid" or "title"
    unmatched: tuple[str, ...] = ()  # study ids

    def references(self, study_id: str) -> tuple[str, ...]:
        return self.by_study.get(study_id, ())


def _by_title(study: StandardStudy, references: Sequence[Reference], threshold: float) -> list[str]:
    if study.title:
        tokens = title_tokens(study.title)
        return [
            r.id for r in references if title_similarity(tokens, title_tokens(r.title)) >= threshold
        ]
    citation = f" {normalize_text(study.citation)} "
    return [
        r.id
        for r in references
        if len(title_tokens(r.title)) >= MIN_CITATION_WORDS
        and f" {normalize_text(r.title)} " in citation
    ]


def match_studies(
    studies: Sequence[StandardStudy],
    references: Sequence[Reference],
    settings: DedupSettings | None = None,
) -> StandardMatch:
    """Match each study to references by DOI, then PMID, then title."""
    threshold = (settings or DedupSettings()).auto_from
    by_study: dict[str, tuple[str, ...]] = {}
    rule: dict[str, str] = {}
    unmatched = []
    for study in studies:
        found: list[str] = []
        if study.doi:
            found, how = [r.id for r in references if r.doi and r.doi == study.doi], "doi"
        if not found and study.pmid:
            found, how = [r.id for r in references if r.pmid and r.pmid == study.pmid], "pmid"
        if not found:
            found, how = _by_title(study, references, threshold), "title"
        if found:
            by_study[study.study_id] = tuple(sorted(found))
            rule[study.study_id] = how
        else:
            unmatched.append(study.study_id)
    return StandardMatch(by_study=by_study, rule=rule, unmatched=tuple(unmatched))
