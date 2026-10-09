"""A text converted by an older version of the rules is converted again on request: a
new document is added, the old one and its text stay (D-028)."""

from pathlib import Path

from typer.testing import CliRunner

from demo import build
from revue_portee.cli.main import app
from revue_portee.domain.journal import EntryType
from revue_portee.fulltext import retrieval
from revue_portee.fulltext.convert import CONVERSION
from revue_portee.protocol import notes
from revue_portee.storage.repositories import fulltext as fulltext_repo
from revue_portee.storage.repositories import journal
from support import TOOL_VERSION


def test_older_conversion_is_converted_again(tmp_path: Path) -> None:
    demo = build(tmp_path)
    try:
        ref = demo.ids()["loneliness"]
        row = retrieval.retrieval_report(demo.folder).row(ref)
        assert row is not None
        assert row.document is not None
        current = row.document
        # a document as converted before the conversion rules were numbered
        texts = demo.folder.path / "textes"
        (texts / f"{current.sha256}.pages.json").write_bytes(
            (texts / f"{current.sha256}.c{CONVERSION}.pages.json").read_bytes()
        )
        moment = demo.clock()
        old = current.model_copy(
            update={"id": "0" * 26, "converter": "pymupdf 1.28.2", "created_at": moment}
        )
        with demo.folder.write() as connection:
            entry = journal.append_entry(
                connection, now=moment, actor_reviewer_id=demo.folder.reviewer_id,
                entry_type=EntryType.FULLTEXT_UPLOADED, summary_fr="test",
                tool_version=TOOL_VERSION,
            )  # fmt: skip
            fulltext_repo.insert_document(connection, old, journal_entry_id=entry.id)
        assert old.conversion == 1
        assert retrieval.paged_text(demo.folder, old).pages
        done = retrieval.reconvert(demo.folder, now=demo.clock, tool_version=TOOL_VERSION)
        again = retrieval.reconvert(demo.folder, now=demo.clock, tool_version=TOOL_VERSION)
        row = retrieval.retrieval_report(demo.folder).row(ref)
        entries = notes.journal_entries(demo.folder)
        with demo.folder.engine.connect() as connection:
            documents = [
                d for d in fulltext_repo.list_documents(connection) if d.reference_id == ref
            ]
    finally:
        demo.folder.close()
    assert (done, again) == (1, 0)
    assert row is not None
    assert row.document is not None
    assert row.document.conversion == CONVERSION
    assert (row.document.url, row.document.license) == (current.url, current.license)
    assert len(documents) == 3  # every conversion stays
    assert entries[-1].entry_type == EntryType.FULLTEXT_CONVERTED
    assert entries[-1].payload["replaces"] == old.id


def test_command(tmp_path: Path) -> None:
    demo = build(tmp_path)
    demo.folder.close()
    result = CliRunner().invoke(app, ["textes-reconvertir", str(demo.folder.path)])
    assert result.exit_code == 0, result.output
    assert "Textes convertis de nouveau : 0" in result.output
    assert CliRunner().invoke(app, ["textes-reconvertir", str(tmp_path / "x")]).exit_code == 1
