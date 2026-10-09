"""Retrieval of full texts (EF-SEL-14, EF-SEL-15): open access in OpenAlex then
Unpaywall, uploads matched to references, texts declared not retrievable, list of the
missing ones. Counts of the demonstration made by hand (tests/fixtures/demo/README.md)."""

import csv
import io
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from demo import (
    BLOCKED,
    NOT_RETRIEVABLE,
    Demo,
    DemoFinder,
    broaden_and_reassess,
    build,
    create,
    deduplicate,
    reconcile,
    retrieve_texts,
    screen,
)
from revue_portee.domain.fulltext import (
    FulltextOrigin,
    MatchKind,
    QuoteCheck,
    RetrievalCounts,
    RetrievalStatus,
    check_quote,
)
from revue_portee.domain.journal import EntryType
from revue_portee.domain.references import Reference
from revue_portee.fulltext import retrieval
from revue_portee.protocol import notes
from revue_portee.sources.http import SourceUnreachableError
from revue_portee.sources.records import OpenAccessLocation
from revue_portee.storage.raw import read_source_pages
from support import TOOL_VERSION, make_pdf, raw_sqlite

CAREGIVERS = "Family caregivers of older adults living\nin rural areas: A qualitative study"


def _screened(tmp_path: Path) -> Demo:
    """The demonstration up to the end of the title and abstract screening."""
    demo = create(tmp_path)
    deduplicate(demo)
    screen(demo)
    reconcile(demo)
    broaden_and_reassess(demo)
    return demo


def test_demonstration_counted_by_hand(tmp_path: Path) -> None:
    demo = _screened(tmp_path)
    try:
        before = retrieval.retrieval_report(demo.folder).counts
        finder = retrieve_texts(demo)
        report = retrieval.retrieval_report(demo.folder)
        ids = demo.ids()
        entries = notes.journal_entries(demo.folder)
        loneliness = report.row(ids["loneliness"])
        housing = report.row(ids["housing"])
        caregivers = report.row(ids["caregivers"])
        assert loneliness is not None
        assert loneliness.document is not None
        text = retrieval.paged_text(demo.folder, loneliness.document)
    finally:
        demo.folder.close()
    assert before == RetrievalCounts(
        sought=3, obtained=0, open_access=0, uploaded=0, not_sought=3, not_found=0,
        not_retrievable=0, needs_ocr=0,
    )  # fmt: skip
    assert report.counts == RetrievalCounts(
        sought=3, obtained=2, open_access=2, uploaded=0, not_sought=0, not_found=0,
        not_retrievable=1, needs_ocr=0,
    )  # fmt: skip
    assert report.counts.open_access_share == pytest.approx(2 / 3)
    # the housing study: the publisher refuses its link, the repository version is taken
    assert finder.downloads == [  # in the order of titles
        BLOCKED,
        "https://repository.example.org/housing.pdf",
        "https://repository.example.org/loneliness.pdf",
    ]
    assert housing is not None
    assert housing.document is not None
    assert (housing.document.origin, housing.document.license, housing.document.version) == (
        FulltextOrigin.UNPAYWALL, "cc-by", "acceptedVersion",
    )  # fmt: skip
    assert loneliness.document.origin is FulltextOrigin.OPENALEX
    assert (loneliness.document.page_count, loneliness.document.references_page) == (3, 3)
    assert check_quote(text.pages, "We interviewed 24 older adults living", 2) is (
        QuoteCheck.AT_PAGE
    )
    assert "Smith" not in " ".join(p.text for p in text.body())
    assert caregivers is not None
    assert caregivers.status is RetrievalStatus.NOT_RETRIEVABLE
    assert caregivers.note is not None
    assert caregivers.note.reason == NOT_RETRIEVABLE
    kinds = [e.entry_type for e in entries if e.entry_type.startswith("fulltext.")]
    assert kinds == [
        EntryType.FULLTEXT_NOT_FOUND,  # caregivers, first in the order of titles
        EntryType.FULLTEXT_OBTAINED,
        EntryType.FULLTEXT_OBTAINED,
        EntryType.FULLTEXT_NOT_RETRIEVABLE,
    ]
    journal_text = " ".join(str(e.payload) + e.summary_fr for e in entries)
    assert "example.org" not in journal_text  # no URL in the journal (public archive)


