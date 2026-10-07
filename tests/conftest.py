"""Shared test configuration.

- Every test that is not marked ``integration`` runs with network access blocked
  (pytest-recording ``block_network``); cassettes are read-only (``--record-mode=none``).
- Cassettes are recorded with credentials and contact parameters replaced by
  fictitious values (ENF-SEC-04).
"""

from collections.abc import Iterator
from typing import Any

import pytest

from revue_portee.config.secrets import forget_loaded_secrets

FAKE_TOKEN = "DUMMY"
FAKE_EMAIL = "contact@example.org"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if item.get_closest_marker("integration") is None:
            item.add_marker(pytest.mark.block_network)


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
    yield
    forget_loaded_secrets()
