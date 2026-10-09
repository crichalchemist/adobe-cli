"""CLI behaviour through the real entry point, faking only the HTTP boundary (spec §6)."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from .conftest import HEALTH, FakeBridge

Run = Callable[..., tuple[int, str, str]]
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
ESTIMATE = {
    "modality": "image",
    "model": "m",
    "estimate": {"cost_in_credits": 4, "is_free": False, "is_unlimited": False},
    "effective_credits": 4,
}


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
