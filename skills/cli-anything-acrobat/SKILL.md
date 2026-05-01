---
name: cli-anything-acrobat
description: >-
  Use when performing PDF operations from scripts or agents — format conversion
  (PDF→DOCX/XLSX/PPTX/PNG), page manipulation (delete/extract/rotate/reorder),
  merge, split, metadata read/write, or text extraction. Requires Adobe Acrobat DC
  installed. Format conversion requires an active Pro subscription; merge/split/info
  run headless without Acrobat open.
agent_guidance: >-
  Always use --json for parseable output. Use absolute paths. Check exit codes.
  Format conversion (export to) requires an active Adobe Acrobat Pro subscription.
  All other operations (merge, split, rotate, info, metadata reads) work without a subscription.
---

# cli-anything-acrobat

Adobe Acrobat DC command-line interface. Invokes the real Acrobat engine for format
conversion; uses pypdf/PyMuPDF for headless operations (merge, split, rotate, info).

## Installation

```bash
pip install cli-anything-acrobat
# or
pipx install cli-anything-acrobat
```

**Requirements:**
- Python 3.10+
- Adobe Acrobat DC installed at `/Applications/Adobe Acrobat DC/`
- Active Adobe Acrobat Pro subscription (for format conversion only)

## Quick Start

```bash
# PDF info
cli-anything-acrobat info document.pdf

# JSON output for agents
cli-anything-acrobat --json info document.pdf

# Start REPL
cli-anything-acrobat
```

## Commands

### `info` — PDF metadata and page count

```bash
cli-anything-acrobat info <pdf>
cli-anything-acrobat --json info <pdf>
```

Returns: `page_count`, `title`, `author`, `subject`, `file_size`, `encrypted`, paths.

### `export to` — Convert PDF to another format (requires Acrobat Pro)

```bash
cli-anything-acrobat export to <pdf> <output>
cli-anything-acrobat export to report.pdf report.docx
cli-anything-acrobat export to report.pdf report.png   # first page as PNG
cli-anything-acrobat export to report.pdf --format xlsx report.xlsx
```

Format is inferred from output extension. Supported: `docx`, `doc`, `xlsx`, `pptx`,
`png`, `jpeg`, `tiff`, `html`, `rtf`, `txt`, `eps`, `ps`, `xml`.

```bash
# List all supported formats
cli-anything-acrobat export formats
cli-anything-acrobat --json export formats
```

### `pages` — Page manipulation

```bash
# Page info
cli-anything-acrobat pages info <pdf>

# Delete pages (1-indexed, supports ranges and "last")
cli-anything-acrobat pages delete <pdf> 1,3-5 -o output.pdf
cli-anything-acrobat pages delete <pdf> last -o output.pdf

# Extract pages to new PDF
cli-anything-acrobat pages extract <pdf> 2-4 -o chapter.pdf

# Rotate pages
cli-anything-acrobat pages rotate <pdf> 90 -o rotated.pdf
cli-anything-acrobat pages rotate <pdf> 90 --pages 1,3,5 -o rotated.pdf

# Reorder pages (1-indexed list of new order)
cli-anything-acrobat pages reorder <pdf> 3 1 2 -o reordered.pdf
```

Page specs: `"3"` (single), `"1,3,5"` (list), `"2-5"` (range), `"1,3-5,7"` (mixed),
`"all"`, `"last"`.

### `merge` — Combine PDFs

```bash
cli-anything-acrobat merge a.pdf b.pdf c.pdf -o combined.pdf
cli-anything-acrobat --json merge a.pdf b.pdf -o out.pdf
```

Returns: `total_pages`, `merged_files`, `output`, `file_size`.

### `split` — Split PDF into chunks

```bash
# Split into 5-page chunks
cli-anything-acrobat split report.pdf --pages-per-chunk 5 -d chunks/

# Split at explicit page boundaries (0-indexed ranges)
cli-anything-acrobat split report.pdf --ranges "0-4,5-9" -d parts/
```

### `metadata` — PDF metadata

```bash
# Read metadata
cli-anything-acrobat metadata get <pdf>
cli-anything-acrobat --json metadata get <pdf>

# Set metadata (writes to output PDF via Acrobat)
cli-anything-acrobat metadata set <pdf> --title "My Doc" --author "Alice" -o out.pdf
```

### `text` — Text extraction (pypdf/PyMuPDF, no Acrobat required)

```bash
cli-anything-acrobat text <pdf>
cli-anything-acrobat text <pdf> --pages 1-3
```

### `project` — Session management

```bash
# Create a session (tracks operations, enables undo)
cli-anything-acrobat project new source.pdf -o project.json
cli-anything-acrobat project info -p project.json
```

## REPL Mode

Run without subcommand for an interactive session with tab-completion:

```bash
cli-anything-acrobat
# acrobat> info document.pdf
# acrobat> pages delete document.pdf 1 -o out.pdf
# acrobat> exit
```

## Output Format

All commands support `--json` for machine-readable output:

```bash
cli-anything-acrobat --json info doc.pdf
# {"page_count": 12, "title": "Annual Report", "author": "Finance", "file_size": 245000, ...}

cli-anything-acrobat --json merge a.pdf b.pdf -o out.pdf
# {"output": "/abs/path/out.pdf", "total_pages": 15, "merged_files": 2, "file_size": 312400}
```

Exit codes: `0` = success, `1` = error (message on stderr).

## Architecture Notes

- **Format conversion** (`export to`): Uses Acrobat JS `doc.saveAs({cConvID: ...})` via
  `osascript do script`. Requires active Pro subscription. Stages output through `/tmp/`
  (macOS sandbox workaround).
- **Headless operations** (`merge`, `split`, `rotate`, `info`, `text`): Use `pypdf` /
  `PyMuPDF`. No Acrobat running required.
- **Page delete/extract**: Uses pypdf by default; falls back to Acrobat for contiguous
  ranges where fidelity matters (annotations, layers).

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| `export to` fails with subscription error | Requires active Adobe Acrobat Pro subscription |
| Relative path silently operates on wrong file | Always use absolute paths |
| No parseable output | Add `--json` before the subcommand |
| `pages delete` removes wrong pages | Pages are **1-indexed**, not 0-indexed |
| `split --ranges` skips pages | Ranges are **0-indexed** (opposite of `delete`) |
| Acrobat not installed but `export to` called | Headless ops (`merge`, `split`, `text`) work; `export to` needs Acrobat at `/Applications/Adobe Acrobat DC/` |

## Version

1.0.0
