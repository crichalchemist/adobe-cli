"""Transport behaviour of utils/bridge.py against a scripted HTTP boundary (spec §6.2)."""

from __future__ import annotations

import http.client
import http.server
import json
import os
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import requests
import urllib3

from artcraft_cli.errors import CliError
from artcraft_cli.utils import bridge

from .conftest import HEALTH, TOKEN, FakeBridge, FakeClock, op_error, refused, write_discovery

_real_session: Callable[[], requests.Session] = bridge._session  # before any patching
SUBMIT_ARGS = {
    "modality": "image",
    "idempotency_token": "0b8f6a52-6a8e-4d55-9d43-3d6c0f6f1a10",
    "max_credits": 5,
    "request": {"model": "m"},
}


def test_missing_discovery_file_reports_bridge_not_running() -> None:
    with pytest.raises(CliError) as caught:
        bridge.health()
    assert caught.value.code == "bridge_not_running"


def test_dead_pid_reports_bridge_not_running_instead_of_hanging(
    fake_bridge: FakeBridge, discovery: Path
) -> None:
    finished = subprocess.Popen([sys.executable, "-c", "pass"])
    finished.wait()
    write_discovery(discovery, pid=finished.pid)

    with pytest.raises(CliError) as caught:
        bridge.health()

    assert caught.value.code == "bridge_not_running"
    assert fake_bridge.calls == []


@pytest.mark.parametrize(
    ("mode", "foreign_owner"), [(0o644, False), (0o640, False), (0o604, False), (0o600, True)]
)
def test_world_readable_or_foreign_discovery_file_is_refused(
    fake_bridge: FakeBridge,
    discovery: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: int,
    foreign_owner: bool,
) -> None:
    discovery.chmod(mode)
    if foreign_owner:
        monkeypatch.setattr(os, "getuid", lambda: discovery.stat().st_uid + 1)

    with pytest.raises(CliError) as caught:
        bridge.health()

    assert caught.value.code == "discovery_insecure"
    assert fake_bridge.calls == []


def test_refused_connection_rereads_discovery_then_reports_not_running(
    fake_bridge: FakeBridge,
) -> None:
    fake_bridge.on("health", refused())
    with pytest.raises(CliError) as caught:
        bridge.health()
    assert caught.value.code == "bridge_not_running"
    assert len(fake_bridge.calls) == 2


def test_restarted_app_on_new_port_is_found_on_retry(
    fake_bridge: FakeBridge, discovery: Path
) -> None:
    def app_restarts_on_new_port() -> BaseException:
        write_discovery(discovery, port=50002)
        return refused()

    fake_bridge.on("health", app_restarts_on_new_port, HEALTH)

    assert bridge.health()["app_version"] == "0.41.0"
    assert [call["url"] for call in fake_bridge.calls] == [
        "http://127.0.0.1:50001/v1/health",
        "http://127.0.0.1:50002/v1/health",
    ]


def test_bridge_error_body_survives_non_2xx_status(fake_bridge: FakeBridge) -> None:
    fake_bridge.on("app.info", op_error("forbidden_origin", "browsers are refused", status=403))
    with pytest.raises(CliError) as caught:
        bridge.rpc("app.info", {})
    assert (caught.value.code, caught.value.message) == ("forbidden_origin", "browsers are refused")


def test_op_error_with_http_200_raises_its_code(fake_bridge: FakeBridge) -> None:
    details = {"effective_credits": 12, "max_credits": 5}
    fake_bridge.on("generate.submit", op_error("cost_exceeds_limit", "too dear", details))
    with pytest.raises(CliError) as caught:
        bridge.rpc("generate.submit", SUBMIT_ARGS)
    assert caught.value.code == "cost_exceeds_limit"
    assert caught.value.details == details


def test_read_timeout_after_send_is_never_reported_as_not_running(
    fake_bridge: FakeBridge,
) -> None:
    fake_bridge.on("jobs.list", requests.ReadTimeout())
    with pytest.raises(CliError) as caught:
        bridge.rpc("jobs.list", {})
    assert caught.value.code == "response_timeout"
    assert len(fake_bridge.calls) == 1


