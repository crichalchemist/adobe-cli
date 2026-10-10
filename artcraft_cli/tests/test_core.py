"""CLI behaviour through the real entry point, faking only the HTTP boundary (spec §6)."""

from __future__ import annotations

import io
import itertools
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import requests

from .conftest import HEALTH, FakeBridge, FakeClock, op_error

Run = Callable[..., tuple[int, str, str]]
TOKEN_A = "0b8f6a52-6a8e-4d55-9d43-3d6c0f6f1a10"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
ESTIMATE = {
    "modality": "image",
    "model": "m",
    "estimate": {"cost_in_credits": 4, "is_free": False, "is_unlimited": False},
    "effective_credits": 4,
}


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


def jobs_seen(*views: dict[str, Any], unresolved: list[dict[str, str]] | None = None) -> Any:
    return {"jobs": list(views), "unresolved": unresolved or []}


def error_of(out: str) -> dict[str, Any]:
    body = json.loads(out)
    assert set(body) == {"error"}
    error: dict[str, Any] = body["error"]
    return error


# --- Output contract (spec §6.1) -------------------------------------------------------


def test_cli_without_subcommand_prints_help(run: Run) -> None:
    code, out, _ = run()
    assert code == 0
    assert "Usage: artcraft-cli" in out


def test_json_success_is_one_compact_object_without_error_key(
    fake_bridge: FakeBridge, run: Run
) -> None:
    fake_bridge.on("health", HEALTH)
    code, out, err = run("--json", "ping")

    assert (code, err) == (0, "")
    assert out.count("\n") == 1
    body = json.loads(out)
    assert "error" not in body
    assert out.strip() == json.dumps(body, separators=(",", ":"))
    assert body["bridge"] == {
        "port": 50001,
        "pid": os.getpid(),
        "app_version": "0.41.0",
        "protocol": 1,
    }


def test_json_errors_are_objects_on_stdout_with_exit_1(run: Run) -> None:
    code, out, err = run("--json", "ping")

    assert (code, err) == (1, "")
    error = error_of(out)
    assert error["code"] == "bridge_not_running"
    assert error["retryable"] is True
    assert "ARTCRAFT_CLI_BRIDGE=1" in error["hint"]


def test_human_errors_go_to_stderr(run: Run) -> None:
    code, out, err = run("ping")

    assert (code, out) == (1, "")
    assert err.startswith("error[bridge_not_running]: ")
    assert "\nhint: start ArtCraft with ARTCRAFT_CLI_BRIDGE=1" in err


@pytest.mark.parametrize(
    "argv",
    [
        ["nope"],
        ["models", "list"],
        ["jobs"],
        ["generate", "image"],
        ["jobs", "list", "--limit", "0"],
        ["generate", "image", "--model", "m", "--max-credits", "5", "--idempotency-token", "nope"],
        [
            "generate",
            "image",
            "--model",
            "m",
            "--max-credits",
            "5",
            "--idempotency-token",
            TOKEN_A.upper(),
        ],
    ],
)
def test_usage_errors_render_as_json_with_exit_1(run: Run, argv: list[str]) -> None:
    code, out, err = run("--json", *argv)
    assert (code, err) == (1, "")
    assert error_of(out)["code"] == "usage_error"


# --- generate: request building and --dry-run (spec §6.3) ------------------------------


@pytest.mark.parametrize(
    "spend_flags", [[], ["--max-credits", "5", "--dry-run"]], ids=["neither", "both"]
)
def test_spend_without_max_credits_is_refused_before_any_rpc(
    fake_bridge: FakeBridge, run: Run, spend_flags: list[str]
) -> None:
    code, out, _ = run("--json", "generate", "image", "--model", "m", "--prompt", "x", *spend_flags)
    assert code == 1
    error = error_of(out)
    assert error["code"] == "usage_error"
    assert "--max-credits" in error["message"]
    assert fake_bridge.calls == []


def test_dry_run_never_uploads_or_submits(
    fake_bridge: FakeBridge, run: Run, tmp_path: Path
) -> None:
    ref = tmp_path / "ref.png"
    ref.write_bytes(PNG)
    fake_bridge.on("generate.estimate", ESTIMATE)

    code, out, _ = run(
        "--json", "generate", "image", "--model", "m", "--prompt", "x",
        "--media", f"image_media_tokens={ref}", "--dry-run",
    )  # fmt: skip

    assert code == 0
    assert fake_bridge.ops() == ["generate.estimate"]
    assert json.loads(out)["effective_credits"] == 4


