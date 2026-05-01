# Adobe Acrobat DC — CLI Harness SOP

## Software Overview

Adobe Acrobat DC is a proprietary PDF editor and converter available on macOS via
`/Applications/Adobe Acrobat DC/Adobe Acrobat.app`. It has no native CLI but exposes
two automation surfaces:

1. **AppleScript** (Acrobat.sdef) — open/close docs, page manipulation, bookmarks,
   annotations, find text, export via conversion objects.
2. **Acrobat JavaScript API** (via AppleScript `do script`) — full programmatic
   access including `app.openDoc`, `doc.saveAs`, `doc.deletePages`,
   `doc.extractPages`, `doc.insertPages`, and metadata access.

## Backend Strategy: Dual Backend

### Primary: Acrobat JavaScript via osascript

All Acrobat-specific operations use the Acrobat JS API invoked through
AppleScript `do script`. This approach avoids modal dialog blocking:

- `app.openDoc({cPath: ..., bHidden: true})` — opens invisibly, dialog-immune
- `doc.saveAs({cPath: ..., cConvID: ...})` — converts to 19 formats
- `doc.closeDoc(false)` — closes without saving
- `doc.deletePages({nStart: ..., nEnd: ...})`
- `doc.extractPages({nStart: ..., nEnd: ..., cPath: ...})`
- `doc.insertPages({nPage: ..., cPath: ..., nStart: ..., nEnd: ...})`

**Critical**: Always use `app.openDoc({bHidden: true})` never the AppleScript
`open ... with invisible` command — the latter blocks on payment/license dialogs.

### Secondary: pypdf (headless, no Acrobat required)

For merge, split, rotation, and fast metadata reads:
- `pypdf` 6.x — merge, split, rotate pages, encrypt/decrypt, metadata
- `PyMuPDF (fitz)` — text extraction, page rendering to images

### Acrobat as Required Dependency

Adobe Acrobat DC is a **required hard dependency** for format conversion (PDF→DOCX,
PDF→XLSX, PDF→PPTX, etc.) and advanced operations. Without a licensed Acrobat
installation, those commands fail with a clear error message.

## Export Format Conversion IDs

All IDs use the `doc.saveAs({cConvID: ...})` pattern:

| Format               | cConvID                        |
|----------------------|--------------------------------|
| Word Document (.docx)| com.adobe.acrobat.docx         |
| Word 97-2003 (.doc)  | com.adobe.acrobat.doc          |
| Excel (.xlsx)        | com.adobe.acrobat.xlsx         |
| XML Spreadsheet      | com.adobe.acrobat.spreadsheet  |
| PowerPoint (.pptx)   | com.adobe.acrobat.pptx         |
| JPEG                 | com.adobe.acrobat.jpeg         |
| JPEG 2000            | com.adobe.acrobat.jp2k         |
| TIFF                 | com.adobe.acrobat.tiff         |
| PNG                  | com.adobe.acrobat.png          |
| HTML                 | com.adobe.acrobat.html         |
| Rich Text Format     | com.adobe.acrobat.rtf          |
| Encapsulated PS      | com.adobe.acrobat.eps          |
| PostScript           | com.adobe.acrobat.ps           |
| Accessible Text      | com.adobe.acrobat.accesstext   |
| Plain Text           | com.adobe.acrobat.plain-text   |
| XML 1.0              | com.adobe.acrobat.xml-1-00     |

## Session Model

Unlike document-composition apps (LibreOffice, Blender), Acrobat's native format
IS the deliverable — PDFs are edited in place. The session tracks:

```json
{
  "source_pdf": "/abs/path/to/source.pdf",
  "output_pdf": "/abs/path/to/output.pdf",
  "dirty": false,
  "operations": [],
  "metadata_overrides": {}
}
```

- `source_pdf`: The PDF being worked on
- `output_pdf`: Where to write results (defaults to source_pdf)
- `dirty`: True when operations are queued but not applied
- `operations`: Log of applied operations for audit trail
- `metadata_overrides`: Pending metadata changes

## JavaScript Execution Pattern

All backend calls follow this pattern:

```python
import subprocess, json

def _run_js(js_code: str, timeout: int = 30) -> str:
    js_single = js_code.replace("\n", " ").replace('"', '\\"')
    result = subprocess.run(
        ["osascript", "-e",
         f'tell application id "com.adobe.Acrobat.Pro" to do script "{js_single}"'],
        capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        raise RuntimeError(f"Acrobat JS error: {result.stderr.strip()}")
    return result.stdout.strip()
```

## Verification Probe (Run Before Using)

```bash
osascript -e 'tell application id "com.adobe.Acrobat.Pro" to get version'
# Expected: 24.x.x
```

## Known Issues

1. **Modal dialog blocking**: Acrobat's payment/subscription dialog blocks the
   AppleScript `open` command event loop. Use `app.openDoc({bHidden: true})` via
   `do script` instead. The dialog does NOT block `do script` execution.

2. **License requirement**: Format conversion (PDF→DOCX etc.) requires a licensed
   Acrobat Pro installation. The harness fails loudly with install instructions if
   Acrobat is not found or not licensed.

3. **macOS only**: This harness is macOS-specific. The AppleScript + Acrobat JS
   automation surface does not exist on other platforms.
