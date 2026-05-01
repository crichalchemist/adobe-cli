"""Timeline clip and track inspection via CEP bridge."""
from __future__ import annotations
from cli_anything.premierepro.utils import cep_backend as cep


def get_timeline_clips(sequence_name: str | None = None) -> list[dict]:
    """Return all clips on video/audio tracks of the active (or named) sequence."""
    if sequence_name:
        safe = cep.escape_estk(sequence_name)
        seq_resolve = f"""
var _seq = null;
for (var _i = 0; _i < app.project.sequences.numSequences; _i++) {{
    if (app.project.sequences[_i].name === "{safe}") {{
        _seq = app.project.sequences[_i]; break;
    }}
}}
if (!_seq) return JSON.stringify([]);
"""
    else:
        seq_resolve = "var _seq = app.project.activeSequence; if (!_seq) return JSON.stringify([]);"

    script = f"""
(function() {{
    {seq_resolve}
    var clips = [];
    function collectTracks(tracks, trackType) {{
        for (var t = 0; t < tracks.numTracks; t++) {{
            var track = tracks[t];
            for (var c = 0; c < track.clips.numItems; c++) {{
                var clip = track.clips[c];
                clips.push({{
                    name: clip.name,
                    track: trackType + (t + 1),
                    start: clip.start.seconds,
                    end: clip.end.seconds,
                    duration: clip.duration.seconds,
                    media_path: clip.projectItem ? clip.projectItem.getMediaPath() : null
                }});
            }}
        }}
    }}
    collectTracks(_seq.videoTracks, "V");
    collectTracks(_seq.audioTracks, "A");
    return JSON.stringify(clips);
}})()
"""
    return cep.eval_json(script)
