"""Illustrator backend: executes ExtendScript in Adobe Illustrator via osascript.

Transport: write JSX to a temp file, then:
    osascript -e 'tell application "Adobe Illustrator" to do javascript "#include \"/tmp/x.jsx\""'

This sidesteps all AppleScript string-escaping complexity — only the temp path is
embedded in the AppleScript string, and /tmp paths never contain special characters.

The JSON polyfill is prepended to every script because Illustrator's ExtendScript
engine is ES3 (no native JSON).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


APP_NAME = "Adobe Illustrator"
PING_TIMEOUT = 10
DEFAULT_TIMEOUT = 30
EXPORT_TIMEOUT = 120


class IllustratorNotRunningError(RuntimeError):
    """Raised when Adobe Illustrator is not running or not responding."""


# Loop-based stringify avoids regex backslash patterns that survive poorly
# through multiple escaping layers. Char-by-char iteration is ES3-safe.
_JSON_POLYFILL = """\
if (typeof JSON === "undefined") {
    var JSON = {};
    JSON.stringify = function(v) {
        if (v === null || v === undefined) return "null";
        if (typeof v === "number") return isFinite(v) ? String(v) : "null";
        if (typeof v === "boolean") return String(v);
        if (typeof v === "string") {
            var out = '"';
            for (var i = 0; i < v.length; i++) {
                var c = v.charAt(i);
                if (c === '"') out += '\\\\"';
                else if (c === '\\\\') out += '\\\\\\\\';
                else if (c === '\\n') out += '\\\\n';
                else if (c === '\\r') out += '\\\\r';
                else if (c === '\\t') out += '\\\\t';
                else out += c;
            }
            return out + '"';
        }
        if (v instanceof Array) {
            var a = [];
            for (var i = 0; i < v.length; i++) a.push(JSON.stringify(v[i]));
            return "[" + a.join(",") + "]";
        }
        if (typeof v === "object") {
            var b = [];
            for (var k in v) {
                if (Object.prototype.hasOwnProperty.call(v, k))
                    b.push(JSON.stringify(k) + ":" + JSON.stringify(v[k]));
            }
            return "{" + b.join(",") + "}";
        }
        return undefined;
    };
    JSON.parse = function(s) { return eval("(" + s + ")"); };
}
"""


def _write_jsx(script_body: str) -> Path:
    """Write polyfill + script body to a temp .jsx file; caller must delete it."""
    fd, path_str = tempfile.mkstemp(prefix="cli_illustrator_", suffix=".jsx", dir="/tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(_JSON_POLYFILL)
            f.write("\n")
            f.write(script_body)
    except Exception:
        os.unlink(path_str)
        raise
    return Path(path_str)


def _run_jsx_file(jsx_path: Path, timeout: int) -> str:
    """Execute a .jsx file in Illustrator via AppleScript #include directive."""
    abs_path = str(jsx_path.resolve())
    script = f'tell application "{APP_NAME}" to do javascript "#include \\"{abs_path}\\""'
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        err = result.stderr.strip()
        if "Application isn" in err or "can't get" in err.lower() or "is not running" in err.lower():
            raise IllustratorNotRunningError(
                f"Adobe Illustrator is not running or not responding.\n"
                f"Launch Illustrator and open a document, then try again.\n"
                f"Details: {err}"
            )
        raise RuntimeError(f"Illustrator script execution failed:\n{err}")
    return result.stdout.strip()


def eval_jsx(script_body: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Execute ExtendScript in Illustrator, return raw string result."""
    jsx_path = _write_jsx(script_body)
    try:
        raw = _run_jsx_file(jsx_path, timeout)
    finally:
        jsx_path.unlink(missing_ok=True)
    if raw.startswith("Error ") or raw.startswith("TypeError") or raw.startswith("ReferenceError"):
        raise RuntimeError(f"ExtendScript error: {raw}")
    return raw


def eval_json(script_body: str, timeout: int = DEFAULT_TIMEOUT) -> dict | list:
    """Execute ExtendScript in Illustrator, parse JSON result."""
    raw = eval_jsx(script_body, timeout)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Expected JSON from Illustrator, got: {raw!r}") from exc


def ping() -> dict:
    """Return health-check dict; raises IllustratorNotRunningError if not reachable."""
    script = """\
var result = {ok: true, app: "illustrator", version: "1.0.0", app_version: app.version};
JSON.stringify(result);
"""
    return eval_json(script, timeout=PING_TIMEOUT)


def reachable() -> bool:
    """Return True if Illustrator is running and responsive."""
    try:
        ping()
        return True
    except (IllustratorNotRunningError, RuntimeError, subprocess.TimeoutExpired):
        return False
