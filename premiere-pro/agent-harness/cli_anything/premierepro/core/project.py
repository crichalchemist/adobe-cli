"""Premiere Pro project operations via CEP bridge."""
from __future__ import annotations
from cli_anything.premierepro.utils import cep_backend as cep


_PROJECT_INFO_SCRIPT = """
(function() {
    var proj = app.project;
    if (!proj) return JSON.stringify({error: "No project open"});
    var seqs = [];
    for (var i = 0; i < proj.sequences.numSequences; i++) {
        var s = proj.sequences[i];
        seqs.push({name: s.name, id: s.sequenceID});
    }
    return JSON.stringify({
        name: proj.name,
        path: proj.path,
        sequence_count: proj.sequences.numSequences,
        sequences: seqs,
        dirty: proj.dirty
    });
})()
"""


def get_project_info() -> dict:
    """Return info about the currently open Premiere Pro project."""
    return cep.eval_json(_PROJECT_INFO_SCRIPT)


def open_project(path: str) -> bool:
    """Open a .prproj file in Premiere Pro. Returns True on success."""
    safe_path = path.replace("\\", "\\\\").replace('"', '\\"')
    script = f'app.openDocument("{safe_path}"); "true"'
    result = cep.eval_script(script)
    return result == "true"


def close_project(save: bool = False) -> bool:
    """Close the active project. save=True saves before closing."""
    flag = "1" if save else "0"
    script = f'app.project.closeDocument({flag}, false); "true"'
    result = cep.eval_script(script)
    return result == "true"


def get_project_items() -> list[dict]:
    """Return flat list of all items in the project bin."""
    script = """
(function() {
    function collectItems(item, out) {
        out.push({name: item.name, type: item.type,
                  path: item.getMediaPath ? item.getMediaPath() : null});
        if (item.children) {
            for (var i = 0; i < item.children.numItems; i++) {
                collectItems(item.children[i], out);
            }
        }
    }
    var items = [];
    collectItems(app.project.rootItem, items);
    return JSON.stringify(items);
})()
"""
    return cep.eval_json(script)