def test_files_and_raw_answers_are_kept(tmp_path: Path) -> None:
    demo = build(tmp_path)
    try:
        housing = retrieval.retrieval_report(demo.folder).row(demo.ids()["housing"])
        assert housing is not None
        assert housing.document is not None
        document = housing.document
        answers = read_source_pages(demo.folder.path, document.raw_dir)
    finally:
        demo.folder.close()
    texts = demo.folder.path / "textes"
    assert (texts / f"{document.sha256}.pdf").read_bytes().startswith(b"%PDF-")
    assert (texts / f"{document.sha256}.c2.pages.json").is_file()  # conversion 2
    assert answers[0] == {"source": "openalex", "answer": {"results": [{"id": "W0"}]}}
    assert answers[1] == {
        "source": "unpaywall",
        "answer": {"doi": "10.5555/demo.0001", "is_oa": True},
    }
    downloads: Any = answers[2]
    assert [d["error"] is None for d in downloads["downloads"]] == [False, True]
    assert "403" in downloads["downloads"][0]["error"]


def test_tables_are_append_only(tmp_path: Path) -> None:
    demo = build(tmp_path)
    demo.folder.close()
    for table in ("fulltext_document", "retrieval_note"):
        with (
            pytest.raises(sqlite3.IntegrityError, match=f"append-only: {table}"),
            raw_sqlite(demo.folder.path / "revue.sqlite") as connection,
        ):
            connection.execute(f"DELETE FROM {table}")  # noqa: S608 - fixed table names


class _Unreachable:
    def __init__(self, after: int) -> None:
        self.after = after
        self.asked = 0

    def openalex(self, reference: Reference) -> tuple[list[OpenAccessLocation], dict[str, Any]]:
        self.asked += 1
        if self.asked > self.after:
            raise SourceUnreachableError("OpenAlex", "api.openalex.org")
        return [], {}

    def unpaywall(self, doi: str) -> tuple[list[OpenAccessLocation], dict[str, Any]]:
        return [], {}

    def download(self, url: str) -> bytes:
        raise AssertionError(url)


def test_a_source_that_cannot_answer_stops_and_the_retrieval_resumes(tmp_path: Path) -> None:
    demo = _screened(tmp_path)
    try:
        source = _Unreachable(after=1)
        with pytest.raises(SourceUnreachableError):
            retrieval.retrieve_open_access(
                demo.folder, now=demo.clock, tool_version=TOOL_VERSION, finder=lambda: source
            )
        assert retrieval.retrieval_report(demo.folder).counts.not_found == 1
        progress: list[tuple[int, int]] = []
        summary = retrieval.retrieve_open_access(
            demo.folder, now=demo.clock, tool_version=TOOL_VERSION,
            finder=lambda: DemoFinder(demo.ids()), progress=lambda *a: progress.append(a),
        )  # fmt: skip
        assert (summary.looked_for, summary.obtained, summary.not_found) == (2, 2, 0)
        assert progress == [(1, 2), (2, 2)]
        # nothing left to look for, unless the references not found are asked again
        again = retrieval.retrieve_open_access(
            demo.folder, now=demo.clock, tool_version=TOOL_VERSION,
            finder=lambda: DemoFinder(demo.ids()),
        )  # fmt: skip
        assert again.looked_for == 0
        retried = retrieval.retrieve_open_access(
            demo.folder, now=demo.clock, tool_version=TOOL_VERSION,
            finder=lambda: DemoFinder(demo.ids()), retry_not_found=True, limit=5,
        )  # fmt: skip
        assert (retried.looked_for, retried.not_found) == (1, 1)
    finally:
        demo.folder.close()


