"""Generation jobs: list, get, wait, download results, dismiss."""

from __future__ import annotations

from typing import Any

from artcraft_cli.utils import bridge


def list_jobs(*, all_origins: bool, remote: bool, limit: int) -> dict[str, Any]:
    return bridge.rpc(
        "jobs.list",
        {"origin": "all" if all_origins else "cli", "limit": limit, "include_remote": remote},
    )
