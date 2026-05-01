# TEST.md — cli-anything-acrobat Test Plan & Results

## Test Inventory Plan

| File              | Tests planned | Scope                              |
|-------------------|---------------|------------------------------------|
| `test_core.py`    | 32            | Unit tests — synthetic data, no Acrobat |
| `test_full_e2e.py`| 20            | E2E tests — real PDFs, real Acrobat |

---

## Unit Test Plan (`test_core.py`)

All unit tests use synthetic data and do NOT require Adobe Acrobat or network access.

### `core/session.py` — 6 tests

| Test | What's tested | Edge cases |
|------|--------------|------------|
| `test_new_session` | `new_session()` sets source/output correctly | |
| `test_session_log_operation` | `log_operation()` sets dirty=True and appends | |
| `test_session_to_dict_from_dict` | Round-trip serialization | Empty session |
| `test_locked_save_and_load` | `save_session` + `load_session` round-trip | Creates missing dirs |
| `test_load_missing_file` | FileNotFoundError on missing session file | |
| `test_reset_session` | `reset_session()` clears global state | |

### `core/pages.py` — resolve_pages function — 8 tests

| Test | Input → Expected output |
|------|------------------------|
| `test_resolve_single_page` | "3" → [2] (0-indexed) |
| `test_resolve_range` | "2-4" → [1, 2, 3] |
| `test_resolve_comma_list` | "1,3,5" → [0, 2, 4] |
| `test_resolve_mixed` | "1,3-5,7" → [0, 2, 3, 4, 6] |
| `test_resolve_all` | "all" → [0..total-1] |
| `test_resolve_last` | "last" → [total-1] |
| `test_resolve_out_of_range` | "10" with 3 pages → [] |
| `test_resolve_deduplication` | "1,1,2-3" → [0, 1, 2] |

### `core/pages.py` — delete/extract validation — 4 tests

| Test | What's tested |
|------|--------------|
| `test_delete_all_pages_raises` | Deleting all pages raises ValueError |
| `test_delete_invalid_spec_raises` | Out-of-range spec raises ValueError |
| `test_extract_empty_spec_raises` | Empty spec raises ValueError |
| `test_reorder_out_of_range_raises` | Reorder with invalid page index raises ValueError |

### `core/export.py` — format resolution — 5 tests

| Test | What's tested |
|------|--------------|
| `test_resolve_format_docx` | "docx" maps to conv ID |
| `test_resolve_format_alias_word` | "word" alias → "docx" |
| `test_resolve_format_case_insensitive` | "DOCX" → same as "docx" |
| `test_unsupported_format_raises` | "xyz123" raises ValueError |
| `test_list_formats_completeness` | All conv IDs present in list |

### `utils/pypdf_backend.py` — headless operations — 9 tests

| Test | What's tested |
|------|--------------|
| `test_get_info_real_pdf` | Returns dict with required keys |
| `test_merge_two_pdfs` | Output page count = sum of inputs |
| `test_merge_one_pdf_raises` | <2 inputs raises ValueError |
| `test_split_by_chunk` | Split 4-page PDF into 2-page chunks → 2 files |
| `test_split_by_ranges` | Split with explicit ranges |
| `test_rotate_90` | Rotation applied to output PDF |
| `test_rotate_invalid_degrees_raises` | degrees=45 raises ValueError |
| `test_extract_pages_pypdf` | Extracted page count matches spec |
| `test_delete_pages_pypdf_count` | Remaining pages = total - deleted |

---

## E2E Test Plan (`test_full_e2e.py`)

All E2E tests require:
- Adobe Acrobat DC installed and licensed at `/Applications/Adobe Acrobat DC/`
- Real PDF files (generated synthetically via pypdf in test fixtures)
- Tests invoke the **real Acrobat** for conversion; NOT skipped if Acrobat missing (they FAIL)

### Backend probe — 2 tests

| Test | Verification |
|------|-------------|
| `test_acrobat_version` | `get_version()` returns "24.x.x" string |
| `test_acrobat_doc_info_js` | JS `app.openDoc` returns valid page count + metadata |

### Format conversion — 8 tests

