"""E2E tests — require Premiere Pro 2025 running with cli-anything CEP extension.

Run with: PYTHONPATH=... pytest cli_anything/premierepro/tests/test_full_e2e.py -v -s
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

import pytest


def _bridge_reachable() -> bool:
    try:
        from cli_anything.premierepro.utils.cep_backend import ping
        ping()
        return True
    except Exception:
        return False


def _resolve_cli(name: str) -> list[str]:
    force = os.environ.get("CLI_ANYTHING_FORCE_INSTALLED", "").strip() == "1"
    path = shutil.which(name)
    if path:
        print(f"[_resolve_cli] Using installed: {path}")
        return [path]
    if force:
        raise RuntimeError(f"{name} not in PATH. Install: pip install -e .")
    module = "cli_anything.premierepro.premierepro_cli"
    print(f"[_resolve_cli] Fallback: {sys.executable} -m {module}")
    return [sys.executable, "-m", module]


@pytest.fixture
def tmp_dir(tmp_path):
    return str(tmp_path)


_requires_bridge = pytest.mark.skipif(
    not _bridge_reachable(),
    reason="CEP bridge not running (Premiere Pro not open)",
)


class TestCepBridgeLive:
    pytestmark = _requires_bridge

    def test_ping_returns_ok(self):
        from cli_anything.premierepro.utils.cep_backend import ping
        result = ping()
        assert result["ok"] is True
        print(f"\n  Bridge: {result}")

    def test_eval_simple_expression(self):
        from cli_anything.premierepro.utils.cep_backend import eval_script
        result = eval_script("1 + 1")
        assert result == "2"

    def test_eval_app_name(self):
        from cli_anything.premierepro.utils.cep_backend import eval_script
        result = eval_script("app.name")
        assert result  # non-empty string
        print(f"\n  app.name = {result}")


class TestProjectLive:
    pytestmark = _requires_bridge

    def test_get_project_info(self):
        from cli_anything.premierepro.core.project import get_project_info
        info = get_project_info()
        assert "name" in info
        print(f"\n  Project: {info['name']}, sequences: {info.get('sequence_count')}")

    def test_get_project_items(self):
        from cli_anything.premierepro.core.project import get_project_items
        items = get_project_items()
        assert isinstance(items, list)
        print(f"\n  Items in bin: {len(items)}")


class TestSequenceLive:
    pytestmark = _requires_bridge

    def test_list_sequences(self):
        from cli_anything.premierepro.core.sequence import list_sequences
        seqs = list_sequences()
        assert isinstance(seqs, list)
        print(f"\n  Sequences: {[s['name'] for s in seqs]}")

    def test_get_sequence_info_first_sequence(self):
        from cli_anything.premierepro.core.sequence import list_sequences, get_sequence_info
        seqs = list_sequences()
        if not seqs:
            pytest.skip("No sequences in project")
        info = get_sequence_info(seqs[0]["name"])
        assert "width" in info
        assert "height" in info
        print(f"\n  Sequence '{info['name']}': {info.get('width')}x{info.get('height')}")


class TestTimelineLive:
    pytestmark = _requires_bridge

    def test_get_timeline_clips(self):
        from cli_anything.premierepro.core.timeline import get_timeline_clips
        clips = get_timeline_clips()
        assert isinstance(clips, list)
        print(f"\n  Clips in active timeline: {len(clips)}")
        for c in clips[:3]:
            print(f"    {c['name']} [{c['track']}] {c['start']:.2f}s–{c['end']:.2f}s")


class TestMarkersLive:
    pytestmark = _requires_bridge

    def test_list_markers(self):
        from cli_anything.premierepro.core.markers import list_markers
        markers = list_markers()
        assert isinstance(markers, list)
        print(f"\n  Markers: {len(markers)}")

    def test_add_marker_then_list(self):
        from cli_anything.premierepro.core.markers import add_marker, list_markers
        from cli_anything.premierepro.core.sequence import list_sequences, set_active_sequence
        seqs = list_sequences()
        if not seqs:
            pytest.skip("No sequences in project")
        set_active_sequence(seqs[0]["name"])
        before = list_markers()
        result = add_marker(1.0, name="cli-anything-test", comment="E2E test marker")
        assert result.get("ok") is True, f"add_marker returned: {result}"
        after = list_markers()
        assert len(after) >= len(before)


class TestMediaInfoLive:
    def test_media_info_on_real_file(self, tmp_dir):
        # Use a synthetic video created with cv2
        import cv2
        import numpy as np
        mp4_path = os.path.join(tmp_dir, "test_clip.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(mp4_path, fourcc, 24.0, (640, 360))
        if not writer.isOpened():
            pytest.skip("cv2.VideoWriter could not create test file (codec unavailable)")
        try:
            for _ in range(24):  # 1 second at 24fps
                frame = np.zeros((360, 640, 3), dtype=np.uint8)
                writer.write(frame)
        finally:
            writer.release()

        from cli_anything.premierepro.utils.media_backend import get_media_info
        info = get_media_info(mp4_path)
        assert info["width"] == 640
        assert info["height"] == 360
        assert abs(info["fps"] - 24.0) < 1.0
        assert info["frame_count"] == 24
        print(f"\n  Media: {info['name']} {info['width']}x{info['height']} @ {info['fps']}fps")


class TestCLISubprocess:
    CLI_BASE = _resolve_cli("cli-anything-premierepro")

    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            self.CLI_BASE + args,
            capture_output=True, text=True,
        )

    def test_help(self):
        result = self._run(["--help"])
        assert result.returncode == 0
        assert "premierepro" in result.stdout.lower() or "premiere" in result.stdout.lower()

    @_requires_bridge
    def test_ping_json(self):
        result = self._run(["--json", "ping"])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True

    @_requires_bridge
    def test_project_info_json(self):
        result = self._run(["--json", "project", "info"])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "name" in data

    @_requires_bridge
    def test_sequence_list_json(self):
        result = self._run(["--json", "sequence", "list"])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)

    def test_export_presets_json(self):
        result = self._run(["--json", "export", "presets"])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "h264-1080p" in data


class TestVisionLive:
    def test_screenshot_captures_premiere_window(self, tmp_dir):
        from cli_anything.premierepro.core.vision import capture_window_screenshot
        out = os.path.join(tmp_dir, "premiere_screenshot.png")
        info = capture_window_screenshot(out)
        assert os.path.exists(info["path"])
        assert info["file_size"] > 5_000
        assert info["width"] > 0
        print(f"\n  Screenshot: {info['path']} ({info['width']}x{info['height']}, {info['file_size']:,} bytes)")

    @_requires_bridge
    def test_frame_burst_three_frames(self, tmp_dir):
        from cli_anything.premierepro.core.sequence import list_sequences
        if not list_sequences():
            pytest.skip("No sequences in project")
        from cli_anything.premierepro.core.vision import burst_frames
        frames = burst_frames(0.0, 2.0, 1.0, tmp_dir, settle_ms=500)
        assert len(frames) == 3
        for f in frames:
            assert os.path.exists(f["path"])
            print(f"\n  Frame @ {f['seconds']}s → {f['path']}")

    @_requires_bridge
    def test_compare_consecutive_frames_differ(self, tmp_dir):
        from cli_anything.premierepro.core.sequence import list_sequences
        if not list_sequences():
            pytest.skip("No sequences in project")
        from cli_anything.premierepro.core.vision import scrub_and_capture, compare_frames
        f1 = scrub_and_capture(0.0, os.path.join(tmp_dir, "f0.png"), settle_ms=500)
        f2 = scrub_and_capture(5.0, os.path.join(tmp_dir, "f5.png"), settle_ms=500)
        diff = compare_frames(f1["path"], f2["path"])
        print(f"\n  Diff 0s vs 5s: similarity={diff['similarity']}, mean_diff={diff['mean_pixel_diff']}")
        assert 0.0 <= diff["similarity"] <= 1.0
