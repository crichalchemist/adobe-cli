"""Sequence list and inspection via CEP bridge."""
from __future__ import annotations
from cli_anything.premierepro.utils import cep_backend as cep


def list_sequences() -> list[dict]:
    """Return list of all sequences in the active project."""
    script = """
(function() {
    var seqs = [];
    for (var i = 0; i < app.project.sequences.numSequences; i++) {
        var s = app.project.sequences[i];
        seqs.push({
            name: s.name,
            id: s.sequenceID,
            duration: s.end,
            frame_rate: s.timebase,
            width: s.frameSizeHorizontal,
            height: s.frameSizeVertical,
            video_track_count: s.videoTracks.numTracks,
            audio_track_count: s.audioTracks.numTracks
        });
    }
    return JSON.stringify(seqs);
})()
"""
    return cep.eval_json(script)


def get_sequence_info(name: str) -> dict:
    """Return detailed info for the sequence matching name (case-sensitive)."""
    safe_name = cep.escape_estk(name)
    script = f"""
(function() {{
    for (var i = 0; i < app.project.sequences.numSequences; i++) {{
        var s = app.project.sequences[i];
        if (s.name === "{safe_name}") {{
            return JSON.stringify({{
                name: s.name,
                id: s.sequenceID,
                duration: s.end,
                frame_rate: s.timebase,
                width: s.frameSizeHorizontal,
                height: s.frameSizeVertical,
                video_track_count: s.videoTracks.numTracks,
                audio_track_count: s.audioTracks.numTracks
            }});
        }}
    }}
    return JSON.stringify({{error: "Sequence not found: {safe_name}"}});
}})()
"""
    return cep.eval_json(script)


def set_active_sequence(name: str) -> bool:
    """Set the active sequence by name. Returns True on success."""
    safe_name = cep.escape_estk(name)
    script = f"""
(function() {{
    for (var i = 0; i < app.project.sequences.numSequences; i++) {{
        var s = app.project.sequences[i];
        if (s.name === "{safe_name}") {{
            app.project.activeSequence = s;
            return "true";
        }}
    }}
    return "false";
}})()
"""
    return cep.eval_script(script) == "true"
