"""Sequence marker operations via CEP bridge."""
from __future__ import annotations
import math
from cli_anything.premierepro.utils import cep_backend as cep


def list_markers(sequence_name: str | None = None) -> list[dict]:
    """List all markers on the active or named sequence."""
    if sequence_name:
        safe = cep.escape_estk(sequence_name)
        resolve = (
            f'var _seq = null; for (var _i=0;_i<app.project.sequences.numSequences;_i++) '
            f'{{ if (app.project.sequences[_i].name==="{safe}") '
            f'{{ _seq=app.project.sequences[_i];break; }} }}'
        )
    else:
        resolve = "var _seq = app.project.activeSequence;"
    script = f"""
(function() {{
    {resolve}
    if (!_seq) return JSON.stringify([]);
    var markers = [];
    var m = _seq.markers;
    var marker = m.getFirstMarker();
    while (marker) {{
        markers.push({{
            name: marker.name, comment: marker.comments,
            time: marker.start.seconds, duration: marker.end.seconds - marker.start.seconds,
            type: marker.type
        }});
        marker = m.getNextMarker(marker);
    }}
    return JSON.stringify(markers);
}})()
"""
    return cep.eval_json(script)


def add_marker(time_seconds: float, name: str = "", comment: str = "") -> dict:
    """Add a marker at time_seconds on the active sequence."""
    if not isinstance(time_seconds, (int, float)):
        raise TypeError(f"time_seconds must be numeric, got {type(time_seconds)}")
    if not math.isfinite(time_seconds):
        raise ValueError(f"time_seconds must be finite, got {time_seconds}")
    safe_name = cep.escape_estk(name)
    safe_comment = cep.escape_estk(comment)
    script = f"""
(function() {{
    var seq = app.project.activeSequence;
    if (!seq) return JSON.stringify({{error: "No active sequence"}});
    var marker = seq.markers.createMarker({time_seconds});
    marker.name = "{safe_name}";
    marker.comments = "{safe_comment}";
    return JSON.stringify({{ok: true, time: {time_seconds}, name: "{safe_name}"}});
}})()
"""
    return cep.eval_json(script)
