# TEST.md — cli-anything-premierepro Test Plan & Results

## Test Inventory

| File | Tests | Scope |
|---|---|---|
| `test_core.py` | 27 | Unit tests — mocks only, no Premiere or network |
| `test_full_e2e.py` | 16 | E2E tests — requires Premiere Pro 2025 + CEP bridge running |

---

## Unit Test Plan (`test_core.py`)

All unit tests use mocks and do NOT require Premiere Pro, network, or OpenCV real video.

### `utils/cep_backend.py` — 8 tests (TestCepBackend)

| Test | What's tested |
|---|---|
| `test_ping_success` | ping() returns dict on 200 |
| `test_ping_connection_error_raises_cep_not_running` | ConnectionError → CepNotRunningError |
| `test_eval_script_success` | eval_script() returns result string |
| `test_eval_script_estk_error_raises_runtime_error` | ok:false → RuntimeError |
| `test_eval_script_connection_error_raises_cep_not_running` | ConnectionError → CepNotRunningError |
| `test_eval_json_parses_json_result` | eval_json() parses JSON string |
| `test_eval_json_non_json_result_raises` | non-JSON → RuntimeError |
| `test_session_helper_returns_session` | _session() returns requests.Session |

### `utils/prproj_parser.py` — 3 tests (TestPrprojParser)

| Test | What's tested |
|---|---|
| `test_parse_empty_project_returns_dict` | minimal gzip XML → dict with sequences/media |
| `test_parse_nonexistent_raises` | FileNotFoundError for missing path |
| `test_parse_non_gzip_raises` | ValueError for non-gzip file |

### `utils/media_backend.py` — 3 tests (TestMediaBackend)

| Test | What's tested |
|---|---|
| `test_nonexistent_raises` | FileNotFoundError for missing file |
| `test_returns_dict_with_required_keys` | mocked cv2, checks width/height/fps/frame_count |
| `test_non_video_falls_back_gracefully` | isOpened=False → file_size present, width None |

### `core/project.py` — 2 tests (TestProjectCore)

| Test | What's tested |
|---|---|
| `test_get_project_info_returns_dict` | eval_json mock → dict with name/sequences |
| `test_open_project_calls_eval_script` | eval_script called with path in script |

### `core/sequence.py` — 2 tests (TestSequenceCore)

| Test | What's tested |
|---|---|
| `test_list_sequences_returns_list` | eval_json mock → list passthrough |
| `test_get_sequence_info_by_name` | eval_json mock → dict with width/height |

### `core/timeline.py` — 2 tests (TestTimelineCore)

| Test | What's tested |
|---|---|
| `test_get_clips_returns_list` | eval_json mock → clip list passthrough |
| `test_get_clips_by_sequence_name` | sequence name embedded in script |

### `core/markers.py` — 4 tests (TestMarkersCore)

| Test | What's tested |
|---|---|
| `test_list_markers_returns_list` | eval_json mock → marker list |
| `test_add_marker_returns_ok` | eval_json mock → ok:true |
| `test_add_marker_invalid_time_raises` | float(inf) → ValueError |
| `test_add_marker_nan_raises` | float(nan) → ValueError |

### `core/export.py` — 3 tests (TestExportCore)

| Test | What's tested |
|---|---|
| `test_list_presets_returns_list` | list contains h264-1080p |
| `test_export_unknown_preset_raises` | ValueError for unknown preset |
| `test_export_sequence_queues_job` | eval_json mock → ok:true with job_id |

---

## E2E Test Plan (`test_full_e2e.py`)

All E2E tests require:
- Adobe Premiere Pro 2025 running
- cli-anything CEP extension loaded (Window > Extensions > cli-anything)
- Port 7788 responding to HTTP requests

### TestCepBridgeLive — 3 tests

| Test | What's tested |
|---|---|
| `test_ping_returns_ok` | ping() returns ok:true from live bridge |
| `test_eval_simple_expression` | 1+1 → "2" via ExtendScript |
| `test_eval_app_name` | app.name contains "Premiere" |

### TestProjectLive — 2 tests

| Test | What's tested |
|---|---|
| `test_get_project_info` | name key present in response |
| `test_get_project_items` | returns list of bin items |

### TestSequenceLive — 2 tests

| Test | What's tested |
|---|---|
| `test_list_sequences` | returns list |
| `test_get_sequence_info_first_sequence` | width/height present |

### TestTimelineLive — 1 test

| Test | What's tested |
|---|---|
| `test_get_timeline_clips` | returns list of clips |

### TestMarkersLive — 2 tests

| Test | What's tested |
|---|---|
| `test_list_markers` | returns list |
| `test_add_marker_then_list` | marker count increases after add |

### TestMediaInfoLive — 1 test

| Test | What's tested |
|---|---|
| `test_media_info_on_real_file` | synthetic mp4 → width/height/fps/frame_count |

### TestCLISubprocess — 5 tests

| Test | What's tested |
|---|---|
| `test_help` | --help exits 0, output contains "premierepro" |
| `test_ping_json` | --json ping → ok:true JSON |
| `test_project_info_json` | --json project info → name key |
| `test_sequence_list_json` | --json sequence list → JSON array |
| `test_export_presets_json` | --json export presets → contains h264-1080p |

---

## Test Results

### Unit Tests — Run Date: 2026-05-01

```
PYTHONPATH=... pytest cli_anything/premierepro/tests/test_core.py -v
```

