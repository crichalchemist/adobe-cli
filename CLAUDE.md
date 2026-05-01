# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**This repository is a Claude Code plugin.** Plugin metadata lives in `.claude-plugin/plugin.json`. Skills are auto-discovered from `skills/`. The `SessionStart` hook injects context on startup.

## Plugin Structure

```
adobe-cli/
  .claude-plugin/
    plugin.json                     # Plugin metadata (name, description, version, author)
  hooks/
    hooks.json                      # Hook registrations (SessionStart)
    run-hook.cmd                    # Cross-platform dispatcher (Unix + Windows polyglot)
    session-start                   # Extensionless hook script — runs on startup
  skills/
    SKILL.md                        # Router skill — links to per-harness skills
  <app>/agent-harness/cli_anything/<app>/skills/SKILL.md  # Per-harness canonical skills
```

Skills for each harness live inside their package (`<app>/agent-harness/cli_anything/<app>/skills/SKILL.md`). `skills/SKILL.md` is the umbrella router that links to them.

## Repository Layout

```
adobe-cli/
  acrobat/agent-harness/       # cli-anything-acrobat Python package
  illustrator/agent-harness/   # cli-anything-illustrator Python package
  premiere-pro/agent-harness/  # cli-anything-premierepro Python package
  skills/SKILL.md              # Router skill — links to per-harness SKILL.md files
```

Each `agent-harness/` is an independent installable Python package with its own `setup.py` and test suite, all living in one unified repository.

## Architecture

Each harness uses the IPC strategy appropriate to its app:

**Premiere Pro** (CEP panel bridge):
```
Python CLI (Click)
  → HTTP POST localhost:7788 (requests)
    → CEP panel (Chromium/Node.js via CEPHtmlEngine subprocess)
      → csInterface.evalScript()
        → ExtendScript (ESTK / ES3)
```

**Illustrator** (`#include` temp file via osascript):
```
Python CLI (Click)
  → subprocess osascript -e 'tell application "Adobe Illustrator" to do javascript "#include \"/tmp/x.jsx\""'
    → Adobe Illustrator ExtendScript engine (native JSON in 2026)
```

**Acrobat** (osascript `do script`):
```
Python CLI (Click)
  → subprocess osascript -e 'tell application id "com.adobe.Acrobat.Pro" to do script "..."'
    → Acrobat JavaScript API
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

## Illustrator Harness (`illustrator/agent-harness/`)

### Install

```bash
pipx install -e .
```

No CEP setup. No extensions. Just Illustrator open.

### Tests

```bash
# Unit tests (no Illustrator required)
PYTHONPATH=. pytest cli_anything/illustrator/tests/test_core.py -v

# E2E tests (Illustrator must be open with a document)
PYTHONPATH=. pytest cli_anything/illustrator/tests/test_full_e2e.py -v -s
```

### Module Map

```
cli_anything/illustrator/
  illustrator_cli.py      # Click CLI entry point
  core/
    document.py           # get_document_info, list_documents, open_document, close_document, save_document
    layer.py              # list_layers, set_layer_visible, set_layer_locked
    artboard.py           # list_artboards, set_active_artboard
    object.py             # list_objects, get_selection
    text.py               # list_text_frames, set_text_content
    swatch.py             # list_swatches
    export.py             # export_png, export_jpeg, export_svg, export_pdf
  utils/
    ai_backend.py         # osascript transport: eval_jsx(), eval_json(), ping(), reachable()
    repl_skin.py          # REPL presentation layer
```

### Key Invariants

- **Transport**: Python writes JSX to `/tmp/cli_illustrator_XXXXXX.jsx`, Illustrator reads via `#include`. Only the path is embedded in the AppleScript string.
- **Native JSON**: Illustrator 2026 has native JSON — the polyfill guard `if (typeof JSON === "undefined")` is false. BUT native JSON serializes `undefined` as the text `"undefined"` (non-standard). Scripts must normalize all values to avoid `undefined` properties.
- **Export sandbox**: PNG/JPEG must be written to `Folder.temp` (= Python `tempfile.gettempdir()`), NOT `/tmp`. SVG/PDF via `saveAs` have no restriction.
- **`doc.modified`**: undefined in Illustrator ExtendScript — use `doc.saved === false` instead.
- **`doc.fullName`**: for unsaved documents, points to the Illustrator app directory. Gate on `doc.saved` before calling `.fsName`.

## Skills

`skills/SKILL.md` is a router that links to the per-harness skill files. Each harness is the canonical source at `<app>/agent-harness/cli_anything/<app>/skills/SKILL.md`, packaged via `setup.py`. Update skills in the harness directory only.

## Adding a New Harness

Follow the same namespace package pattern:
- Package name: `cli-anything-<app>`
- Namespace: `cli_anything.<app>.*`
- `cli_anything/` has **no `__init__.py`** (PEP 420 namespace package)
- `cli_anything/<app>/` has `__init__.py`
- Entry point: `cli-anything-<app>=cli_anything.<app>.<app>_cli:cli`
- `setup.py` uses `find_namespace_packages(include=["cli_anything.*"])`
