"""ArtCraft app preferences."""

from __future__ import annotations

from typing import Any

from artcraft_cli.utils import bridge

WRITABLE = ("play_sounds", "auto_download")


def get() -> dict[str, Any]:
    return bridge.rpc("settings.get", {})


def set_preference(preference: str, value: bool) -> dict[str, Any]:
    return bridge.rpc("settings.set", {"preference": preference, "value": value})
