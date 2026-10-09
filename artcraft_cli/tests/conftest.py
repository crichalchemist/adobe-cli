"""Fixtures. Unit tests fake only the HTTP boundary (requests), the clock and the OS."""

from __future__ import annotations

import io
import json
import os
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import pytest
import requests
import urllib3

from artcraft_cli.artcraft_cli import main
from artcraft_cli.utils import bridge

TOKEN = "ab" * 32
PORT = 50001
HEALTH = {
    "bridge_protocol_version": 1,
    "app_version": "0.41.0",
    "pid": 4242,
    "started_at": "2026-10-09T15:04:05Z",
    "ops": ["app.info", "account.session", "models.list", "jobs.list", "generate.estimate"],
    "readiness": {"credentials_synced": True, "session_cookie_present": True},
}

Outcome = dict[str, Any] | requests.Response | BaseException | Callable[[], Any]


def write_discovery(
    path: Path,
    *,
    port: int = PORT,
    pid: int | None = None,
    version: int = 1,
    token: str = TOKEN,
    mode: int = 0o600,
) -> None:
    path.write_text(
        json.dumps(
            {
                "bridge_protocol_version": version,
                "port": port,
                "pid": os.getpid() if pid is None else pid,
                "token": token,
                "app_version": "0.41.0",
                "started_at": "2026-10-09T15:04:05Z",
            }
        ),
        encoding="utf-8",
    )
    path.chmod(mode)


def response(status: int, body: Any) -> requests.Response:
    """A real requests.Response carrying `body` (bytes are sent as-is, else JSON)."""
    resp = requests.Response()
    resp.status_code = status
    resp.raw = io.BytesIO(body if isinstance(body, bytes) else json.dumps(body).encode())
    return resp


def op_error(code: str, message: str = "x", details: Any = None, status: int = 200) -> Any:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return response(status, {"ok": False, "error": error})


def refused() -> requests.ConnectionError:
    """What requests raises when nothing is listening on the port."""
    reason = urllib3.exceptions.NewConnectionError(cast(Any, None), "Connection refused")
    return requests.ConnectionError(urllib3.exceptions.MaxRetryError(cast(Any, None), "/", reason))


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class FakeBridge:
    """Stands in for requests.Session. Outcomes are queued per op ("health" for GET);
    the last outcome of a queue repeats."""

    def __init__(self, clock: FakeClock | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._queues: dict[str, list[Outcome]] = {}
        self._clock = clock

    def on(self, op: str, *outcomes: Outcome) -> FakeBridge:
        self._queues.setdefault(op, []).extend(outcomes)
        return self

    def ops(self) -> list[str]:
        return [call["op"] for call in self.calls]

    def args(self, op: str) -> list[dict[str, Any]]:
        return [call["json"]["args"] for call in self.calls if call["op"] == op]

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any] | None = None,
        timeout: Any = None,
    ) -> requests.Response:
        op = "health" if url.endswith("/v1/health") else str((json or {})["op"])
        self.calls.append(
            {
                "op": op,
                "method": method,
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
                "t": self._clock.now if self._clock else 0.0,
            }
        )
        queue = self._queues.get(op)
        if not queue:
            raise AssertionError(f"unexpected bridge call: {op}")
        outcome = queue.pop(0) if len(queue) > 1 else queue[0]
        if callable(outcome) and not isinstance(outcome, BaseException):
            outcome = outcome()
        if isinstance(outcome, BaseException):
            raise outcome
        if isinstance(outcome, requests.Response):
            return outcome
        return response(200, {"ok": True, "data": outcome})


@pytest.fixture(autouse=True)
def _isolate_bridge(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Unit tests never reach a real ArtCraft, its discovery file, or the network."""
    if request.node.get_closest_marker("e2e"):
        return

    def no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("unit test reached the network")

    monkeypatch.setattr(bridge, "DISCOVERY_PATH", tmp_path / "absent" / "cli_bridge.json")
    monkeypatch.setattr(bridge, "_session", no_network)
    monkeypatch.setattr(requests, "get", no_network)


@pytest.fixture
def discovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "cli_bridge.json"
    write_discovery(path)
    monkeypatch.setattr(bridge, "DISCOVERY_PATH", path)
    return path


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(time, "monotonic", fake.monotonic)
    monkeypatch.setattr(time, "sleep", fake.sleep)
    return fake


@pytest.fixture
def fake_bridge(discovery: Path, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> FakeBridge:
    fake = FakeBridge(clock)
    monkeypatch.setattr(bridge, "_session", lambda: fake)
    return fake


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Iterator[Callable[..., tuple[int, str, str]]]:
    """Run the real console entry point; returns (exit_code, stdout, stderr)."""

    def invoke(*argv: str) -> tuple[int, str, str]:
        code = main(list(argv))
        out, err = capsys.readouterr()
        return code, out, err

    yield invoke
