"""RIS imports (EF-COL-03, EF-COL-05) and Crossref enrichment (EF-COL-02)."""

import threading
import time
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from revue_portee.collect import enrichment, imports
from revue_portee.domain.journal import EntryType
from revue_portee.domain.references import IssueKind, SourceKind
from revue_portee.protocol import notes
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.storage.raw import read_source_pages
from revue_portee.storage.repositories import references as references_repo
from support import TOOL_VERSION, make_clock, new_project

Clock = Callable[[], datetime]
FIXTURES = Path(__file__).parents[2] / "fixtures" / "ris"


@pytest.fixture
def setup(tmp_path: Path) -> Iterator[tuple[ProjectFolder, Clock]]:
    clock = make_clock()
    folder = new_project(tmp_path, clock)
    yield folder, clock
    folder.close()


def test_import_real_export_with_provenance(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    content = (FIXTURES / "cinahl-ebscohost.ris").read_bytes()
    imported = imports.import_ris(
        folder, "cinahl.ris", content, now=clock, tool_version=TOOL_VERSION
    )
    assert (imported.record_count, imported.issues) == (26, ())
    assert imported.database_declared == "CINAHL Complete (EBSCOhost)"
    assert (folder.path / "imports" / f"{imported.sha256}.ris").read_bytes() == content
    with folder.engine.connect() as connection:
        provenance = sorted(references_repo.list_provenance(connection), key=lambda p: p.page or 0)
        references = references_repo.list_references(connection)
    assert len(references) == 26
    assert {p.source for p in provenance} == {SourceKind.RIS}
    assert provenance[0].original_id == "193890507"
    assert provenance[0].import_file_id == imported.id
    assert [p.page for p in provenance][:3] == [1, 2, 3]
    entry = notes.journal_entries(folder)[-1]
    assert entry.entry_type == EntryType.IMPORT_COMPLETED
    assert entry.payload["records_found"] == 26
    with pytest.raises(imports.AlreadyImportedError):
        imports.import_ris(folder, "copie.ris", content, now=clock, tool_version=TOOL_VERSION)
    assert imports.imported_files(folder) == [imported]


def test_malformed_records_are_listed_and_declared_database_kept(
    setup: tuple[ProjectFolder, Clock],
) -> None:
    folder, clock = setup
    content = "TY  - JOUR\nTI  - Titre\nER  -\nTY  - JOUR\nER  -\n".encode("cp1252")
    imported = imports.import_ris(
        folder,
        "ovid.ris",
        content,
        database="PsycINFO (Ovid)",
        now=clock,
        tool_version=TOOL_VERSION,
    )
    assert imported.record_count == 1
    assert [(i.kind, i.record) for i in imported.issues] == [(IssueKind.EMPTY, 2)]
    assert imported.database_declared == "PsycINFO (Ovid)"
    latin = "TY  - JOUR\nTI  - Société\nER  -\n".encode("cp1252")
    imports.import_ris(folder, "latin.ris", latin, now=clock, tool_version=TOOL_VERSION)
    with folder.engine.connect() as connection:
        titles = {r.title for r in references_repo.list_references(connection)}
    assert "Société" in titles
    with pytest.raises(imports.NothingToImportError):
        imports.import_ris(folder, "vide.ris", b"rien", now=clock, tool_version=TOOL_VERSION)


class FakeCrossref:
    """Knows one DOI; records the largest number of simultaneous calls."""

    def __init__(self) -> None:
        self.active = 0
        self.peak = 0
        self.lock = threading.Lock()
        self.asked: list[str] = []

    def work(self, doi: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.asked.append(doi)
        time.sleep(0.01)
        with self.lock:
            self.active -= 1
        if doi == "10.3310/PHR06130":
            work = {
                "title": ["Public health research report"],
                "container-title": ["Public Health Research"],
                "author": [{"family": "Doe", "given": "Jane"}],
                "published-print": {"date-parts": [[2018, 11]]},
                "abstract": "<jats:p>An <jats:italic>abstract</jats:italic>.</jats:p>",
                "volume": "6",
            }
            return work, {"message": work}
        return None, {"status": 404}


def test_crossref_fills_only_missing_fields(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    content = (
        "TY  - JOUR\nPY  - 2018\nDO  - 10.3310/phr06130\nAN  - 30475559\nDB  - PubMed\nER  -\n"
        + "".join(f"TY  - JOUR\nTI  - Titre {n}\nDO  - 10.1000/x{n}\nER  -\n" for n in range(8))
        + "TY  - JOUR\nTI  - Sans DOI\nER  -\n"
    ).encode()
    imports.import_ris(folder, "a.ris", content, now=clock, tool_version=TOOL_VERSION)
    assert len(enrichment.enrichment_candidates(folder)) == 9  # with DOI and missing fields
    crossref = FakeCrossref()
    summary = enrichment.enrich_references(
        folder, now=clock, tool_version=TOOL_VERSION, source=lambda: crossref, max_workers=8
    )
    assert crossref.peak <= 3  # concurrency capped at three
    assert (summary.checked, summary.enriched, summary.not_found) == (9, 1, 8)
    report = next(r for r in enrichment.references_with_enrichment(folder) if r.pmid)
    assert report.title == "Public health research report"
    assert report.authors == ("Doe, Jane",)
    assert report.year == 2018  # kept from the export, not replaced
    assert report.abstract == "An abstract ."
    assert report.volume == "6"
    assert enrichment.enrichment_candidates(folder) == []  # checked DOIs are not asked again
    again = enrichment.enrich_references(
        folder, now=clock, tool_version=TOOL_VERSION, source=lambda: crossref
    )
    assert again.checked == 0
    entry = notes.journal_entries(folder)[-1]
    assert entry.entry_type == EntryType.ENRICH_COMPLETED
    assert entry.payload["fields_added"] == summary.fields
    assert len(read_source_pages(folder.path, str(entry.payload["raw_dir"]))) == 9


class FailingCrossref(FakeCrossref):
    """Fails on the third DOI asked."""

    def work(self, doi: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        if len(self.asked) == 2:
            from revue_portee.sources.http import SourceUnreachableError

            self.asked.append(doi)
            raise SourceUnreachableError("Crossref", "api.crossref.org")
        return super().work(doi)


def test_enrichment_keeps_the_batches_already_recorded(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    content = "".join(f"TY  - JOUR\nTI  - T{n}\nDO  - 10.1000/b{n}\nER  -\n" for n in range(5))
    imports.import_ris(folder, "b.ris", content.encode(), now=clock, tool_version=TOOL_VERSION)
    with folder.engine.connect() as connection:
        assert references_repo.count_enrichment_candidates(connection) == 5
    from revue_portee.sources.http import SourceUnreachableError

    with pytest.raises(SourceUnreachableError):
        enrichment.enrich_references(
            folder,
            now=clock,
            tool_version=TOOL_VERSION,
            source=FailingCrossref,
            batch_size=2,
            max_workers=1,
        )
    remaining = enrichment.enrichment_candidates(folder)
    assert len(remaining) == 3  # the first batch of two is kept
    with folder.engine.connect() as connection:
        assert references_repo.count_enrichment_candidates(connection) == 3
    summary = enrichment.enrich_references(
        folder, now=clock, tool_version=TOOL_VERSION, source=FakeCrossref, batch_size=2
    )
    assert summary.checked == 3


def test_concurrent_import_of_the_same_file(
    setup: tuple[ProjectFolder, Clock], monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, clock = setup
    content = b"TY  - JOUR\nTI  - T\nER  -\n"
    imports.import_ris(folder, "a.ris", content, now=clock, tool_version=TOOL_VERSION)
    original = references_repo.get_import_by_sha256
    calls: list[int] = []

    def first_check_misses(connection: Any, sha256: str) -> Any:  # noqa: ANN401
        calls.append(1)
        return None if len(calls) == 1 else original(connection, sha256)

    monkeypatch.setattr(references_repo, "get_import_by_sha256", first_check_misses)
    with pytest.raises(imports.AlreadyImportedError):
        imports.import_ris(folder, "b.ris", content, now=clock, tool_version=TOOL_VERSION)


def test_encodings_and_database_names(setup: tuple[ProjectFolder, Clock]) -> None:
    folder, clock = setup
    latin = b"TY  - JOUR\nTI  - Caf\xe9 \x81\nER  -\n"  # 0x81 is not cp1252
    imported = imports.import_ris(folder, "l.ris", latin, now=clock, tool_version=TOOL_VERSION)
    assert imported.record_count == 1
    assert imported.database_declared == ""  # no DB or DP tag: no name
    mixed = b"TY  - JOUR\nTI  - A\nDB  - PubMed\nER  -\nTY  - JOUR\nTI  - B\nER  -\n"
    named = imports.import_ris(folder, "m.ris", mixed, now=clock, tool_version=TOOL_VERSION)
    assert named.database_declared == "PubMed"
    with pytest.raises(imports.UnreadableFileError):
        imports.import_ris(
            folder, "u16.ris", "TY  - JOUR".encode("utf-16"), now=clock, tool_version=TOOL_VERSION
        )
