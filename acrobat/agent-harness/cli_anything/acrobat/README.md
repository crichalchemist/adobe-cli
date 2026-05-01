# cli-anything-acrobat

Adobe Acrobat DC command-line interface. Wraps Acrobat's native engine for format conversion
and uses pypdf/PyMuPDF for headless PDF operations.

## Requirements

- macOS (uses AppleScript + Acrobat JS via `osascript`)
- Adobe Acrobat DC installed at `/Applications/Adobe Acrobat DC/`
- Active Adobe Acrobat Pro subscription (for format conversion)
- Python 3.10+

## Installation

```bash
pip install -e .
# or
pipx install .
```

After installation, `cli-anything-acrobat` is available in PATH.

## Usage

```bash
# PDF info
cli-anything-acrobat info document.pdf
cli-anything-acrobat --json info document.pdf

# Format conversion (requires Acrobat Pro subscription)
cli-anything-acrobat export to report.pdf report.docx
cli-anything-acrobat export to slides.pdf slides.pptx
cli-anything-acrobat export to report.pdf page1.png   # first page as PNG

# List supported formats
cli-anything-acrobat export formats

# Page operations
cli-anything-acrobat pages delete doc.pdf 1,3-5 -o cleaned.pdf
cli-anything-acrobat pages extract doc.pdf 2-6 -o chapter2.pdf
cli-anything-acrobat pages rotate doc.pdf 90 -o rotated.pdf
cli-anything-acrobat pages reorder doc.pdf 3 1 2 -o reordered.pdf

# Merge / split
cli-anything-acrobat merge cover.pdf body.pdf appendix.pdf -o final.pdf
cli-anything-acrobat split report.pdf --pages-per-chunk 10 -d chapters/

# Metadata
cli-anything-acrobat metadata get doc.pdf
cli-anything-acrobat metadata set doc.pdf --title "My Doc" --author "Alice" -o out.pdf

# Text extraction (no Acrobat required)
cli-anything-acrobat text doc.pdf

# Interactive REPL
cli-anything-acrobat
```

## JSON Output Mode

All commands accept `--json` for machine-readable output:

```bash
cli-anything-acrobat --json info doc.pdf
# {"page_count": 12, "title": "Annual Report", ...}

cli-anything-acrobat --json merge a.pdf b.pdf -o out.pdf
# {"output": "/abs/path/out.pdf", "total_pages": 15, "file_size": 312400}
```

## Architecture

Two backends:

| Operation | Backend |
|-----------|---------|
| Format conversion (PDF→DOCX/XLSX/PNG/etc.) | Acrobat JS via `osascript do script` |
| Merge, split, rotate, info, text extraction | pypdf + PyMuPDF (headless, no Acrobat) |
| Page delete/extract | pypdf (Acrobat fallback for contiguous ranges) |

**macOS sandbox note**: Acrobat cannot write to `/private/var/folders/` (per-process temp dirs).
The backend automatically stages output through `/tmp/` and moves to the final destination.

## Page Spec Format

All page arguments use 1-indexed human-readable specs:

- `"3"` — single page
- `"1,3,5"` — comma-separated list
- `"2-5"` — inclusive range
- `"1,3-5,7"` — mixed
- `"all"` — all pages
- `"last"` — last page

## Testing

```bash
# Unit tests (no Acrobat required)
PYTHONPATH=/path/to/agent-harness pytest cli_anything/acrobat/tests/test_core.py -v

# E2E tests (requires Acrobat DC + Pro subscription)
PYTHONPATH=/path/to/agent-harness pytest cli_anything/acrobat/tests/test_full_e2e.py -v
```

See `tests/TEST.md` for full test plan and results.
