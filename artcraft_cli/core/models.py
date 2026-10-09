"""Generation models known to ArtCraft."""

from __future__ import annotations

from typing import Any

from artcraft_cli.utils import bridge

KINDS = ("image", "video")


def list_models(kind: str) -> dict[str, Any]:
    return bridge.rpc("models.list", {"kind": kind})