| Test | Source → Output | Verification |
|------|----------------|-------------|
| `test_export_to_docx` | PDF → .docx | File exists, size > 1000, valid ZIP/OOXML |
| `test_export_to_xlsx` | PDF → .xlsx | File exists, size > 1000, valid ZIP/OOXML |
| `test_export_to_pptx` | PDF → .pptx | File exists, size > 1000, valid ZIP/OOXML |
| `test_export_to_png` | PDF → .png | File exists, PNG magic bytes |
| `test_export_to_jpeg` | PDF → .jpg | File exists, JPEG magic bytes |
| `test_export_to_txt` | PDF → .txt | File exists, contains readable text |
| `test_export_to_rtf` | PDF → .rtf | File exists, starts with {\rtf |
| `test_export_to_html` | PDF → .html | File exists, contains <html or <!DOCTYPE |

### Page operations via Acrobat — 3 tests

| Test | What's tested | Verification |
|------|--------------|-------------|
| `test_extract_pages_acrobat` | extractPages JS on multi-page PDF | Output PDF exists, page count = spec |
| `test_delete_pages_acrobat` | deletePages JS on multi-page PDF | Output PDF exists, page count correct |
| `test_rotate_pages_pypdf` | Rotate via pypdf (no Acrobat) | Output PDF exists, same page count |

### CLI subprocess tests — 5 tests

Uses `_resolve_cli("cli-anything-acrobat")` — never hardcodes paths.

| Test | Command tested | Verification |
|------|---------------|-------------|
| `test_cli_help` | `--help` | returncode=0, "acrobat" in output |
| `test_cli_info` | `info <pdf>` | returncode=0, page_count present |
| `test_cli_info_json` | `--json info <pdf>` | Valid JSON with page_count key |
| `test_cli_export_to_docx` | `export to <pdf> out.docx` | DOCX file exists, valid ZIP |
| `test_cli_merge_json` | `--json merge a.pdf b.pdf -o out.pdf` | JSON result, merged PDF exists |

---

## Realistic Workflow Scenarios

### Scenario 1: Document Conversion Pipeline
- **Simulates**: Converting a business PDF to editable Word for revision
- **Operations chained**: `info` → `export to --format docx`
- **Verified**: DOCX is valid OOXML ZIP with `word/document.xml` entry

### Scenario 2: PDF Assembly
- **Simulates**: Combining cover page, body, and appendix PDFs
- **Operations chained**: `merge cover.pdf body.pdf appendix.pdf -o final.pdf`
- **Verified**: Output page count = sum of inputs

### Scenario 3: Archival Split
- **Simulates**: Splitting a large report into per-chapter files
- **Operations chained**: `split report.pdf --pages-per-chunk 5 -d chapters/`
- **Verified**: Each chunk file exists, page counts sum to total

### Scenario 4: Page Cleanup + Export
- **Simulates**: Remove blank back cover, extract chapters, export as images
- **Operations chained**: `pages delete last -o clean.pdf` → `pages extract 1-5 -o ch1.pdf` → `export to ch1.pdf ch1.png`
- **Verified**: Each output file exists with correct format magic bytes

### Scenario 5: Metadata Authoring
- **Simulates**: Setting document metadata before archiving
- **Operations chained**: `metadata get` → `metadata set --title X --author Y -o out.pdf`
- **Verified**: metadata get on output PDF shows updated fields

---

## Test Results

### Phase 6 Final Run — 2026-04-30 (55/55 PASSED)

#### Summary

| Suite | Tests | Result |
|-------|-------|--------|
| `test_core.py` | 33 | ✅ 33 passed |
| `test_full_e2e.py` | 22 | ✅ 22 passed |
| **Total** | **55** | **✅ 55 passed** |

**Key bugs fixed during Phase 6**:
1. **macOS sandbox write restriction**: Acrobat can't write to `/private/var/folders/` (pytest temp dirs). Fixed by staging output through `/tmp/` with `_acrobat_tmp()` then moving to final destination.
2. **Image format per-page naming**: PNG/JPEG exports create `{stem}_Page_N.{ext}` files, not a single file. Fixed by scanning for page files and moving the first one to the requested output path.
3. **`mkstemp` pre-creates empty file**: Acrobat won't overwrite a pre-existing empty file in some format converters. Fixed by unlinking the temp file before passing the path to Acrobat.

---

### Phase 6 Initial Run — 2026-04-30

#### Unit Tests (`test_core.py`) — 33/33 PASSED

```
platform darwin -- Python 3.13.13, pytest-9.0.2
collected 33 items

TestSession::test_new_session PASSED
TestSession::test_new_session_defaults_output_to_source PASSED
TestSession::test_session_log_operation PASSED
TestSession::test_session_to_dict_from_dict PASSED
TestSession::test_locked_save_and_load PASSED
TestSession::test_load_missing_file_raises PASSED
TestSession::test_reset_session PASSED
TestResolvePages::test_resolve_single_page PASSED
TestResolvePages::test_resolve_range PASSED
TestResolvePages::test_resolve_comma_list PASSED
TestResolvePages::test_resolve_mixed PASSED
TestResolvePages::test_resolve_all PASSED
TestResolvePages::test_resolve_last PASSED
TestResolvePages::test_resolve_out_of_range PASSED
TestResolvePages::test_resolve_deduplication PASSED
TestPageValidation::test_delete_all_pages_raises PASSED
TestPageValidation::test_delete_invalid_spec_raises PASSED
TestPageValidation::test_extract_empty_spec_raises PASSED
TestPageValidation::test_reorder_out_of_range_raises PASSED
TestExportFormatResolution::test_resolve_format_docx PASSED
TestExportFormatResolution::test_resolve_format_alias_word PASSED
TestExportFormatResolution::test_resolve_format_case_insensitive PASSED
TestExportFormatResolution::test_unsupported_format_raises PASSED
TestExportFormatResolution::test_list_formats_completeness PASSED
TestPypdfBackend::test_get_info_real_pdf PASSED
TestPypdfBackend::test_merge_two_pdfs PASSED
TestPypdfBackend::test_merge_one_pdf_raises PASSED
TestPypdfBackend::test_split_by_chunk PASSED
TestPypdfBackend::test_split_by_ranges PASSED
TestPypdfBackend::test_rotate_90 PASSED
TestPypdfBackend::test_rotate_invalid_degrees_raises PASSED
TestPypdfBackend::test_extract_pages_pypdf PASSED
TestPypdfBackend::test_delete_pages_pypdf_count PASSED

33 passed in 0.59s
```

#### E2E Tests (`test_full_e2e.py`) — 12/22 PASSED, 10 FAILED

```
collected 22 items

TestAcrobatBackendProbe::test_acrobat_version PASSED
TestAcrobatBackendProbe::test_acrobat_doc_info_js PASSED
TestFormatConversion::test_export_to_docx FAILED  ← subscription required
TestFormatConversion::test_export_to_xlsx FAILED  ← subscription required
TestFormatConversion::test_export_to_pptx FAILED  ← subscription required
TestFormatConversion::test_export_to_png FAILED   ← subscription required
TestFormatConversion::test_export_to_jpeg FAILED  ← subscription required
TestFormatConversion::test_export_to_txt FAILED   ← subscription required
TestFormatConversion::test_export_to_rtf FAILED   ← subscription required
TestFormatConversion::test_export_to_html FAILED  ← subscription required
TestPageOperations::test_extract_pages_acrobat FAILED ← subscription/dialog blocking
TestPageOperations::test_delete_pages_acrobat PASSED
TestPageOperations::test_rotate_pages_pypdf PASSED
TestCLISubprocess::test_cli_help PASSED
TestCLISubprocess::test_cli_info PASSED
TestCLISubprocess::test_cli_info_json PASSED
TestCLISubprocess::test_cli_export_to_docx FAILED ← subscription required
TestCLISubprocess::test_cli_merge_json PASSED
TestWorkflowScenarios::test_scenario_info_then_merge PASSED
TestWorkflowScenarios::test_scenario_archival_split PASSED
TestWorkflowScenarios::test_scenario_page_cleanup PASSED
TestWorkflowScenarios::test_scenario_metadata_roundtrip PASSED

12 passed, 10 failed in 9.51s
```

#### Known Limitation: Format Conversion Requires Active Adobe Subscription

`doc.saveAs({cConvID: ...})` in Acrobat JS triggers Adobe's conversion engine, which requires
an active Acrobat Pro subscription. When the subscription is invalid, expired, or in trial mode,
Acrobat may:
1. Show a payment/subscription modal (blocking all further `do script` events with error -1708)
2. Run the JS without error but produce no output file

**Affected tests**: All `TestFormatConversion` tests, `test_extract_pages_acrobat`, `test_cli_export_to_docx`

**Tests that pass without subscription**: `info`, `merge`, `split`, `rotate` (via pypdf), `delete` (via pypdf),
metadata reads, CLI `--help`, `info`, `info --json`, `merge --json`, all 4 workflow scenarios.

**To run format conversion tests**: Ensure a valid Adobe Acrobat Pro subscription is active and no
subscription/payment dialogs are blocking Acrobat.

