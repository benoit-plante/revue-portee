"""Tolerant RIS reader for exports of subscription databases (EF-COL-03).

Tested on real exports from EBSCOhost (SocINDEX, CINAHL, ERIC), PubMed and Érudit.
Tolerated variants: a byte order mark, Windows line ends, one or two spaces before
the dash, blank lines inside a record, values wrapped over several lines (each
continuation line joins the previous value), repeated tags (two abstracts are kept
both), DOIs given as URLs or inside other fields. Pure functions: no I/O.

Records without any usable field are not imported but listed, as are lines outside
any record and records that the file ends before closing (those are imported).
"""

import re
from dataclasses import dataclass, field

from revue_portee.domain.references import ImportIssue, IssueKind, clean_doi, clean_pmid

__all__ = ["RisRecord", "RisResult", "detect_database", "parse_ris"]

_TAG = re.compile(r"^([A-Z][A-Z0-9])\s{1,2}-(?: (.*)|\s*)$")
_YEAR = re.compile(r"(?<!\d)(1[0-9]{3}|20[0-9]{2}|2100)(?!\d)")


@dataclass(frozen=True, slots=True)
class RisRecord:
    """One record: its position, first line and every value of every tag, in order."""

    position: int  # 1-based, counting every record including empty ones
    line: int
    tags: dict[str, tuple[str, ...]]

    def first(self, *names: str) -> str:
        for name in names:
            for value in self.tags.get(name, ()):
                if value.strip():
                    return " ".join(value.split())
        return ""

    def all(self, *names: str) -> tuple[str, ...]:
        return tuple(
            " ".join(v.split()) for name in names for v in self.tags.get(name, ()) if v.strip()
        )

    @property
    def title(self) -> str:
        return self.first("TI", "T1", "CT", "BT")

    @property
    def authors(self) -> tuple[str, ...]:
        return self.all("AU", "A1")

    @property
    def abstract(self) -> str:
        return "\n\n".join(self.all("AB", "N2"))

    @property
    def container_title(self) -> str:
        container = self.first("JO", "JF", "JA", "J2")
        if container:
            return container
        return self.first("T2") if self.title else ""

    @property
    def year(self) -> int | None:
        for value in self.all("PY", "Y1", "DA"):
            match = _YEAR.search(value)
            if match:
                return int(match.group(1))
        return None

    @property
    def volume(self) -> str:
        return self.first("VL")

    @property
    def issue(self) -> str:
        return self.first("IS", "CP")

    @property
    def language(self) -> str:
        return self.first("LA")

    @property
    def url(self) -> str:
        return self.first("UR", "L2")

    @property
    def doc_type(self) -> str:
        return self.first("TY")

    @property
    def pages(self) -> str:
        start, end = self.first("SP"), self.first("EP")
        if start and end and end != start:
            return f"{start}-{end}"
        return start

    @property
    def doi(self) -> str:
        for value in self.all("DO", "M3", "UR", "L1", "L2", "N1", "AN"):
            doi = clean_doi(value)
            if doi:
                return doi
        return ""

    @property
    def database(self) -> str:
        return self.first("DB")

    @property
    def provider(self) -> str:
        return self.first("DP")

    @property
    def pmid(self) -> str:
        if "pubmed" in f"{self.database} {self.provider}".casefold():
            return clean_pmid(self.first("AN"))
        return ""

    @property
    def accession(self) -> str:
        return self.first("AN", "ID", "M1")

    @property
    def empty(self) -> bool:
        return not (self.title or self.abstract or self.authors or self.doi)


@dataclass(frozen=True, slots=True)
class RisResult:
    records: tuple[RisRecord, ...]  # importable records (not empty)
    issues: tuple[ImportIssue, ...] = ()
    total: int = 0  # every TY found, empty records included
    database_counts: dict[str, int] = field(default_factory=dict)


def _snippet(line: str) -> str:
    return " ".join(line.split())[:80]


def parse_ris(text: str) -> RisResult:
    """Read every record of a RIS file."""
    lines = text.removeprefix("﻿").splitlines()
    records: list[RisRecord] = []
    issues: list[ImportIssue] = []
    tags: dict[str, list[str]] | None = None
    start = 0
    last: str | None = None
    position = 0

    def close(at_line: int, *, terminated: bool) -> None:
        nonlocal tags
        assert tags is not None  # noqa: S101 - only called inside a record
        record = RisRecord(
            position=position, line=start, tags={k: tuple(v) for k, v in tags.items()}
        )
        if record.empty:
            issues.append(ImportIssue(kind=IssueKind.EMPTY, line=start, record=position))
        else:
            records.append(record)
        if not terminated:
            issues.append(ImportIssue(kind=IssueKind.UNTERMINATED, line=at_line, record=position))
        tags = None

    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        match = _TAG.match(line)
        if match is None:
            if tags is not None and last is not None:  # wrapped value
                tags[last][-1] = f"{tags[last][-1]} {line.strip()}"
            else:
                issues.append(
                    ImportIssue(kind=IssueKind.BAD_LINE, line=number, text=_snippet(line))
                )
            continue
        tag, value = match.group(1), (match.group(2) or "").strip()
        if tag == "TY":
            if tags is not None:
                close(number, terminated=False)
            position += 1
            tags, start, last = {"TY": [value]}, number, "TY"
        elif tag == "ER":
            if tags is None:
                issues.append(ImportIssue(kind=IssueKind.NO_TYPE, line=number, text="ER"))
            else:
                close(number, terminated=True)
            last = None
        elif tags is None:
            issues.append(ImportIssue(kind=IssueKind.NO_TYPE, line=number, text=_snippet(line)))
        else:
            tags.setdefault(tag, []).append(value)
            last = tag
    if tags is not None:
        close(len(lines), terminated=False)
    counts: dict[str, int] = {}
    for record in records:
        name = detect_database(record)
        counts[name] = counts.get(name, 0) + 1
    return RisResult(
        records=tuple(records), issues=tuple(issues), total=position, database_counts=counts
    )


def detect_database(record: RisRecord) -> str:
    """Database and platform named by the record, e.g. "CINAHL Complete (EBSCOhost)"."""
    database, provider = record.database, record.provider
    if database and provider and provider.casefold() not in database.casefold():
        if database.casefold() in provider.casefold():  # "Érudit" and "Érudit: www…"
            return database
        return f"{database} ({provider})"
    return database or provider
