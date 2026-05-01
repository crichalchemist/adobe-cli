"""Layer operations for Adobe Illustrator."""

from __future__ import annotations

from typing import Any


class LayerNotFoundError(RuntimeError):
    """Raised when the named layer does not exist."""


def _escape_js_str(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def list_layers(backend: Any) -> list[dict]:
    """Return all layers (including sublayers) as a flat list with depth."""
    script = """\
var result = [];
function collectLayers(layers, depth) {
    for (var i = 0; i < layers.length; i++) {
        var l = layers[i];
        result.push({
            name: l.name,
            visible: l.visible,
            locked: l.locked,
            depth: depth
        });
        if (l.layers && l.layers.length) {
            collectLayers(l.layers, depth + 1);
        }
    }
}
if (app.documents.length) {
    collectLayers(app.activeDocument.layers, 0);
}
JSON.stringify(result);
"""
    data = backend.eval_json(script)
    return data if isinstance(data, list) else []


def set_layer_visible(name: str, visible: bool, backend: Any) -> dict:
    """Set the visibility of a named layer."""
    esc = _escape_js_str(name)
    vis_str = "true" if visible else "false"
    script = f"""\
var found = false;
if (app.documents.length) {{
    var layers = app.activeDocument.layers;
    for (var i = 0; i < layers.length; i++) {{
        if (layers[i].name === "{esc}") {{
            layers[i].visible = {vis_str};
            found = true;
            break;
        }}
    }}
}}
if (found) {{
    JSON.stringify({{ok: true, name: "{esc}", visible: {vis_str}}});
}} else {{
    JSON.stringify({{error: "Layer not found: {esc}"}});
}}
"""
    data = backend.eval_json(script)
    if isinstance(data, dict) and "error" in data:
        raise LayerNotFoundError(data["error"])
    return data


def set_layer_locked(name: str, locked: bool, backend: Any) -> dict:
    """Set the locked state of a named layer."""
    esc = _escape_js_str(name)
    lock_str = "true" if locked else "false"
    script = f"""\
var found = false;
if (app.documents.length) {{
    var layers = app.activeDocument.layers;
    for (var i = 0; i < layers.length; i++) {{
        if (layers[i].name === "{esc}") {{
            layers[i].locked = {lock_str};
            found = true;
            break;
        }}
    }}
}}
if (found) {{
    JSON.stringify({{ok: true, name: "{esc}", locked: {lock_str}}});
}} else {{
    JSON.stringify({{error: "Layer not found: {esc}"}});
}}
"""
    data = backend.eval_json(script)
    if isinstance(data, dict) and "error" in data:
        raise LayerNotFoundError(data["error"])
    return data
