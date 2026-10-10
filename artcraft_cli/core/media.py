"""Library media: image upload, lookup, listing and CDN downloads."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from artcraft_cli.errors import CliError
from artcraft_cli.utils import bridge


def download_to(
    media_token: str, cdn_url: str | None, out_dir: Path, *, force: bool
) -> tuple[Path, int]:
    """Save one file as <out_dir>/<media_token><suffix of the CDN path>."""
    if not cdn_url:
        raise CliError("download_failed", f"media {media_token} has no cdn_url")
    path = out_dir / f"{media_token}{Path(urlparse(cdn_url).path).suffix}"
    return path, bridge.download(cdn_url, path, force=force)
