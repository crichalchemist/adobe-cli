"""Restart recovery and malformed discovery values in utils/bridge.py (spec §6.2)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import requests

from artcraft_cli.errors import CliError
from artcraft_cli.utils import bridge

from .conftest import HEALTH, FakeBridge, op_error, write_discovery

NEW_TOKEN = "cd" * 32


def _patch_discovery(path: Path, **fields: Any) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(fields)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_401_rereads_discovery_and_retries_with_the_new_token(
    fake_bridge: FakeBridge, discovery: Path
) -> None:
    def app_restarted_with_new_token() -> Any:
        write_discovery(discovery, token=NEW_TOKEN)
        return op_error("unauthorized", status=401)

    fake_bridge.on("health", app_restarted_with_new_token, HEALTH)

    assert bridge.health()["app_version"] == "0.41.0"
    assert [call["headers"]["Authorization"] for call in fake_bridge.calls] == [
        "Bearer " + "ab" * 32,
        f"Bearer {NEW_TOKEN}",
    ]


def test_second_401_after_token_refresh_reports_unauthorized(
    fake_bridge: FakeBridge, discovery: Path
) -> None:
    def app_rejects_every_token() -> Any:
        write_discovery(discovery, token=NEW_TOKEN)
        return op_error("unauthorized", status=401)

    fake_bridge.on("health", app_rejects_every_token)

    with pytest.raises(CliError) as caught:
        bridge.health()

    assert caught.value.code == "unauthorized"
    assert len(fake_bridge.calls) == 2


@pytest.mark.parametrize("pid", ["abc", "4242", 0, -1, True, 1.5])
def test_malformed_discovery_pid_is_reported_as_protocol_error(
    fake_bridge: FakeBridge, discovery: Path, pid: Any
) -> None:
    _patch_discovery(discovery, pid=pid)

    with pytest.raises(CliError) as caught:
        bridge.health()

    assert caught.value.code == "bridge_protocol_error"
    assert fake_bridge.calls == []


@pytest.mark.parametrize("port", ["50001", 0, 65536, -1, True, 1.5])
def test_malformed_discovery_port_is_reported_as_protocol_error(
    fake_bridge: FakeBridge, discovery: Path, port: Any
) -> None:
    _patch_discovery(discovery, port=port)

    with pytest.raises(CliError) as caught:
        bridge.health()

    assert caught.value.code == "bridge_protocol_error"
    assert fake_bridge.calls == []


def test_discovery_token_with_trailing_newline_is_refused_without_echoing_it(
    fake_bridge: FakeBridge,
    discovery: Path,
    run: Callable[..., tuple[int, str, str]],
) -> None:
    secret = "cd" * 32
    write_discovery(discovery, token=secret + "\n")

    code, out, err = run("--json", "ping")

    assert (code, json.loads(out)["error"]["code"]) == (1, "bridge_protocol_error")
    assert secret not in out + err
    assert fake_bridge.calls == []


def test_unexpected_request_error_on_submit_reports_outcome_unknown(
    fake_bridge: FakeBridge,
) -> None:
    token = "0b8f6a52-6a8e-4d55-9d43-3d6c0f6f1a10"
    fake_bridge.on("generate.submit", requests.exceptions.ContentDecodingError("bad gzip"))

    with pytest.raises(CliError) as caught:
        bridge.rpc("generate.submit", {"idempotency_token": token})

    assert caught.value.code == "outcome_unknown"
    assert caught.value.details == {"idempotency_token": token, "reason": "connection_lost"}
