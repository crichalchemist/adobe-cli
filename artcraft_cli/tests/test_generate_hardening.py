"""generate outcomes after a paid submit: the token and the job ids must come back on failure."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from .conftest import FakeBridge

Run = Callable[..., tuple[int, str, str]]
TOKEN = "0b8f6a52-6a8e-4d55-9d43-3d6c0f6f1a10"
SUBMIT = [
    "--json", "generate", "image", "--model", "m", "--prompt", "x",
    "--max-credits", "5", "--idempotency-token", TOKEN,
]  # fmt: skip


def job(job_id: str, status: str, files: list[str] | None = None) -> dict[str, Any]:
    """A JobView (spec §7.6) with the fields the CLI reads."""
    return {
        "job_id": job_id,
        "status": status,
        "terminal": status in ("succeeded", "failed", "cancelled"),
        "result": {
            "files": [
                {"media_token": token, "cdn_url": f"https://cdn.example/{token}.png"}
                for token in files or []
            ],
            "batch_token": None,
        }
        if status == "succeeded"
        else None,
        "failure": {"category": "model", "message": "nsfw"} if status == "failed" else None,
    }


def jobs_seen(*views: dict[str, Any]) -> dict[str, Any]:
    return {"jobs": list(views), "unresolved": []}


def error_of(out: str) -> dict[str, Any]:
    error: dict[str, Any] = json.loads(out)["error"]
    return error


def test_wait_returns_the_finished_jobs_after_submit(fake_bridge: FakeBridge, run: Run) -> None:
    fake_bridge.on("generate.submit", {"job_ids": ["j1"]})
    fake_bridge.on("jobs.get", jobs_seen(job("j1", "succeeded", ["a1"])))

    code, out, _ = run(*SUBMIT, "--wait")

    assert code == 0
    body = json.loads(out)
    assert [view["job_id"] for view in body["jobs"]] == ["j1"]
    assert "downloads" not in body


def test_download_alone_waits_then_saves_every_result_file(
    fake_bridge: FakeBridge, run: Run, cdn: list[dict[str, Any]], tmp_path: Path
) -> None:
    fake_bridge.on("generate.submit", {"job_ids": ["j1"]})
    fake_bridge.on("jobs.get", jobs_seen(job("j1", "succeeded", ["a1", "a2"])))

    code, out, _ = run(*SUBMIT, "--download", str(tmp_path))

    assert code == 0
    body = json.loads(out)
    assert [Path(item["path"]).name for item in body["downloads"]] == ["a1.png", "a2.png"]
    assert [view["job_id"] for view in body["jobs"]] == ["j1"]
    assert (tmp_path / "a1.png").read_bytes().startswith(b"image-bytes:")
    assert fake_bridge.args("jobs.get")


def test_job_failure_after_submit_reports_token_and_job_ids(
    fake_bridge: FakeBridge, run: Run
) -> None:
    fake_bridge.on("generate.submit", {"job_ids": ["j1"]})
    fake_bridge.on("jobs.get", jobs_seen(job("j1", "failed")))

    code, out, _ = run(*SUBMIT, "--wait")

    assert code == 1
    error = error_of(out)
    assert error["code"] == "job_failed"
    assert error["details"]["idempotency_token"] == TOKEN
    assert error["details"]["job_ids"] == ["j1"]


def test_download_failure_after_submit_reports_token_and_job_ids(
    fake_bridge: FakeBridge, run: Run, cdn: list[dict[str, Any]], tmp_path: Path
) -> None:
    done = job("j1", "succeeded", ["a1"])
    done["result"]["files"][0]["cdn_url"] = "http://cdn.example/a1.png"
    fake_bridge.on("generate.submit", {"job_ids": ["j1"]})
    fake_bridge.on("jobs.get", jobs_seen(done))

    code, out, _ = run(*SUBMIT, "--download", str(tmp_path))

    assert code == 1
    error = error_of(out)
    assert error["code"] == "download_failed"
    assert error["details"]["idempotency_token"] == TOKEN
    assert error["details"]["job_ids"] == ["j1"]


def test_unwritable_download_dir_refused_before_submit_has_no_job_ids(
    fake_bridge: FakeBridge, run: Run, tmp_path: Path
) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        code, out, _ = run(*SUBMIT, "--download", str(locked))
    finally:
        locked.chmod(0o700)

    assert code == 1
    assert error_of(out)["details"] == {"idempotency_token": TOKEN}
    assert fake_bridge.calls == []


def test_malformed_jobs_reply_after_paid_submit_still_reports_token_and_job_ids(
    fake_bridge: FakeBridge, run: Run
) -> None:
    fake_bridge.on("generate.submit", {"job_ids": ["j1"]})
    fake_bridge.on("jobs.get", {"jobs": [job("j1", "running")]})

    code, out, _ = run(*SUBMIT, "--wait")

    assert code == 1
    assert out.count("\n") == 1
    error = error_of(out)
    assert error["code"] == "bridge_protocol_error"
    assert error["details"]["idempotency_token"] == TOKEN
    assert error["details"]["job_ids"] == ["j1"]


@pytest.mark.parametrize("reply", [{}, {"job_ids": []}, {"job_ids": "j1"}, {"job_ids": [1]}])
def test_submit_reply_without_job_ids_reports_protocol_error_with_token(
    fake_bridge: FakeBridge, run: Run, reply: dict[str, Any]
) -> None:
    fake_bridge.on("generate.submit", reply)

    code, out, _ = run(*SUBMIT)

    assert code == 1
    error = error_of(out)
    assert error["code"] == "bridge_protocol_error"
    assert error["message"] == "generate.submit reply has no job_ids"
    assert error["details"]["idempotency_token"] == TOKEN


def test_interrupt_during_submit_reports_outcome_unknown_with_token(
    fake_bridge: FakeBridge, run: Run
) -> None:
    fake_bridge.on("generate.submit", KeyboardInterrupt())

    code, out, _ = run(*SUBMIT)

    assert code == 1
    error = error_of(out)
    assert error["code"] == "outcome_unknown"
    assert error["details"]["reason"] == "connection_lost"
    assert error["details"]["idempotency_token"] == TOKEN


def test_interrupt_while_waiting_reports_token_and_job_ids(
    fake_bridge: FakeBridge, run: Run
) -> None:
    fake_bridge.on("generate.submit", {"job_ids": ["j1"]})
    fake_bridge.on("jobs.get", KeyboardInterrupt())

    code, out, _ = run(*SUBMIT, "--wait")

    assert code == 1
    error = error_of(out)
    assert error["code"] == "job_wait_timeout"
    assert error["details"]["idempotency_token"] == TOKEN
    assert error["details"]["job_ids"] == ["j1"]


def test_human_mode_error_after_paid_submit_shows_token_and_job_ids(
    fake_bridge: FakeBridge, run: Run
) -> None:
    fake_bridge.on("generate.submit", {"job_ids": ["j1"]})
    fake_bridge.on("jobs.get", jobs_seen(job("j1", "running")))
    argv = [arg for arg in SUBMIT if arg != "--json"]

    code, _, err = run(*argv, "--wait", "--timeout", "1")

    assert code == 1
    details = [line for line in err.splitlines() if line.startswith("details: ")]
    assert len(details) == 1
    assert TOKEN in details[0]
    assert '"job_ids":["j1"]' in details[0]
