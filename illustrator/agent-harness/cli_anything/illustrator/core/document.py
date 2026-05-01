"""Document-level operations for Adobe Illustrator."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class Backend(Protocol):
    def eval_json(self, script: str, timeout: int = 30) -> dict | list: ...
    def eval_jsx(self, script: str, timeout: int = 30) -> str: ...


class DocumentNotOpenError(RuntimeError):
    """Raised when no document is open in Illustrator."""


_RULER_UNIT_MAP: dict[int, str] = {
    0: "inches",
    1: "centimeters",
    2: "millimeters",
    3: "points",
    4: "picas",
    5: "Q",
    6: "pixels",
}


def _parse_color_space(raw: str) -> str:
    return "CMYK" if raw == "CMYK" else "RGB"


def _parse_ruler_units(raw: int | str) -> str:
    if isinstance(raw, int):
        return _RULER_UNIT_MAP.get(raw, str(raw))
    return str(raw)


def get_document_info(backend: Any) -> dict:
    """Return metadata for the active document."""
    script = """\
if (!app.documents.length) {
    JSON.stringify({error: "No document open"});
} else {
    var doc = app.activeDocument;
    var path = "";
    try {
        if (doc.saved) { path = doc.fullName.fsName; }
    } catch(e) {}
    var rulerStr = doc.rulerUnits.toString();
    var units = rulerStr.replace("RulerUnits.", "");
    var result = {
        name: doc.name,
        path: path,
        width: doc.width,
        height: doc.height,
        color_space: (doc.documentColorSpace === DocumentColorSpace.CMYK) ? "CMYK" : "RGB",
        ruler_units: units,
        layer_count: doc.layers.length,
        artboard_count: doc.artboards.length,
        path_item_count: doc.pathItems.length,
        text_frame_count: doc.textFrames.length,
        swatch_count: doc.swatches.length,
        modified: (doc.saved === false)
    };
    JSON.stringify(result);
}
"""
    data = backend.eval_json(script)
    if isinstance(data, dict) and "error" in data:
        raise DocumentNotOpenError(data["error"])
    return data


def list_documents(backend: Any) -> list[dict]:
    """Return a list of all open documents."""
    script = """\
var docs = [];
for (var i = 0; i < app.documents.length; i++) {
    var doc = app.documents[i];
    var path = "";
    try { if (doc.saved) { path = doc.fullName.fsName; } } catch(e) {}
    docs.push({
        name: doc.name,
        path: path,
        width: doc.width,
        height: doc.height,
        color_space: (doc.documentColorSpace === DocumentColorSpace.CMYK) ? "CMYK" : "RGB",
        active: (i === 0)
    });
}
JSON.stringify(docs);
"""
    result = backend.eval_json(script)
    if not isinstance(result, list):
        return []
    return result


def open_document(path: str, backend: Any) -> dict:
    """Open a .ai, .eps, or .pdf file in Illustrator."""
    resolved = Path(path).resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"File not found: {path}")
    suffix = resolved.suffix.lower()
    if suffix not in {".ai", ".eps", ".pdf", ".svg", ".fxg"}:
        raise ValueError(f"Unsupported file type: {suffix}")

    fs_path = str(resolved).replace("\\", "/").replace('"', '\\"')
    script = f"""\
var f = new File("{fs_path}");
app.open(f);
var doc = app.activeDocument;
var path = "";
try {{ path = doc.fullName.fsName; }} catch(e) {{}}
JSON.stringify({{ok: true, name: doc.name, path: path}});
"""
    return backend.eval_json(script)


def close_document(backend: Any, save: bool = False) -> dict:
    """Close the active document."""
    save_opt = "SaveOptions.SAVECHANGES" if save else "SaveOptions.DONOTSAVECHANGES"
    script = f"""\
if (!app.documents.length) {{
    JSON.stringify({{error: "No document open"}});
}} else {{
    var name = app.activeDocument.name;
    app.activeDocument.close({save_opt});
    JSON.stringify({{ok: true, closed: name}});
}}
"""
    data = backend.eval_json(script)
    if isinstance(data, dict) and "error" in data:
        raise DocumentNotOpenError(data["error"])
    return data


def save_document(backend: Any) -> dict:
    """Save the active document in place."""
    script = """\
if (!app.documents.length) {
    JSON.stringify({error: "No document open"});
} else {
    app.activeDocument.save();
    JSON.stringify({ok: true, name: app.activeDocument.name});
}
"""
    data = backend.eval_json(script)
    if isinstance(data, dict) and "error" in data:
        raise DocumentNotOpenError(data["error"])
    return data
