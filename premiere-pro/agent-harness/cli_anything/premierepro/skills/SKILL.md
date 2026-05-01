---
name: cli-anything-premierepro
description: >-
  Use when driving Adobe Premiere Pro 2025 from scripts or agents — opening
  projects, inspecting sequences and timelines, managing markers, queuing AME
  exports, capturing timeline frames, or reading media metadata. Most commands
  require Premiere Pro running with the cli-anything CEP bridge. Use `project
  parse` or `media` for offline operations without Premiere open.
agent_guidance: >-
  Most commands require Premiere Pro 2025 running with the cli-anything CEP
  extension loaded (bridge on localhost:7788). Always use --json for parseable
  output. Use absolute file paths. Call `ping` first to verify the bridge is
  up. Set an active sequence with `sequence activate` before marker or timeline
  commands that don't accept --sequence. Only `project parse` and `media` work
  without Premiere running.
---

# cli-anything-premierepro

Adobe Premiere Pro 2025 CLI. Drives Premiere via a CEP extension HTTP bridge;
`project parse` and `media` run headless.

## Installation

```bash
pip install -e /path/to/premiere-pro/agent-harness
```

**Requirements:**
- macOS (Ventura / Sonoma tested)
- Adobe Premiere Pro 2025 (version 25.x)
- Python 3.10+
- CEP debug mode enabled, extension symlinked (see README.md)

## Quick Start

```bash
# Verify bridge is up
cli-anything-premierepro ping

# JSON output for agents
cli-anything-premierepro --json ping

# Start REPL
cli-anything-premierepro
```

## Commands

### `ping` — Health check

```bash
cli-anything-premierepro ping
cli-anything-premierepro --json ping
```

Returns: `{"ok": true, "version": "1.0.0", "app": "premierepro"}`. Fails with exit 1 if bridge is not running.

---

### `project` — Project commands

```bash
# Active project info (name, path, sequence count)
cli-anything-premierepro project info
cli-anything-premierepro --json project info

# Open a .prproj file
cli-anything-premierepro project open /path/to/cut.prproj

# List all items in project bin
cli-anything-premierepro project items
cli-anything-premierepro --json project items

# Parse a .prproj offline (no Premiere required — reads gzip XML)
cli-anything-premierepro project parse /path/to/cut.prproj
cli-anything-premierepro --json project parse /path/to/cut.prproj
```

---

### `sequence` — Sequence commands

```bash
# List all sequences
cli-anything-premierepro sequence list
cli-anything-premierepro --json sequence list

# Detailed info for a named sequence
cli-anything-premierepro sequence info "Main Cut"
cli-anything-premierepro --json sequence info "Main Cut"

# Set active sequence (required before marker/timeline commands that omit --sequence)
cli-anything-premierepro sequence activate "Main Cut"
```

`sequence info` returns: `name`, `width`, `height`, `fps`, `duration`, `track_count`.

---

### `timeline` — Timeline inspection

```bash
# List clips in the active sequence
cli-anything-premierepro timeline clips
cli-anything-premierepro --json timeline clips

# List clips in a named sequence
cli-anything-premierepro timeline clips --sequence "B-Roll"
cli-anything-premierepro --json timeline clips --sequence "B-Roll"
```

Each clip: `name`, `track`, `start` (seconds), `end` (seconds), `duration` (seconds).

---

### `markers` — Sequence markers

```bash
# List markers on active sequence
cli-anything-premierepro markers list
cli-anything-premierepro --json markers list

# List markers on a named sequence
cli-anything-premierepro markers list --sequence "Main Cut"

# Add a marker at 30.5 seconds on the active sequence
cli-anything-premierepro markers add 30.5
cli-anything-premierepro markers add 30.5 --name "Chapter 2" --comment "scene change"
cli-anything-premierepro --json markers add 30.5 --name "Chapter 2"
```

Each marker: `name`, `comment`, `time` (seconds), `duration` (seconds), `type`.

