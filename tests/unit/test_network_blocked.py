import asyncio
import os
import socket

import pytest

from conftest import PROXY_VARIABLES


def test_ordinary_tests_cannot_open_connections() -> None:
    # 192.0.2.1 is TEST-NET-1 (RFC 5737): never routed, even if blocking failed.
    with pytest.raises(RuntimeError, match="Network is disabled"):
        socket.create_connection(("192.0.2.1", 80), timeout=0.1)


@pytest.mark.parametrize("host", ["127.0.0.2", "::1"])
def test_only_the_loopback_address_is_open(host: str) -> None:
    with pytest.raises(RuntimeError, match="Network is disabled"):
        socket.create_connection((host, 80), timeout=0.1)


def test_the_loopback_address_is_open() -> None:
    with (
        socket.create_server(("127.0.0.1", 0)) as server,
        socket.create_connection(server.getsockname(), timeout=1),
    ):
        pass


def test_an_event_loop_can_be_created() -> None:
    # On Windows, the event loop connects an internal socket pair through 127.0.0.1.
    asyncio.run(asyncio.sleep(0))


def test_proxy_variables_are_removed() -> None:
    assert not any(name in os.environ for name in PROXY_VARIABLES)
