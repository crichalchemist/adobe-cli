---
name: cli-anything-illustrator
description: >-
  Use when driving Adobe Illustrator 2026 from scripts or agents — inspecting
  documents, layers, artboards, page items, text frames, and swatches, or
  exporting artwork as PNG, JPEG, SVG, or PDF. Requires Illustrator running
  with a document open; the bridge is `osascript do javascript` (no CEP panel
  needed). All commands require Illustrator to be running.
agent_guidance: >-
  Always use --json for parseable output. Use `ping` first to verify
  Illustrator is running. Paths must be absolute. Layer names are
  case-sensitive. Artboard indices are zero-based. Export formats PNG and JPEG
  write to the macOS per-user temp dir then move; SVG and PDF use saveAs.
  `document info` gives you layer_count and artboard_count before you call
  layer or artboard subcommands.
---

# cli-anything-illustrator

Adobe Illustrator 2026 CLI. Drives Illustrator via `osascript do javascript`
with a temp-file `#include` transport; no CEP extension required.

## Installation

```bash
pipx install -e /path/to/illustrator/agent-harness
```

**Requirements:**
- macOS (Ventura / Sonoma tested)
- Adobe Illustrator 2026 (version 30.x)
- Python 3.10+

## Quick Start

```bash
# Verify Illustrator is running
cli-anything-illustrator ping

# JSON output for agents
cli-anything-illustrator --json ping

# Start REPL
cli-anything-illustrator
```

## Commands

### `ping` — Health check

```bash
cli-anything-illustrator ping
cli-anything-illustrator --json ping
```

Returns: `{"ok": true, "version": "1.0.0", "app": "illustrator", "app_version": "30.3.0"}`. Exits 1 if Illustrator is not running.

---

### `document` — Document commands

```bash
# Active document metadata
cli-anything-illustrator document info
cli-anything-illustrator --json document info

# List all open documents
cli-anything-illustrator document list
cli-anything-illustrator --json document list

# Open a file
cli-anything-illustrator document open /path/to/file.ai

# Save the active document
cli-anything-illustrator document save

# Close (without saving)
cli-anything-illustrator document close

# Close and save
cli-anything-illustrator document close --save
```

`document info` returns: `name`, `path`, `width`, `height`, `color_space`, `ruler_units`,
`layer_count`, `artboard_count`, `path_item_count`, `text_frame_count`, `swatch_count`, `modified`.

Supported open formats: `.ai`, `.eps`, `.pdf`, `.svg`, `.fxg`.

---

### `layer` — Layer commands

```bash
# List all layers (including sublayers, with depth)
cli-anything-illustrator layer list
cli-anything-illustrator --json layer list

# Show / hide a layer
cli-anything-illustrator layer visible "Artwork" on
cli-anything-illustrator layer visible "Artwork" off

# Lock / unlock a layer
cli-anything-illustrator layer locked "Text" on
cli-anything-illustrator layer locked "Text" off
```

Each layer entry: `name`, `visible`, `locked`, `depth` (0 = top-level, 1 = sublayer).

---

### `artboard` — Artboard commands

```bash
# List all artboards
cli-anything-illustrator artboard list
cli-anything-illustrator --json artboard list

# Set active artboard (zero-based index)
cli-anything-illustrator artboard set-active 0
cli-anything-illustrator artboard set-active 2
```

Each artboard: `index`, `name`, `width`, `height`, `x`, `y`.

---

### `object` — Page item commands

```bash
# List all page items in active document
cli-anything-illustrator object list
cli-anything-illustrator --json object list

# Filter by layer
cli-anything-illustrator object list --layer "Artwork"

# Show currently selected items
cli-anything-illustrator object selection
cli-anything-illustrator --json object selection
```

Each item: `index`, `name`, `type`, `x`, `y`, `width`, `height`, `visible`, `locked`, `layer`.

---

### `text` — Text frame commands

```bash
# List all text frames
cli-anything-illustrator text list
cli-anything-illustrator --json text list

# Replace text frame contents (zero-based index)
cli-anything-illustrator text set 0 "New headline text"
```

Each text frame: `index`, `contents`, `x`, `y`, `width`, `height`, `layer`.

---

### `swatch` — Swatch commands

```bash
# List swatches (excludes [None] and [Registration] by default)
cli-anything-illustrator swatch list
cli-anything-illustrator --json swatch list

# Include system swatches
cli-anything-illustrator swatch list --all
```

Each swatch: `name`, `spot`, `color_type`. CMYK swatches also have `c`, `m`, `y`, `k`; RGB swatches have `r`, `g`, `b`.

---

### `export` — Export commands

```bash
# Export as PNG (72 DPI by default)
cli-anything-illustrator export png /tmp/out.png
cli-anything-illustrator export png /tmp/out.png --resolution 300
cli-anything-illustrator export png /tmp/out.png --artboard 0

# Export as JPEG
cli-anything-illustrator export jpeg /tmp/out.jpg --quality 8 --resolution 150

# Export as SVG
cli-anything-illustrator export svg /tmp/out.svg

# Save as PDF
cli-anything-illustrator export pdf /tmp/out.pdf
```

All export commands print `{"output": "/path/to/file", "file_size": N}`.
PNG and JPEG are written to the macOS per-user temp dir first (Illustrator sandbox
restriction), then moved to the requested path.

---

## REPL Mode

```bash
cli-anything-illustrator
# illustrator> ping
# illustrator> --json document info
# illustrator> layer list
# illustrator> export png /tmp/test.png
# illustrator> exit
```

---

## Output Format

All commands support `--json` for machine-readable output:

```bash
cli-anything-illustrator --json ping
# {"ok": true, "version": "1.0.0", "app": "illustrator", "app_version": "30.3.0"}

cli-anything-illustrator --json document info
# {"name": "logo.ai", "width": 800.0, "height": 600.0, "color_space": "CMYK", ...}

cli-anything-illustrator --json layer list
# [{"name": "Artwork", "visible": true, "locked": false, "depth": 0}, ...]
```

Exit codes: `0` = success, `1` = error (message on stderr or in `{"error": "..."}` JSON).

---

## Architecture Notes

- **Transport**: Python writes ExtendScript to a temp `.jsx` file in `/tmp`, then invokes
  `osascript -e 'tell application "Adobe Illustrator" to do javascript "#include \"/tmp/x.jsx\""'`.
  The `#include` approach avoids shell-escaping the script body entirely.
- **JSON**: Illustrator 2026 has native JSON. The polyfill guard (`if typeof JSON === "undefined"`)
  means the polyfill is a no-op on this version. Scripts avoid `undefined` values since
  the native engine serializes them as the text `"undefined"` (non-standard).
- **Export sandbox**: Illustrator can only write raster files (PNG, JPEG) to the macOS
  per-user temp dir (`Folder.temp` / Python `tempfile.gettempdir()`), not to `/tmp`.
  Vector/PDF exports via `saveAs` have no such restriction.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| `ping` fails | Illustrator must be open. Check Activity Monitor. |
| `layer visible "Artwork" on` fails | Layer name is case-sensitive; check `layer list` first. |
| `artboard set-active 5` → "out of range" | Check `artboard list` for valid indices. |
| `export png /tmp/out.png` → file missing | Use an absolute path outside `/tmp` (e.g. `~/Desktop/out.png`). `/tmp` is writable for `.jsx` scripts but not Illustrator raster output. |
| `object list` returns empty | No page items on visible layers, or document has no objects. |

## Version

1.0.0