def test_upload_one_file_then_a_better_version(tmp_path: Path) -> None:
    demo = build(tmp_path)
    try:
        ref = demo.ids()["caregivers"]
        data = make_pdf(["Family caregivers of older adults\nliving in rural areas", "Methods"])
        first = retrieval.add_upload(
            demo.folder, ref, data, filename="C:/Users/x/caregivers.pdf", now=demo.clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
        same = retrieval.add_upload(
            demo.folder, ref, data, filename="again.pdf", now=demo.clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
        better = retrieval.add_upload(
            demo.folder, ref, make_pdf(["Published version", "Methods", "Results"]),
            filename="published.pdf", now=demo.clock, tool_version=TOOL_VERSION,
        )  # fmt: skip
        report = retrieval.retrieval_report(demo.folder)
    finally:
        demo.folder.close()
    assert same == first
    assert first.filename == "caregivers.pdf"  # the name only, never the folder
    row = report.row(ref)
    assert row is not None
    assert row.document == better
    assert row.status is RetrievalStatus.OBTAINED
    assert row.note is None
    # a text found after the declaration takes precedence over it
    assert (report.counts.obtained, report.counts.uploaded, report.counts.not_retrievable) == (
        3, 1, 0,
    )  # fmt: skip


def test_upload_errors(tmp_path: Path) -> None:
    demo = build(tmp_path)
    try:
        gardens = demo.ids()["gardens"]  # excluded: not sought
        with pytest.raises(retrieval.FulltextError):
            retrieval.add_upload(
                demo.folder, gardens, make_pdf(["x"]), filename="x.pdf", now=demo.clock,
                tool_version=TOOL_VERSION,
            )  # fmt: skip
        with pytest.raises(retrieval.FulltextError):
            retrieval.add_upload(
                demo.folder, demo.ids()["caregivers"], b"<html>", filename="x.pdf",
                now=demo.clock, tool_version=TOOL_VERSION,
            )  # fmt: skip
    finally:
        demo.folder.close()


def test_upload_a_set_of_files(tmp_path: Path) -> None:
    demo = build(tmp_path)
    try:
        ids = demo.ids()
        housing = retrieval.retrieval_report(demo.folder).row(ids["housing"])
        assert housing is not None
        assert housing.document is not None
        kept = (demo.folder.path / "textes" / f"{housing.document.sha256}.pdf").read_bytes()
        files = [
            ("caregivers.pdf", make_pdf([CAREGIVERS])),
            ("10.5555_DEMO.0001.pdf", kept),  # same file as the one in force
            ("unknown.pdf", make_pdf(["A study of something else entirely"])),
            ("broken.pdf", b"%PDF-1.4 broken"),
        ]  # fmt: skip
        report = retrieval.upload_files(
            demo.folder, files, now=demo.clock, tool_version=TOOL_VERSION
        )
        counts = retrieval.retrieval_report(demo.folder).counts
    finally:
        demo.folder.close()
    assert [(o.filename, o.reference_id, o.kind) for o in report.added] == [
        ("caregivers.pdf", ids["caregivers"], MatchKind.TITLE)
    ]
    assert [(o.filename, o.kind) for o in report.already] == [
        ("10.5555_DEMO.0001.pdf", MatchKind.DOI_IN_FILENAME)
    ]
    assert [o.filename for o in report.unmatched] == ["unknown.pdf"]
    assert [o.filename for o in report.unreadable] == ["broken.pdf"]
    assert report.unreadable[0].message
    assert (counts.obtained, counts.uploaded) == (3, 1)


def test_declare_not_retrievable_errors(tmp_path: Path) -> None:
    demo = build(tmp_path)
    try:
        ids = demo.ids()
        with pytest.raises(retrieval.FulltextError):
            retrieval.declare_not_retrievable(
                demo.folder, ids["caregivers"], "  ", now=demo.clock, tool_version=TOOL_VERSION
            )
        with pytest.raises(retrieval.FulltextError):  # a text is already obtained
            retrieval.declare_not_retrievable(
                demo.folder, ids["loneliness"], "x", now=demo.clock, tool_version=TOOL_VERSION
            )
    finally:
        demo.folder.close()


def test_export_missing(tmp_path: Path) -> None:
    demo = _screened(tmp_path)
    try:
        path, rows = retrieval.export_missing(demo.folder)
        before = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))
        retrieve_texts(demo)
        path, after_rows = retrieval.export_missing(demo.folder)
        after = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))
        ids = demo.ids()
    finally:
        demo.folder.close()
    assert path.name == "textes-manquants.csv"
    assert (rows, after_rows) == (3, 1)
    assert {r["status"] for r in before} == {"not_sought"}
    assert [(r["reference_id"], r["status"], r["reason"]) for r in after] == [
        (ids["caregivers"], "not_retrievable", NOT_RETRIEVABLE)
    ]


def test_nothing_sought_before_the_screening(tmp_path: Path) -> None:
    demo = create(tmp_path)
    try:
        summary = retrieval.retrieve_open_access(
            demo.folder, now=demo.clock, tool_version=TOOL_VERSION,
            finder=lambda: DemoFinder({}),
        )  # fmt: skip
        report = retrieval.retrieval_report(demo.folder)
    finally:
        demo.folder.close()
    assert summary.looked_for == 0
    assert report.rows == []
    assert report.row("x") is None
