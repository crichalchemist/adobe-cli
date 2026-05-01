# cli-anything-illustrator — Test Plan & Results

## Test Inventory Plan

| File | Planned tests |
|------|--------------|
| `test_core.py` | 40 unit tests |
| `test_full_e2e.py` | 18 E2E tests |

---

## Unit Test Plan (`test_core.py`)

Unit tests run with **no Illustrator process required**. Backend is always injected as a mock.

### `TestBackendEscape` — `ai_backend._escape_path` (3 tests)
- `test_normal_path` — `/tmp/foo.jsx` passes through unchanged
- `test_path_with_spaces` — spaces are not a problem for the #include approach
- `test_jsx_write_and_cleanup` — temp file created, contains polyfill prefix + body, cleaned up after

### `TestDocumentCore` — `core.document` (10 tests)
Functions under test: `get_document_info`, `list_documents`, `parse_document_result`

- `test_get_document_info_parses_result` — mock backend returns JSON, result dict has expected keys
- `test_get_document_info_color_space_cmyk` — CMYK color space parsed correctly
- `test_get_document_info_color_space_rgb` — RGB parsed correctly
- `test_get_document_info_ruler_units` — ruler units string mapped correctly
- `test_list_documents_empty` — mock returns `[]`, function returns empty list
- `test_list_documents_multiple` — multiple open docs returned with correct structure
- `test_document_not_open_raises` — backend returns error JSON, raises `DocumentNotOpenError`
- `test_open_document_path_validated` — non-existent path raises `FileNotFoundError`
- `test_open_document_nonai_raises` — `.txt` extension raises `ValueError`
- `test_close_document_returns_ok` — mock returns ok, result has `{"ok": true}`

### `TestLayerCore` — `core.layer` (8 tests)
Functions under test: `list_layers`, `set_layer_visible`, `set_layer_locked`

- `test_list_layers_returns_list` — mock returns layer list, structure verified
- `test_list_layers_includes_visibility` — visible/locked flags present
- `test_list_layers_includes_sublayers` — nested layers flattened with depth
- `test_set_visible_builds_correct_script` — script sent to backend contains layer name + `visible = true`
- `test_set_visible_false` — `visible = false` in script
- `test_set_locked_builds_correct_script` — locked flag in script
- `test_layer_not_found_raises` — backend returns error JSON, raises `LayerNotFoundError`
- `test_layer_name_escaped_in_script` — layer name with special chars properly quoted

### `TestArtboardCore` — `core.artboard` (5 tests)
Functions under test: `list_artboards`, `set_active_artboard`

- `test_list_artboards_returns_list` — mock returns artboard list with name/width/height
- `test_list_artboards_includes_index` — zero-based index field present
- `test_set_active_artboard_valid_index` — script targets correct artboard index
- `test_set_active_artboard_negative_index_raises` — raises `ValueError`
- `test_set_active_artboard_out_of_range_raises` — backend error JSON raises `ArtboardError`

### `TestObjectCore` — `core.object` (6 tests)
Functions under test: `list_objects`, `get_selection`

- `test_list_objects_returns_list` — mock returns page items with type/name/position/size
- `test_list_objects_layer_filter` — `layer=` param passes layer name in script
- `test_list_objects_no_active_doc_raises` — backend error raises `DocumentNotOpenError`
- `test_get_selection_empty` — empty array returned when nothing selected
- `test_get_selection_single_item` — single selected item has correct structure
- `test_get_selection_multiple_items` — multiple items returned

### `TestTextCore` — `core.text` (5 tests)
Functions under test: `list_text_frames`, `set_text_content`

- `test_list_text_frames_returns_list` — mock returns text frames with contents/position
- `test_list_text_frames_empty` — empty list when no text frames
- `test_set_text_content_builds_script` — script targets correct index, sets contents
- `test_set_text_content_index_out_of_range_raises` — raises `ValueError` for negative index
- `test_set_text_content_escapes_quotes` — double-quotes in content properly escaped in script

### `TestSwatchCore` — `core.swatch` (3 tests)
Functions under test: `list_swatches`

- `test_list_swatches_returns_list` — mock returns swatches with name/type/color values
- `test_list_swatches_skips_none_swatch` — the "[None]" swatch excluded by default
- `test_list_swatches_includes_spot_colors` — spot color type preserved

---

## E2E Test Plan (`test_full_e2e.py`)

All E2E tests skip automatically when Illustrator is not running (`_bridge_reachable()` returns False). Tests that export files print artifact paths for manual inspection.

### `TestBridgeE2E` (3 tests)
- `test_ping_returns_ok` — `ping()` returns `{"ok": True}` with `app_version` containing "30"
- `test_ping_has_version_field` — version field present and non-empty
- `test_illustrator_not_running_raises` — (run without Illustrator) appropriate error raised

### `TestDocumentE2E` (4 tests, requires open document)
- `test_get_document_info_live` — live doc info has correct keys, width/height > 0
- `test_list_documents_live` — at least one document in list
- `test_document_name_is_string` — name field is non-empty string
- `test_document_color_space_valid` — color_space is "CMYK" or "RGB"

