"""Shared helpers for tests (importable thanks to pytest's ``pythonpath = ["tests"]``)."""

import sqlite3
from collections.abc import Callable, Iterator, Mapping
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pymupdf

from revue_portee.ai.base import ModelProvider
from revue_portee.ai.providers.fake import FakeProvider, Responder
from revue_portee.ai.settings import AITaskConfig
from revue_portee.storage.project_folder import ProjectFolder, create_project_folder

TOOL_VERSION = "0.0.0-test (abc123)"
START = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def make_clock(start: datetime = START) -> Callable[[], datetime]:
    """Deterministic clock: each call returns one second later than the previous one."""
    state = {"now": start}

    def now() -> datetime:
        state["now"] += timedelta(seconds=1)
        return state["now"]

    return now


def new_project(path: Path, clock: Callable[[], datetime] | None = None) -> ProjectFolder:
    return create_project_folder(
        path / "demo",
        title="Soutien à la parentalité et santé mentale des enfants",
        language="fr",
        reviewer_name="Benoit Plante",
        now=clock or make_clock(),
        tool_version=TOOL_VERSION,
    )


@contextmanager
def raw_sqlite(database: Path) -> Iterator[sqlite3.Connection]:
    """Direct access to a project database, bypassing the application (commit + close)."""
    with closing(sqlite3.connect(database)) as connection, connection:
        yield connection


def fake_factory(
    responders: Mapping[str, Responder], *, model_returned: str = "fake-model-2026-10-07"
) -> Callable[[AITaskConfig], ModelProvider]:
    """Provider factory for services and the web app: one FakeProvider per task, answering
    with the responder of that task (model names stay fictitious)."""

    def factory(config: AITaskConfig) -> ModelProvider:
        return FakeProvider(
            model=str(config.model),
            model_returned=model_returned,
            responder=lambda item: responders[type(item).__name__](item),
        )

    return factory


def make_pdf(
    pages: list[str],
    *,
    first_label: int | None = None,
    password: str | None = None,
) -> bytes:
    """A small PDF with one text per page (each line written as given); with
    ``first_label``, PDF page labels numbered from it."""
    document = pymupdf.open()  # type: ignore[no-untyped-call]
    for text in pages:
        page = document.new_page()
        page.insert_text((72, 72), text, fontsize=10)
    if first_label is not None:
        document.set_page_labels(  # type: ignore[no-untyped-call]
            [{"startpage": 0, "prefix": "", "style": "D", "firstpagenum": first_label}]
        )
    if password is None:
        data = document.tobytes()  # type: ignore[no-untyped-call]
    else:
        data = document.tobytes(  # type: ignore[no-untyped-call]
            encryption=pymupdf.PDF_ENCRYPT_AES_256,  # type: ignore[attr-defined]
            user_pw=password,
            owner_pw=password + "-owner",
        )
    document.close()  # type: ignore[no-untyped-call]
    return bytes(data)