def test_protocol_version_mismatch_is_refused(fake_bridge: FakeBridge, discovery: Path) -> None:
    write_discovery(discovery, version=2)
    with pytest.raises(CliError) as caught:
        bridge.health()
    assert caught.value.code == "bridge_protocol_mismatch"
    assert fake_bridge.calls == []


def test_proxy_env_vars_never_route_bridge_traffic(
    discovery: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Health(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = json.dumps({"ok": True, "data": HEALTH}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: Any) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Health)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        write_discovery(discovery, port=server.server_address[1])
        for name in ("HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
            monkeypatch.setenv(name, "http://127.0.0.1:9")  # discard port: nothing answers
        for name in ("NO_PROXY", "no_proxy"):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setattr(bridge, "_sess", None)
        monkeypatch.setattr(bridge, "_session", _real_session)

        assert bridge.health()["app_version"] == "0.41.0"
    finally:
        server.shutdown()
        server.server_close()


def test_token_never_appears_in_stdout_stderr_or_exceptions(
    fake_bridge: FakeBridge, run: Callable[..., tuple[int, str, str]]
) -> None:
    fake_bridge.on("health", HEALTH)
    fake_bridge.on("app.info", op_error("unauthorized", status=401))
    fake_bridge.on("jobs.list", refused())
    fake_bridge.on("models.list", requests.ReadTimeout())
    fake_bridge.on("account.session", requests.ConnectionError("dropped"))

    outputs: list[str] = []
    for argv in (
        ["ping"],
        ["--json", "ping"],
        ["app", "info"],
        ["--json", "jobs", "list"],
        ["models", "list", "--kind", "image"],
        ["--json", "account", "whoami"],
    ):
        _, out, err = run(*argv)
        outputs += [out, err]
    failing_ops: list[tuple[str, dict[str, Any]]] = [
        ("app.info", {}),
        ("jobs.list", {}),
        ("models.list", {"kind": "image"}),
    ]
    for op, args in failing_ops:
        with pytest.raises(CliError) as caught:
            bridge.rpc(op, args)
        outputs += [str(caught.value), repr(caught.value), json.dumps(caught.value.details)]

    assert all(TOKEN not in text for text in outputs)


def test_credentials_not_synced_is_retried_briefly_then_surfaced(
    fake_bridge: FakeBridge, clock: FakeClock
) -> None:
    fake_bridge.on("account.session", op_error("credentials_not_synced"))
    started = clock.now

    with pytest.raises(CliError) as caught:
        bridge.rpc("account.session", {})

    assert caught.value.code == "credentials_not_synced"
    assert len(fake_bridge.calls) > 1
    assert clock.now - started <= bridge.NOT_SYNCED_WAIT_S


def test_connection_dropped_after_send_never_resubmits(fake_bridge: FakeBridge) -> None:
    dropped = requests.ConnectionError(
        urllib3.exceptions.ProtocolError(
            "Connection aborted.", http.client.RemoteDisconnected("closed without response")
        )
    )
    fake_bridge.on("generate.submit", dropped)

    with pytest.raises(CliError) as caught:
        bridge.rpc("generate.submit", SUBMIT_ARGS)

    assert caught.value.code == "outcome_unknown"
    assert caught.value.details == {
        "idempotency_token": SUBMIT_ARGS["idempotency_token"],
        "reason": "connection_lost",
    }
    assert fake_bridge.ops() == ["generate.submit"]


def test_bridge_token_is_never_sent_to_cdn_hosts(
    fake_bridge: FakeBridge,
    run: Callable[..., tuple[int, str, str]],
    cdn: list[dict[str, Any]],
    tmp_path: Path,
) -> None:
    finished = {
        "job_id": "j1",
        "status": "succeeded",
        "terminal": True,
        "result": {"files": [{"media_token": "a1", "cdn_url": "https://cdn.example/a1.png"}]},
    }
    fake_bridge.on("jobs.get", {"jobs": [finished], "unresolved": []})

    code, _, _ = run("--json", "jobs", "wait", "j1", "--download", str(tmp_path))

    assert code == 0
    assert [call["url"] for call in cdn] == ["https://cdn.example/a1.png"]
    assert "headers" not in cdn[0]
    assert TOKEN not in json.dumps(cdn, default=str)
    assert fake_bridge.ops() == ["jobs.get"]
