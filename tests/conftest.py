"""Shared test configuration.

- Every test that is not marked ``integration`` runs with network access blocked
  (pytest-recording ``block_network``); cassettes are read-only (``--record-mode=none``).
  Only the loopback address stays open, because asyncio on Windows builds the internal
  socket pair of its event loop with a TCP connection to 127.0.0.1; proxy variables are
  removed so that no request can leave through a local proxy.
- Cassettes are recorded with credentials and contact parameters replaced by
  fictitious values (ENF-SEC-04).
- A full run fails when a package listed in ``coverage_gate_packages`` is below
  ``coverage_gate_fail_under`` (see ``tests/_plugins/coverage_gate.py``).
"""

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx2
import pytest
from pydantic import SecretStr

from recording import cassette_client
from revue_portee.config.secrets import SecretName, forget_loaded_secrets, get_secret

pytest_plugins = ["_plugins.coverage_gate"]

FAKE_TOKEN = "DUMMY"
FAKE_EMAIL = "contact@example.org"


CASSETTES = Path(__file__).parent / "cassettes"

# Regexes matched from the start of the host by pytest-recording.
LOOPBACK_ONLY = [r"127\.0\.0\.1$"]
PROXY_VARIABLES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


def _record_mode(config: pytest.Config) -> str:
    return str(config.getoption("--record-mode") or "none")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    recording = _record_mode(config) != "none"
    for item in items:
        if item.get_closest_marker("integration") is not None:
            continue
        if recording and item.get_closest_marker("cassette") is not None:
            continue  # recording a cassette calls the real service
        item.add_marker(pytest.mark.block_network(allowed_hosts=LOOPBACK_ONLY))


@pytest.fixture(autouse=True)
def _no_proxy_while_blocked(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A proxy on the loopback address would otherwise reach the real network."""
    if request.node.get_closest_marker("block_network") is not None:
        for name in PROXY_VARIABLES:
            monkeypatch.delenv(name, raising=False)


@pytest.fixture
def http_cassette(request: pytest.FixtureRequest) -> Iterator[httpx2.Client]:
    """Client replaying ``tests/cassettes/<module>/<test>.json`` (see tests/recording.py).

    Only for tests marked ``cassette``; recording happens with ``--record-mode=once``."""
    if request.node.get_closest_marker("cassette") is None:
        raise pytest.UsageError("http_cassette requires @pytest.mark.cassette")
    module = request.node.module.__name__.rsplit(".", 1)[-1]
    path = CASSETTES / module / f"{request.node.name}.json"
    mode = _record_mode(request.config)
    forbidden: tuple[str, ...] = ()
    if mode != "none":
        forbidden = (get_secret(SecretName.CONTACT_EMAIL).get_secret_value(),)
    with cassette_client(path, mode, forbidden=forbidden) as client:
        yield client


@pytest.fixture
def contact_email(request: pytest.FixtureRequest) -> SecretStr:
    """The real contact address while recording, a fictitious one otherwise."""
    if _record_mode(request.config) != "none":
        return get_secret(SecretName.CONTACT_EMAIL)
    return SecretStr(FAKE_EMAIL)


@pytest.fixture(scope="module")
def vcr_config() -> dict[str, Any]:
    return {
        "filter_headers": [
            ("authorization", FAKE_TOKEN),
            ("x-api-key", FAKE_TOKEN),
            ("api-key", FAKE_TOKEN),
        ],
        "filter_query_parameters": [
            ("api_key", FAKE_TOKEN),
            ("email", FAKE_EMAIL),
            ("mailto", FAKE_EMAIL),
        ],
        "filter_post_data_parameters": [
            ("api_key", FAKE_TOKEN),
            ("email", FAKE_EMAIL),
            ("mailto", FAKE_EMAIL),
        ],
        "decode_compressed_response": True,
    }


@pytest.fixture(autouse=True)
def _forget_secrets() -> Iterator[None]:
    factory = logging.getLogRecordFactory()
    yield
    forget_loaded_secrets()
    logging.setLogRecordFactory(factory)  # undo install_secret_redaction()
