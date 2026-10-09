"""Archive of the project (EF-PRJ-04, ENF-REP-06): every number of the diagram is
recomputed from the public archive alone, with the standard library only (no import of
revue_portee, no API key), and matches the count made by hand."""

import csv
import hashlib
import io
import json
import zipfile
from collections import Counter
from pathlib import Path

import pytest

from demo import build, create
from revue_portee.domain.criteria import CriterionKind, PccElement
from revue_portee.domain.journal import EntryType
from revue_portee.protocol import criteria, notes
from revue_portee.screening.archive import (
    ArchiveKind,
    SecretInArchiveError,
    archive_files,
    export_archive,
)
from revue_portee.storage.archive import write_zip
from revue_portee.storage.project_folder import open_project_folder
from support import TOOL_VERSION, make_clock

KEEP = {"include", "uncertain"}


# --- An independent reader of the archive (standard library only) -------------------


class Archive:
    def __init__(self, path: Path) -> None:
        self.zip = zipfile.ZipFile(path)
        (self.root,) = {name.split("/")[0] for name in self.zip.namelist()}

    def names(self) -> set[str]:
        return {name.split("/", 1)[1] for name in self.zip.namelist()}

    def text(self, name: str) -> str:
        return self.zip.read(f"{self.root}/{name}").decode("utf-8")

    def rows(self, name: str) -> list[dict[str, str]]:
        return list(csv.DictReader(io.StringIO(self.text(name))))


def _full_text(
    archive: Archive, decisions: dict[str, dict[str, str]], order: dict[str, int]
) -> dict[str, object]:
    """The full-text boxes, following LISEZMOI.md."""
    finals = []
    for row in archive.rows("donnees/etat-texte-integral.csv"):
        if not row["final_decision_id"]:
            continue
        final = decisions[row["final_decision_id"]]
        human = [
            d
            for d in decisions.values()
            if d["reference_id"] == row["reference_id"]
            and d["reviewer_kind"] == "human"
            and d["stage"] == "full_text"
        ]
        assert final["id"] == max(human, key=lambda d: order[d["id"]])["id"]
        finals.append((final, row["primary_reason"]))
    reasons = Counter(reason for final, reason in finals if final["value"] == "exclude")
    return {
        "assessed": len(finals),
        "reports_excluded": dict(reasons),
        "included": sum(1 for final, _reason in finals if final["value"] == "include"),
    }


def recount(archive: Archive) -> dict[str, object]:
    """The numbers of the diagram, following LISEZMOI.md."""
    dedup = archive.rows("donnees/dedoublonnage.csv")
    decisions = {d["id"]: d for d in archive.rows("donnees/decisions.csv")}
    order = {d["id"]: int(d["order"]) for d in decisions.values()}
    remaining = {r["reference_id"] for r in dedup if not r["duplicate_of"]}
    state = archive.rows("donnees/etat-du-tri.csv")
    assert {s["reference_id"] for s in state} == remaining
    finals = []
    for row in state:
        if not row["final_decision_id"]:
            continue
        final = decisions[row["final_decision_id"]]
        # the decision in force is the latest human decision on the reference
        human = [
            d
            for d in decisions.values()
            if d["reference_id"] == row["reference_id"]
            and d["reviewer_kind"] == "human"
            and d["stage"] == "title_abstract"
        ]
        assert final["id"] == max(human, key=lambda d: order[d["id"]])["id"]
        finals.append(final)
    excluded = [f for f in finals if f["value"] == "exclude"]
    members = archive.rows("donnees/membres-des-tours.csv")
    reassessments = []
    for change in archive.rows("donnees/reevaluations.csv"):
        round_id = change["reassessment_round_id"]
        verified = [
            d
            for d in decisions.values()
            if d["round_id"] == round_id and d["reviewer_kind"] == "human"
        ]
        flips = [
            (decisions[d["supersedes_decision_id"]]["value"] in KEEP, d["value"] in KEEP)
            for d in verified
        ]
        reassessments.append(
            {
                "from_version": int(change["from_version"]),
                "to_version": int(change["to_version"]),
                "reassessed": sum(1 for m in members if m["round_id"] == round_id),
                "kept_to_excluded": sum(1 for before, after in flips if before and not after),
                "excluded_to_kept": sum(1 for before, after in flips if not before and after),
                "completed": change["completed"] == "1",
            }
        )
    return {
        "identified_by_source": dict(sorted(Counter(r["source"] for r in dedup).items())),
        "identified": len(dedup),
        "duplicates_removed": len(dedup) - len(remaining),
        "screened": len(finals),
        "excluded": len(excluded),
        "excluded_by_person": sum(1 for f in excluded if f["reviewer_kind"] == "human"),
        "excluded_by_automation": sum(1 for f in excluded if f["reviewer_kind"] == "ai"),
        "sought": len(finals) - len(excluded),
        "not_retrieved": sum(
            1 for t in archive.rows("donnees/textes.csv") if t["status"] == "not_retrievable"
        ),
        **_full_text(archive, decisions, order),
        "reassessments": reassessments,
        "disagreements_open": sum(
            1 for s in state if s["disagreement"] == "1" and s["reconciled"] == "0"
        ),
        "duplicate_pairs": len(archive.rows("donnees/paires-a-examiner.csv")),
    }