def test_dry_run_prices_local_image_refs_with_placeholders(
    fake_bridge: FakeBridge, run: Run, tmp_path: Path
) -> None:
    first, second = tmp_path / "a.png", tmp_path / "b.png"
    first.write_bytes(PNG)
    second.write_bytes(PNG)
    fake_bridge.on("generate.estimate", ESTIMATE)

    run(
        "--json", "generate", "image", "--model", "m", "--dry-run",
        "--media", f"image_media_tokens={first}",
        "--media", "image_media_tokens=mf_existing",
        "--media", f"image_media_tokens={second}",
    )  # fmt: skip
    code, out, _ = run(
        "--json", "generate", "video", "--model", "v", "--dry-run",
        "--media", f"start_frame_media_token={first}",
    )  # fmt: skip

    image_args, video_args = fake_bridge.args("generate.estimate")
    assert image_args["request"]["image_media_tokens"] == [
        "mf_estimate_0",
        "mf_existing",
        "mf_estimate_1",
    ]
    assert "start_frame_media_token" not in video_args["request"]
    assert code == 0
    assert json.loads(out)["omitted_inputs"] == ["start_frame_media_token"]


def test_fields_ending_in_tokens_accumulate_lists(fake_bridge: FakeBridge, run: Run) -> None:
    fake_bridge.on("generate.estimate", ESTIMATE)

    run(
        "--json", "generate", "image", "--model", "m", "--dry-run",
        "--media", "image_media_tokens=mf_a", "--media", "image_media_tokens=mf_b",
        "--media", "style_media_token=mf_c", "--set", "aspect_ratio=\"wide\"", "--set", "n=2",
    )  # fmt: skip
    code, out, _ = run(
        "--json", "generate", "image", "--model", "m", "--dry-run",
        "--media", "style_media_token=mf_c", "--media", "style_media_token=mf_d",
    )  # fmt: skip

    (args,) = fake_bridge.args("generate.estimate")
    assert args["request"] == {
        "model": "m",
        "image_media_tokens": ["mf_a", "mf_b"],
        "style_media_token": "mf_c",
        "aspect_ratio": "wide",
        "n": 2,
    }
    assert code == 1
    assert error_of(out)["code"] == "usage_error"


# --- Single-op commands print bridge data unchanged (spec §6.1) -------------------------


SINGLE_OP_COMMANDS: list[tuple[list[str], str, dict[str, Any]]] = [
    (["app", "info"], "app.info", {}),
    (["account", "whoami"], "account.session", {}),
    (["models", "list", "--kind", "video"], "models.list", {"kind": "video"}),
    (["jobs", "list"], "jobs.list", {"origin": "cli", "limit": 50, "include_remote": False}),
    (
        ["jobs", "list", "--all", "--limit", "5"],
        "jobs.list",
        {"origin": "all", "limit": 5, "include_remote": False},
    ),
    (["account", "credits"], "account.credits", {}),
    (["account", "subscription"], "account.subscription", {}),
    (
        ["jobs", "list", "--remote"],
        "jobs.list",
        {"origin": "cli", "limit": 50, "include_remote": True},
    ),
    (["jobs", "get", "j1"], "jobs.get", {"job_ids": ["j1"], "include_remote": False}),
    (
        ["jobs", "get", "j1", "j2", "--remote"],
        "jobs.get",
        {"job_ids": ["j1", "j2"], "include_remote": True},
    ),
]


@pytest.mark.parametrize(
    ("argv", "op", "args"), SINGLE_OP_COMMANDS, ids=["-".join(row[0]) for row in SINGLE_OP_COMMANDS]
)
def test_single_op_commands_print_bridge_data_unchanged(
    fake_bridge: FakeBridge, run: Run, argv: list[str], op: str, args: dict[str, Any]
) -> None:
    data = {"op": op, "nested": [1, {"kept": True}], "maybe": None}
    fake_bridge.on(op, data)

    code, out, err = run("--json", *argv)

    assert (code, err) == (0, "")
    assert json.loads(out) == data
    assert fake_bridge.args(op) == [args]


# --- generate submit (spec §6.2, §6.3) --------------------------------------------------


@pytest.mark.parametrize(
    ("outcome", "code"),
    [
        (op_error("internal_error", status=500), "internal_error"),
        (op_error("bridge_busy", status=503), "bridge_busy"),
        (op_error("upstream_error"), "upstream_error"),
        (op_error("operation_in_progress"), "operation_in_progress"),
    ],
)
def test_submit_is_never_auto_retried_after_send(
    fake_bridge: FakeBridge, run: Run, outcome: requests.Response, code: str
) -> None:
    fake_bridge.on("generate.submit", outcome)

    exit_code, out, _ = run(
        "--json", "generate", "image", "--model", "m", "--prompt", "x",
        "--max-credits", "5", "--idempotency-token", TOKEN_A,
    )  # fmt: skip

    assert exit_code == 1
    error = error_of(out)
    assert error["code"] == code
    assert error["details"]["idempotency_token"] == TOKEN_A
    assert fake_bridge.ops() == ["generate.submit"]