### `TestLayerE2E` (3 tests)
- `test_list_layers_live` — returns list of at least 1 layer
- `test_layer_has_required_fields` — each layer has name, visible, locked
- `test_toggle_layer_visible` — set visible=False then visible=True, verify round-trip

### `TestArtboardE2E` (2 tests)
- `test_list_artboards_live` — returns list, each has name/width/height/index
- `test_set_active_artboard_live` — set artboard 0, verify active artboard index

### `TestExportE2E` (4 tests — print artifact paths)
- `test_export_png_creates_file` — PNG file created, size > 0, magic bytes `\x89PNG`
- `test_export_svg_creates_file` — SVG file created, contains `<svg`
- `test_export_pdf_creates_file` — PDF created, starts with `%PDF-`
- `test_export_jpeg_creates_file` — JPEG created, magic bytes `\xff\xd8\xff`

### `TestCLISubprocess` (2 tests)
- `test_help_exits_zero` — `cli-anything-illustrator --help` exits 0
- `test_ping_json` — `cli-anything-illustrator --json ping` returns parseable JSON with `ok: true`

---

## Workflow Scenarios

### Workflow 1: Brand asset inspection
**Simulates:** Designer asks agent "what artboards and layers does this file have?"
**Operations:**
1. `document info` → get dimensions, color space
2. `layer list` → enumerate all layers with visibility
3. `artboard list` → enumerate artboards with sizes

**Verified:** All output is valid JSON, layer/artboard counts match document structure.

### Workflow 2: Export pipeline
**Simulates:** Agent exports each artboard as PNG for a web delivery package.
**Operations:**
1. `document info` → confirm doc is open
2. `artboard list` → get artboard count
3. `export png /tmp/out_0.png --artboard 0`
4. `export png /tmp/out_1.png --artboard 1`

**Verified:** Both PNGs exist, size > 0, valid PNG magic bytes.

### Workflow 3: Text inventory
**Simulates:** QA agent audits all text in a document.
**Operations:**
1. `text list` → get all text frames with contents
2. `selection info` → confirm current selection state

**Verified:** Text frames have non-empty contents field.

---

## Test Results

Run on 2026-05-01 against Illustrator 2026 (30.3.0), Python 3.13.13, macOS 13.6.

