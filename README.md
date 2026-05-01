# adobe-cli

Command-line harnesses for Adobe desktop applications. AI agents and shell scripts can open projects, inspect timelines, manipulate documents, and trigger exports — without touching a mouse.

Built on the **[CLI-Anything](https://github.com/HKUDS/CLI-Anything)** methodology by [HKUDS](https://github.com/HKUDS): a pattern for wrapping stateful GUI applications behind a local HTTP or IPC bridge so scripts and AI agents can drive them programmatically.

> **Not affiliated with Adobe Inc.** This project is an independent, community-built tool. Adobe, Acrobat, and Premiere Pro are trademarks of Adobe Inc. Use of those names here is purely descriptive.

---

## Harnesses

| Package | Application | Bridge |
|---------|-------------|--------|
| [`cli-anything-premierepro`](premiere-pro/agent-harness/) | Adobe Premiere Pro 2025 | CEP panel → ExtendScript |
| [`cli-anything-acrobat`](acrobat/agent-harness/) | Adobe Acrobat DC | Acrobat JS via `osascript` |
| [`cli-anything-illustrator`](illustrator/agent-harness/) | Adobe Illustrator 2026 | `osascript do javascript` + `#include` |

---

## cli-anything-premierepro

Drive Premiere Pro from scripts or agents: open projects, inspect sequences and timelines, manage markers, queue AME exports, and capture timeline frames for visual verification.

### Requirements

- macOS (Ventura / Sonoma)
- Adobe Premiere Pro 2025 (version 25.x)
- Python 3.10+

### Install

```bash
# 1. Enable unsigned CEP extensions (one-time)
defaults write com.adobe.CSXS.11 PlayerDebugMode 1
defaults write com.adobe.CSXS.12 PlayerDebugMode 1

# 2. Symlink the CEP extension (one-time)
ln -s "$(pwd)/premiere-pro/agent-harness/cli_anything/premierepro/cep" \
  ~/Library/Application\ Support/Adobe/CEP/extensions/com.cli-anything.premierepro

# 3. Install the Python package
pip install -e premiere-pro/agent-harness/

# 4. Relaunch Premiere Pro — the HTTP bridge starts automatically on port 7788

# 5. Verify
cli-anything-premierepro ping
```

### Usage

```bash
# Project
cli-anything-premierepro project info
cli-anything-premierepro project open /path/to/cut.prproj

# Sequences
cli-anything-premierepro sequence list
cli-anything-premierepro sequence activate "Main Cut"

# Timeline
cli-anything-premierepro timeline clips
cli-anything-premierepro timeline clips --sequence "B-Roll"

# Markers
cli-anything-premierepro markers list
cli-anything-premierepro markers add 30.5 --name "Chapter 2"

# Export (requires Adobe Media Encoder)
cli-anything-premierepro export render output.mp4 --preset h264-1080p
cli-anything-premierepro export presets

# Agent vision — capture what Premiere is showing
cli-anything-premierepro vision screenshot -o /tmp/frame.png
cli-anything-premierepro vision frame 30.5          # scrub + capture
cli-anything-premierepro vision burst 0 60 5 -d /tmp/frames/
cli-anything-premierepro vision compare /tmp/a.png /tmp/b.png

# Offline (no Premiere required)
cli-anything-premierepro project parse /path/to/cut.prproj
cli-anything-premierepro media /path/to/clip.mp4
```

Use `--json` anywhere for machine-readable output:

```bash
cli-anything-premierepro --json sequence list
# [{"name": "Main Cut", "width": 1920, "height": 1080, "fps": 23.976, ...}]
```

Run `cli-anything-premierepro` with no arguments to enter the interactive REPL.

---

## cli-anything-illustrator

Drive Illustrator 2026 from scripts or agents: inspect documents, enumerate layers and artboards, list page items and text frames, query swatches, and export artwork as PNG, JPEG, SVG, or PDF — no CEP extension required.

### Requirements

- macOS (Ventura / Sonoma)
- Adobe Illustrator 2026 (version 30.x)
- Python 3.10+

### Install

```bash
pipx install -e illustrator/agent-harness/
```

### Usage

```bash
# Health check
cli-anything-illustrator ping

# Document
cli-anything-illustrator document info
cli-anything-illustrator document open /path/to/file.ai

# Layers
cli-anything-illustrator layer list
cli-anything-illustrator layer visible "Artwork" off

# Artboards
cli-anything-illustrator artboard list
cli-anything-illustrator artboard set-active 1

# Objects & selection
cli-anything-illustrator object list --layer "Artwork"
cli-anything-illustrator object selection

# Text frames
cli-anything-illustrator text list
cli-anything-illustrator text set 0 "New headline"

# Swatches
cli-anything-illustrator swatch list

# Export
cli-anything-illustrator export png /tmp/out.png --resolution 300
cli-anything-illustrator export jpeg /tmp/out.jpg --artboard 0 --quality 9
cli-anything-illustrator export svg /tmp/out.svg
cli-anything-illustrator export pdf /tmp/out.pdf
```

Use `--json` anywhere for machine-readable output. Run `cli-anything-illustrator` with no arguments for the REPL.

---

## cli-anything-acrobat

Perform PDF operations from scripts or agents: format conversion, page manipulation, merge, split, and metadata — using Acrobat's native engine.

### Requirements

- macOS
- Adobe Acrobat DC
- Python 3.10+
- Active Acrobat Pro subscription (format conversion only; all other ops work without one)

### Install

```bash
pip install -e acrobat/agent-harness/
```

### Usage

```bash
# PDF info
cli-anything-acrobat info document.pdf

# Format conversion (requires Acrobat Pro)
cli-anything-acrobat export to report.pdf report.docx
cli-anything-acrobat export to report.pdf report.png

# Page manipulation
cli-anything-acrobat pages delete document.pdf 1,3-5 -o out.pdf
cli-anything-acrobat pages extract document.pdf 2-4 -o chapter.pdf
cli-anything-acrobat pages rotate document.pdf 90 -o rotated.pdf

# Merge / split
cli-anything-acrobat merge a.pdf b.pdf c.pdf -o combined.pdf
cli-anything-acrobat split report.pdf --pages-per-chunk 5 -d chunks/

# Text extraction (no Acrobat required)
cli-anything-acrobat text document.pdf

# Metadata
cli-anything-acrobat metadata get document.pdf
cli-anything-acrobat metadata set document.pdf --title "Annual Report" -o out.pdf
```

Use `--json` for machine-readable output. Run `cli-anything-acrobat` with no arguments for the REPL.

---

## The cli-anything Pattern

> **Attribution:** The cli-anything pattern was created by [HKUDS](https://github.com/HKUDS) — see [CLI-Anything: Making ALL Software Agent-Native](https://github.com/HKUDS/CLI-Anything). Browse and install community CLIs via the [CLI Hub](https://hkuds.github.io/CLI-Anything/) (`pip install cli-anything-hub`).

Each harness follows the same structure:

```
<app>/agent-harness/
  setup.py                          # pip-installable; namespace: cli_anything.<app>
  <APP>.md                          # Developer SOP — architecture, gotchas, API quirks
  cli_anything/<app>/
    <app>_cli.py                    # Click CLI entry point
    core/                           # Business logic (pure functions, testable without running the app)
    utils/
      cep_backend.py OR backend.py  # App-facing transport layer
    tests/
      test_core.py                  # Unit tests (no app required)
      test_full_e2e.py              # E2E tests (app must be running)
    skills/SKILL.md                 # Agent skill descriptor (packaged copy)
skills/
  cli-anything-<app>/SKILL.md       # Canonical skill descriptor
```

The IPC strategy differs per app:
- **Premiere Pro**: CEP panel running Node.js HTTP server → `csInterface.evalScript()` → ExtendScript
- **Acrobat**: Python → `osascript` → AppleScript `do script` → Acrobat JavaScript API

Core modules are always pure Python and testable without the application running. The transport layer is the only component that requires the host app.

---

## License

[Elastic License 2.0](LICENSE) — free to use and modify; may not be offered as a hosted/managed service.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
