"""Parse .prproj (gzip-compressed XML) Premiere Pro project files.

.prproj files are gzip-compressed XML with Adobe's proprietary schema.
This parser extracts structural information accessible without running Premiere.
"""
from __future__ import annotations
import gzip
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ITEM_TYPE_SEQUENCE = "2"


@dataclass
class SequenceInfo:
    name: str
    uid: str
    frame_rate: str | None = None
    width: int | None = None
    height: int | None = None


@dataclass
class MediaRef:
    name: str
    path: str | None = None
    media_type: str | None = None  # "video", "audio", "image", "unknown"


def parse_prproj(path: str) -> dict[str, Any]:
    """Parse a .prproj file and return a dict with sequences and media refs."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Project file not found: {path}")

    try:
        with gzip.open(path, "rb") as f:
            raw = f.read()
    except (OSError, gzip.BadGzipFile) as exc:
        raise ValueError(f"File is not a valid .prproj (not gzip): {path}") from exc

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"File is not a valid .prproj (bad XML): {path}") from exc

    sequences = _extract_sequences(root)
    media = _extract_media(root)

    return {
        "path": os.path.abspath(path),
        "file_size": os.path.getsize(path),
        "sequences": [vars(s) for s in sequences],
        "sequence_count": len(sequences),
        "media": [vars(m) for m in media],
        "media_count": len(media),
    }


def _extract_sequences(root: ET.Element) -> list[SequenceInfo]:
    seqs: list[SequenceInfo] = []
    seen: set[str] = set()
    for el in root.iter():
        name_el = el.find("Name")
        uid = el.get("ObjectUID") or el.get("ObjectRef") or ""
        # Only deduplicate when a non-empty UID is present; UID-less elements each get through
        if uid and uid in seen:
            continue
        if el.tag == "Sequence" and name_el is not None:
            if uid:
                seen.add(uid)
            seqs.append(SequenceInfo(name=name_el.text or "Untitled", uid=uid))
        elif el.tag == "ProjectItem" and el.get("type") == PROJECT_ITEM_TYPE_SEQUENCE and name_el is not None:
            if uid:
                seen.add(uid)
            seqs.append(SequenceInfo(name=name_el.text or "Untitled", uid=uid))
    return seqs


def _extract_media(root: ET.Element) -> list[MediaRef]:
    media: list[MediaRef] = []
    seen: set[str] = set()
    for el in root.iter():
        # Avoid Element.__bool__ deprecation: check None explicitly
        path_el = el.find("ActualMediaFilePath")
        if path_el is None:
            path_el = el.find("FilePath")
        if path_el is None:
            continue
        fpath = path_el.text or ""
        if not fpath or fpath in seen:
            continue
        seen.add(fpath)
        name_el = el.find("Name")
        name = (name_el.text if name_el is not None else None) or Path(fpath).name
        ext = Path(fpath).suffix.lower()
        media.append(MediaRef(name=name, path=fpath, media_type=_media_type_from_ext(ext)))
    return media


def _media_type_from_ext(ext: str) -> str:
    if ext in {".mp4", ".mov", ".avi", ".mxf", ".mkv", ".r3d", ".braw"}:
        return "video"
    if ext in {".mp3", ".wav", ".aac", ".aiff", ".m4a", ".flac"}:
        return "audio"
    if ext in {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".dpx", ".exr", ".psd"}:
        return "image"
    return "unknown"