def check_journal(archive: Archive) -> int:
    """Recompute the hash chain of the journal (LISEZMOI.md)."""
    previous = "0" * 64
    lines = archive.text("donnees/journal.jsonl").splitlines()
    for line in lines:
        entry = json.loads(line)
        assert entry["prev_hash"] == previous
        content = {k: v for k, v in entry.items() if k != "hash"}
        canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == entry["hash"]
        previous = entry["hash"]
    return len(lines)


# --- Tests --------------------------------------------------------------------------


def test_public_archive_recounted_by_hand(tmp_path: Path) -> None:
    demo = build(tmp_path)
    try:
        result = export_archive(demo.folder, now=make_clock(), tool_version=TOOL_VERSION)
        entries = notes.journal_entries(demo.folder)
    finally:
        demo.folder.close()
    archive = Archive(result.path)
    counted = recount(archive)
    # the count made by hand (tests/fixtures/demo/README.md)
    assert counted == {
        "identified_by_source": {
            "APA PsycInfo (EBSCOhost)": 4,
            "CINAHL (EBSCOhost)": 3,
            "PubMed": 2,
        },
        "identified": 9,
        "duplicates_removed": 4,
        "screened": 5,
        "excluded": 2,
        "excluded_by_person": 2,
        "excluded_by_automation": 0,
        "sought": 3,
        "not_retrieved": 1,
        "assessed": 2,
        "reports_excluded": {"P1": 1},
        "included": 1,
        "reassessments": [
            {
                "from_version": 1,
                "to_version": 2,
                "reassessed": 2,
                "kept_to_excluded": 0,
                "excluded_to_kept": 1,
                "completed": True,
            }
        ],
        "disagreements_open": 0,
        "duplicate_pairs": 0,
    }
    # ... and the numbers the diagram declares
    declared = json.loads(archive.text("donnees/diagramme.json"))
    for key in ("identified_by_source", "identified", "duplicates_removed", "screened",
                "excluded", "excluded_by_person", "excluded_by_automation", "sought",
                "not_retrieved", "reassessments"):  # fmt: skip
        assert declared[key] == counted[key], key
    full_text = declared["full_text"]
    assert full_text["assessed"] == counted["assessed"]
    assert full_text["excluded_by_reason"] == counted["reports_excluded"]
    assert full_text["included"] == counted["included"]
    assert {r["mode"] for r in archive.rows("donnees/tours.csv")} == {"blind"}
    assert check_journal(archive) == len(entries) - 1  # the export is recorded afterwards
    # nothing copyrighted, no database in the public archive
    names = archive.names()
    assert "revue.sqlite" not in names
    assert not any(name.startswith(("brut/", "imports/", "textes/")) for name in names)
    references = archive.rows("donnees/references.csv")
    assert "abstract" not in references[0]
    assert "url" not in references[0]
    texts = archive.rows("donnees/textes.csv")
    assert len(texts) == 3
    assert "url" not in texts[0]
    assert "filename" not in texts[0]
    assert "example.org" not in archive.text("donnees/textes.csv")
    assert {
        "LISEZMOI.md",
        "projet.toml",
        "exports/diagramme-fr.svg",
        "exports/diagramme-en.svg",
        "exports/methode-fr.md",
        "exports/methode-en.docx",
        "donnees/appels-ia.csv",
        "donnees/criteres.csv",
        "donnees/tours.csv",
    } <= names
    calls = archive.rows("donnees/appels-ia.csv")
    assert {c["model_returned"] for c in calls} == {"fake-model-2026-10-07"}
    # the export is in the journal, with the digest of the file
    last = entries[-1]
    assert last.entry_type == EntryType.ARCHIVE_EXPORTED
    assert last.payload["sha256"] == hashlib.sha256(result.path.read_bytes()).hexdigest()
    assert last.payload["kind"] == "publique"


