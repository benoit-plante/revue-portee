"""HTTP access to bibliographic APIs: client, rate limiting, retries, clear errors.

Every connector receives an ``httpx2.Client`` (tests give one whose transport replays
recorded responses). Errors are raised as :class:`SourceError` with a French message
that names the service, never a key or an address (docs/03-architecture.md §8).
"""

import json
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx2

from revue_portee import __version__
from revue_portee.i18n import gettext as _

__all__ = [
    "MAX_PDF_BYTES",
    "NotAPdfError",
    "PdfTooLargeError",
    "RateLimiter",
    "SourceAccessError",
    "SourceAnswer",
    "SourceError",
    "SourceInvalidAnswerError",
    "SourceUnreachableError",
    "chunks",
    "get_json",
    "get_pdf",
    "get_text",
    "make_client",
    "merge_answers",
]

USER_AGENT = f"revue-portee/{__version__} (+https://github.com/benoit-plante/revue-portee)"
_RETRY_STATUSES = {429, 500, 502, 503, 504}


@dataclass(frozen=True, slots=True)
class SourceAnswer:
    """What a database answered: number of records, identifiers asked for, raw JSON."""

    count: int
    ids: tuple[str, ...]
    raw: dict[str, Any]


def chunks(values: Sequence[str], size: int) -> list[Sequence[str]]:
    """``values`` cut into consecutive lists of at most ``size`` items."""
    return [values[i : i + size] for i in range(0, len(values), size)]


def merge_answers(answers: Sequence[SourceAnswer]) -> SourceAnswer:
    """One answer for several requests on parts of an identifier list."""
    if len(answers) == 1:
        return answers[0]
    return SourceAnswer(
        count=sum(a.count for a in answers),
        ids=tuple(i for a in answers for i in a.ids),
        raw={"pages": [a.raw for a in answers]},
    )


class SourceError(RuntimeError):
    """A bibliographic service could not answer (French message for the interface)."""


class SourceUnreachableError(SourceError):
    def __init__(self, service: str, host: str) -> None:
        super().__init__(
            _(
                "{service} cannot be reached: check the network connection (the domain "
                "{host} must be allowed in the environment)."
            ).format(service=service, host=host)
        )


class SourceAccessError(SourceError):
    def __init__(self, service: str, status: int) -> None:
        self.status = status
        super().__init__(
            _("{service} refused the request (HTTP error {status}).").format(
                service=service, status=status
            )
        )


class SourceInvalidAnswerError(SourceError):
    def __init__(self, service: str) -> None:
        super().__init__(_("{service} sent an answer that cannot be read.").format(service=service))


class NotAPdfError(SourceError):
    def __init__(self, host: str) -> None:
        super().__init__(
            _("The file sent by {host} is not a PDF (often a web page asking to sign in).").format(
                host=host
            )
        )


class PdfTooLargeError(SourceError):
    def __init__(self, host: str, limit: int) -> None:
        super().__init__(
            _("The file sent by {host} is larger than {limit} MB.").format(
                host=host, limit=limit // 1_000_000
            )
        )


@dataclass
class RateLimiter:
    """At most one request every ``interval`` seconds (per service), across threads."""

    interval: float
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    _last: float | None = field(default=None, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def wait(self) -> None:
        with self._lock:
            if self._last is not None:
                delay = self._last + self.interval - self.clock()
                if delay > 0:
                    self.sleep(delay)
            self._last = self.clock()


def make_client(*, timeout: float = 30.0) -> httpx2.Client:
    """Client for the real services (environment proxy and certificates honoured)."""
    return httpx2.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}, trust_env=True)


def get_text(
    client: httpx2.Client,
    url: str,
    params: Mapping[str, str],
    *,
    service: str,
    limiter: RateLimiter,
    retries: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """GET ``url`` and return its text.

    429, 5xx, timeouts and connections cut during the answer are retried with exponential
    backoff; every failure ends as a :class:`SourceError` with a French message."""
    host = httpx2.URL(url).host
    for attempt in range(retries + 1):
        last = attempt == retries
        limiter.wait()
        try:
            response = client.get(url, params=dict(params))
        except (httpx2.ConnectError, httpx2.ProxyError, httpx2.UnsupportedProtocol) as error:
            raise SourceUnreachableError(service, host) from error
        except httpx2.TransportError as error:  # timeouts, read and protocol errors
            if last:
                raise SourceUnreachableError(service, host) from error
            sleep(2**attempt)
            continue
        if response.status_code in _RETRY_STATUSES and not last:
            sleep(2**attempt)
            continue
        if response.status_code >= 400:
            raise SourceAccessError(service, response.status_code)
        return response.text
    raise AssertionError("unreachable")  # pragma: no cover - the loop returns or raises


def get_json(
    client: httpx2.Client,
    url: str,
    params: Mapping[str, str],
    *,
    service: str,
    limiter: RateLimiter,
    retries: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:  # noqa: ANN401 - JSON documents are untyped until read by the connector
    """GET ``url`` and decode its JSON object (see :func:`get_text`)."""
    text = get_text(
        client, url, params, service=service, limiter=limiter, retries=retries, sleep=sleep
    )
    try:
        document = json.loads(text)
    except ValueError as error:
        raise SourceInvalidAnswerError(service) from error
    if not isinstance(document, dict):
        raise SourceInvalidAnswerError(service)
    return document


MAX_PDF_BYTES = 100_000_000


def get_pdf(
    client: httpx2.Client,
    url: str,
    *,
    limiter: RateLimiter,
    max_bytes: int = MAX_PDF_BYTES,
    retries: int = 2,
    sleep: Callable[[float], None] = time.sleep,
) -> bytes:
    """Download the PDF at ``url`` (redirects followed, http and https only).

    Retried like :func:`get_text`; a file that does not start like a PDF, or larger
    than ``max_bytes``, ends as a :class:`SourceError` naming the host."""
    parsed = httpx2.URL(url)
    host = parsed.host or url
    if parsed.scheme not in ("http", "https"):
        raise NotAPdfError(host)
    for attempt in range(retries + 1):
        last = attempt == retries
        limiter.wait()
        data = bytearray()
        try:
            with client.stream("GET", url, follow_redirects=True) as response:
                if response.status_code in _RETRY_STATUSES and not last:
                    sleep(2**attempt)
                    continue
                if response.status_code >= 400:
                    raise SourceAccessError(host, response.status_code)
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > max_bytes:
                        raise PdfTooLargeError(host, max_bytes)
        except (httpx2.ConnectError, httpx2.ProxyError, httpx2.UnsupportedProtocol) as error:
            raise SourceUnreachableError(host, host) from error
        except httpx2.TransportError as error:  # timeouts, read and protocol errors
            if last:
                raise SourceUnreachableError(host, host) from error
            sleep(2**attempt)
            continue
        if not bytes(data[:1024]).lstrip().startswith(b"%PDF-"):
            raise NotAPdfError(host)
        return bytes(data)
    raise AssertionError("unreachable")  # pragma: no cover - the loop returns or raises
