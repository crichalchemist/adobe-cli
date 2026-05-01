"""Unit tests for cli-anything-premierepro core modules.
All tests use mocks — no Premiere Pro or network required.
"""
import gzip
import json
import os
import tempfile

import pytest
from unittest.mock import patch, MagicMock

from cli_anything.premierepro.utils.prproj_parser import parse_prproj
from cli_anything.premierepro.utils.media_backend import get_media_info
from cli_anything.premierepro.core.project import get_project_info, open_project
from cli_anything.premierepro.core.sequence import list_sequences, get_sequence_info


class TestCepBackend:
    def test_ping_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "version": "1.0.0"}
        with patch("cli_anything.premierepro.utils.cep_backend._sess") as mock_sess:
            mock_sess.get.return_value = mock_resp
            from cli_anything.premierepro.utils.cep_backend import ping
            result = ping()
        assert result["ok"] is True
        assert result["version"] == "1.0.0"

    def test_ping_connection_error_raises_cep_not_running(self):
        import requests as req_lib
        with patch("cli_anything.premierepro.utils.cep_backend._sess") as mock_sess:
            mock_sess.get.side_effect = req_lib.exceptions.ConnectionError
            from cli_anything.premierepro.utils.cep_backend import ping, CepNotRunningError
            with pytest.raises(CepNotRunningError):
                ping()

    def test_eval_script_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "result": "MyProject"}
        with patch("cli_anything.premierepro.utils.cep_backend._sess") as mock_sess:
            mock_sess.post.return_value = mock_resp
            from cli_anything.premierepro.utils.cep_backend import eval_script
            result = eval_script("app.project.name")
        assert result == "MyProject"

    def test_eval_script_estk_error_raises_runtime_error(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": False, "error": "ExtendScript error"}
        with patch("cli_anything.premierepro.utils.cep_backend._sess") as mock_sess:
            mock_sess.post.return_value = mock_resp
            from cli_anything.premierepro.utils.cep_backend import eval_script
            with pytest.raises(RuntimeError, match="ExtendScript error"):
                eval_script("bad_script()")

    def test_eval_script_connection_error_raises_cep_not_running(self):
        import requests as req_lib
        with patch("cli_anything.premierepro.utils.cep_backend._sess") as mock_sess:
            mock_sess.post.side_effect = req_lib.exceptions.ConnectionError
            from cli_anything.premierepro.utils.cep_backend import eval_script, CepNotRunningError
            with pytest.raises(CepNotRunningError):
                eval_script("app.project.name")

    def test_eval_json_parses_json_result(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "result": '{"name": "Test", "count": 3}'}
        with patch("cli_anything.premierepro.utils.cep_backend._sess") as mock_sess:
            mock_sess.post.return_value = mock_resp
            from cli_anything.premierepro.utils.cep_backend import eval_json
            result = eval_json("JSON.stringify({name:'Test', count:3})")
        assert result["name"] == "Test"
        assert result["count"] == 3

    def test_eval_json_non_json_result_raises(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "result": "not json at all"}
        with patch("cli_anything.premierepro.utils.cep_backend._sess") as mock_sess:
            mock_sess.post.return_value = mock_resp
            from cli_anything.premierepro.utils.cep_backend import eval_json
            with pytest.raises(RuntimeError, match="non-JSON"):
                eval_json("1+1")

    def test_session_helper_returns_session(self):
        from cli_anything.premierepro.utils.cep_backend import _session
        import requests
        sess = _session()
        assert isinstance(sess, requests.Session)


class TestPrprojParser:
    def _make_prproj(self, xml_body: str) -> str:
        """Write a minimal gzip-compressed .prproj and return its path."""
        content = f"""<?xml version="1.0" encoding="UTF-8"?>
<PremiereData Version="3">
  <Project ObjectRef="1"/>
  <Project ObjectUID="1" ClassID="{{62ad66dd-0dcd-42da-a660-6d8fbde4cf7f}}" Version="1">
    <Node Version="1">
      <Properties Version="1">
        <ProjectViewState.List Version="1"/>
      </Properties>
    </Node>
    {xml_body}
  </Project>
</PremiereData>"""
        fd, path = tempfile.mkstemp(suffix=".prproj")
        os.close(fd)
        with gzip.open(path, "wb") as f:
            f.write(content.encode("utf-8"))
        return path

    def test_parse_empty_project_returns_dict(self):
        path = self._make_prproj("")
        result = parse_prproj(path)
        assert isinstance(result, dict)
        assert "sequences" in result
        assert "media" in result

    def test_parse_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            parse_prproj("/nonexistent/path.prproj")

    def test_parse_non_gzip_raises(self):
        fd, path = tempfile.mkstemp(suffix=".prproj")
        os.close(fd)
        with open(path, "w") as f:
            f.write("not gzip")
        with pytest.raises(ValueError, match="not a valid .prproj"):
            parse_prproj(path)


class TestMediaBackend:
    def test_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            get_media_info("/nonexistent/file.mp4")

    def test_returns_dict_with_required_keys(self, tmp_path):
        p = tmp_path / "fake.mp4"
        p.write_bytes(b"\x00" * 10)
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            3: 1920.0,   # CAP_PROP_FRAME_WIDTH
            4: 1080.0,   # CAP_PROP_FRAME_HEIGHT
            5: 29.97,    # CAP_PROP_FPS
            7: 300.0,    # CAP_PROP_FRAME_COUNT
        }.get(prop, 0.0)
        with patch("cli_anything.premierepro.utils.media_backend.cv2.VideoCapture",
                   return_value=mock_cap):
            info = get_media_info(str(p))
        assert info["width"] == 1920
        assert info["height"] == 1080
        assert abs(info["fps"] - 29.97) < 0.01
        assert info["frame_count"] == 300
        assert "duration_seconds" in info
        assert "file_size" in info

    def test_non_video_falls_back_gracefully(self, tmp_path):
        p = tmp_path / "image.png"
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        with patch("cli_anything.premierepro.utils.media_backend.cv2.VideoCapture",
                   return_value=mock_cap):
            info = get_media_info(str(p))
        assert info["file_size"] > 0
        assert info.get("width") is None or info.get("width") == 0