```
============================= test session starts ==============================
platform darwin -- Python 3.13.13, pytest-9.0.2, pluggy-1.6.0
rootdir: /Volumes/Containers/adobe-cli/illustrator/agent-harness

cli_anything/illustrator/tests/test_core.py::TestBackendEscape::test_write_jsx_contains_polyfill PASSED
cli_anything/illustrator/tests/test_core.py::TestBackendEscape::test_write_jsx_creates_temp_file PASSED
cli_anything/illustrator/tests/test_core.py::TestBackendEscape::test_write_jsx_cleanup PASSED
cli_anything/illustrator/tests/test_core.py::TestDocumentCore::test_get_document_info_parses_result PASSED
cli_anything/illustrator/tests/test_core.py::TestDocumentCore::test_get_document_info_expected_keys PASSED
cli_anything/illustrator/tests/test_core.py::TestDocumentCore::test_get_document_info_cmyk_color_space PASSED
cli_anything/illustrator/tests/test_core.py::TestDocumentCore::test_get_document_info_rgb_color_space PASSED
cli_anything/illustrator/tests/test_core.py::TestDocumentCore::test_get_document_info_raises_on_error PASSED
cli_anything/illustrator/tests/test_core.py::TestDocumentCore::test_list_documents_empty PASSED
cli_anything/illustrator/tests/test_core.py::TestDocumentCore::test_list_documents_multiple PASSED
cli_anything/illustrator/tests/test_core.py::TestDocumentCore::test_open_document_nonexistent_path_raises PASSED
cli_anything/illustrator/tests/test_core.py::TestDocumentCore::test_open_document_bad_extension_raises PASSED
cli_anything/illustrator/tests/test_core.py::TestDocumentCore::test_close_document_returns_ok PASSED
cli_anything/illustrator/tests/test_core.py::TestDocumentCore::test_close_document_raises_if_no_doc PASSED
cli_anything/illustrator/tests/test_core.py::TestLayerCore::test_list_layers_returns_list PASSED
cli_anything/illustrator/tests/test_core.py::TestLayerCore::test_list_layers_includes_visibility PASSED
cli_anything/illustrator/tests/test_core.py::TestLayerCore::test_list_layers_includes_sublayers PASSED
cli_anything/illustrator/tests/test_core.py::TestLayerCore::test_set_visible_returns_ok PASSED
cli_anything/illustrator/tests/test_core.py::TestLayerCore::test_set_visible_false_passes_correctly PASSED
cli_anything/illustrator/tests/test_core.py::TestLayerCore::test_set_locked_returns_ok PASSED
cli_anything/illustrator/tests/test_core.py::TestLayerCore::test_set_visible_layer_not_found_raises PASSED
cli_anything/illustrator/tests/test_core.py::TestLayerCore::test_layer_name_escaped_in_script PASSED
cli_anything/illustrator/tests/test_core.py::TestArtboardCore::test_list_artboards_returns_list PASSED
cli_anything/illustrator/tests/test_core.py::TestArtboardCore::test_list_artboards_includes_index PASSED
cli_anything/illustrator/tests/test_core.py::TestArtboardCore::test_set_active_artboard_returns_ok PASSED
cli_anything/illustrator/tests/test_core.py::TestArtboardCore::test_set_active_artboard_negative_raises PASSED
cli_anything/illustrator/tests/test_core.py::TestArtboardCore::test_set_active_artboard_out_of_range_raises PASSED
cli_anything/illustrator/tests/test_core.py::TestObjectCore::test_list_objects_returns_list PASSED
cli_anything/illustrator/tests/test_core.py::TestObjectCore::test_list_objects_layer_filter_passes_in_script PASSED
cli_anything/illustrator/tests/test_core.py::TestObjectCore::test_list_objects_no_doc_returns_empty PASSED
cli_anything/illustrator/tests/test_core.py::TestObjectCore::test_get_selection_empty PASSED
cli_anything/illustrator/tests/test_core.py::TestObjectCore::test_get_selection_single_item PASSED
cli_anything/illustrator/tests/test_core.py::TestObjectCore::test_get_selection_multiple_items PASSED
cli_anything/illustrator/tests/test_core.py::TestTextCore::test_list_text_frames_returns_list PASSED
cli_anything/illustrator/tests/test_core.py::TestTextCore::test_list_text_frames_empty PASSED
cli_anything/illustrator/tests/test_core.py::TestTextCore::test_set_text_content_builds_script PASSED
cli_anything/illustrator/tests/test_core.py::TestTextCore::test_set_text_content_negative_index_raises PASSED
cli_anything/illustrator/tests/test_core.py::TestTextCore::test_set_text_content_escapes_double_quotes PASSED
cli_anything/illustrator/tests/test_core.py::TestSwatchCore::test_list_swatches_returns_list PASSED
cli_anything/illustrator/tests/test_core.py::TestSwatchCore::test_list_swatches_skips_none_swatch PASSED
cli_anything/illustrator/tests/test_core.py::TestSwatchCore::test_list_swatches_includes_spot_colors PASSED
cli_anything/illustrator/tests/test_full_e2e.py::TestBridgeE2E::test_ping_returns_ok PASSED
cli_anything/illustrator/tests/test_full_e2e.py::TestBridgeE2E::test_ping_has_app_version PASSED
cli_anything/illustrator/tests/test_full_e2e.py::TestBridgeE2E::test_ping_version_starts_with_30 PASSED
cli_anything/illustrator/tests/test_full_e2e.py::TestDocumentE2E::test_get_document_info_live PASSED
cli_anything/illustrator/tests/test_full_e2e.py::TestDocumentE2E::test_list_documents_live PASSED
cli_anything/illustrator/tests/test_full_e2e.py::TestDocumentE2E::test_document_name_is_string PASSED
cli_anything/illustrator/tests/test_full_e2e.py::TestDocumentE2E::test_document_color_space_valid PASSED
cli_anything/illustrator/tests/test_full_e2e.py::TestLayerE2E::test_list_layers_live PASSED
cli_anything/illustrator/tests/test_full_e2e.py::TestLayerE2E::test_layer_has_required_fields PASSED
cli_anything/illustrator/tests/test_full_e2e.py::TestLayerE2E::test_toggle_layer_visible PASSED
cli_anything/illustrator/tests/test_full_e2e.py::TestArtboardE2E::test_list_artboards_live PASSED
cli_anything/illustrator/tests/test_full_e2e.py::TestArtboardE2E::test_set_active_artboard_live PASSED
cli_anything/illustrator/tests/test_full_e2e.py::TestExportE2E::test_export_png_creates_file PASSED
cli_anything/illustrator/tests/test_full_e2e.py::TestExportE2E::test_export_jpeg_creates_file PASSED
cli_anything/illustrator/tests/test_full_e2e.py::TestExportE2E::test_export_svg_creates_file PASSED
cli_anything/illustrator/tests/test_full_e2e.py::TestExportE2E::test_export_pdf_creates_file PASSED
cli_anything/illustrator/tests/test_full_e2e.py::TestCLISubprocess::test_help_exits_zero PASSED
cli_anything/illustrator/tests/test_full_e2e.py::TestCLISubprocess::test_ping_json PASSED

============================== 59 passed in 10.94s ==============================
```

### Summary

| Metric | Value |
|--------|-------|
| Total tests | 59 |
| Passed | 59 |
| Failed | 0 |
| Pass rate | 100% |
| Execution time | 10.94s |

### Coverage Notes

- All 7 command groups covered in unit and/or E2E tests
- Export: all 4 formats (PNG, JPEG, SVG, PDF) verified with magic bytes / format markers
- Layer toggle is a round-trip test (off → verify → on → verify)
- CLI subprocess tests use the installed `cli-anything-illustrator` binary
- Not covered: `document open` E2E (would need a `.ai` file on disk), `text set` E2E (requires a document with text frames)