def test_same_project_same_archive(tmp_path: Path) -> None:
    demo = build(tmp_path)
    try:
        moment = make_clock()()
        files = archive_files(
            demo.folder, ArchiveKind.PUBLIC, now=lambda: moment, tool_version=TOOL_VERSION
        )
        again = archive_files(
            demo.folder, ArchiveKind.PUBLIC, now=lambda: moment, tool_version=TOOL_VERSION
        )
    finally:
        demo.folder.close()
    assert files == again
    write_zip(tmp_path / "a.zip", files, moment)
    write_zip(tmp_path / "b.zip", again, moment)
    assert (tmp_path / "a.zip").read_bytes() == (tmp_path / "b.zip").read_bytes()


def test_complete_archive_reopens(tmp_path: Path) -> None:
    demo = build(tmp_path / "work")
    try:
        result = export_archive(
            demo.folder, kind=ArchiveKind.COMPLETE, now=make_clock(), tool_version=TOOL_VERSION
        )
    finally:
        demo.folder.close()
    archive = Archive(result.path)
    names = archive.names()
    assert "revue.sqlite" in names
    assert any(name.startswith("brut/") for name in names)
    assert "Archive complète" in archive.text("LISEZMOI.md")
    archive.zip.extractall(tmp_path / "copy")
    reopened = open_project_folder(
        tmp_path / "copy" / archive.root,
        now=make_clock(),
        tool_version=TOOL_VERSION,
        record_opening=False,
    )
    try:
        assert notes.verify_journal(reopened).valid
    finally:
        reopened.close()


def test_a_secret_stops_the_export(tmp_path: Path) -> None:
    demo = create(tmp_path)
    leaked = "sk-" + "ant-" + "api03-" + "Q" * 24
    try:
        criteria.add_criterion(
            demo.folder, pcc_element=PccElement.CONTEXT, kind=CriterionKind.INCLUSION,
            text=f"Clé collée par erreur : {leaked}", now=demo.clock, tool_version=TOOL_VERSION,
        )  # fmt: skip
        criteria.activate_draft(
            demo.folder, rationale="Contexte ajouté.", now=demo.clock, tool_version=TOOL_VERSION
        )
        with pytest.raises(SecretInArchiveError) as raised:
            export_archive(demo.folder, now=demo.clock, tool_version=TOOL_VERSION)
    finally:
        demo.folder.close()
    message = str(raised.value)
    assert "donnees/criteres.csv" in message
    assert leaked not in message
    assert not list((demo.folder.path / "exports").glob("archive-*.zip"))
