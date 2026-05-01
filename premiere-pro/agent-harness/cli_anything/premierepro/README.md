# cli-anything-premierepro

Drive Adobe Premiere Pro 2025 from the command line. AI agents and shell scripts can open projects, inspect sequences, manage markers, scrub the timeline, and trigger AME exports — all via a local HTTP bridge.

---

## Requirements

- macOS (tested on Ventura / Sonoma)
- Adobe Premiere Pro 2025 (version 25.x)
- Python 3.10+
- `opencv-python-headless` (installed automatically via `pip install -e .`)

---

## Installation

### Step 1 — Enable CEP debug mode

Allows unsigned extensions to load:

```bash
defaults write com.adobe.CSXS.11 PlayerDebugMode 1
defaults write com.adobe.CSXS.12 PlayerDebugMode 1
```

### Step 2 — Install the CEP extension

```bash
ln -s /Volumes/Containers/adobe-cli/premiere-pro/agent-harness/cli_anything/premierepro/cep \
  ~/Library/Application\ Support/Adobe/CEP/extensions/com.cli-anything.premierepro
```

### Step 3 — Install the Python package

```bash
cd /Volumes/Containers/adobe-cli/premiere-pro/agent-harness
pip install -e .
```

### Step 4 — Launch Premiere Pro

Quit and relaunch Premiere Pro. The CEP bridge starts automatically — no manual panel opening needed after the first launch.

### Step 5 — Verify

```bash
curl http://localhost:7788/ping
# → {"ok":true,"version":"1.0.0","app":"premierepro"}
```

Or via the CLI:

```bash
cli-anything-premierepro ping
```

---

## CLI Usage

```bash
cli-anything-premierepro --help
```

### Health check

```bash
cli-anything-premierepro ping
```

### Project commands

```bash
cli-anything-premierepro project info
cli-anything-premierepro project open /path/to/project.prproj
cli-anything-premierepro project items
```

### Sequence commands

```bash
cli-anything-premierepro sequence list
cli-anything-premierepro sequence info "My Sequence"
cli-anything-premierepro sequence activate "My Sequence"
```

### Timeline

```bash
cli-anything-premierepro timeline clips
```

### Markers

```bash
cli-anything-premierepro markers list
cli-anything-premierepro markers add 30.5 --name "Chapter 2"
```

### Scrub (bridge only)

Move the playhead via the HTTP bridge directly — there is no CLI subcommand:

```bash
curl -s -X POST http://localhost:7788/scrub -d '{"seconds":30.5}'
```

### Export

```bash
cli-anything-premierepro export render output.mp4 --preset h264-1080p
cli-anything-premierepro export presets
cli-anything-premierepro export status
```

Requires Adobe Media Encoder to be installed.

### Media info (no Premiere required)

```bash
cli-anything-premierepro media /path/to/clip.mp4
```

---

## JSON Output (for agents)

Any command accepts `--json` for machine-readable output:

```bash
cli-anything-premierepro --json sequence list
cli-anything-premierepro --json markers list
cli-anything-premierepro --json project info
```

---

## REPL Mode

Running without a subcommand drops into an interactive REPL with tab completion:

```bash
cli-anything-premierepro
```

All CLI commands are available inside the REPL. Type `help` to list them, `exit` or `quit` to leave.

---

## Offline Commands (no Premiere required)

These work without Premiere Pro running:

```bash
# Parse a .prproj file and list sequences/media
cli-anything-premierepro project parse /path/to/project.prproj

# Inspect a media file (duration, codec, resolution, etc.)
cli-anything-premierepro media /path/to/clip.mp4
```

`.prproj` files are gzip-compressed XML. The parser extracts sequences and project items without opening Premiere Pro.

---

## Troubleshooting

**Bridge not running** (`Connection refused` on port 7788):
- Confirm PPro is open and the CEP extension loaded (check `/tmp/cep-alive.txt` exists).
- If `/tmp/cep-alive.txt` is missing after relaunch, the JS panel never ran — review the CEP setup in `PREMIEREPRO.md`.

**Extensions menu greyed out**:
- The manifest CSXS version must be `12.0` for PPro 25.x. See `PREMIEREPRO.md`.

**`activeSequence` errors**:
- Call `sequence activate "<name>"` before commands that require an active sequence.

For full architecture and hard-won CEP setup details, see [`PREMIEREPRO.md`](../../PREMIEREPRO.md) at the repo root.