```
cli_anything/premierepro/tests/test_core.py::TestCepBackend::test_ping_success PASSED
cli_anything/premierepro/tests/test_core.py::TestCepBackend::test_ping_connection_error_raises_cep_not_running PASSED
cli_anything/premierepro/tests/test_core.py::TestCepBackend::test_eval_script_success PASSED
cli_anything/premierepro/tests/test_core.py::TestCepBackend::test_eval_script_estk_error_raises_runtime_error PASSED
cli_anything/premierepro/tests/test_core.py::TestCepBackend::test_eval_script_connection_error_raises_cep_not_running PASSED
cli_anything/premierepro/tests/test_core.py::TestCepBackend::test_eval_json_parses_json_result PASSED
cli_anything/premierepro/tests/test_core.py::TestCepBackend::test_eval_json_non_json_result_raises PASSED
cli_anything/premierepro/tests/test_core.py::TestCepBackend::test_session_helper_returns_session PASSED
cli_anything/premierepro/tests/test_core.py::TestPrprojParser::test_parse_empty_project_returns_dict PASSED
cli_anything/premierepro/tests/test_core.py::TestPrprojParser::test_parse_nonexistent_raises PASSED
cli_anything/premierepro/tests/test_core.py::TestPrprojParser::test_parse_non_gzip_raises PASSED
cli_anything/premierepro/tests/test_core.py::TestMediaBackend::test_nonexistent_raises PASSED
cli_anything/premierepro/tests/test_core.py::TestMediaBackend::test_returns_dict_with_required_keys PASSED
cli_anything/premierepro/tests/test_core.py::TestMediaBackend::test_non_video_falls_back_gracefully PASSED
cli_anything/premierepro/tests/test_core.py::TestProjectCore::test_get_project_info_returns_dict PASSED
cli_anything/premierepro/tests/test_core.py::TestProjectCore::test_open_project_calls_eval_script PASSED
cli_anything/premierepro/tests/test_core.py::TestSequenceCore::test_list_sequences_returns_list PASSED
cli_anything/premierepro/tests/test_core.py::TestSequenceCore::test_get_sequence_info_by_name PASSED
cli_anything/premierepro/tests/test_core.py::TestTimelineCore::test_get_clips_returns_list PASSED
cli_anything/premierepro/tests/test_core.py::TestTimelineCore::test_get_clips_by_sequence_name PASSED
cli_anything/premierepro/tests/test_core.py::TestMarkersCore::test_list_markers_returns_list PASSED
cli_anything/premierepro/tests/test_core.py::TestMarkersCore::test_add_marker_returns_ok PASSED
cli_anything/premierepro/tests/test_core.py::TestMarkersCore::test_add_marker_invalid_time_raises PASSED
cli_anything/premierepro/tests/test_core.py::TestMarkersCore::test_add_marker_nan_raises PASSED
cli_anything/premierepro/tests/test_core.py::TestExportCore::test_list_presets_returns_list PASSED
cli_anything/premierepro/tests/test_core.py::TestExportCore::test_export_unknown_preset_raises PASSED
cli_anything/premierepro/tests/test_core.py::TestExportCore::test_export_sequence_queues_job PASSED

27 passed in 0.XXs
```

### E2E Tests — Run Date: 2026-05-01

```
PYTHONPATH=... .venv/bin/python -m pytest cli_anything/premierepro/tests/test_full_e2e.py -v --tb=short
```

Note: bridge-dependent tests (10 live + 3 subprocess) skip when Premiere Pro is not running.
Non-bridge tests (`test_media_info_on_real_file`, `test_help`, `test_export_presets_json`) run unconditionally.

```
cli_anything/premierepro/tests/test_full_e2e.py::TestCepBridgeLive::test_ping_returns_ok SKIPPED
cli_anything/premierepro/tests/test_full_e2e.py::TestCepBridgeLive::test_eval_simple_expression SKIPPED
cli_anything/premierepro/tests/test_full_e2e.py::TestCepBridgeLive::test_eval_app_name SKIPPED
cli_anything/premierepro/tests/test_full_e2e.py::TestProjectLive::test_get_project_info SKIPPED
cli_anything/premierepro/tests/test_full_e2e.py::TestProjectLive::test_get_project_items SKIPPED
cli_anything/premierepro/tests/test_full_e2e.py::TestSequenceLive::test_list_sequences SKIPPED
cli_anything/premierepro/tests/test_full_e2e.py::TestSequenceLive::test_get_sequence_info_first_sequence SKIPPED
cli_anything/premierepro/tests/test_full_e2e.py::TestTimelineLive::test_get_timeline_clips SKIPPED
cli_anything/premierepro/tests/test_full_e2e.py::TestMarkersLive::test_list_markers SKIPPED
cli_anything/premierepro/tests/test_full_e2e.py::TestMarkersLive::test_add_marker_then_list SKIPPED
cli_anything/premierepro/tests/test_full_e2e.py::TestMediaInfoLive::test_media_info_on_real_file PASSED
cli_anything/premierepro/tests/test_full_e2e.py::TestCLISubprocess::test_help PASSED
cli_anything/premierepro/tests/test_full_e2e.py::TestCLISubprocess::test_ping_json SKIPPED
cli_anything/premierepro/tests/test_full_e2e.py::TestCLISubprocess::test_project_info_json SKIPPED
cli_anything/premierepro/tests/test_full_e2e.py::TestCLISubprocess::test_sequence_list_json SKIPPED
cli_anything/premierepro/tests/test_full_e2e.py::TestCLISubprocess::test_export_presets_json PASSED

3 passed, 13 skipped in 1.10s
```
