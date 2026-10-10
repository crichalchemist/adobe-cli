"""Library media: image upload, lookup, listing and CDN downloads."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from artcraft_cli.errors import CliError
from artcraft_cli.utils import bridge


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
