"""Raw responses of model calls, kept compressed in the project (ENF-TRA-03):
``brut/ia/AAAA/MM/<ai_call_id>.json.gz`` (docs/03-architecture.md §4)."""

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from pydantic import JsonValue

__all__ = ["raw_response_path", "read_raw_response", "write_raw_response"]


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
