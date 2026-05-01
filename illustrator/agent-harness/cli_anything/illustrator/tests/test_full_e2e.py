"""E2E tests for cli-anything-illustrator.

Requires Adobe Illustrator 2026 running with a document open.
All tests skip cleanly when Illustrator is unreachable.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cli_anything.illustrator.utils import ai_backend as _backend


def _bridge_reachable() -> bool:
    return _backend.reachable()


_SKIP_NO_BRIDGE = pytest.mark.skipif(
    not _bridge_reachable(),
    reason="Illustrator not running — skipping E2E tests",
)


def _resolve_cli(name: str) -> list[str]:
    """Find installed CLI or fall back to python -m for dev."""
    import shutil
    force = os.environ.get("CLI_ANYTHING_FORCE_INSTALLED", "").strip() == "1"
    path = shutil.which(name)
    if path:
        print(f"[_resolve_cli] Using installed command: {path}")
        return [path]
    if force:
        raise RuntimeError(f"{name} not found in PATH. Install with: pip install -e .")
    module = "cli_anything.illustrator.illustrator_cli"
    print(f"[_resolve_cli] Falling back to: {sys.executable} -m {module}")
    return [sys.executable, "-m", module]


# ---------------------------------------------------------------------------
# TestBridgeE2E
# ---------------------------------------------------------------------------

@_SKIP_NO_BRIDGE
class TestBridgeE2E:
    def test_ping_returns_ok(self):
        result = _backend.ping()
        assert result["ok"] is True

    def test_ping_has_app_version(self):
        result = _backend.ping()
        assert "app_version" in result
        assert len(result["app_version"]) > 0

    def test_ping_version_starts_with_30(self):
        result = _backend.ping()
        assert result["app_version"].startswith("30"), (
            f"Expected Illustrator 2026 (version 30.x), got {result['app_version']}"
        )


# ---------------------------------------------------------------------------
# TestDocumentE2E
# ---------------------------------------------------------------------------

@_SKIP_NO_BRIDGE
class TestDocumentE2E:
    def test_get_document_info_live(self):
        from cli_anything.illustrator.core.document import get_document_info
        info = get_document_info(_backend)
        assert "name" in info
        assert info["width"] > 0
        assert info["height"] > 0

    def test_list_documents_live(self):
        from cli_anything.illustrator.core.document import list_documents
        docs = list_documents(_backend)
        assert len(docs) >= 1

    def test_document_name_is_string(self):
        from cli_anything.illustrator.core.document import get_document_info
        info = get_document_info(_backend)
        assert isinstance(info["name"], str)
        assert len(info["name"]) > 0

    def test_document_color_space_valid(self):
        from cli_anything.illustrator.core.document import get_document_info
        info = get_document_info(_backend)
        assert info["color_space"] in ("CMYK", "RGB")


# ---------------------------------------------------------------------------
# TestLayerE2E
# ---------------------------------------------------------------------------

@_SKIP_NO_BRIDGE
class TestLayerE2E:
    def test_list_layers_live(self):
        from cli_anything.illustrator.core.layer import list_layers
        layers = list_layers(_backend)
        assert len(layers) >= 1

    def test_layer_has_required_fields(self):
        from cli_anything.illustrator.core.layer import list_layers
        layers = list_layers(_backend)
        for l in layers:
            assert "name" in l
            assert "visible" in l
            assert "locked" in l

    def test_toggle_layer_visible(self):
        from cli_anything.illustrator.core.layer import list_layers, set_layer_visible
        layers = list_layers(_backend)
        assert layers, "No layers to test"
        name = layers[0]["name"]
        original = layers[0]["visible"]
        # Toggle off then on
        set_layer_visible(name, not original, _backend)
        toggled = list_layers(_backend)
        assert toggled[0]["visible"] == (not original)
        # Restore
        set_layer_visible(name, original, _backend)
        restored = list_layers(_backend)
        assert restored[0]["visible"] == original


# ---------------------------------------------------------------------------
# TestArtboardE2E
# ---------------------------------------------------------------------------

@_SKIP_NO_BRIDGE
class TestArtboardE2E:
    def test_list_artboards_live(self):
        from cli_anything.illustrator.core.artboard import list_artboards
        abs_ = list_artboards(_backend)
        assert len(abs_) >= 1
        for ab in abs_:
            assert "name" in ab
            assert "width" in ab
            assert "height" in ab
            assert "index" in ab

    def test_set_active_artboard_live(self):
        from cli_anything.illustrator.core.artboard import list_artboards, set_active_artboard
        abs_ = list_artboards(_backend)
        assert abs_
        result = set_active_artboard(0, _backend)
        assert result["ok"] is True
        assert result["index"] == 0


# ---------------------------------------------------------------------------
# TestExportE2E
# ---------------------------------------------------------------------------

@_SKIP_NO_BRIDGE
class TestExportE2E:
    def test_export_png_creates_file(self, tmp_path):
        from cli_anything.illustrator.core.export import export_png
        out = str(tmp_path / "test_export.png")
        result = export_png(out, _backend, resolution=72.0)
        assert Path(out).exists()
        assert result["file_size"] > 0
        magic = Path(out).read_bytes()[:4]
        assert magic == b"\x89PNG", f"Not a valid PNG: {magic!r}"
        print(f"\n  PNG: {out} ({result['file_size']:,} bytes)")

    def test_export_jpeg_creates_file(self, tmp_path):
        from cli_anything.illustrator.core.export import export_jpeg
        out = str(tmp_path / "test_export.jpg")
        result = export_jpeg(out, _backend, quality=7, resolution=72.0)
        assert Path(out).exists()
        assert result["file_size"] > 0
        magic = Path(out).read_bytes()[:3]
        assert magic == b"\xff\xd8\xff", f"Not a valid JPEG: {magic!r}"
        print(f"\n  JPEG: {out} ({result['file_size']:,} bytes)")

    def test_export_svg_creates_file(self, tmp_path):
        from cli_anything.illustrator.core.export import export_svg
        out = str(tmp_path / "test_export.svg")
        result = export_svg(out, _backend)
        assert Path(out).exists()
        assert result["file_size"] > 0
        content = Path(out).read_text(encoding="utf-8", errors="replace")
        assert "<svg" in content or "<?xml" in content, "Not a valid SVG file"
        print(f"\n  SVG: {out} ({result['file_size']:,} bytes)")

    def test_export_pdf_creates_file(self, tmp_path):
        from cli_anything.illustrator.core.export import export_pdf
        out = str(tmp_path / "test_export.pdf")
        result = export_pdf(out, _backend)
        assert Path(out).exists()
        assert result["file_size"] > 0
        magic = Path(out).read_bytes()[:5]
        assert magic == b"%PDF-", f"Not a valid PDF: {magic!r}"
        print(f"\n  PDF: {out} ({result['file_size']:,} bytes)")


# ---------------------------------------------------------------------------
# TestCLISubprocess
# ---------------------------------------------------------------------------

class TestCLISubprocess:
    CLI_BASE = _resolve_cli("cli-anything-illustrator")

    def _run(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            self.CLI_BASE + args,
            capture_output=True,
            text=True,
            check=check,
        )

    def test_help_exits_zero(self):
        result = self._run(["--help"])
        assert result.returncode == 0
        assert "illustrator" in result.stdout.lower() or "Usage" in result.stdout

    @_SKIP_NO_BRIDGE
    def test_ping_json(self):
        result = self._run(["--json", "ping"])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["app"] == "illustrator"