def test_read_timeout_on_submit_reports_outcome_unknown(fake_bridge: FakeBridge, run: Run) -> None:
    fake_bridge.on("generate.submit", requests.ReadTimeout())

    code, out, _ = run(
        "--json", "generate", "image", "--model", "m", "--prompt", "x",
        "--max-credits", "5", "--idempotency-token", TOKEN_A,
    )  # fmt: skip

    assert code == 1
    error = error_of(out)
    assert error["code"] == "outcome_unknown"
    assert error["details"] == {"idempotency_token": TOKEN_A, "reason": "response_timeout"}
    assert error["retryable"] is False
    assert fake_bridge.ops() == ["generate.submit"]


def test_unwritable_download_dir_is_refused_before_any_spend(
    fake_bridge: FakeBridge, run: Run, tmp_path: Path
) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        code, out, _ = run(
            "--json", "generate", "image", "--model", "m", "--prompt", "x", "--max-credits", "5",
            "--idempotency-token", TOKEN_A, "--download", str(locked),
        )  # fmt: skip
    finally:
        locked.chmod(0o700)

    assert code == 1
    error = error_of(out)
    assert (error["code"], error["details"]["idempotency_token"]) == ("usage_error", TOKEN_A)
    assert fake_bridge.calls == []


# --- jobs wait (spec §6.4) --------------------------------------------------------------


def test_wait_returns_all_files_when_every_job_succeeds(
    fake_bridge: FakeBridge, run: Run, cdn: list[dict[str, Any]], tmp_path: Path
) -> None:
    fake_bridge.on(
        "jobs.get",
        jobs_seen(job("j1", "running"), job("j2", "queued")),
        jobs_seen(job("j1", "succeeded", ["a1"]), job("j2", "succeeded", ["b1"])),
        jobs_seen(job("j1", "succeeded", ["a1"]), job("j2", "succeeded", ["b1", "b2", "b3"])),
    )

    code, out, _ = run("--json", "jobs", "wait", "j1", "j2", "--download", str(tmp_path))

    assert code == 0
    body = json.loads(out)
    saved = [Path(item["path"]) for item in body["downloads"]]
    assert [path.name for path in saved] == ["a1.png", "b1.png", "b2.png", "b3.png"]
    assert all(path.read_bytes().startswith(b"image-bytes:") for path in saved)
    assert fake_bridge.args("jobs.get")[-1]["include_remote"] is True


def test_wait_fails_with_job_failed_and_full_details(fake_bridge: FakeBridge, run: Run) -> None:
    fake_bridge.on("jobs.get", jobs_seen(job("j1", "running")), jobs_seen(job("j1", "failed")))

    code, out, _ = run("--json", "jobs", "wait", "j1")

    assert code == 1
    error = error_of(out)
    assert error["code"] == "job_failed"
    assert error["details"]["status"] == "failed"
    assert error["details"]["job"]["failure"] == {"category": "model", "message": "nsfw"}


def test_wait_times_out_with_last_seen_state(
    fake_bridge: FakeBridge, run: Run, clock: FakeClock
) -> None:
    fake_bridge.on("jobs.get", jobs_seen(job("j1", "running")))
    started = clock.now

    code, out, _ = run("--json", "jobs", "wait", "j1", "--timeout", "30")

    assert code == 1
    error = error_of(out)
    assert error["code"] == "job_wait_timeout"
    assert error["details"]["last_seen"]["jobs"][0]["status"] == "running"
    assert clock.now - started <= 30


def test_wait_never_polls_faster_than_five_seconds(fake_bridge: FakeBridge, run: Run) -> None:
    fake_bridge.on(
        "jobs.get",
        *[jobs_seen(job("j1", "running"))] * 30,
        jobs_seen(job("j1", "succeeded", ["a1"])),
    )

    code, _, _ = run("--json", "jobs", "wait", "j1")

    times = [call["t"] for call in fake_bridge.calls]
    assert code == 0
    assert len(times) == 32
    assert all(later - earlier >= 5 for earlier, later in itertools.pairwise(times))


def test_wait_checks_remote_at_most_once_a_minute(fake_bridge: FakeBridge, run: Run) -> None:
    fake_bridge.on("jobs.get", jobs_seen(job("j1", "running")))

    run("--json", "jobs", "wait", "j1", "--timeout", "300")

    remote_times = [
        call["t"] for call in fake_bridge.calls if call["json"]["args"]["include_remote"]
    ]
    assert len(remote_times) >= 4
    assert all(later - earlier >= 60 for earlier, later in itertools.pairwise(remote_times))


