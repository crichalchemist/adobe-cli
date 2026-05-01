"""Text frame operations for Adobe Illustrator."""

from __future__ import annotations

from typing import Any


def _escape_js_str(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def list_text_frames(backend: Any) -> list[dict]:
    """Return all text frames in the active document."""
    script = """\
var result = [];
if (app.documents.length) {
    var frames = app.activeDocument.textFrames;
    for (var i = 0; i < frames.length; i++) {
        var f = frames[i];
        var gb = f.geometricBounds;
        result.push({
            index: i,
            contents: f.contents,
            x: gb[0],
            y: gb[1],
            width: gb[2] - gb[0],
            height: gb[1] - gb[3],
            layer: f.layer ? f.layer.name : ""
        });
    }
}
JSON.stringify(result);
"""
    data = backend.eval_json(script)
    return data if isinstance(data, list) else []


def set_text_content(index: int, content: str, backend: Any) -> dict:
    """Replace the contents of a text frame at the given zero-based index."""
    if index < 0:
        raise ValueError(f"Text frame index must be >= 0, got {index}")
    esc = _escape_js_str(content)
    script = f"""\
if (!app.documents.length) {{
    JSON.stringify({{error: "No document open"}});
}} else {{
    var frames = app.activeDocument.textFrames;
    if ({index} >= frames.length) {{
        JSON.stringify({{error: "Text frame index {index} out of range (count: " + frames.length + ")"}});
    }} else {{
        frames[{index}].contents = "{esc}";
        JSON.stringify({{ok: true, index: {index}, contents: "{esc}"}});
    }}
}}
"""
    return backend.eval_json(script)
