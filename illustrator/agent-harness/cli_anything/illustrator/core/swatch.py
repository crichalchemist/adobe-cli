"""Swatch operations for Adobe Illustrator."""

from __future__ import annotations

from typing import Any

_NONE_SWATCH = "[None]"
_REGISTRATION_SWATCH = "[Registration]"


def list_swatches(backend: Any, include_none: bool = False) -> list[dict]:
    """Return swatches in the active document.

    The "[None]" and "[Registration]" swatches are excluded by default;
    they are Illustrator internals, not user-defined colors.
    """
    script = """\
var result = [];
if (app.documents.length) {
    var swatches = app.activeDocument.swatches;
    for (var i = 0; i < swatches.length; i++) {
        var s = swatches[i];
        var entry = {name: s.name, spot: (s.spot !== null && s.spot !== undefined)};
        try {
            var c = s.color;
            var tn = c.typename;
            entry.color_type = tn;
            if (tn === "CMYKColor") {
                entry.c = c.cyan;
                entry.m = c.magenta;
                entry.y = c.yellow;
                entry.k = c.black;
            } else if (tn === "RGBColor") {
                entry.r = c.red;
                entry.g = c.green;
                entry.b = c.blue;
            } else if (tn === "SpotColor") {
                entry.tint = c.tint;
            } else if (tn === "GrayColor") {
                entry.gray = c.gray;
            }
        } catch(e) {
            entry.color_type = "unknown";
        }
        result.push(entry);
    }
}
JSON.stringify(result);
"""
    data = backend.eval_json(script)
    if not isinstance(data, list):
        return []
    if include_none:
        return data
    return [s for s in data if s.get("name") not in (_NONE_SWATCH, _REGISTRATION_SWATCH)]
