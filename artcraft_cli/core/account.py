"""ArtCraft account state."""

from __future__ import annotations

from typing import Any

from artcraft_cli.utils import bridge


def whoami() -> dict[str, Any]:
    return bridge.rpc("account.session", {})