def test_wait_fails_fast_on_unknown_job_ids(
    fake_bridge: FakeBridge, run: Run, clock: FakeClock
) -> None:
    unknown = [{"job_id": "nope", "reason": "job_not_found"}]
    fake_bridge.on("jobs.get", jobs_seen(job("j1", "running"), unresolved=unknown))
    started = clock.now

    code, out, _ = run("--json", "jobs", "wait", "j1", "nope")

    assert code == 1
    assert error_of(out)["code"] == "job_not_found"
    assert clock.now == started


def test_wait_treats_cancelled_jobs_as_failed(fake_bridge: FakeBridge, run: Run) -> None:
    fake_bridge.on("jobs.get", jobs_seen(job("j1", "succeeded", ["a1"]), job("j2", "cancelled")))

    code, out, _ = run("--json", "jobs", "wait", "j1", "j2")

    assert code == 1
    error = error_of(out)
    assert (error["code"], error["details"]["status"]) == ("job_failed", "cancelled")


def test_wait_fails_fast_when_logged_out(
    fake_bridge: FakeBridge, run: Run, clock: FakeClock
) -> None:
    logged_out = [{"job_id": "j9", "reason": "not_logged_in"}]
    fake_bridge.on("jobs.get", jobs_seen(unresolved=logged_out))
    started = clock.now

    code, out, _ = run("--json", "jobs", "wait", "j9")

    assert code == 1
    assert error_of(out)["code"] == "not_logged_in"
    assert clock.now == started


def test_wait_finishes_jobs_that_succeed_in_the_last_interval(
    fake_bridge: FakeBridge, run: Run
) -> None:
    fake_bridge.on(
        "jobs.get",
        jobs_seen(job("j1", "running")),
        jobs_seen(job("j1", "running")),
        jobs_seen(job("j1", "succeeded", ["a1"])),
    )

    code, out, _ = run("--json", "jobs", "wait", "j1", "--timeout", "14")

    assert code == 0
    assert [view["status"] for view in json.loads(out)["jobs"]] == ["succeeded"]
    assert fake_bridge.args("jobs.get")[-1]["include_remote"] is True


def test_download_refuses_to_clobber_and_rejects_non_https(
    fake_bridge: FakeBridge, run: Run, cdn: list[dict[str, Any]], tmp_path: Path
) -> None:
    done = job("j1", "succeeded", ["a1"])
    plain_http = job("j2", "succeeded", ["b1"])
    plain_http["result"]["files"][0]["cdn_url"] = "http://cdn.example/b1.png"
    fake_bridge.on("jobs.get", jobs_seen(done), jobs_seen(done), jobs_seen(plain_http))
    (tmp_path / "a1.png").write_bytes(b"keep me")

    code, out, _ = run("--json", "jobs", "wait", "j1", "--download", str(tmp_path))
    assert (code, error_of(out)["code"]) == (1, "output_exists")
    assert (tmp_path / "a1.png").read_bytes() == b"keep me"

    code, _, _ = run("--json", "jobs", "wait", "j1", "--download", str(tmp_path), "--force")
    assert code == 0
    assert (tmp_path / "a1.png").read_bytes() != b"keep me"

    code, out, _ = run("--json", "jobs", "wait", "j2", "--download", str(tmp_path))
    assert (code, error_of(out)["code"]) == (1, "download_failed")
    assert all(call["url"].startswith("https://") for call in cdn)


class DropsMidway(io.BytesIO):
    """A CDN body whose connection resets after the first chunk."""

    def read(self, size: int | None = -1, /) -> bytes:
        if self.tell():
            raise ConnectionResetError("connection reset by peer")
        return super().read(4)


def test_interrupted_download_leaves_no_partial_file(
    fake_bridge: FakeBridge, run: Run, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def dropping_get(url: str, **kwargs: Any) -> requests.Response:
        resp = requests.Response()
        resp.status_code = 200
        resp.raw = DropsMidway(b"partial image bytes")
        return resp

    monkeypatch.setattr(requests, "get", dropping_get)
    fake_bridge.on("jobs.get", jobs_seen(job("j1", "succeeded", ["a1"])))
    dest = tmp_path / "downloads"
    dest.mkdir()

    code, out, _ = run("--json", "jobs", "wait", "j1", "--download", str(dest))

    assert (code, error_of(out)["code"]) == (1, "download_failed")
    assert list(dest.iterdir()) == []


def test_local_write_failures_during_download_are_json_errors(
    fake_bridge: FakeBridge, run: Run, cdn: list[dict[str, Any]], tmp_path: Path
) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    fake_bridge.on("jobs.get", jobs_seen(job("j1", "succeeded", ["a1"])))
    try:
        code, out, _ = run("--json", "jobs", "wait", "j1", "--download", str(locked))
    finally:
        locked.chmod(0o700)

    assert code == 1
    assert error_of(out)["code"] == "download_failed"
    assert list(locked.iterdir()) == []
