"""CLI errors and the code → (hint, retryable) table from the wire contract (spec §5.6)."""

from __future__ import annotations

from typing import Any


class CliError(Exception):
    """An error with a stable snake_case code. Messages never carry the bridge token."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details: dict[str, Any] = details or {}


HINTS: dict[str, tuple[str | None, bool]] = {
    # Gate and bridge failures (non-2xx HTTP)
    "invalid_request": (None, False),
    "unauthorized": ("the app restarted; the CLI already re-read discovery once", True),
    "forbidden_host": ("call 127.0.0.1", False),
    "forbidden_origin": ("browsers cannot use the bridge", False),
    "not_found": (None, False),
    "method_not_allowed": (None, False),
    "payload_too_large": ("images must be 20 MiB or smaller", False),
    "unsupported_media_type": (None, False),
    "internal_error": ("check the ArtCraft log", False),
    "bridge_busy": ("back off, then retry", True),
    # Op errors (HTTP 200, ok: false)
    "unknown_op": ("run `artcraft-cli ping` to see the supported ops", False),
    "invalid_args": (None, False),
    "args_too_large": (None, False),
    "unsupported_route": ("pick a model from `artcraft-cli models list`", False),
    "operation_in_progress": ("wait, then retry with the same --idempotency-token", True),
    "credentials_not_synced": ("the app just started; the CLI already waited 5 s", True),
    "not_logged_in": ("log in inside the ArtCraft app", False),
    "cost_exceeds_limit": ("raise --max-credits or choose another model", False),
    "estimate_unavailable": (None, False),
    "insufficient_credits": ("buy credits in the ArtCraft app", False),
    "rate_limited": ("back off, then retry", True),
    "upstream_bad_input": ("fix the request", False),
    "upstream_unavailable": ("retry later", True),
    "upstream_error": (None, False),
    "outcome_unknown": (
        "do not resubmit; run `artcraft-cli --json jobs list --remote --all` and match on "
        "model and a created_at at or after the submit time",
        False,
    ),
    "job_not_found": (None, False),
    "job_not_terminal": ("wait for the job to finish first", False),
    "media_not_found": (None, False),
    "upload_type_unsupported": ("convert the image to PNG, JPEG or GIF first", False),
    "setting_not_writable": (None, False),
    "local_store_error": ("check the ArtCraft log", False),
    # CLI-only codes
    "usage_error": ("see --help", False),
    "bridge_not_running": ("start ArtCraft with ARTCRAFT_CLI_BRIDGE=1", True),
    "discovery_insecure": ("fix the discovery file's owner or mode, or restart ArtCraft", False),
    "bridge_protocol_mismatch": ("update artcraft-cli or the ArtCraft app", False),
    "bridge_protocol_error": ("check the ArtCraft log", False),
    "response_timeout": ("retry", True),
    "job_failed": ("inspect details", False),
    "job_wait_timeout": ("wait longer, or check `artcraft-cli jobs get`", True),
    "download_failed": ("retry", True),
    "output_exists": ("pass --force or choose another --out", False),
    "input_file_error": (None, False),
}


def error_payload(err: CliError) -> dict[str, Any]:
    """The --json error object. Unknown codes are generic and not retryable."""
    hint, retryable = HINTS.get(err.code, (None, False))
    body: dict[str, Any] = {
        "code": err.code,
        "message": err.message,
        "hint": hint,
        "retryable": retryable,
    }
    if err.details:
        body["details"] = err.details
    return {"error": body}
