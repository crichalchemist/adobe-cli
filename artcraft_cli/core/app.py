"""Bridge status and app information."""

from __future__ import annotations

from typing import Any

from artcraft_cli.utils import bridge


def ping() -> dict[str, Any]:
    """Health plus discovery: what `artcraft-cli ping` prints (never the token)."""
    health = bridge.health()
    discovery = bridge.read_discovery()  # after health, so a retried port is reported
    return {
        "bridge": {
            "port": discovery["port"],
            "pid": discovery["pid"],
            "app_version": health["app_version"],
            "protocol": health["bridge_protocol_version"],
        },
        "readiness": health["readiness"],
        "ops": health["ops"],
    }


def info() -> dict[str, Any]:
    return bridge.rpc("app.info", {})
