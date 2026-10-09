"""CLI behaviour through the real entry point, faking only the HTTP boundary (spec §6)."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

import pytest

from .conftest import HEALTH, FakeBridge

Run = Callable[..., tuple[int, str, str]]


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
