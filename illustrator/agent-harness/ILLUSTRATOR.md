# ILLUSTRATOR.md — cli-anything-illustrator Developer SOP

## Architecture

```
Python CLI (Click)
  → subprocess.run(["osascript", "-e", 'tell application "Adobe Illustrator" to do javascript "#include \"/tmp/x.jsx\""'])
    → Adobe Illustrator 2026 ExtendScript engine
      → app.activeDocument, app.documents, etc.
```

No CEP panel. No HTTP server. No Node.js. Just AppleScript calling `do javascript` directly.

## IPC Transport: #include Temp File

**Why not embed the script in the AppleScript string?**
ExtendScript (which Illustrator executes via `do javascript`) can contain backslashes, quotes,
multi-line content, and regex patterns. Embedding all that in a double-quoted AppleScript
string requires complex, layered escaping that becomes unmaintainable.

**The `#include` solution:**
1. Python writes the full script to `/tmp/cli_illustrator_XXXXXXXX.jsx`
2. AppleScript executes: `do javascript "#include \"/tmp/cli_illustrator_XXXXXXXX.jsx\""`
3. Only the temp file PATH needs embedding in the AppleScript string — paths are never special

Code: `ai_backend._write_jsx(body)` → `ai_backend._run_jsx_file(path, timeout)` → cleanup.

## JSON Polyfill — Mostly a No-Op on Illustrator 2026

Premiere Pro uses ExtendScript ES3 (no native JSON). Illustrator 2026 has **native JSON**,
so `if (typeof JSON === "undefined")` evaluates to false and the polyfill is never installed.

**Gotcha — native JSON and `undefined`:**
Illustrator 2026's native `JSON.stringify(undefined)` returns the string `"undefined"` (not
`undefined` the JS value, and not `"null"`). Properties with `undefined` values appear as
`"key":"undefined"` in the JSON output, which breaks `json.loads()`.

**Fix:** Never include `undefined` values in result objects. Normalize:
- `doc.modified` is `undefined` in Illustrator → use `(doc.saved === false)`
- `doc.fullName` for unsaved docs points to the Illustrator app dir → gate on `doc.saved`
- Any optional property that might be `undefined` → conditional with a string/boolean default

## Export Sandbox Restriction

Illustrator (and most macOS app-store-distributed apps) runs in a sandbox that restricts
file writes. For raster export (`ExportType.PNG24`, `ExportType.JPEG`), Illustrator can only
write to the macOS per-user temp dir (`Folder.temp` in ExtendScript, `tempfile.gettempdir()`
in Python). Both resolve to `/var/folders/<hash>/T`.

**`/tmp` is NOT writable for raster output.** The JSX file (which Illustrator reads via
`#include`) is written there by Python and that works — Illustrator can READ from `/tmp`.

**Fix in `export.py`:** `_EXPORT_TMP_DIR = tempfile.gettempdir()` — use this, not `"/tmp"`.

Vector formats (`ExportType.SVG`, `doc.saveAs()` for PDF) do NOT have this restriction —
they use `saveAs` which Illustrator can direct anywhere.

## Proof-of-Life Diagnostic

```bash
# Test that osascript can reach Illustrator
osascript -e 'tell application "Adobe Illustrator" to return version'
# Expected: 30.3.0

# Test that #include transport works
echo 'var x = 1+1; String(x);' > /tmp/test.jsx
osascript -e 'tell application "Adobe Illustrator" to do javascript "#include \"/tmp/test.jsx\""'
# Expected: 2

# Test that JSON is available
cat > /tmp/test_json.jsx << 'EOF'
var result = {ok: true, version: app.version};
JSON.stringify(result);
EOF
osascript -e 'tell application "Adobe Illustrator" to do javascript "#include \"/tmp/test_json.jsx\""'
# Expected: {"ok":true,"version":"30.3.0"}

# Test the CLI
cli-anything-illustrator ping
cli-anything-illustrator --json document info
```

## API Quirks

### `doc.fullName` for unsaved documents
Returns a `File` object pointing to the Illustrator **application directory**, not the document.
Always gate on `doc.saved` before calling `doc.fullName.fsName`.

### `doc.modified` is `undefined`
This property doesn't exist in Illustrator's ExtendScript. Use `doc.saved` instead:
- `doc.saved === false` → document has unsaved changes or was never saved.

### `doc.rulerUnits.toString()` returns full enum name
`"RulerUnits.Points"` not `"Points"`. Strip the prefix: `.replace("RulerUnits.", "")`.

### Layer visibility toggle
`layer.visible = false` immediately hides the layer in Illustrator's UI. This is
not undoable via the scripting API — agents should restore original state after inspection.

### `exportFile` vs `saveAs` for PDF
- `exportFile(f, ExportType.PDF24, ...)` — doesn't work reliably
- `saveAs(f, new PDFSaveOptions())` — correct way to save as PDF

### Artboard index
`doc.artboards.setActiveArtboardIndex(n)` — zero-based. The active artboard determines
which artboard is used when `artBoardClipping = true` in PNG/JPEG export options.

### Timing: `do javascript` is synchronous
Unlike CEP's `evalScript` (which is async), AppleScript's `do javascript` blocks until
the script completes. No polling needed, but long exports (complex PDFs) may hit the
`timeout` parameter of `subprocess.run`.

## Setup

No extension to install. Just:
1. Ensure Adobe Illustrator 2026 is open
2. `pip install -e .` (or `pipx install -e .`)
3. `cli-anything-illustrator ping`

## Running Tests

```bash
# Unit tests (no Illustrator required)
PYTHONPATH=. pytest cli_anything/illustrator/tests/test_core.py -v

# E2E tests (Illustrator must be open with a document)
PYTHONPATH=. pytest cli_anything/illustrator/tests/test_full_e2e.py -v -s

# Full suite
PYTHONPATH=. pytest cli_anything/illustrator/tests/ -v
```
