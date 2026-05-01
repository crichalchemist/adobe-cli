"""Export operations for Adobe Illustrator.

All exports write to /tmp first (guaranteed writable), then move to the
caller-specified output path. Illustrator's ExtendScript file APIs require
Folder objects created in advance; File objects represent the target.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

# Python and Illustrator's Folder.temp resolve to the same per-user temp dir.
# /tmp is NOT writable by Illustrator's sandbox for raster export output.
_EXPORT_TMP_DIR = tempfile.gettempdir()

EXPORT_TIMEOUT = 120


def _js_path(path: str) -> str:
    """Return a JS-safe path string: forward slashes, escaped double-quotes."""
    return path.replace("\\", "/").replace('"', '\\"')


def _tmp_path(suffix: str) -> str:
    """Create a placeholder temp path in the per-user temp dir that Illustrator can write to."""
    import os
    fd, tmp = tempfile.mkstemp(prefix="cli_illustrator_export_", suffix=suffix, dir=_EXPORT_TMP_DIR)
    os.close(fd)
    os.unlink(tmp)
    return tmp


def export_png(
    output_path: str,
    backend: Any,
    artboard: int | None = None,
    resolution: float = 150.0,
) -> dict:
    """Export active document (or artboard) as PNG."""
    tmp = _tmp_path(".png")
    tmp_js = _js_path(tmp)
    artboard_js = f"opts.artBoardClipping = true; doc.artboards.setActiveArtboardIndex({artboard});" if artboard is not None else ""

    script = f"""\
var doc = app.activeDocument;
var opts = new ExportOptionsPNG24();
opts.antiAliasing = true;
opts.transparency = true;
opts.resolution = {resolution};
{artboard_js}
var f = new File("{tmp_js}");
doc.exportFile(f, ExportType.PNG24, opts);
JSON.stringify({{ok: true, tmp: "{tmp_js}"}});
"""
    backend.eval_json(script, timeout=EXPORT_TIMEOUT)
    return _move_output(tmp, output_path, ".png")


def export_jpeg(
    output_path: str,
    backend: Any,
    artboard: int | None = None,
    quality: int = 8,
    resolution: float = 150.0,
) -> dict:
    """Export active document (or artboard) as JPEG."""
    if not 1 <= quality <= 10:
        raise ValueError(f"JPEG quality must be 1–10, got {quality}")
    tmp = _tmp_path(".jpg")
    tmp_js = _js_path(tmp)
    artboard_js = f"opts.artBoardClipping = true; doc.artboards.setActiveArtboardIndex({artboard});" if artboard is not None else ""

    script = f"""\
var doc = app.activeDocument;
var opts = new ExportOptionsJPEG();
opts.qualitySetting = {quality};
opts.resolution = {resolution};
opts.antiAliasing = true;
{artboard_js}
var f = new File("{tmp_js}");
doc.exportFile(f, ExportType.JPEG, opts);
JSON.stringify({{ok: true, tmp: "{tmp_js}"}});
"""
    backend.eval_json(script, timeout=EXPORT_TIMEOUT)
    return _move_output(tmp, output_path, ".jpg")


def export_svg(
    output_path: str,
    backend: Any,
) -> dict:
    """Export active document as SVG (Scalable Vector Graphics)."""
    tmp = _tmp_path(".svg")
    tmp_js = _js_path(tmp)

    script = f"""\
var doc = app.activeDocument;
var opts = new ExportOptionsSVG();
opts.embedRasterImages = false;
opts.cssProperties = SVGCSSPropertyLocation.PRESENTATIONATTRIBUTES;
var f = new File("{tmp_js}");
doc.exportFile(f, ExportType.SVG, opts);
JSON.stringify({{ok: true, tmp: "{tmp_js}"}});
"""
    backend.eval_json(script, timeout=EXPORT_TIMEOUT)
    return _move_output(tmp, output_path, ".svg")


def export_pdf(
    output_path: str,
    backend: Any,
) -> dict:
    """Save active document as PDF."""
    tmp = _tmp_path(".pdf")
    tmp_js = _js_path(tmp)

    script = f"""\
var doc = app.activeDocument;
var opts = new PDFSaveOptions();
opts.compatibility = PDFCompatibility.ACROBAT5;
opts.generateThumbnails = false;
opts.preserveEditability = false;
var f = new File("{tmp_js}");
doc.saveAs(f, opts);
JSON.stringify({{ok: true, tmp: "{tmp_js}"}});
"""
    backend.eval_json(script, timeout=EXPORT_TIMEOUT)
    return _move_output(tmp, output_path, ".pdf")


def _move_output(tmp: str, output_path: str, expected_suffix: str) -> dict:
    """Move tmp file to output_path; find the actual file if Illustrator changed the name."""
    tmp_path = Path(tmp)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if tmp_path.exists():
        shutil.move(str(tmp_path), str(out_path))
        return {"output": str(out_path), "file_size": out_path.stat().st_size}

    # Illustrator sometimes appends the artboard name to the filename
    stem = tmp_path.stem
    parent = tmp_path.parent
    candidates = sorted(parent.glob(f"{stem}*{expected_suffix}"))
    if candidates:
        shutil.move(str(candidates[0]), str(out_path))
        for extra in candidates[1:]:
            extra.unlink(missing_ok=True)
        return {"output": str(out_path), "file_size": out_path.stat().st_size}

    raise RuntimeError(
        f"Export appeared to succeed but no output file found near {tmp}.\n"
        f"Ensure Illustrator has a document open and can write to /tmp."
    )
