"""Library media: image upload, lookup, listing and CDN downloads."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from urllib.parse import urlparse

from artcraft_cli.errors import CliError
from artcraft_cli.utils import bridge


def idempotency_token(value: str | None) -> str:
    """The caller's token if it is a canonical lowercase UUID, else a fresh uuid4."""
    if value is None:
        return str(uuid.uuid4())
    try:
        canonical = str(uuid.UUID(value))
    except ValueError:
        canonical = ""
    if canonical != value:
        raise CliError("usage_error", "--idempotency-token must be a lowercase hyphenated UUID")
    return value


def prepare_download_dir(out_dir: Path) -> None:
    """Create out_dir and check it is writable, so a bad --download fails before any spend."""
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CliError("usage_error", f"--download {out_dir}: {exc.strerror}") from None
    if not os.access(out_dir, os.W_OK | os.X_OK):
        raise CliError("usage_error", f"--download {out_dir} is not writable")


def plan(media_token: str, cdn_url: str | None, out_dir: Path) -> tuple[str, Path]:
    """Check a result file without fetching it; return (cdn_url, its destination path)."""
    if not cdn_url:
        raise CliError("download_failed", f"media {media_token} has no cdn_url")
    if media_token in ("", ".", "..") or Path(media_token).name != media_token:
        raise CliError(
            "download_failed",
            "media token is not a plain file name",
            {"media_token": media_token},
        )
    return cdn_url, out_dir / f"{media_token}{Path(urlparse(cdn_url).path).suffix}"


def download_to(
    media_token: str, cdn_url: str | None, out_dir: Path, *, force: bool
) -> tuple[Path, int]:
    """Save one file as <out_dir>/<media_token><suffix of the CDN path>."""
    url, path = plan(media_token, cdn_url, out_dir)
    return path, bridge.download(url, path, force=force)
