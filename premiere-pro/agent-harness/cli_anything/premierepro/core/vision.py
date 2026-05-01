"""Agent vision: screenshot capture and frame burst for Premiere Pro.

Workflow: CEP /scrub endpoint moves the active sequence playhead via ExtendScript,
then macOS screencapture grabs Premiere Pro's window by CGWindowID.
OpenCV compares frames for programmatic change detection.
"""
from __future__ import annotations
import os
import subprocess
import tempfile
import time
from typing import Optional

import cv2
import numpy as np

from cli_anything.premierepro.utils import cep_backend as cep


def _get_premiere_window_id() -> Optional[str]:
    """Return CGWindowID for Premiere Pro's main window via Quartz."""
    script = (
        "import Quartz\n"
        "ws = Quartz.CGWindowListCopyWindowInfo("
        "Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)\n"
        "ids = [str(w['kCGWindowNumber']) for w in ws "
        "if 'Premiere' in (w.get('kCGWindowOwnerName') or '')]\n"
        "print(ids[0] if ids else '')"
    )
    try:
        r = subprocess.run(
            ["python3", "-c", script], capture_output=True, text=True, timeout=5
        )
        if r.returncode != 0:
            return None  # Quartz unavailable; fall back to full-screen capture
        wid = r.stdout.strip()
        return wid or None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def capture_window_screenshot(output_path: Optional[str] = None) -> dict:
    """Capture Premiere Pro's window as PNG. Returns {path, file_size, width, height}."""
    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".png", prefix="ppro_vision_")
        os.close(fd)
        os.unlink(output_path)

    wid = _get_premiere_window_id()
    cmd = (["screencapture", "-x", "-l", wid, output_path]
           if wid else ["screencapture", "-x", output_path])

    result = subprocess.run(cmd, capture_output=True, timeout=10)
    if result.returncode != 0 or not os.path.exists(output_path):
        raise RuntimeError(f"screencapture failed (rc={result.returncode})")

    img = cv2.imread(output_path)
    if img is None:
        raise RuntimeError(f"screencapture wrote an unreadable image: {output_path}")
    h, w = img.shape[:2]
    return {
        "path": output_path,
        "file_size": os.path.getsize(output_path),
        "width": w,
        "height": h,
    }


def scrub_and_capture(
    seconds: float,
    output_path: Optional[str] = None,
    settle_ms: int = 300,
) -> dict:
    """Move timeline playhead to `seconds`, wait settle_ms, then screenshot."""
    resp = cep._session().post(
        f"{cep.BASE_URL}/scrub",
        json={"seconds": seconds},
        timeout=cep.TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("error", "Scrub failed"))

    time.sleep(settle_ms / 1000.0)
    info = capture_window_screenshot(output_path)
    info["seconds"] = seconds
    return info


def burst_frames(
    start: float,
    end: float,
    step: float,
    output_dir: str,
    settle_ms: int = 300,
) -> list[dict]:
    """Capture one frame every `step` seconds from `start` to `end` inclusive."""
    if step <= 0:
        raise ValueError(f"step must be positive, got {step}")
    os.makedirs(output_dir, exist_ok=True)
    frames: list[dict] = []
    t, idx = start, 0
    while t <= end + 1e-9:
        out_path = os.path.join(output_dir, f"frame_{idx:04d}_{t:.3f}s.png")
        frames.append(scrub_and_capture(t, output_path=out_path, settle_ms=settle_ms))
        t = round(t + step, 6)
        idx += 1
    return frames


def compare_frames(path_a: str, path_b: str) -> dict:
    """Pixel-diff two PNG frames; return metrics for agent decision-making."""
    img_a = cv2.imread(path_a)
    img_b = cv2.imread(path_b)
    if img_a is None or img_b is None:
        raise ValueError(f"Could not read: {path_a}, {path_b}")
    if img_a.shape != img_b.shape:
        img_b = cv2.resize(img_b, (img_a.shape[1], img_a.shape[0]))
    diff = cv2.absdiff(img_a, img_b)
    mean_diff = float(np.mean(diff))
    return {
        "mean_pixel_diff": round(mean_diff, 3),
        "max_pixel_diff": float(np.max(diff)),
        "similarity": round(1.0 - mean_diff / 255.0, 4),
        "identical": mean_diff < 0.5,
    }
