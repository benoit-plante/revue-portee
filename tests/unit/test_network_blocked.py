import socket

import pytest


def test_ordinary_tests_cannot_open_connections() -> None:
    # 192.0.2.1 is TEST-NET-1 (RFC 5737): never routed, even if blocking failed.
    with pytest.raises(RuntimeError, match="Network is disabled"):
        socket.create_connection(("192.0.2.1", 80), timeout=0.1)
