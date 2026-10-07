"""Raw answers kept compressed in the project (ENF-TRA-03, ENF-REP-02,
docs/03-architecture.md §4): model calls in ``brut/ia/AAAA/MM/<ai_call_id>.json.gz``,
database APIs in ``brut/sources/<search_run_id>/page-0001.json.gz``."""

import gzip
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from pydantic import JsonValue

__all__ = [
    "raw_response_path",
    "read_raw_response",
    "read_source_pages",
    "remove_raw_response",
    "remove_source_pages",
    "source_raw_dir",
    "write_raw_response",
    "write_source_pages",
]


def raw_response_path(ai_call_id: str, created_at: datetime) -> str:
    """Path relative to the project folder (POSIX form, as stored in ``ai_call``)."""
    moment = created_at.astimezone(UTC)
    return str(PurePosixPath("brut", "ia", f"{moment:%Y}", f"{moment:%m}", f"{ai_call_id}.json.gz"))


def write_raw_response(
    folder: Path, ai_call_id: str, created_at: datetime, response: JsonValue
) -> str:
    """Store ``response`` (never overwritten) and return its relative path."""
    relative = raw_response_path(ai_call_id, created_at)
    target = folder.joinpath(*PurePosixPath(relative).parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(response, ensure_ascii=False, sort_keys=True).encode("utf-8")
    with target.open("xb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        gz.write(data)
    return relative


def read_raw_response(folder: Path, relative: str) -> JsonValue:
    target = folder.joinpath(*PurePosixPath(relative).parts)
    with gzip.open(target, "rb") as gz:
        value: JsonValue = json.loads(gz.read().decode("utf-8"))
    return value


def remove_raw_response(folder: Path, relative: str) -> None:
    """Remove a raw response whose call could not be recorded (no orphan file)."""
    folder.joinpath(*PurePosixPath(relative).parts).unlink(missing_ok=True)


def source_raw_dir(search_run_id: str) -> str:
    """Folder of the raw answers of one search run or check: ``brut/sources/<id>``."""
    return str(PurePosixPath("brut", "sources", search_run_id))


def write_source_pages(folder: Path, search_run_id: str, pages: Sequence[JsonValue]) -> str:
    """Store the raw answers of a database API (never overwritten), one file per answer:
    ``brut/sources/<id>/page-0001.json.gz``. Returns the folder, relative."""
    relative = source_raw_dir(search_run_id)
    target = folder.joinpath(*PurePosixPath(relative).parts)
    target.mkdir(parents=True, exist_ok=False)
    for number, page in enumerate(pages, start=1):
        data = json.dumps(page, ensure_ascii=False, sort_keys=True).encode("utf-8")
        path = target / f"page-{number:04d}.json.gz"
        with path.open("xb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
            gz.write(data)
    return relative


def read_source_pages(folder: Path, relative: str) -> list[JsonValue]:
    target = folder.joinpath(*PurePosixPath(relative).parts)
    pages: list[JsonValue] = []
    for path in sorted(target.glob("page-*.json.gz")):
        with gzip.open(path, "rb") as gz:
            pages.append(json.loads(gz.read().decode("utf-8")))
    return pages


def remove_source_pages(folder: Path, relative: str) -> None:
    """Remove the answers of a run that could not be recorded (no orphan folder)."""
    target = folder.joinpath(*PurePosixPath(relative).parts)
    for path in target.glob("page-*.json.gz"):
        path.unlink()
    if target.exists():
        target.rmdir()
