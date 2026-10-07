"""HTTP access to bibliographic APIs: client, rate limiting, retries, clear errors.

Every connector receives an ``httpx2.Client`` (tests give one whose transport replays
recorded responses). Errors are raised as :class:`SourceError` with a French message
that names the service, never a key or an address (docs/03-architecture.md §8).
"""

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx2

from revue_portee import __version__
from revue_portee.i18n import gettext as _

__all__ = [
    "RateLimiter",
    "SourceAccessError",
    "SourceError",
    "SourceUnreachableError",
    "get_json",
    "make_client",
]

USER_AGENT = f"revue-portee/{__version__} (+https://github.com/benoit-plante/revue-portee)"
_RETRY_STATUSES = {429, 500, 502, 503, 504}


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
        super().__init__(
            _("{service} refused the request (HTTP error {status}).").format(
                service=service, status=status
            )
        )


@dataclass
class RateLimiter:
    """At most one request every ``interval`` seconds (per service)."""

    interval: float
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    _last: float | None = field(default=None, init=False)

    def wait(self) -> None:
        if self._last is not None:
            delay = self._last + self.interval - self.clock()
            if delay > 0:
                self.sleep(delay)
        self._last = self.clock()


def make_client(*, timeout: float = 30.0) -> httpx2.Client:
    """Client for the real services (environment proxy and certificates honoured)."""
    return httpx2.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}, trust_env=True)


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
    """GET ``url`` and decode its JSON, retrying on 429 and 5xx with exponential backoff."""
    host = httpx2.URL(url).host
    for attempt in range(retries + 1):
        limiter.wait()
        try:
            response = client.get(url, params=dict(params))
        except (httpx2.ConnectError, httpx2.ProxyError) as error:
            raise SourceUnreachableError(service, host) from error
        except httpx2.TimeoutException as error:
            if attempt == retries:
                raise SourceUnreachableError(service, host) from error
            sleep(2**attempt)
            continue
        if response.status_code in _RETRY_STATUSES and attempt < retries:
            sleep(2**attempt)
            continue
        if response.status_code >= 400:
            raise SourceAccessError(service, response.status_code)
        return response.json()
    raise SourceAccessError(service, response.status_code)  # pragma: no cover - loop returns
