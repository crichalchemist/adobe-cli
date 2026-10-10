"""The only module that talks to the ArtCraft bridge or reads its discovery file (spec §6.2)."""

from __future__ import annotations

import contextlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
import urllib3

from artcraft_cli import SUPPORTED_BRIDGE_PROTOCOL
from artcraft_cli.errors import CliError

DISCOVERY_PATH = Path.home() / "Artcraft" / "state" / "cli_bridge.json"
DISCOVERY_KEYS = ("bridge_protocol_version", "port", "pid", "token", "app_version", "started_at")
HEALTH_KEYS = ("bridge_protocol_version", "app_version", "ops", "readiness")
CONNECT_TIMEOUT = 3
READ_TIMEOUT = 150
HEALTH_TIMEOUT = 5
NOT_SYNCED_WAIT_S = 5
NOT_SYNCED_POLL_S = 0.5
DOWNLOAD_TIMEOUT = 60
DOWNLOAD_CHUNK_BYTES = 1024 * 1024
SUBMIT_OP = "generate.submit"

_sess: requests.Session | None = None


def _session() -> requests.Session:
    """The bridge session; env proxies are ignored. Tests patch this function."""
    global _sess
    if _sess is None:
        _sess = requests.Session()
        _sess.trust_env = False
    return _sess


MAX_PORT = 65535
TOKEN_RE = re.compile(r"[0-9a-f]{64}")


def read_discovery() -> dict[str, Any]:
    """Read and check the discovery file. Runs before every bridge call."""
    path = DISCOVERY_PATH
    if not path.exists():
        raise CliError("bridge_not_running", f"no discovery file at {path}")
    if os.name == "posix":
        st = path.stat()
        if st.st_uid != os.getuid() or st.st_mode & 0o077:
            raise CliError("discovery_insecure", f"{path} must be owned by you with mode 0600")
    try:
        discovery = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise CliError("bridge_protocol_error", f"cannot parse {path}") from None
    if not isinstance(discovery, dict) or any(key not in discovery for key in DISCOVERY_KEYS):
        raise CliError("bridge_protocol_error", f"{path} is missing required keys")
    version = discovery["bridge_protocol_version"]
    if version != SUPPORTED_BRIDGE_PROTOCOL:
        raise CliError(
            "bridge_protocol_mismatch",
            f"bridge protocol {version} is not supported (expected {SUPPORTED_BRIDGE_PROTOCOL})",
        )
    pid = discovery["pid"]
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise CliError("bridge_protocol_error", f"{path} has an invalid pid")
    port = discovery["port"]
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= MAX_PORT:
        raise CliError("bridge_protocol_error", f"{path} has an invalid port")
    token = discovery["token"]
    if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
        raise CliError("bridge_protocol_error", f"{path} has an invalid token")
    if not _pid_alive(pid):
        raise CliError("bridge_not_running", f"ArtCraft pid {pid} is not running")
    return discovery


def _pid_alive(pid: int) -> bool:
    if os.name != "posix":
        return True  # os.kill(pid, 0) would terminate the process on Windows
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def health() -> dict[str, Any]:
    """GET /v1/health: protocol, app version, pid, ops allowlist, readiness."""
    data = _call("GET", "/v1/health", None, HEALTH_TIMEOUT, submit_token=None)
    if any(key not in data for key in HEALTH_KEYS):
        raise CliError("bridge_protocol_error", "health response is missing required keys")
    if data["bridge_protocol_version"] != SUPPORTED_BRIDGE_PROTOCOL:
        raise CliError(
            "bridge_protocol_mismatch",
            f"bridge protocol {data['bridge_protocol_version']} is not supported",
        )
    return data


def rpc(op: str, args: dict[str, Any]) -> dict[str, Any]:
    """POST /v1/rpc and return `data`; an `ok: false` envelope raises CliError(code)."""
    submit_token = str(args["idempotency_token"]) if op == SUBMIT_OP else None
    deadline = time.monotonic() + NOT_SYNCED_WAIT_S
    while True:
        try:
            return _call(
                "POST", "/v1/rpc", {"op": op, "args": args}, READ_TIMEOUT, submit_token=submit_token
            )
        except CliError as err:
            if err.code != "credentials_not_synced" or time.monotonic() >= deadline:
                raise
        time.sleep(NOT_SYNCED_POLL_S)


