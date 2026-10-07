"""Recorded HTTP answers for the bibliographic connectors (httpx2).

vcrpy does not patch ``httpx2``, so the connectors are tested against a project-specific
cassette: a JSON file of request and response pairs, under ``tests/cassettes/``.

- Replay (``--record-mode=none``, the default): a transport answers each request from
  the cassette, matched on method and URL (query parameters sorted, contact parameters
  filtered); an unknown request fails the test.
- Recording (``--record-mode=once`` with no cassette yet, or ``all``): a real client,
  which honours the environment proxy and certificates, sends the requests, and the
  answers are written with ``api_key``, ``email`` and ``mailto`` replaced by
  fictitious values; only the ``content-type`` header is kept.
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx2

from revue_portee.sources.http import USER_AGENT

FAKE_TOKEN = "DUMMY"
FAKE_EMAIL = "contact@example.org"
_FILTERED = {"api_key": FAKE_TOKEN, "email": FAKE_EMAIL, "mailto": FAKE_EMAIL}


def request_key(method: str, url: httpx2.URL) -> str:
    params: list[tuple[str, str | int | float | bool | None]] = sorted(
        (k, _FILTERED.get(k, v)) for k, v in url.params.multi_items()
    )
    return f"{method} {url.copy_with(query=None)}?{httpx2.QueryParams(params)}"


class CassetteMissError(AssertionError):
    pass


class ReplayTransport(httpx2.BaseTransport):
    def __init__(self, interactions: list[dict[str, Any]]) -> None:
        self._answers: dict[str, list[dict[str, Any]]] = {}
        for interaction in interactions:
            self._answers.setdefault(interaction["request"], []).append(interaction["response"])
        self._used: dict[str, int] = {}

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        key = request_key(request.method, request.url)
        answers = self._answers.get(key)
        if not answers:
            raise CassetteMissError(f"request absent from the cassette: {key}")
        index = self._used.get(key, 0)
        self._used[key] = index + 1
        answer = answers[min(index, len(answers) - 1)]
        return httpx2.Response(
            answer["status"],
            headers={"content-type": answer.get("content_type", "application/json")},
            content=answer["body"].encode("utf-8"),
            request=request,
        )


def _should_record(path: Path, record_mode: str) -> bool:
    if record_mode == "none":
        return False
    return record_mode in {"all", "rewrite"} or not path.exists()


@contextmanager
def cassette_client(
    path: Path, record_mode: str, *, forbidden: tuple[str, ...] = ()
) -> Iterator[httpx2.Client]:
    """A client replaying ``path``, or recording into it when the mode asks so.

    ``forbidden`` holds the secret values used while recording: the cassette is not
    written if one of them appears in it."""
    if not _should_record(path, record_mode):
        if not path.exists():
            raise CassetteMissError(
                f"no cassette {path.name}: record it with "
                "`uv run pytest <test> --record-mode=once` (calls the real service)"
            )
        interactions = json.loads(path.read_text(encoding="utf-8"))
        with httpx2.Client(transport=ReplayTransport(interactions)) as client:
            yield client
        return
    recorded: list[dict[str, Any]] = []

    def keep(response: httpx2.Response) -> None:
        response.read()
        recorded.append(
            {
                "request": request_key(response.request.method, response.request.url),
                "response": {
                    "status": response.status_code,
                    "content_type": response.headers.get("content-type", ""),
                    "body": response.text,
                },
            }
        )

    with httpx2.Client(
        timeout=60.0,
        headers={"User-Agent": USER_AGENT},
        trust_env=True,
        event_hooks={"response": [keep]},
    ) as client:
        yield client
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(recorded, ensure_ascii=False, indent=1) + "\n"
    if any(secret and secret in text for secret in forbidden):
        raise AssertionError("a secret value appears in the recorded answers: not written")
    path.write_text(text, encoding="utf-8")