class TestProjectCore:
    def test_get_project_info_returns_dict(self):
        with patch("cli_anything.premierepro.core.project.cep.eval_json",
                   return_value={"name": "Test", "path": "/tmp/t.prproj",
                                  "sequences": 2, "frameRate": "23976/1000"}):
            info = get_project_info()
        assert info["name"] == "Test"
        assert info["sequences"] == 2

    def test_open_project_calls_eval_script(self):
        with patch("cli_anything.premierepro.core.project.cep.eval_script") as mock_eval:
            mock_eval.return_value = "true"
            result = open_project("/tmp/test.prproj")
        assert result is True
        mock_eval.assert_called_once()
        assert "/tmp/test.prproj" in mock_eval.call_args[0][0]


class TestSequenceCore:
    def test_list_sequences_returns_list(self):
        mock_seqs = [{"name": "Seq 01", "id": "abc123", "duration": 10.0}]
        with patch("cli_anything.premierepro.core.sequence.cep.eval_json",
                   return_value=mock_seqs):
            result = list_sequences()
        assert result == mock_seqs

    def test_get_sequence_info_by_name(self):
        mock_info = {"name": "Seq 01", "id": "abc", "width": 1920, "height": 1080}
        with patch("cli_anything.premierepro.core.sequence.cep.eval_json",
                   return_value=mock_info):
            result = get_sequence_info("Seq 01")
        assert result["width"] == 1920


class TestTimelineCore:
    def test_get_clips_returns_list(self):
        mock_clips = [
            {"name": "clip1.mp4", "track": "V1", "start": 0.0, "end": 5.0, "duration": 5.0, "media_path": "/tmp/clip1.mp4"},
        ]
        with patch("cli_anything.premierepro.core.timeline.cep.eval_json",
                   return_value=mock_clips):
            from cli_anything.premierepro.core.timeline import get_timeline_clips
            result = get_timeline_clips()
        assert result == mock_clips

    def test_get_clips_by_sequence_name(self):
        with patch("cli_anything.premierepro.core.timeline.cep.eval_json",
                   return_value=[]) as mock_eval:
            from cli_anything.premierepro.core.timeline import get_timeline_clips
            result = get_timeline_clips("My Sequence")
        assert result == []
        assert "My Sequence" in mock_eval.call_args[0][0]


class TestMarkersCore:
    def test_list_markers_returns_list(self):
        mock_markers = [{"name": "cut", "time": 2.5, "comment": "", "type": "Comment", "duration": 0.0}]
        with patch("cli_anything.premierepro.core.markers.cep.eval_json",
                   return_value=mock_markers):
            from cli_anything.premierepro.core.markers import list_markers
            result = list_markers()
        assert result == mock_markers

    def test_add_marker_returns_ok(self):
        with patch("cli_anything.premierepro.core.markers.cep.eval_json",
                   return_value={"ok": True, "time": 1.0, "name": "test"}):
            from cli_anything.premierepro.core.markers import add_marker
            result = add_marker(1.0, name="test")
        assert result["ok"] is True

    def test_add_marker_invalid_time_raises(self):
        from cli_anything.premierepro.core.markers import add_marker
        with pytest.raises(ValueError, match="finite"):
            add_marker(float("inf"))

    def test_add_marker_nan_raises(self):
        from cli_anything.premierepro.core.markers import add_marker
        with pytest.raises(ValueError, match="finite"):
            add_marker(float("nan"))

    def test_add_marker_non_numeric_raises(self):
        from cli_anything.premierepro.core.markers import add_marker
        with pytest.raises(TypeError):
            add_marker("five seconds")


