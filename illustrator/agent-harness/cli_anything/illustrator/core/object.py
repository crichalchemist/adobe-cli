"""Page item (object) and selection operations for Adobe Illustrator."""

from __future__ import annotations

from typing import Any


def _escape_js_str(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def list_objects(backend: Any, layer: str | None = None) -> list[dict]:
    """Return page items from the active document, optionally filtered by layer name."""
    if layer:
        layer_filter = f"""\
    var items;
    var found = false;
    for (var li = 0; li < doc.layers.length; li++) {{
        if (doc.layers[li].name === "{_escape_js_str(layer)}") {{
            items = doc.layers[li].pageItems;
            found = true;
            break;
        }}
    }}
    if (!found) {{ JSON.stringify([]); }}
"""
        items_ref = "items"
    else:
        layer_filter = "    var items = doc.pageItems;"
        items_ref = "items"

    script = f"""\
var result = [];
if (app.documents.length) {{
    var doc = app.activeDocument;
{layer_filter}
    if (typeof items !== "undefined") {{
        for (var i = 0; i < {items_ref}.length; i++) {{
            var item = {items_ref}[i];
            var gb = item.geometricBounds;
            result.push({{
                index: i,
                name: item.name || "",
                type: item.typename,
                x: gb[0],
                y: gb[1],
                width: gb[2] - gb[0],
                height: gb[1] - gb[3],
                visible: item.hidden ? false : true,
                locked: item.locked,
                layer: item.layer ? item.layer.name : ""
            }});
        }}
    }}
}}
JSON.stringify(result);
"""
    data = backend.eval_json(script)
    return data if isinstance(data, list) else []


def get_selection(backend: Any) -> list[dict]:
    """Return the currently selected page items."""
    script = """\
var result = [];
if (app.documents.length) {
    var sel = app.activeDocument.selection;
    for (var i = 0; i < sel.length; i++) {
        var item = sel[i];
        var gb = item.geometricBounds;
        result.push({
            index: i,
            name: item.name || "",
            type: item.typename,
            x: gb[0],
            y: gb[1],
            width: gb[2] - gb[0],
            height: gb[1] - gb[3],
            layer: item.layer ? item.layer.name : ""
        });
    }
}
JSON.stringify(result);
"""
    data = backend.eval_json(script)
    return data if isinstance(data, list) else []
