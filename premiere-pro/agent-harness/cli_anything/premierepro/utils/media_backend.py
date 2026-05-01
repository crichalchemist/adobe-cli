"""Media file metadata using OpenCV and macOS mdls.

OpenCV handles video frame metrics; mdls fills in codec/bitrate metadata
using macOS Spotlight which has native codec awareness.
"""
from __future__ import annotations
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

import cv2

_MDLS_TIMEOUT_SECONDS = 5

_MDLS_ATTRS = [
    "kMDItemCodecs",
    "kMDItemTotalBitRate",
    "kMDItemContentType",
    "kMDItemDurationSeconds",
]


@contextmanager
def _video_capture(path: str) -> Generator[cv2.VideoCapture, None, None]:
    cap = cv2.VideoCapture(path)
    try:
        yield cap
    finally:
        cap.release()


def get_media_info(path: str) -> dict[str, Any]:
    """Return metadata dict for any media file. No Premiere required."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Media file not found: {path}")

    info: dict[str, Any] = {
        "path": str(p.resolve()),
        "file_size": p.stat().st_size,
        "name": p.name,
        "extension": p.suffix.lower(),
    }

    with _video_capture(path) as cap:
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
            fourcc = "".join(chr((fourcc_int >> (8 * i)) & 0xFF) for i in range(4)).strip("\x00")
            info.update({
                "width": w if w > 0 else None,
                "height": h if h > 0 else None,
                "fps": round(fps, 3) if fps else None,
                "frame_count": frame_count if frame_count > 0 else None,
                "duration_seconds": round(frame_count / fps, 3) if fps and frame_count else None,
                "fourcc": fourcc or None,
            })
        else:
            info.update({
                "width": None,
                "height": None,
                "fps": None,
                "frame_count": None,
                "duration_seconds": None,
                "fourcc": None,
            })

    mdls = _mdls_metadata(path)
    if mdls:
        info["codec"] = mdls.get("kMDItemCodecs")
        info["total_bit_rate"] = mdls.get("kMDItemTotalBitRate")
        info["content_type"] = mdls.get("kMDItemContentType")
        info["duration_mdls"] = mdls.get("kMDItemDurationSeconds")

    return info


def _mdls_metadata(path: str) -> dict[str, Any] | None:
    """Call macOS mdls and return selected Spotlight attributes, or None if unavailable."""
    try:
        result = subprocess.run(
            ["mdls", "-raw", "-nullMarker", "null"]
            + [arg for a in _MDLS_ATTRS for arg in ("-name", a)]
            + [path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_MDLS_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            return None
        lines = result.stdout.strip().split("\n")
        try:
            pairs = list(zip(_MDLS_ATTRS, lines, strict=True))
        except ValueError:
            return None  # line count mismatch — malformed output
        out: dict[str, Any] = {}
        for attr, val in pairs:
            v = val.strip()
            if v == "null":
                out[attr] = None
            elif v.startswith("(") and v.endswith(")"):
                inner = v[1:-1].strip()
                out[attr] = [x.strip().strip('"') for x in inner.split(",") if x.strip()]
            else:
                try:
                    out[attr] = float(v)
                except ValueError:
                    out[attr] = v.strip('"')
        return out
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
