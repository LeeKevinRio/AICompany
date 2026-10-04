"""Pure helpers behind the network guard in ``conftest.py``, importable by tests."""

from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlsplit


def proxy_ports() -> set[int]:
    """Ports of the HTTP(S) proxies the environment configures.

    A proxy listens on loopback, so a plain "loopback is fine" rule would let a
    real outbound request through it.
    """
    ports: set[int] = set()
    for name, value in os.environ.items():
        if not name.lower().endswith("_proxy") or name.lower() == "no_proxy" or not value:
            continue
        try:
            port = urlsplit(value if "://" in value else f"http://{value}").port
        except ValueError:
            continue
        if port is not None:
            ports.add(port)
    return ports


class NetworkBlockedError(OSError):
    """Raised by the socket guard when a test tries to reach outside the process."""


def is_blocked_address(address: object, family: int) -> bool:
    if family not in (socket.AF_INET, socket.AF_INET6) or not isinstance(address, tuple):
        return False  # AF_UNIX and friends never leave the machine
    host, port = address[0], address[1]
    try:
        loopback = ipaddress.ip_address(str(host)).is_loopback
    except ValueError:
        return True  # an unresolved host name: a resolver lookup is outside the process
    return not loopback or port in proxy_ports()
