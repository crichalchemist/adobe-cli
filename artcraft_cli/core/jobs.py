"""Generation jobs: list, get, wait, download results, dismiss."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from artcraft_cli.core import media
from artcraft_cli.errors import CliError
from artcraft_cli.utils import bridge

DEFAULT_WAIT_TIMEOUT_S = 900.0
POLL_INTERVAL_S = 5.0
REMOTE_INTERVAL_S = 60.0
FAILED_STATUSES = frozenset({"failed", "cancelled"})
KEEP_POLLING_REASONS = frozenset({"rate_limited", "upstream_unavailable", "credentials_not_synced"})


def list_jobs(*, all_origins: bool, remote: bool, limit: int) -> dict[str, Any]:
    return bridge.rpc(
        "jobs.list",
        {"origin": "all" if all_origins else "cli", "limit": limit, "include_remote": remote},
    )


def get_jobs(job_ids: list[str], *, remote: bool) -> dict[str, Any]:
    return bridge.rpc("jobs.get", {"job_ids": job_ids, "include_remote": remote})


def wait_for_jobs(job_ids: list[str], *, timeout_s: float) -> list[dict[str, Any]]:
    """Poll every 5 s; ask the server at most once a minute, plus one final time."""
    start = time.monotonic()
    last_remote: float | None = None
    finishing = False
    while True:
        now = time.monotonic()
        use_remote = finishing or last_remote is None or now - last_remote >= REMOTE_INTERVAL_S
        seen = get_jobs(job_ids, remote=use_remote)
        if use_remote:
            last_remote = now
        _raise_if_failed(seen, after_remote=use_remote)
        done = _all_succeeded(seen, job_ids)
        if done and use_remote:
            return list(seen["jobs"])
        finishing = done  # one final remote call expands batches before returning
        if not finishing and time.monotonic() - start + POLL_INTERVAL_S > timeout_s:
            raise CliError(
                "job_wait_timeout", f"jobs unfinished after {timeout_s:g} s", {"last_seen": seen}
            )
        time.sleep(POLL_INTERVAL_S)


def _raise_if_failed(seen: dict[str, Any], *, after_remote: bool) -> None:
    for job in seen["jobs"]:
        if job["status"] in FAILED_STATUSES:
            raise CliError(
                "job_failed",
                f"job {job['job_id']} {job['status']}",
                {"status": job["status"], "job": job},
            )
    if after_remote:
        stuck = [u for u in seen["unresolved"] if u["reason"] not in KEEP_POLLING_REASONS]
        if stuck:
            raise CliError(
                stuck[0]["reason"],
                f"cannot resolve job {stuck[0]['job_id']}: {stuck[0]['reason']}",
                {"unresolved": seen["unresolved"]},
            )


def _all_succeeded(seen: dict[str, Any], job_ids: list[str]) -> bool:
    jobs = seen["jobs"]
    return (
        not seen["unresolved"]
        and {job["job_id"] for job in jobs} == set(job_ids)
        and all(job["status"] == "succeeded" for job in jobs)
    )


def download_files(
    finished: list[dict[str, Any]], out_dir: Path, *, force: bool
) -> list[dict[str, str]]:
    """Download every result file of finished jobs into out_dir."""
    downloads: list[dict[str, str]] = []
    for job in finished:
        result = job.get("result") or {}
        for file in result.get("files", []):
            path, _ = media.download_to(
                file["media_token"], file.get("cdn_url"), out_dir, force=force
            )
            downloads.append({"media_token": file["media_token"], "path": str(path)})
    return downloads
