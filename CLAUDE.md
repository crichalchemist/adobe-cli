# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Layout

```
adobe-cli/
  acrobat/agent-harness/       # cli-anything-acrobat Python package
  premiere-pro/agent-harness/  # cli-anything-premierepro Python package
  skills/                      # Canonical SKILL.md files for all harnesses
    cli-anything-acrobat/SKILL.md
    cli-anything-premierepro/SKILL.md
```

Each `agent-harness/` is an independent installable Python package with its own `setup.py` and test suite, all living in one unified repository.

## Architecture

Every harness follows the same two-layer IPC pattern:

```
Python CLI (Click)
  → HTTP POST localhost:<port> (requests)
    → CEP panel (Chromium/Node.js via CEPHtmlEngine subprocess)
      → csInterface.evalScript()
        → Adobe app ExtendScript (ESTK / ES3)
```

- **CEP panel** is a hidden HTML panel that Adobe loads at startup. It runs a Node.js HTTP server inside `CEPHtmlEngine`.
- **ExtendScript** is ES3 — no native JSON, no `Array.forEach`, no `Object.keys`. The bridge prepends a JSON polyfill to every `evalScript` call. All scripts must be wrapped in IIFEs.
- **Results** always travel as strings. Structured data is `JSON.stringify`'d in ESTK and parsed by `cep_backend.eval_json()` in Python.
- **`cep_backend.py`** is the Python HTTP client. `eval_json(script)` → `eval_script(script)` → `POST /eval` → string result → `json.loads`.

## Premiere Pro Harness (`premiere-pro/agent-harness/`)

### Install

```bash
# One-time: enable unsigned CEP extensions
defaults write com.adobe.CSXS.11 PlayerDebugMode 1
defaults write com.adobe.CSXS.12 PlayerDebugMode 1

# One-time: symlink CEP extension
ln -s "$(pwd)/cli_anything/premierepro/cep" \
  ~/Library/Application\ Support/Adobe/CEP/extensions/com.cli-anything.premierepro

# Python package
pip install -e .
```

Restart Premiere Pro. The HTTP bridge starts automatically on port 7788.

### Tests

```bash
# Unit tests (no Premiere required)
PYTHONPATH=. pytest cli_anything/premierepro/tests/test_core.py -v

# Run a single test class
PYTHONPATH=. pytest cli_anything/premierepro/tests/test_core.py::TestMarkersCore -v

# E2E tests (Premiere Pro must be open with a project)
PYTHONPATH=. pytest cli_anything/premierepro/tests/test_full_e2e.py -v -s

# Verify bridge is reachable before running E2E
curl http://localhost:7788/ping
```

E2E tests auto-skip if the bridge is unreachable — no failures for offline runs.

### Module Map

```
cli_anything/premierepro/
  premierepro_cli.py      # Click CLI entry point; all command groups defined here
  core/
    project.py            # get_project_info, open_project, get_project_items
    sequence.py           # list_sequences, get_sequence_info, set_active_sequence
    timeline.py           # get_timeline_clips
    markers.py            # list_markers, add_marker
    export.py             # export_sequence, list_presets, get_encoder_status
    vision.py             # capture_window_screenshot, scrub_and_capture, burst_frames, compare_frames
  utils/
    cep_backend.py        # HTTP client: ping(), eval_script(), eval_json(), _session()
    prproj_parser.py      # Offline .prproj gzip-XML parser (no Premiere needed)
    media_backend.py      # OpenCV + mdls media metadata (no Premiere needed)
    repl_skin.py          # REPL presentation layer
  cep/
    CSXS/manifest.xml     # CEP panel manifest — CSXS 12, all 4 CEF flags required
    js/main.js            # Node.js HTTP server; prepends JSON polyfill to every evalScript
    js/CSInterface.js     # Adobe CEP bridge (must be explicitly loaded in index.html)
```

### Key Invariants

- **Active sequence**: `markers.list_markers()`, `timeline.get_timeline_clips()`, and `markers.add_marker()` operate on `app.project.activeSequence`. Call `sequence.set_active_sequence(name)` first, or pass `--sequence`.
- **`createMarker(seconds)`**: takes a plain float (seconds), not a `Time` object.
- **`setPlayerPosition(ticks)`**: takes ticks, not seconds. Construct `Time`, set `.seconds`, pass `.ticks`.
- **Scrub is bridge-only**: `POST /scrub {"seconds": N}` — there is no `cli-anything-premierepro scrub` subcommand.

### CEP Manifest — Non-Obvious Requirements

The manifest at `cep/CSXS/manifest.xml` requires all of the following or the extension silently fails to load:

1. `ExtensionManifest Version="8.0"` and `RequiredRuntime Name="CSXS" Version="12.0"` (PPro 2025)
2. All four CEF flags: `--allow-file-access`, `--allow-file-access-from-files`, `--enable-nodejs`, `--mixed-context`
3. `<AutoVisible>true</AutoVisible>` — otherwise JS never runs (panel never opens automatically)
4. Panel size at least 200×30 — Chromium defers zero-area frames
5. No `<ScriptPath>` element — that's for ESTK, not Node.js
6. `CSInterface.js` explicitly loaded in `index.html` before `main.js`

**Proof-of-life diagnostic**: if `/tmp/cep-alive.txt` doesn't appear after PPro restart, JS never ran → check items 1–7 in `PREMIEREPRO.md`.

## Skills

`skills/` holds the canonical SKILL.md for each harness. Each harness also carries a copy at `cli_anything/<app>/skills/SKILL.md` (packaged via `setup.py`). When updating a skill, update both locations and keep them in sync.

## Adding a New Harness

Follow the same namespace package pattern:
- Package name: `cli-anything-<app>`
- Namespace: `cli_anything.<app>.*`
- `cli_anything/` has **no `__init__.py`** (PEP 420 namespace package)
- `cli_anything/<app>/` has `__init__.py`
- Entry point: `cli-anything-<app>=cli_anything.<app>.<app>_cli:cli`
- `setup.py` uses `find_namespace_packages(include=["cli_anything.*"])`
