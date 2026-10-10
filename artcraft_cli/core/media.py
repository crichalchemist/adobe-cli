"""Library media: image upload, lookup, listing and CDN downloads."""

from __future__ import annotations

import base64
import os
import re
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from artcraft_cli.errors import CliError
from artcraft_cli.utils import bridge

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
IMAGE_MAGIC = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a")
MEDIA_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


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


def read_image(path: Path) -> bytes:
    """Read a PNG/JPEG/GIF of at most 20 MiB; checked before any RPC."""
    try:
        size = path.stat().st_size
        if size > MAX_UPLOAD_BYTES:
            raise CliError(
                "input_file_error",
                f"{path} is {size} bytes; the limit is {MAX_UPLOAD_BYTES}",
                {"max_bytes": MAX_UPLOAD_BYTES},
            )
        data = path.read_bytes()
    except OSError as exc:
        raise CliError("input_file_error", f"cannot read {path}: {exc.strerror}") from None
    if not data.startswith(IMAGE_MAGIC):
        raise CliError("upload_type_unsupported", f"{path} is not a PNG, JPEG or GIF image")
    return data


def upload(path: Path, token: str) -> dict[str, Any]:
    data = read_image(path)
    content = base64.b64encode(data).decode("ascii")
    return bridge.rpc("media.upload", {"content_base64": content, "idempotency_token": token})


def get(media_token: str) -> dict[str, Any]:
    return bridge.rpc("media.get", {"media_token": media_token})


def list_media(
    *, classes: list[str], page: int, page_size: int, oldest_first: bool
) -> dict[str, Any]:
    args: dict[str, Any] = {
        "page_index": page,
        "page_size": page_size,
        "sort_ascending": oldest_first,
    }
    if classes:
        args["media_classes"] = classes
    return bridge.rpc("media.list", args)


def download(media_token: str, out_dir: Path, *, force: bool) -> dict[str, Any]:
    found = get(media_token)
    path, byte_count = download_to(media_token, found.get("cdn_url"), out_dir, force=force)
    return {"media_token": media_token, "path": str(path), "byte_count": byte_count}


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
    if not isinstance(media_token, str) or not MEDIA_TOKEN_RE.fullmatch(media_token):
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