class TestExportCore:
    def test_list_presets_returns_list(self):
        from cli_anything.premierepro.core.export import list_presets
        presets = list_presets()
        assert isinstance(presets, list)
        assert "h264-1080p" in presets

    def test_export_unknown_preset_raises(self):
        from cli_anything.premierepro.core.export import export_sequence
        with pytest.raises(ValueError, match="Unknown preset"):
            export_sequence("/tmp/out.mp4", preset_name="nonexistent-preset")

    def test_export_sequence_queues_job(self):
        from unittest.mock import MagicMock
        mock_eval = MagicMock(return_value={"ok": True, "job_id": "job-123", "output": "/tmp/out.mp4"})
        with patch("cli_anything.premierepro.core.export.cep.eval_json", mock_eval):
            from cli_anything.premierepro.core.export import export_sequence
            result = export_sequence("/tmp/out.mp4", preset_name="h264-1080p")
        assert result["ok"] is True
        assert "job_id" in result
        script = mock_eval.call_args[0][0]
        assert "/tmp/out.mp4" in script
        assert "H.264" in script


class TestVisionCore:
    def test_capture_screenshot_returns_path(self, tmp_path):
        from unittest.mock import MagicMock
        import numpy as np
        from cli_anything.premierepro.core.vision import capture_window_screenshot

        out = str(tmp_path / "screenshot.png")

        def fake_run(cmd, **kw):
            with open(out, "wb"):
                pass
            return MagicMock(returncode=0)

        with patch("cli_anything.premierepro.core.vision.subprocess.run", side_effect=fake_run):
            with patch("cli_anything.premierepro.core.vision.cv2.imread",
                       return_value=np.zeros((1080, 1920, 3))):
                result = capture_window_screenshot(output_path=out)
        assert result["path"] == out

    def test_capture_screenshot_nonzero_rc_raises(self, tmp_path):
        from unittest.mock import MagicMock
        from cli_anything.premierepro.core.vision import capture_window_screenshot

        out = str(tmp_path / "screenshot.png")
        with patch("cli_anything.premierepro.core.vision.subprocess.run",
                   return_value=MagicMock(returncode=1)):
            with pytest.raises(RuntimeError, match="screencapture failed"):
                capture_window_screenshot(output_path=out)

    def test_burst_calls_scrub_and_capture_correct_count(self, tmp_path):
        from cli_anything.premierepro.core.vision import burst_frames

        with patch("cli_anything.premierepro.core.vision.scrub_and_capture") as mock_sac:
            mock_sac.side_effect = lambda s, output_path, settle_ms: {
                "path": output_path, "seconds": s, "file_size": 100, "width": 1920, "height": 1080
            }
            frames = burst_frames(start=0.0, end=2.0, step=1.0,
                                  output_dir=str(tmp_path), settle_ms=0)
        assert len(frames) == 3
        assert mock_sac.call_count == 3

    def test_compare_frames_identical(self, tmp_path):
        import numpy as np
        import cv2
        from cli_anything.premierepro.core.vision import compare_frames

        img = np.zeros((100, 100, 3), dtype=np.uint8)
        p1 = str(tmp_path / "a.png")
        p2 = str(tmp_path / "b.png")
        cv2.imwrite(p1, img)
        cv2.imwrite(p2, img)
        diff = compare_frames(p1, p2)
        assert diff["identical"] is True
        assert diff["mean_pixel_diff"] == 0.0

    def test_compare_frames_different(self, tmp_path):
        import numpy as np
        import cv2
        from cli_anything.premierepro.core.vision import compare_frames

        img_a = np.zeros((100, 100, 3), dtype=np.uint8)
        img_b = np.full((100, 100, 3), 128, dtype=np.uint8)
        p1 = str(tmp_path / "a.png")
        p2 = str(tmp_path / "b.png")
        cv2.imwrite(p1, img_a)
        cv2.imwrite(p2, img_b)
        diff = compare_frames(p1, p2)
        assert diff["identical"] is False
        assert diff["mean_pixel_diff"] > 0
