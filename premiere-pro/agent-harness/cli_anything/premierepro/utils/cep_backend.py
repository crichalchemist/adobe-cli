"""HTTP client to the cli-anything CEP bridge running inside Premiere Pro."""
from __future__ import annotations
import json
import os
from typing import Any

import requests
from requests.exceptions import ConnectionError as RequestsConnectionError, Timeout

PORT = int(os.environ.get("CLI_ANYTHING_PORT", "7788"))
BASE_URL = f"http://127.0.0.1:{PORT}"
TIMEOUT = 30  # seconds; long enough for slow ExtendScript operations
PING_TIMEOUT = 5  # seconds; liveness check only


class CepNotRunningError(RuntimeError):
    """Raised when the CEP bridge HTTP server is not reachable."""
    def __init__(self) -> None:
        super().__init__(
            f"Cannot reach cli-anything CEP bridge on port {PORT}. "
            "Is Adobe Premiere Pro 2025 open? "
            "Check Window > Extensions > cli-anything is visible."
        )


_sess = requests.Session()


def _session() -> requests.Session:
    return _sess


def ping() -> dict:
    """Return bridge status; raises CepNotRunningError if unreachable."""
    try:
        resp = _session().get(f"{BASE_URL}/ping", timeout=PING_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except (RequestsConnectionError, Timeout) as exc:
        raise CepNotRunningError() from exc
    except (requests.HTTPError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"CEP bridge returned invalid ping response: {exc}") from exc


def eval_script(script: str) -> str:
    """Execute ExtendScript in Premiere Pro and return the string result."""
    try:
        resp = _session().post(
            f"{BASE_URL}/eval",
            json={"script": script},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except (RequestsConnectionError, Timeout) as exc:
        raise CepNotRunningError() from exc
    except (requests.HTTPError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"CEP bridge returned invalid response: {exc}") from exc
    if not data.get("ok"):
        raise RuntimeError(data.get("error", "Unknown ExtendScript error"))
    if "result" not in data:
        raise RuntimeError(f"CEP bridge response missing 'result' field: {data!r}")
    return data["result"]


def escape_estk(value: str) -> str:
    """Escape a string for safe embedding inside ExtendScript double-quoted literals."""
    return (
        value
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def eval_json(script: str) -> Any:
    """Execute ExtendScript that returns JSON.stringify(...) and parse the result."""
    raw = eval_script(script)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"CEP returned non-JSON: {raw!r}") from exc