def _call(
    method: str,
    path: str,
    body: dict[str, Any] | None,
    read_timeout: float,
    *,
    submit_token: str | None,
) -> dict[str, Any]:
    discovery = read_discovery()
    resp = _send(method, path, body, read_timeout, discovery, submit_token)
    if resp is None or resp.status_code == 401:
        # Refused before send, or the gate rejected the token: nothing ran, and the
        # app may have restarted on a new port with a new token. Re-read once.
        discovery = read_discovery()
        resp = _send(method, path, body, read_timeout, discovery, submit_token)
        if resp is None:
            raise CliError("bridge_not_running", "the bridge refused the connection")
    return _parse(resp)


def _send(
    method: str,
    path: str,
    body: dict[str, Any] | None,
    read_timeout: float,
    discovery: dict[str, Any],
    submit_token: str | None,
) -> requests.Response | None:
    """One HTTP attempt. None means the connection was refused before anything was sent."""
    try:
        return _session().request(
            method,
            f"http://127.0.0.1:{discovery['port']}{path}",
            headers={"Authorization": f"Bearer {discovery['token']}"},
            json=body,
            timeout=(CONNECT_TIMEOUT, read_timeout),
        )
    except requests.ConnectionError as exc:
        if _refused_before_send(exc):
            return None
        raise _after_send("connection_lost", read_timeout, submit_token) from None
    except requests.ReadTimeout:
        raise _after_send("response_timeout", read_timeout, submit_token) from None
    except requests.exceptions.ChunkedEncodingError:
        raise _after_send("connection_lost", read_timeout, submit_token) from None


def _refused_before_send(exc: requests.ConnectionError) -> bool:
    if isinstance(exc, requests.ConnectTimeout):
        return True
    reason = exc.args[0] if exc.args else None
    reason = getattr(reason, "reason", reason)  # requests wraps urllib3's MaxRetryError
    return isinstance(reason, (urllib3.exceptions.NewConnectionError, ConnectionRefusedError))


def _after_send(reason: str, read_timeout: float, submit_token: str | None) -> CliError:
    """A failure after the request was sent. Never retried: the op may have run."""
    if submit_token is not None:
        return CliError(
            "outcome_unknown",
            "generate.submit may have been accepted; its outcome is unknown",
            {"idempotency_token": submit_token, "reason": reason},
        )
    if reason == "response_timeout":
        return CliError("response_timeout", f"no response from the bridge within {read_timeout} s")
    return CliError("bridge_protocol_error", "the bridge dropped the connection")


def _parse(resp: requests.Response) -> dict[str, Any]:
    """Parse the envelope first, whatever the HTTP status (spec §5.2)."""
    try:
        envelope = resp.json()
    except ValueError:
        raise CliError(
            "bridge_protocol_error", f"bridge sent a non-JSON response (HTTP {resp.status_code})"
        ) from None
    if not isinstance(envelope, dict) or not isinstance(envelope.get("ok"), bool):
        raise CliError(
            "bridge_protocol_error", f"bridge sent a malformed envelope (HTTP {resp.status_code})"
        )
    if envelope["ok"]:
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise CliError("bridge_protocol_error", "bridge sent a success envelope without data")
        return data
    error = envelope.get("error")
    if not isinstance(error, dict) or not isinstance(error.get("code"), str):
        raise CliError(
            "bridge_protocol_error", f"bridge sent a malformed error (HTTP {resp.status_code})"
        )
    details = error.get("details")
    raise CliError(
        error["code"], str(error.get("message", "")), details if isinstance(details, dict) else None
    )


def download(url: str, dest: Path, *, force: bool) -> int:
    """Fetch a CDN URL into dest. Uses plain requests: no bridge session, no token."""
    if urlparse(url).scheme != "https":
        raise CliError("download_failed", "refusing a download URL that is not https")
    if dest.exists() and not force:
        raise CliError("output_exists", f"{dest} already exists", {"path": str(dest)})
    partial = dest.with_name(dest.name + ".part")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True) as resp:
            resp.raise_for_status()
            with partial.open("wb") as out:
                for chunk in resp.iter_content(DOWNLOAD_CHUNK_BYTES):
                    out.write(chunk)
        partial.replace(dest)
    except OSError as exc:  # requests.RequestException is an OSError too
        with contextlib.suppress(OSError):
            partial.unlink(missing_ok=True)
        raise CliError(
            "download_failed", f"download failed: {type(exc).__name__}", {"path": str(dest)}
        ) from None
    return dest.stat().st_size