---

### `export` — Export via Adobe Media Encoder

```bash
# Queue active sequence for export
cli-anything-premierepro export render /tmp/output.mp4
cli-anything-premierepro export render /tmp/output.mp4 --sequence "Main Cut"
cli-anything-premierepro export render /tmp/output.mp4 --preset h264-720p
cli-anything-premierepro --json export render /tmp/output.mp4 --preset h264-1080p

# List available export presets
cli-anything-premierepro export presets
cli-anything-premierepro --json export presets

# Check AME queue status
cli-anything-premierepro export status
cli-anything-premierepro --json export status
```

Built-in presets: `h264-1080p` (default), `h264-720p`, `h264-4k`, `prores-422`, `hevc-1080p`.
Requires Adobe Media Encoder installed.

---

### `media` — Media file metadata (no Premiere required)

```bash
cli-anything-premierepro media /path/to/clip.mp4
cli-anything-premierepro --json media /path/to/clip.mp4
```

Returns: `name`, `path`, `width`, `height`, `fps`, `frame_count`, `duration` (seconds),
`codec`, `file_size`.

---

### Scrub (bridge only — no CLI command)

Move the active sequence playhead. Use the HTTP bridge directly:

```bash
curl -s -X POST http://localhost:7788/scrub -d '{"seconds": 30.5}'
```

---

## REPL Mode

Run without a subcommand for an interactive session with tab-completion:

```bash
cli-anything-premierepro
# premierepro> ping
# premierepro> --json sequence list
# premierepro> markers add 30.5 --name "Chapter 2"
# premierepro> exit
```

REPL accepts the same flags and arguments as the CLI. Use `help` for command list.

---

## Output Format

All commands support `--json` for machine-readable output:

```bash
cli-anything-premierepro --json ping
# {"ok": true, "version": "1.0.0", "app": "premierepro"}

cli-anything-premierepro --json sequence list
# [{"name": "Main Cut", "width": 1920, "height": 1080, "fps": 23.976, "duration": 245.3}]

cli-anything-premierepro --json markers add 30.5 --name "Act 2"
# {"ok": true, "time": 30.5, "name": "Act 2"}
```

Exit codes: `0` = success, `1` = error (message on stderr).

---

## Architecture Notes

- **Bridge**: A CEP panel (`CEPHtmlEngine`) runs a Node.js HTTP server on `localhost:7788`.
  All Premiere-aware commands route through `POST /eval` → `csInterface.evalScript()` → ExtendScript (ES3).
- **Headless commands**: `project parse` (reads gzip-XML .prproj) and `media` (OpenCV + `mdls`) run without Premiere.
- **ExtendScript**: Runs ES3 in PPro's UI thread. The bridge prepends a JSON polyfill to every script. All scripts are wrapped in IIFEs. Results are always strings.
- **Active sequence**: Many operations act on `app.project.activeSequence`. Call `sequence activate` first, or pass `--sequence` where supported.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Commands fail with "Cannot reach bridge" | Premiere Pro must be open and the CEP extension loaded. Run `ping` to verify. |
| `markers list` / `timeline clips` returns empty | No active sequence. Call `sequence activate "<name>"` first, or pass `--sequence`. |
| `markers add` returns `{"error": "No active sequence"}` | Same — activate a sequence before adding markers. |
| `cli-anything-premierepro scrub 30.5` → "No such command" | `scrub` is bridge-only. Use `curl -X POST http://localhost:7788/scrub -d '{"seconds":30.5}'`. |
| No parseable output | Add `--json` before the subcommand: `cli-anything-premierepro --json sequence list`. |
| `project parse` fails | Ensure the `.prproj` file is readable; it is a gzip-compressed XML file. |
| `vision frame` captures wrong window | Premiere Pro must be visible (not minimized). The `screencapture` tool captures the frontmost matching window. |

## Version

1.0.0
