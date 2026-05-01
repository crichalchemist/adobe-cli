"""Export sequences via Adobe Media Encoder through Premiere Pro's CEP bridge."""
from __future__ import annotations
import os
from cli_anything.premierepro.utils import cep_backend as cep

PRESETS: dict[str, str] = {
    "h264-1080p": "H.264",
    "prores-422": "Apple ProRes 422",
    "prores-4444": "Apple ProRes 4444",
    "dnxhd": "DNxHD",
    "mp3": "MP3",
    "wav": "Waveform Audio",
}


def list_presets() -> list[str]:
    """Return names of built-in export presets."""
    return list(PRESETS.keys())


def export_sequence(
    output_path: str,
    sequence_name: str | None = None,
    preset_name: str = "h264-1080p",
    remove_on_completion: bool = True,
) -> dict:
    """Queue a sequence for export via AME. Returns job info dict."""
    abs_output = os.path.abspath(output_path)
    safe_output = cep.escape_estk(abs_output)
    if preset_name not in PRESETS:
        raise ValueError(f"Unknown preset {preset_name!r}. Valid: {list(PRESETS)}")
    safe_preset = cep.escape_estk(PRESETS[preset_name])
    remove_flag = "true" if remove_on_completion else "false"

    if sequence_name:
        safe_seq = cep.escape_estk(sequence_name)
        resolve = f"""
var _seq = null;
for (var _i = 0; _i < app.project.sequences.numSequences; _i++) {{
    if (app.project.sequences[_i].name === "{safe_seq}") {{
        _seq = app.project.sequences[_i]; break;
    }}
}}
if (!_seq) return JSON.stringify({{error: "Sequence not found: {safe_seq}"}});
"""
    else:
        resolve = "var _seq = app.project.activeSequence; if (!_seq) return JSON.stringify({error: 'No active sequence'});"

    script = f"""
(function() {{
    {resolve}
    var jobID = app.encoder.encodeSequence(
        _seq, "{safe_output}", "{safe_preset}", app.encoder.ENCODE_IN_TO_OUT, {remove_flag}
    );
    app.encoder.startBatch();
    return JSON.stringify({{ok: true, job_id: jobID, output: "{safe_output}"}});
}})()
"""
    return cep.eval_json(script)


def get_encoder_status() -> dict:
    """Return current AME job queue status."""
    script = """
(function() {
    return JSON.stringify({
        is_running: app.encoder.running,
        job_count: app.encoder.getJobCount ? app.encoder.getJobCount() : null
    });
})()
"""
    return cep.eval_json(script)
