"""Artboard operations for Adobe Illustrator."""

from __future__ import annotations

from typing import Any


class ArtboardError(RuntimeError):
    """Raised on artboard index errors or missing document."""


def list_artboards(backend: Any) -> list[dict]:
    """Return all artboards with name, dimensions, and index."""
    script = """\
var result = [];
if (app.documents.length) {
    var doc = app.activeDocument;
    for (var i = 0; i < doc.artboards.length; i++) {
        var ab = doc.artboards[i];
        var r = ab.artboardRect;
        result.push({
            index: i,
            name: ab.name,
            width: r[2] - r[0],
            height: r[1] - r[3],
            x: r[0],
            y: r[3]
        });
    }
}
JSON.stringify(result);
"""
    data = backend.eval_json(script)
    return data if isinstance(data, list) else []


def set_active_artboard(index: int, backend: Any) -> dict:
    """Set the active artboard by zero-based index."""
    if index < 0:
        raise ValueError(f"Artboard index must be >= 0, got {index}")
    script = f"""\
if (!app.documents.length) {{
    JSON.stringify({{error: "No document open"}});
}} else {{
    var doc = app.activeDocument;
    if ({index} >= doc.artboards.length) {{
        JSON.stringify({{error: "Artboard index {index} out of range (count: " + doc.artboards.length + ")"}});
    }} else {{
        doc.artboards.setActiveArtboardIndex({index});
        var ab = doc.artboards[{index}];
        var r = ab.artboardRect;
        JSON.stringify({{ok: true, index: {index}, name: ab.name, width: r[2]-r[0], height: r[1]-r[3]}});
    }}
}}
"""
    data = backend.eval_json(script)
    if isinstance(data, dict) and "error" in data:
        raise ArtboardError(data["error"])
    return data
