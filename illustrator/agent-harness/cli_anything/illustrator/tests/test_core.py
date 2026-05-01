"""Unit tests for cli-anything-illustrator core modules.

No Illustrator process required. Backend is always a mock.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
import tempfile
import os

import pytest

from cli_anything.illustrator.core.document import (
    DocumentNotOpenError,
    get_document_info,
    list_documents,
    open_document,
    close_document,
    save_document,
)
from cli_anything.illustrator.core.layer import (
    LayerNotFoundError,
    list_layers,
    set_layer_visible,
    set_layer_locked,
)
from cli_anything.illustrator.core.artboard import (
    ArtboardError,
    list_artboards,
    set_active_artboard,
)
from cli_anything.illustrator.core.object import list_objects, get_selection
from cli_anything.illustrator.core.text import list_text_frames, set_text_content
from cli_anything.illustrator.core.swatch import list_swatches


def _mock_backend(json_return: Any) -> MagicMock:
    m = MagicMock()
    m.eval_json.return_value = json_return
    m.eval_jsx.return_value = json.dumps(json_return) if not isinstance(json_return, str) else json_return
    return m


# ---------------------------------------------------------------------------
# TestBackendEscape
# ---------------------------------------------------------------------------

class TestBackendEscape:
    def test_write_jsx_contains_polyfill(self):
        from cli_anything.illustrator.utils.ai_backend import _write_jsx, _JSON_POLYFILL
        path = _write_jsx("var x = 1;")
        try:
            content = path.read_text()
            assert "typeof JSON" in content
            assert "var x = 1;" in content
        finally:
            path.unlink(missing_ok=True)

    def test_write_jsx_creates_temp_file(self):
        from cli_anything.illustrator.utils.ai_backend import _write_jsx
        path = _write_jsx("var y = 2;")
        try:
            assert path.exists()
            assert path.suffix == ".jsx"
            assert path.parent == Path("/tmp")
        finally:
            path.unlink(missing_ok=True)

    def test_write_jsx_cleanup(self):
        from cli_anything.illustrator.utils.ai_backend import _write_jsx
        path = _write_jsx("var z = 3;")
        path.unlink()
        assert not path.exists()


# ---------------------------------------------------------------------------
# TestDocumentCore
# ---------------------------------------------------------------------------

class TestDocumentCore:
    _DOC_RESPONSE = {
        "name": "logo.ai",
        "path": "/Users/test/logo.ai",
        "width": 800.0,
        "height": 600.0,
        "color_space": "CMYK",
        "ruler_units": "RulerUnits.Points",
        "layer_count": 3,
        "artboard_count": 2,
        "path_item_count": 10,
        "text_frame_count": 2,
        "swatch_count": 5,
        "modified": False,
    }

    def test_get_document_info_parses_result(self):
        backend = _mock_backend(self._DOC_RESPONSE)
        result = get_document_info(backend)
        assert result["name"] == "logo.ai"
        assert result["width"] == 800.0
        assert result["color_space"] == "CMYK"

    def test_get_document_info_expected_keys(self):
        backend = _mock_backend(self._DOC_RESPONSE)
        result = get_document_info(backend)
        for key in ("name", "width", "height", "color_space", "layer_count", "artboard_count"):
            assert key in result, f"Missing key: {key}"

    def test_get_document_info_cmyk_color_space(self):
        resp = dict(self._DOC_RESPONSE, color_space="CMYK")
        backend = _mock_backend(resp)
        result = get_document_info(backend)
        assert result["color_space"] == "CMYK"

    def test_get_document_info_rgb_color_space(self):
        resp = dict(self._DOC_RESPONSE, color_space="RGB")
        backend = _mock_backend(resp)
        result = get_document_info(backend)
        assert result["color_space"] == "RGB"

    def test_get_document_info_raises_on_error(self):
        backend = _mock_backend({"error": "No document open"})
        with pytest.raises(DocumentNotOpenError):
            get_document_info(backend)

    def test_list_documents_empty(self):
        backend = _mock_backend([])
        result = list_documents(backend)
        assert result == []

    def test_list_documents_multiple(self):
        docs = [
            {"name": "a.ai", "path": "/tmp/a.ai", "width": 100, "height": 100, "color_space": "RGB", "active": True},
            {"name": "b.ai", "path": "/tmp/b.ai", "width": 200, "height": 200, "color_space": "CMYK", "active": False},
        ]
        backend = _mock_backend(docs)
        result = list_documents(backend)
        assert len(result) == 2
        assert result[0]["name"] == "a.ai"
        assert result[1]["name"] == "b.ai"

    def test_open_document_nonexistent_path_raises(self, tmp_path):
        backend = _mock_backend({"ok": True, "name": "x.ai", "path": "/tmp/x.ai"})
        with pytest.raises(FileNotFoundError):
            open_document(str(tmp_path / "missing.ai"), backend)

    def test_open_document_bad_extension_raises(self, tmp_path):
        p = tmp_path / "file.txt"
        p.write_text("not an ai file")
        backend = _mock_backend({"ok": True, "name": "file.txt", "path": str(p)})
        with pytest.raises(ValueError, match="Unsupported"):
            open_document(str(p), backend)

    def test_close_document_returns_ok(self):
        backend = _mock_backend({"ok": True, "closed": "logo.ai"})
        result = close_document(backend)
        assert result["ok"] is True
        assert result["closed"] == "logo.ai"

    def test_close_document_raises_if_no_doc(self):
        backend = _mock_backend({"error": "No document open"})
        with pytest.raises(DocumentNotOpenError):
            close_document(backend)


# ---------------------------------------------------------------------------
# TestLayerCore
# ---------------------------------------------------------------------------

class TestLayerCore:
    _LAYERS = [
        {"name": "Background", "visible": True, "locked": False, "depth": 0},
        {"name": "Artwork", "visible": True, "locked": False, "depth": 0},
        {"name": "Text", "visible": False, "locked": True, "depth": 0},
        {"name": "Sub-layer", "visible": True, "locked": False, "depth": 1},
    ]

    def test_list_layers_returns_list(self):
        backend = _mock_backend(self._LAYERS)
        result = list_layers(backend)
        assert isinstance(result, list)
        assert len(result) == 4

    def test_list_layers_includes_visibility(self):
        backend = _mock_backend(self._LAYERS)
        result = list_layers(backend)
        assert "visible" in result[0]
        assert "locked" in result[0]

    def test_list_layers_includes_sublayers(self):
        backend = _mock_backend(self._LAYERS)
        result = list_layers(backend)
        depths = [l["depth"] for l in result]
        assert 1 in depths

    def test_set_visible_returns_ok(self):
        backend = _mock_backend({"ok": True, "name": "Artwork", "visible": True})
        result = set_layer_visible("Artwork", True, backend)
        assert result["ok"] is True

    def test_set_visible_false_passes_correctly(self):
        backend = _mock_backend({"ok": True, "name": "Artwork", "visible": False})
        result = set_layer_visible("Artwork", False, backend)
        assert result["visible"] is False
        # Verify the script sent to backend contains "false"
        call_args = backend.eval_json.call_args[0][0]
        assert "false" in call_args

    def test_set_locked_returns_ok(self):
        backend = _mock_backend({"ok": True, "name": "Text", "locked": True})
        result = set_layer_locked("Text", True, backend)
        assert result["ok"] is True

    def test_set_visible_layer_not_found_raises(self):
        backend = _mock_backend({"error": "Layer not found: Ghost"})
        with pytest.raises(LayerNotFoundError):
            set_layer_visible("Ghost", True, backend)

    def test_layer_name_escaped_in_script(self):
        backend = _mock_backend({"ok": True, "name": 'My "Layer"', "visible": True})
        set_layer_visible('My "Layer"', True, backend)
        call_args = backend.eval_json.call_args[0][0]
        assert '\\"' in call_args


# ---------------------------------------------------------------------------
# TestArtboardCore
# ---------------------------------------------------------------------------

class TestArtboardCore:
    _ARTBOARDS = [
        {"index": 0, "name": "Artboard 1", "width": 800.0, "height": 600.0, "x": 0.0, "y": 0.0},
        {"index": 1, "name": "Artboard 2", "width": 400.0, "height": 300.0, "x": 850.0, "y": 0.0},
    ]

    def test_list_artboards_returns_list(self):
        backend = _mock_backend(self._ARTBOARDS)
        result = list_artboards(backend)
        assert len(result) == 2

    def test_list_artboards_includes_index(self):
        backend = _mock_backend(self._ARTBOARDS)
        result = list_artboards(backend)
        assert result[0]["index"] == 0
        assert result[1]["index"] == 1

    def test_set_active_artboard_returns_ok(self):
        backend = _mock_backend({"ok": True, "index": 1, "name": "Artboard 2", "width": 400.0, "height": 300.0})
        result = set_active_artboard(1, backend)
        assert result["ok"] is True
        assert result["index"] == 1

    def test_set_active_artboard_negative_raises(self):
        backend = _mock_backend({})
        with pytest.raises(ValueError, match="must be >= 0"):
            set_active_artboard(-1, backend)

    def test_set_active_artboard_out_of_range_raises(self):
        backend = _mock_backend({"error": "Artboard index 99 out of range (count: 2)"})
        with pytest.raises(ArtboardError):
            set_active_artboard(99, backend)


# ---------------------------------------------------------------------------
# TestObjectCore
# ---------------------------------------------------------------------------

class TestObjectCore:
    _OBJECTS = [
        {"index": 0, "name": "rect1", "type": "PathItem", "x": 0.0, "y": 100.0, "width": 200.0, "height": 100.0, "visible": True, "locked": False, "layer": "Artwork"},
        {"index": 1, "name": "", "type": "CompoundPathItem", "x": 210.0, "y": 100.0, "width": 50.0, "height": 50.0, "visible": True, "locked": False, "layer": "Artwork"},
    ]

    def test_list_objects_returns_list(self):
        backend = _mock_backend(self._OBJECTS)
        result = list_objects(backend)
        assert len(result) == 2

    def test_list_objects_layer_filter_passes_in_script(self):
        backend = _mock_backend([])
        list_objects(backend, layer="Artwork")
        call_args = backend.eval_json.call_args[0][0]
        assert "Artwork" in call_args

    def test_list_objects_no_doc_returns_empty(self):
        backend = _mock_backend([])
        result = list_objects(backend)
        assert result == []

    def test_get_selection_empty(self):
        backend = _mock_backend([])
        result = get_selection(backend)
        assert result == []

    def test_get_selection_single_item(self):
        sel = [{"index": 0, "name": "rect1", "type": "PathItem", "x": 0.0, "y": 100.0, "width": 200.0, "height": 100.0, "layer": "Artwork"}]
        backend = _mock_backend(sel)
        result = get_selection(backend)
        assert len(result) == 1
        assert result[0]["type"] == "PathItem"

    def test_get_selection_multiple_items(self):
        sel = [
            {"index": 0, "name": "a", "type": "PathItem", "x": 0.0, "y": 0.0, "width": 10.0, "height": 10.0, "layer": "L"},
            {"index": 1, "name": "b", "type": "TextFrame", "x": 20.0, "y": 0.0, "width": 30.0, "height": 10.0, "layer": "L"},
        ]
        backend = _mock_backend(sel)
        result = get_selection(backend)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# TestTextCore
# ---------------------------------------------------------------------------

class TestTextCore:
    _FRAMES = [
        {"index": 0, "contents": "Hello World", "x": 10.0, "y": 90.0, "width": 200.0, "height": 20.0, "layer": "Text"},
        {"index": 1, "contents": "Subtitle", "x": 10.0, "y": 60.0, "width": 150.0, "height": 15.0, "layer": "Text"},
    ]

    def test_list_text_frames_returns_list(self):
        backend = _mock_backend(self._FRAMES)
        result = list_text_frames(backend)
        assert len(result) == 2
        assert result[0]["contents"] == "Hello World"

    def test_list_text_frames_empty(self):
        backend = _mock_backend([])
        result = list_text_frames(backend)
        assert result == []

    def test_set_text_content_builds_script(self):
        backend = _mock_backend({"ok": True, "index": 0, "contents": "New Text"})
        result = set_text_content(0, "New Text", backend)
        assert result["ok"] is True
        call_args = backend.eval_json.call_args[0][0]
        assert "New Text" in call_args

    def test_set_text_content_negative_index_raises(self):
        backend = _mock_backend({})
        with pytest.raises(ValueError, match="must be >= 0"):
            set_text_content(-1, "text", backend)

    def test_set_text_content_escapes_double_quotes(self):
        backend = _mock_backend({"ok": True, "index": 0, "contents": 'Say "hello"'})
        set_text_content(0, 'Say "hello"', backend)
        call_args = backend.eval_json.call_args[0][0]
        assert '\\"' in call_args


# ---------------------------------------------------------------------------
# TestSwatchCore
# ---------------------------------------------------------------------------

class TestSwatchCore:
    _SWATCHES = [
        {"name": "[None]", "spot": False, "color_type": "GrayColor", "gray": 0},
        {"name": "[Registration]", "spot": False, "color_type": "CMYKColor", "c": 100, "m": 100, "y": 100, "k": 100},
        {"name": "Pantone 485 C", "spot": True, "color_type": "SpotColor", "tint": 100},
        {"name": "Logo Blue", "spot": False, "color_type": "CMYKColor", "c": 90, "m": 45, "y": 0, "k": 0},
    ]

    def test_list_swatches_returns_list(self):
        backend = _mock_backend(self._SWATCHES)
        result = list_swatches(backend)
        # [None] and [Registration] excluded by default
        assert len(result) == 2

    def test_list_swatches_skips_none_swatch(self):
        backend = _mock_backend(self._SWATCHES)
        result = list_swatches(backend)
        names = [s["name"] for s in result]
        assert "[None]" not in names

    def test_list_swatches_includes_spot_colors(self):
        backend = _mock_backend(self._SWATCHES)
        result = list_swatches(backend)
        spot = [s for s in result if s.get("spot")]
        assert len(spot) == 1
        assert spot[0]["name"] == "Pantone 485 C"
