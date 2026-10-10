"""Download safety: results stay in the download folder and never leave partial sets (spec §6.4)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import requests

from .conftest import FakeBridge, response

Run = Callable[..., tuple[int, str, str]]


def finished(job_id: str, *files: tuple[str, str]) -> dict[str, Any]:
    """A succeeded JobView whose result files are (media_token, cdn_url) pairs."""
    return {
        "job_id": job_id,
        "status": "succeeded",
        "terminal": True,
        "result": {
            "files": [{"media_token": token, "cdn_url": url} for token, url in files],
        },
    }


def error_of(out: str) -> dict[str, Any]:
    error: dict[str, Any] = json.loads(out)["error"]
    return error


@pytest.mark.parametrize("token", ["../escape", "/abs/escape", "nested/x", "", ".", ".."])
def test_hostile_media_tokens_never_write_outside_the_download_folder(
    fake_bridge: FakeBridge, run: Run, cdn: list[dict[str, Any]], tmp_path: Path, token: str
) -> None:
    out_dir = tmp_path / "downloads"
    out_dir.mkdir()
    before = sorted(p.name for p in tmp_path.iterdir())
    fake_bridge.on(
        "jobs.get",
        {"jobs": [finished("j1", (token, "https://cdn.example/x.png"))], "unresolved": []},
    )

    code, out, _ = run("--json", "jobs", "wait", "j1", "--download", str(out_dir))

    assert (code, error_of(out)["code"]) == (1, "download_failed")
    assert cdn == []
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    assert list(out_dir.iterdir()) == []


def test_force_cannot_replace_a_file_outside_the_download_folder(
    fake_bridge: FakeBridge, run: Run, cdn: list[dict[str, Any]], tmp_path: Path
) -> None:
    outside = tmp_path / "x.png"
    outside.write_bytes(b"keep me")
    out_dir = tmp_path / "downloads"
    out_dir.mkdir()
    fake_bridge.on(
        "jobs.get",
        {"jobs": [finished("j1", ("../x", "https://cdn.example/x.png"))], "unresolved": []},
    )

    code, out, _ = run("--json", "jobs", "wait", "j1", "--download", str(out_dir), "--force")

    assert (code, error_of(out)["code"]) == (1, "download_failed")
    assert outside.read_bytes() == b"keep me"
    assert cdn == []


def test_existing_destination_is_refused_before_any_file_is_fetched(
    fake_bridge: FakeBridge, run: Run, cdn: list[dict[str, Any]], tmp_path: Path
) -> None:
    out_dir = tmp_path / "downloads"
    out_dir.mkdir()
    (out_dir / "b1.png").write_bytes(b"keep me")
    fake_bridge.on(
        "jobs.get",
        {
            "jobs": [
                finished(
                    "j1",
                    ("a1", "https://cdn.example/a1.png"),
                    ("b1", "https://cdn.example/b1.png"),
                )
            ],
            "unresolved": [],
        },
    )

    code, out, _ = run("--json", "jobs", "wait", "j1", "--download", str(out_dir))

    assert (code, error_of(out)["code"]) == (1, "output_exists")
    assert cdn == []
    assert sorted(p.name for p in out_dir.iterdir()) == ["b1.png"]


def test_interrupted_multi_file_download_reports_the_files_already_saved(
    fake_bridge: FakeBridge, run: Run, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def first_ok_then_reset(url: str, **kwargs: Any) -> requests.Response:
        if url.endswith("a1.png"):
            return response(200, b"first file")
        raise requests.ConnectionError("connection reset by peer")

    monkeypatch.setattr(requests, "get", first_ok_then_reset)
    out_dir = tmp_path / "downloads"
    out_dir.mkdir()
    fake_bridge.on(
        "jobs.get",
        {
            "jobs": [
                finished(
                    "j1",
                    ("a1", "https://cdn.example/a1.png"),
                    ("b1", "https://cdn.example/b1.png"),
                )
            ],
            "unresolved": [],
        },
    )

    code, out, _ = run("--json", "jobs", "wait", "j1", "--download", str(out_dir))

    error = error_of(out)
    assert (code, error["code"]) == (1, "download_failed")
    assert error["details"]["downloaded"] == [str(out_dir / "a1.png")]
    assert sorted(p.name for p in out_dir.iterdir()) == ["a1.png"]
