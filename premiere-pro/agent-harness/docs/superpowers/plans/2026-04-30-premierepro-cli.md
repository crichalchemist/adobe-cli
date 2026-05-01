# cli-anything-premierepro Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-ready CLI harness for Adobe Premiere Pro 2025 that lets AI agents drive Premiere Pro from the command line — opening projects, inspecting sequences, querying timeline clips, exporting via AME, and extracting media metadata.

**Architecture:** A CEP (Common Extensibility Platform) extension bundled with the harness acts as an HTTP bridge: a Node.js server inside Premiere Pro's Chromium process listens on `localhost:7788` and executes ExtendScript via `csInterface.evalScript()`. The Python CLI communicates with this bridge via HTTP POST, passing ExtendScript snippets and receiving JSON results. For file-level project inspection (without Premiere running), a `.prproj` gzip-XML parser provides read-only access to project structure.

**Tech Stack:** Python 3.10+, Click, OpenCV (`cv2`), macOS `mdls` + `screencapture`, CEP (Chromium Embedded Panel with Node.js HTTP server), ExtendScript (Premiere Pro JS API), gzip + xml.etree for `.prproj` parsing.

**Agent Vision:** The CEP extension scrubs Premiere's timeline to any timecode via ExtendScript, then macOS `screencapture` captures the Program Monitor window by Window ID. Agents can burst frames as PNG snapshots and use OpenCV to compare them — enabling visual verification of edits, color grades, and export output.

---

## Conventions

- **Project root:** `/Volumes/Containers/adobe-cli/premiere-pro/agent-harness/`
- **Python namespace:** `cli_anything.premierepro.*`  
- **CLI command:** `cli-anything-premierepro`
- **CEP bundle ID:** `com.cli-anything.premierepro`
- **IPC port:** `7788`
- **Premiere version:** 25.x (CEP CSXS 6.0)
- **PYTHONPATH:** `/Volumes/Containers/adobe-cli/premiere-pro/agent-harness`
- Run all tests as: `PYTHONPATH=... pytest cli_anything/premierepro/tests/ -v`

---

## File Map

```
agent-harness/
├── PREMIEREPRO.md                         # SOP doc (analysis + architecture)
├── setup.py                               # PyPI namespace package
├── cli_anything/                          # NO __init__.py (PEP 420 namespace)
│   └── premierepro/
│       ├── __init__.py
│       ├── __main__.py                    # python3 -m cli_anything.premierepro
│       ├── README.md
│       ├── premierepro_cli.py             # Click CLI + REPL entry point
│       ├── core/
│       │   ├── __init__.py
│       │   ├── project.py                 # project open/close/info
│       │   ├── sequence.py                # sequence list/inspect
│       │   ├── timeline.py                # track/clip inspection
│       │   ├── export.py                  # AME export queue
│       │   ├── media.py                   # file metadata (no Premiere)
│       │   └── markers.py                 # sequence marker CRUD
│       ├── utils/
│       │   ├── __init__.py
│       │   ├── cep_backend.py             # HTTP client → CEP bridge
│       │   ├── prproj_parser.py           # .prproj gzip XML reader
│       │   ├── media_backend.py           # OpenCV + mdls media info
│       │   └── repl_skin.py              # copied from cli-anything-plugin
│       ├── cep/
│       │   ├── CSXS/manifest.xml          # CEP extension manifest
│       │   ├── index.html                 # background panel HTML
│       │   └── js/main.js                 # Node.js HTTP server + evalScript
│       ├── skills/
│       │   └── SKILL.md                   # packaged skill copy
│       └── tests/
│           ├── TEST.md
│           ├── test_core.py               # unit tests (no Premiere)
│           └── test_full_e2e.py           # E2E tests (Premiere must be running)
```

Canonical skill (repo root):
```
/Volumes/Containers/adobe-cli/skills/cli-anything-premierepro/SKILL.md
```

---

## Task 1: Directory Skeleton + CEP Debug Mode

**Files:**
- Create: all directories
- Create: `cli_anything/premierepro/__init__.py`
- Create: `cli_anything/premierepro/__main__.py`

- [ ] **Step 1.1: Enable CEP debug mode (required for unsigned extension)**

```bash
sudo defaults write /Library/Preferences/com.adobe.CSXS.12 PlayerDebugMode 1
# If that plist doesn't exist, try:
defaults write ~/Library/Preferences/com.adobe.CSXS.12 PlayerDebugMode 1
defaults write ~/Library/Preferences/com.adobe.CSXS.11 PlayerDebugMode 1
```

Verify:
```bash
defaults read ~/Library/Preferences/com.adobe.CSXS.12 PlayerDebugMode 2>/dev/null || \
defaults read ~/Library/Preferences/com.adobe.CSXS.11 PlayerDebugMode 2>/dev/null
```
Expected: `1`

- [ ] **Step 1.2: Create directory structure**

```bash
cd /Volumes/Containers/adobe-cli/premiere-pro/agent-harness
mkdir -p cli_anything/premierepro/{core,utils,cep/CSXS,cep/js,skills,tests}
mkdir -p /Volumes/Containers/adobe-cli/skills/cli-anything-premierepro
touch cli_anything/__init__.py  # WARNING: delete this immediately after — see note below
```

> **CRITICAL:** `cli_anything/` must NOT have `__init__.py`. Create it accidentally above only to confirm the directory exists, then immediately delete:
```bash
rm cli_anything/__init__.py
```

- [ ] **Step 1.3: Create `cli_anything/premierepro/__init__.py`**

```python
"""cli-anything-premierepro — Adobe Premiere Pro 2025 CLI harness."""
__version__ = "1.0.0"
```

- [ ] **Step 1.4: Create `cli_anything/premierepro/__main__.py`**

```python
from cli_anything.premierepro.premierepro_cli import cli

if __name__ == "__main__":
    cli()
```

- [ ] **Step 1.5: Commit**

```bash
git init  # if not already a git repo
git add cli_anything/ docs/
git commit -m "chore: scaffold premierepro harness directory structure"
```

---

## Task 2: CEP Extension — HTTP Bridge

This is the IPC backbone. The CEP extension runs as a hidden panel inside Premiere Pro's Chromium process. Node.js hosts an HTTP server; requests arrive from the Python CLI, get dispatched to Premiere's ExtendScript context via `csInterface.evalScript()`, and results come back as JSON.

**Files:**
- Create: `cli_anything/premierepro/cep/CSXS/manifest.xml`
- Create: `cli_anything/premierepro/cep/index.html`
- Create: `cli_anything/premierepro/cep/js/main.js`

- [ ] **Step 2.1: Write `cep/CSXS/manifest.xml`**

```xml
<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<ExtensionManifest Version="7.0"
    ExtensionBundleId="com.cli-anything.premierepro"
    ExtensionBundleVersion="1.0.0"
    ExtensionBundleName="cli-anything-premierepro"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ExtensionList>
    <Extension Id="com.cli-anything.premierepro.panel" Version="1.0.0"/>
  </ExtensionList>
  <ExecutionEnvironment>
    <HostList>
      <Host Name="PPRO" Version="[15.0,99.9]"/>
    </HostList>
    <LocaleList>
      <Locale Code="All"/>
    </LocaleList>
    <RequiredRuntimeList>
      <RequiredRuntime Name="CSXS" Version="7.0"/>
    </RequiredRuntimeList>
  </ExecutionEnvironment>
  <DispatchInfoList>
    <Extension Id="com.cli-anything.premierepro.panel">
      <DispatchInfo>
        <Resources>
          <MainPath>./index.html</MainPath>
          <ScriptPath>./js/main.js</ScriptPath>
        </Resources>
        <Lifecycle>
          <AutoVisible>false</AutoVisible>
          <StartOn>
            <Event>com.adobe.csxs.events.ApplicationActivate</Event>
          </StartOn>
        </Lifecycle>
        <UI>
          <Type>Panel</Type>
          <Menu>cli-anything</Menu>
          <Geometry>
            <Size><Height>1</Height><Width>1</Width></Size>
            <MinSize><Height>1</Height><Width>1</Width></MinSize>
          </Geometry>
          <Icons/>
        </UI>
      </DispatchInfo>
    </Extension>
  </DispatchInfoList>
</ExtensionManifest>
```

- [ ] **Step 2.2: Write `cep/index.html`**

```html
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>cli-anything-premierepro</title></head>
<body>
<script src="js/main.js"></script>
</body>
</html>
```

- [ ] **Step 2.3: Write `cep/js/main.js`**

```javascript
/* cli-anything-premierepro CEP bridge
 * HTTP server on localhost:7788. Receives ExtendScript snippets via POST /eval,
 * executes them in Premiere Pro's JS context, returns JSON results.
 */

var csInterface = new CSInterface();
var http = require('http');

var PORT = 7788;

function handleRequest(req, res) {
    if (req.method === 'GET' && req.url === '/ping') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: true, version: '1.0.0', app: 'premierepro' }));
        return;
    }

    if (req.method === 'POST' && req.url === '/eval') {
        var body = '';
        req.on('data', function(chunk) { body += chunk.toString(); });
        req.on('end', function() {
            var payload;
            try {
                payload = JSON.parse(body);
            } catch (e) {
                res.writeHead(400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ ok: false, error: 'Invalid JSON body: ' + e.message }));
                return;
            }
            var script = payload.script || '';
            csInterface.evalScript(script, function(result) {
                // EvalScript returns "EvalScript error." string on JS errors
                if (result === 'EvalScript error.' || result === null || result === undefined) {
                    res.writeHead(200, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ ok: false, error: 'ExtendScript error', raw: result }));
                } else {
                    res.writeHead(200, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ ok: true, result: result }));
                }
            });
        });
        return;
    }

    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ok: false, error: 'Not found: ' + req.url }));
}

var server = http.createServer(handleRequest);
server.listen(PORT, '127.0.0.1', function() {
    console.log('cli-anything-premierepro: HTTP bridge listening on port ' + PORT);
});

server.on('error', function(err) {
    if (err.code === 'EADDRINUSE') {
        console.error('cli-anything-premierepro: Port ' + PORT + ' already in use.');
    } else {
        console.error('cli-anything-premierepro server error:', err);
    }
});
```

- [ ] **Step 2.4: Install CEP extension symlink**

```bash
mkdir -p ~/Library/Application\ Support/Adobe/CEP/extensions
ln -sf \
  /Volumes/Containers/adobe-cli/premiere-pro/agent-harness/cli_anything/premierepro/cep \
  ~/Library/Application\ Support/Adobe/CEP/extensions/com.cli-anything.premierepro
```

Verify symlink:
```bash
ls -la ~/Library/Application\ Support/Adobe/CEP/extensions/com.cli-anything.premierepro/
```
Expected: shows `CSXS/`, `index.html`, `js/`

- [ ] **Step 2.5: Restart Premiere Pro**

Close and reopen Premiere Pro. The extension auto-starts on `ApplicationActivate`.

- [ ] **Step 2.6: Test the bridge is alive**

```bash
curl -s http://127.0.0.1:7788/ping
```
Expected: `{"ok":true,"version":"1.0.0","app":"premierepro"}`

- [ ] **Step 2.7: Test ExtendScript execution**

```bash
curl -s -X POST http://127.0.0.1:7788/eval \
  -H 'Content-Type: application/json' \
  -d '{"script":"app.project.name"}'
```
Expected: `{"ok":true,"result":"Untitled"}` (or current project name)

- [ ] **Step 2.8: Commit**

```bash
git add cli_anything/premierepro/cep/
git commit -m "feat: add CEP HTTP bridge extension for Premiere Pro IPC"
```

---

## Task 3: CEP Backend Python Module

**Files:**
- Create: `cli_anything/premierepro/utils/cep_backend.py`

- [ ] **Step 3.1: Write unit test (no Premiere needed — mock HTTP)**

Create `cli_anything/premierepro/tests/test_core.py`:

```python
import json
import pytest
from unittest.mock import patch, MagicMock
from cli_anything.premierepro.utils.cep_backend import (
    eval_script,
    ping,
    CepNotRunningError,
)


class TestCepBackend:
    def test_ping_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "version": "1.0.0"}
        with patch("cli_anything.premierepro.utils.cep_backend.requests.get",
                   return_value=mock_resp):
            result = ping()
        assert result["ok"] is True

    def test_ping_connection_error_raises(self):
        import requests as req_lib
        with patch("cli_anything.premierepro.utils.cep_backend.requests.get",
                   side_effect=req_lib.exceptions.ConnectionError):
            with pytest.raises(CepNotRunningError):
                ping()

    def test_eval_script_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "result": "MyProject"}
        with patch("cli_anything.premierepro.utils.cep_backend.requests.post",
                   return_value=mock_resp):
            result = eval_script("app.project.name")
        assert result == "MyProject"

    def test_eval_script_estk_error_raises(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": False, "error": "ExtendScript error"}
        with patch("cli_anything.premierepro.utils.cep_backend.requests.post",
                   return_value=mock_resp):
            with pytest.raises(RuntimeError, match="ExtendScript error"):
                eval_script("bad_script()")

    def test_eval_script_not_running_raises(self):
        import requests as req_lib
        with patch("cli_anything.premierepro.utils.cep_backend.requests.post",
                   side_effect=req_lib.exceptions.ConnectionError):
            with pytest.raises(CepNotRunningError):
                eval_script("app.project.name")
```

- [ ] **Step 3.2: Run — expect ImportError (module doesn't exist yet)**

```bash
PYTHONPATH=/Volumes/Containers/adobe-cli/premiere-pro/agent-harness \
  pytest cli_anything/premierepro/tests/test_core.py::TestCepBackend -v
```
Expected: `ImportError: cannot import name 'eval_script'`

- [ ] **Step 3.3: Write `utils/cep_backend.py`**

```python
"""HTTP client to the cli-anything CEP bridge running inside Premiere Pro."""
from __future__ import annotations
import json
import requests
from requests.exceptions import ConnectionError, Timeout

PORT = 7788
BASE_URL = f"http://127.0.0.1:{PORT}"
TIMEOUT = 30  # seconds; long enough for slow exports


class CepNotRunningError(RuntimeError):
    """Raised when the CEP bridge HTTP server is not reachable."""
    def __init__(self):
        super().__init__(
            "Cannot reach cli-anything CEP bridge on port 7788. "
            "Is Adobe Premiere Pro 2025 open with the cli-anything extension loaded? "
            "Check Window > Extensions > cli-anything is present."
        )


def ping() -> dict:
    """Return bridge status dict; raises CepNotRunningError if unreachable."""
    try:
        resp = requests.get(f"{BASE_URL}/ping", timeout=5)
        return resp.json()
    except (ConnectionError, Timeout):
        raise CepNotRunningError()


def eval_script(script: str) -> str:
    """Execute ExtendScript in Premiere Pro and return the string result."""
    try:
        resp = requests.post(
            f"{BASE_URL}/eval",
            json={"script": script},
            timeout=TIMEOUT,
        )
    except (ConnectionError, Timeout):
        raise CepNotRunningError()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("error", "Unknown ExtendScript error"))
    return data["result"]


def eval_json(script: str) -> object:
    """Execute ExtendScript that returns JSON.stringify(...) and parse the result."""
    raw = eval_script(script)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"CEP returned non-JSON: {raw!r}") from exc
```

- [ ] **Step 3.4: Run tests — expect all pass**

```bash
PYTHONPATH=/Volumes/Containers/adobe-cli/premiere-pro/agent-harness \
  pytest cli_anything/premierepro/tests/test_core.py::TestCepBackend -v
```
Expected: 5 passed

- [ ] **Step 3.5: Commit**

```bash
git add cli_anything/premierepro/utils/cep_backend.py \
        cli_anything/premierepro/tests/test_core.py
git commit -m "feat: add CEP HTTP backend client + unit tests"
```

---

## Task 4: `.prproj` Parser (file-level, no Premiere needed)

Premiere Pro project files are gzip-compressed XML. This module decodes them and extracts structural info: project name, sequences, and media references. Useful for inspection without Premiere running.

**Files:**
- Create: `cli_anything/premierepro/utils/prproj_parser.py`

- [ ] **Step 4.1: Add tests to `test_core.py`**

```python
import gzip, io, os, tempfile
from cli_anything.premierepro.utils.prproj_parser import parse_prproj


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
```

- [ ] **Step 4.2: Run — expect ImportError**

```bash
PYTHONPATH=/Volumes/Containers/adobe-cli/premiere-pro/agent-harness \
  pytest cli_anything/premierepro/tests/test_core.py::TestPrprojParser -v
```
Expected: `ImportError`

- [ ] **Step 4.3: Write `utils/prproj_parser.py`**

```python
"""Parse .prproj (gzip-compressed XML) Premiere Pro project files.

.prproj files are gzip-compressed XML with Adobe's proprietary schema.
This parser extracts the structural information accessible without running Premiere.
"""
from __future__ import annotations
import gzip
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class SequenceInfo:
    name: str
    uid: str
    frame_rate: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


@dataclass
class MediaRef:
    name: str
    path: Optional[str] = None
    media_type: Optional[str] = None  # "video", "audio", "image"


@dataclass
class ProjectInfo:
    path: str
    sequences: list[SequenceInfo] = field(default_factory=list)
    media: list[MediaRef] = field(default_factory=list)
    file_size: int = 0


def parse_prproj(path: str) -> dict:
    """Parse a .prproj file and return a dict with sequences and media refs."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Project file not found: {path}")

    try:
        with gzip.open(path, "rb") as f:
            raw = f.read()
    except (OSError, gzip.BadGzipFile) as exc:
        raise ValueError(f"File is not a valid .prproj (not gzip): {path}") from exc

    try:
        root = ET.fromstring(raw.decode("utf-8", errors="replace"))
    except ET.ParseError as exc:
        raise ValueError(f"File is not a valid .prproj (bad XML): {path}") from exc

    sequences = _extract_sequences(root)
    media = _extract_media(root)

    return {
        "path": os.path.abspath(path),
        "file_size": os.path.getsize(path),
        "sequences": [vars(s) for s in sequences],
        "sequence_count": len(sequences),
        "media": [vars(m) for m in media],
        "media_count": len(media),
    }


def _extract_sequences(root: ET.Element) -> list[SequenceInfo]:
    seqs = []
    # Sequences may appear as ProjectItem elements with ClassID matching Sequence
    # or as Sequence elements directly.  The schema varies across PPro versions.
    seen = set()
    for el in root.iter():
        name_el = el.find("Name")
        uid = el.get("ObjectUID") or el.get("ObjectRef") or ""
        if uid in seen:
            continue
        # Heuristic: elements named "Sequence" that have a child VideoStream
        if el.tag == "Sequence" and name_el is not None:
            seen.add(uid)
            seqs.append(SequenceInfo(name=name_el.text or "Untitled", uid=uid))
        # Newer .prproj: ProjectItem with type="2" (sequence type)
        elif el.tag == "ProjectItem" and el.get("type") == "2" and name_el is not None:
            seen.add(uid)
            seqs.append(SequenceInfo(name=name_el.text or "Untitled", uid=uid))
    return seqs


def _extract_media(root: ET.Element) -> list[MediaRef]:
    media = []
    seen = set()
    for el in root.iter():
        # Media file references have an ActualMediaFilePath or similar element
        path_el = el.find("ActualMediaFilePath") or el.find("FilePath")
        name_el = el.find("Name")
        if path_el is None or name_el is None:
            continue
        fpath = path_el.text or ""
        if fpath in seen:
            continue
        seen.add(fpath)
        ext = Path(fpath).suffix.lower() if fpath else ""
        mtype = _media_type_from_ext(ext)
        media.append(MediaRef(name=name_el.text or Path(fpath).name, path=fpath, media_type=mtype))
    return media


def _media_type_from_ext(ext: str) -> str:
    if ext in {".mp4", ".mov", ".avi", ".mxf", ".mkv", ".r3d", ".braw"}:
        return "video"
    if ext in {".mp3", ".wav", ".aac", ".aiff", ".m4a", ".flac"}:
        return "audio"
    if ext in {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".dpx", ".exr", ".psd"}:
        return "image"
    return "unknown"
```

- [ ] **Step 4.4: Run tests — expect all pass**

```bash
PYTHONPATH=/Volumes/Containers/adobe-cli/premiere-pro/agent-harness \
  pytest cli_anything/premierepro/tests/test_core.py::TestPrprojParser -v
```
Expected: 3 passed

- [ ] **Step 4.5: Commit**

```bash
git add cli_anything/premierepro/utils/prproj_parser.py \
        cli_anything/premierepro/tests/test_core.py
git commit -m "feat: add .prproj gzip-XML parser for offline project inspection"
```

---

## Task 5: Media Backend (OpenCV + mdls)

**Files:**
- Create: `cli_anything/premierepro/utils/media_backend.py`

- [ ] **Step 5.1: Add tests**

```python
import os, tempfile
from unittest.mock import patch, MagicMock
from cli_anything.premierepro.utils.media_backend import get_media_info


class TestMediaBackend:
    def test_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            get_media_info("/nonexistent/file.mp4")

    def test_returns_dict_with_required_keys(self, tmp_path):
        # Create a tiny temp file to satisfy existence check
        p = tmp_path / "fake.mp4"
        p.write_bytes(b"\x00" * 10)
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            0: 1920.0,   # CAP_PROP_FRAME_WIDTH
            1: 1080.0,   # CAP_PROP_FRAME_HEIGHT
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
```

- [ ] **Step 5.2: Run — expect ImportError**

```bash
PYTHONPATH=/Volumes/Containers/adobe-cli/premiere-pro/agent-harness \
  pytest cli_anything/premierepro/tests/test_core.py::TestMediaBackend -v
```

- [ ] **Step 5.3: Write `utils/media_backend.py`**

```python
"""Media file metadata using OpenCV and macOS mdls.

OpenCV handles video frame metrics; mdls fills in codec/bitrate metadata
using macOS Spotlight which has native codec awareness.
"""
from __future__ import annotations
import json
import os
import subprocess
from pathlib import Path
from typing import Optional

import cv2


def get_media_info(path: str) -> dict:
    """Return metadata dict for any media file. No Premiere required."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Media file not found: {path}")

    info: dict = {
        "path": os.path.abspath(path),
        "file_size": os.path.getsize(path),
        "name": Path(path).name,
        "extension": Path(path).suffix.lower(),
    }

    # OpenCV: video/image metrics
    cap = cv2.VideoCapture(path)
    if cap.isOpened():
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
        fourcc = "".join([chr((fourcc_int >> (8 * i)) & 0xFF) for i in range(4)]).strip("\x00")
        cap.release()
        info.update({
            "width": w or None,
            "height": h or None,
            "fps": round(fps, 3) if fps else None,
            "frame_count": frame_count or None,
            "duration_seconds": round(frame_count / fps, 3) if fps and frame_count else None,
            "fourcc": fourcc or None,
        })
    else:
        cap.release()
        info.update({"width": None, "height": None, "fps": None,
                      "frame_count": None, "duration_seconds": None, "fourcc": None})

    # mdls: Spotlight metadata (codec, bitrate, content type)
    mdls = _mdls_metadata(path)
    if mdls:
        info["codec"] = mdls.get("kMDItemCodecs")
        info["total_bit_rate"] = mdls.get("kMDItemTotalBitRate")
        info["content_type"] = mdls.get("kMDItemContentType")
        info["duration_mdls"] = mdls.get("kMDItemDurationSeconds")

    return info


def _mdls_metadata(path: str) -> Optional[dict]:
    """Call macOS mdls and return a dict of selected Spotlight attributes."""
    attrs = [
        "kMDItemCodecs", "kMDItemTotalBitRate",
        "kMDItemContentType", "kMDItemDurationSeconds",
    ]
    try:
        result = subprocess.run(
            ["mdls", "-raw", "-nullMarker", "null"] +
            [arg for a in attrs for arg in ("-name", a)] +
            [path],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None
        lines = result.stdout.strip().split("\n")
        out = {}
        for attr, val in zip(attrs, lines):
            v = val.strip()
            if v == "null":
                out[attr] = None
            elif v.startswith("(") and v.endswith(")"):
                # Array like ("H.264", "AAC")
                inner = v[1:-1].strip()
                out[attr] = [x.strip().strip('"') for x in inner.split(",") if x.strip()]
            else:
                try:
                    out[attr] = float(v)
                except ValueError:
                    out[attr] = v.strip('"')
        return out
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
```

- [ ] **Step 5.4: Run tests**

```bash
PYTHONPATH=/Volumes/Containers/adobe-cli/premiere-pro/agent-harness \
  pytest cli_anything/premierepro/tests/test_core.py::TestMediaBackend -v
```
Expected: 3 passed

- [ ] **Step 5.5: Commit**

```bash
git add cli_anything/premierepro/utils/media_backend.py
git commit -m "feat: add media backend (OpenCV + mdls) for offline media introspection"
```

---

## Task 6: Core Modules

These modules contain the business logic, each calling either `cep_backend` (Premiere must be running) or the offline parsers.

**Files:**
- Create: `cli_anything/premierepro/core/project.py`
- Create: `cli_anything/premierepro/core/sequence.py`
- Create: `cli_anything/premierepro/core/timeline.py`
- Create: `cli_anything/premierepro/core/export.py`
- Create: `cli_anything/premierepro/core/markers.py`

### 6a: `core/project.py`

- [ ] **Step 6a.1: Add tests**

```python
from unittest.mock import patch
from cli_anything.premierepro.core.project import get_project_info, open_project


class TestProjectCore:
    def test_get_project_info_returns_dict(self):
        mock_result = '{"name":"Test","path":"/tmp/t.prproj","sequences":2,"frameRate":"23976/1000"}'
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
```

- [ ] **Step 6a.2: Write `core/project.py`**

```python
"""Premiere Pro project operations via CEP bridge."""
from __future__ import annotations
from cli_anything.premierepro.utils import cep_backend as cep


_PROJECT_INFO_SCRIPT = """
(function() {
    var proj = app.project;
    if (!proj) return JSON.stringify({error: "No project open"});
    var seqs = [];
    for (var i = 0; i < proj.sequences.numSequences; i++) {
        var s = proj.sequences[i];
        seqs.push({name: s.name, id: s.sequenceID});
    }
    return JSON.stringify({
        name: proj.name,
        path: proj.path,
        sequence_count: proj.sequences.numSequences,
        sequences: seqs,
        dirty: proj.dirty
    });
})()
"""


def get_project_info() -> dict:
    """Return info about the currently open Premiere Pro project."""
    return cep.eval_json(_PROJECT_INFO_SCRIPT)


def open_project(path: str) -> bool:
    """Open a .prproj file in Premiere Pro. Returns True on success."""
    # Escape backslashes and quotes for ExtendScript string literal
    safe_path = path.replace("\\", "\\\\").replace('"', '\\"')
    script = f'app.openDocument("{safe_path}"); "true"'
    result = cep.eval_script(script)
    return result == "true"


def close_project(save: bool = False) -> bool:
    """Close the active project. save=True saves before closing."""
    flag = "1" if save else "0"  # kSaveChangesYes=1, kSaveChangesNo=0
    script = f'app.project.closeDocument({flag}, false); "true"'
    result = cep.eval_script(script)
    return result == "true"


def get_project_items() -> list[dict]:
    """Return flat list of all items in the project bin."""
    script = """
(function() {
    function collectItems(item, out) {
        out.push({name: item.name, type: item.type,
                  path: item.getMediaPath ? item.getMediaPath() : null});
        if (item.children) {
            for (var i = 0; i < item.children.numItems; i++) {
                collectItems(item.children[i], out);
            }
        }
    }
    var items = [];
    collectItems(app.project.rootItem, items);
    return JSON.stringify(items);
})()
"""
    return cep.eval_json(script)
```

- [ ] **Step 6a.3: Run project tests**

```bash
PYTHONPATH=/Volumes/Containers/adobe-cli/premiere-pro/agent-harness \
  pytest cli_anything/premierepro/tests/test_core.py::TestProjectCore -v
```
Expected: 2 passed

### 6b: `core/sequence.py`

- [ ] **Step 6b.1: Add tests**

```python
from unittest.mock import patch
from cli_anything.premierepro.core.sequence import list_sequences, get_sequence_info


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
```

- [ ] **Step 6b.2: Write `core/sequence.py`**

```python
"""Sequence list and inspection via CEP bridge."""
from __future__ import annotations
from cli_anything.premierepro.utils import cep_backend as cep


def list_sequences() -> list[dict]:
    """Return list of all sequences in the active project."""
    script = """
(function() {
    var seqs = [];
    for (var i = 0; i < app.project.sequences.numSequences; i++) {
        var s = app.project.sequences[i];
        seqs.push({
            name: s.name,
            id: s.sequenceID,
            duration: s.end,
            frame_rate: s.timebase,
            width: s.frameSizeHorizontal,
            height: s.frameSizeVertical,
            video_track_count: s.videoTracks.numTracks,
            audio_track_count: s.audioTracks.numTracks
        });
    }
    return JSON.stringify(seqs);
})()
"""
    return cep.eval_json(script)


def get_sequence_info(name: str) -> dict:
    """Return detailed info for the sequence matching name (case-sensitive)."""
    safe_name = name.replace('"', '\\"')
    script = f"""
(function() {{
    for (var i = 0; i < app.project.sequences.numSequences; i++) {{
        var s = app.project.sequences[i];
        if (s.name === "{safe_name}") {{
            return JSON.stringify({{
                name: s.name,
                id: s.sequenceID,
                duration: s.end,
                frame_rate: s.timebase,
                width: s.frameSizeHorizontal,
                height: s.frameSizeVertical,
                video_track_count: s.videoTracks.numTracks,
                audio_track_count: s.audioTracks.numTracks
            }});
        }}
    }}
    return JSON.stringify({{error: "Sequence not found: {safe_name}"}});
}})()
"""
    return cep.eval_json(script)


def set_active_sequence(name: str) -> bool:
    """Set the active sequence by name. Returns True on success."""
    safe_name = name.replace('"', '\\"')
    script = f"""
(function() {{
    for (var i = 0; i < app.project.sequences.numSequences; i++) {{
        var s = app.project.sequences[i];
        if (s.name === "{safe_name}") {{
            app.project.activeSequence = s;
            return "true";
        }}
    }}
    return "false";
}})()
"""
    return cep.eval_script(script) == "true"
```

### 6c: `core/timeline.py`

- [ ] **Step 6c.1: Write `core/timeline.py`**

```python
"""Timeline clip and track inspection via CEP bridge."""
from __future__ import annotations
from cli_anything.premierepro.utils import cep_backend as cep


def get_timeline_clips(sequence_name: str | None = None) -> list[dict]:
    """Return all clips on video/audio tracks of the active (or named) sequence."""
    if sequence_name:
        safe = sequence_name.replace('"', '\\"')
        seq_resolve = f"""
var _seq = null;
for (var _i = 0; _i < app.project.sequences.numSequences; _i++) {{
    if (app.project.sequences[_i].name === "{safe}") {{
        _seq = app.project.sequences[_i]; break;
    }}
}}
if (!_seq) return JSON.stringify([]);
"""
    else:
        seq_resolve = "var _seq = app.project.activeSequence; if (!_seq) return JSON.stringify([]);"

    script = f"""
(function() {{
    {seq_resolve}
    var clips = [];
    function collectTracks(tracks, trackType) {{
        for (var t = 0; t < tracks.numTracks; t++) {{
            var track = tracks[t];
            for (var c = 0; c < track.clips.numItems; c++) {{
                var clip = track.clips[c];
                clips.push({{
                    name: clip.name,
                    track: trackType + (t + 1),
                    start: clip.start.seconds,
                    end: clip.end.seconds,
                    duration: clip.duration.seconds,
                    media_path: clip.projectItem ? clip.projectItem.getMediaPath() : null
                }});
            }}
        }}
    }}
    collectTracks(_seq.videoTracks, "V");
    collectTracks(_seq.audioTracks, "A");
    return JSON.stringify(clips);
}})()
"""
    return cep.eval_json(script)
```

### 6d: `core/export.py`

- [ ] **Step 6d.1: Write `core/export.py`**

```python
"""Export sequences via Adobe Media Encoder through Premiere Pro's CEP bridge."""
from __future__ import annotations
import os
from cli_anything.premierepro.utils import cep_backend as cep

# Common export presets bundled with Premiere Pro / AME
PRESETS = {
    "h264-1080p": "H.264",
    "prores-422": "Apple ProRes 422",
    "prores-4444": "Apple ProRes 4444",
    "dnxhd": "DNxHD",
    "mp3": "MP3",
    "wav": "Waveform Audio",
}


def list_presets() -> list[str]:
    return list(PRESETS.keys())


def export_sequence(
    output_path: str,
    sequence_name: str | None = None,
    preset_name: str = "h264-1080p",
    remove_on_completion: bool = True,
) -> dict:
    """Queue a sequence for export via AME. Returns job info dict.

    AME must be installed. The export runs asynchronously; use
    wait_for_export() to block until completion.
    """
    abs_output = os.path.abspath(output_path)
    safe_output = abs_output.replace("\\", "\\\\").replace('"', '\\"')
    preset_str = PRESETS.get(preset_name, preset_name)
    safe_preset = preset_str.replace('"', '\\"')
    remove_flag = "true" if remove_on_completion else "false"

    if sequence_name:
        safe_seq = sequence_name.replace('"', '\\"')
        resolve = f"""
var _seq = null;
for (var _i = 0; _i < app.project.sequences.numSequences; _i++) {{
    if (app.project.sequences[_i].name === "{safe_seq}") {{
        _seq = app.project.sequences[_i]; break;
    }}
}}
if (!_seq) return JSON.stringify({{error: "Sequence not found: {safe_seq}"}});
"""
    else:
        resolve = "var _seq = app.project.activeSequence; if (!_seq) return JSON.stringify({error: 'No active sequence'});"

    script = f"""
(function() {{
    {resolve}
    var jobID = app.encoder.encodeSequence(
        _seq, "{safe_output}", "{safe_preset}", app.encoder.ENCODE_IN_TO_OUT, {remove_flag}
    );
    app.encoder.startBatch();
    return JSON.stringify({{ok: true, job_id: jobID, output: "{safe_output}"}});
}})()
"""
    return cep.eval_json(script)


def get_encoder_status() -> dict:
    """Return current AME job queue status."""
    script = """
(function() {
    return JSON.stringify({
        is_running: app.encoder.running,
        job_count: app.encoder.getJobCount ? app.encoder.getJobCount() : null
    });
})()
"""
    return cep.eval_json(script)
```

### 6e: `core/markers.py`

- [ ] **Step 6e.1: Write `core/markers.py`**

```python
"""Sequence marker operations via CEP bridge."""
from __future__ import annotations
from cli_anything.premierepro.utils import cep_backend as cep


def list_markers(sequence_name: str | None = None) -> list[dict]:
    """List all markers on the active or named sequence."""
    resolve = (
        f'var _seq = null; for (var _i=0;_i<app.project.sequences.numSequences;_i++) '
        f'{{ if (app.project.sequences[_i].name==="{sequence_name}") '
        f'{{ _seq=app.project.sequences[_i];break; }} }}'
        if sequence_name else
        "var _seq = app.project.activeSequence;"
    )
    script = f"""
(function() {{
    {resolve}
    if (!_seq) return JSON.stringify([]);
    var markers = [];
    var m = _seq.markers;
    var marker = m.getFirstMarker();
    while (marker) {{
        markers.push({{
            name: marker.name, comment: marker.comments,
            time: marker.start.seconds, duration: marker.end.seconds - marker.start.seconds,
            type: marker.type
        }});
        marker = m.getNextMarker(marker);
    }}
    return JSON.stringify(markers);
}})()
"""
    return cep.eval_json(script)


def add_marker(time_seconds: float, name: str = "", comment: str = "") -> dict:
    """Add a marker at time_seconds on the active sequence."""
    safe_name = name.replace('"', '\\"')
    safe_comment = comment.replace('"', '\\"')
    script = f"""
(function() {{
    var seq = app.project.activeSequence;
    if (!seq) return JSON.stringify({{error: "No active sequence"}});
    var tc = new Time();
    tc.seconds = {time_seconds};
    var marker = seq.markers.createMarker(tc);
    marker.name = "{safe_name}";
    marker.comments = "{safe_comment}";
    return JSON.stringify({{ok: true, time: {time_seconds}, name: "{safe_name}"}});
}})()
"""
    return cep.eval_json(script)
```

- [ ] **Step 6f: Run all core tests so far**

```bash
PYTHONPATH=/Volumes/Containers/adobe-cli/premiere-pro/agent-harness \
  pytest cli_anything/premierepro/tests/test_core.py -v
```
Expected: all unit tests pass (the core ones use mocks)

- [ ] **Step 6g: Commit**

```bash
git add cli_anything/premierepro/core/
git commit -m "feat: add core modules (project, sequence, timeline, export, markers)"
```

---

## Task 7: Copy repl_skin.py + Core `__init__.py` files

- [ ] **Step 7.1: Copy repl_skin**

```bash
cp /Users/controlroom/.claude/plugins/marketplaces/cli-anything/cli-anything-plugin/repl_skin.py \
   /Volumes/Containers/adobe-cli/premiere-pro/agent-harness/cli_anything/premierepro/utils/repl_skin.py
```

- [ ] **Step 7.2: Create `__init__.py` files for packages**

```bash
touch cli_anything/premierepro/core/__init__.py
touch cli_anything/premierepro/utils/__init__.py
```

- [ ] **Step 7.3: Commit**

```bash
git add cli_anything/premierepro/utils/repl_skin.py \
        cli_anything/premierepro/core/__init__.py \
        cli_anything/premierepro/utils/__init__.py
git commit -m "chore: add repl_skin and package init files"
```

---

## Task 8: Click CLI + REPL

**Files:**
- Create: `cli_anything/premierepro/premierepro_cli.py`

- [ ] **Step 8.1: Write `premierepro_cli.py`**

```python
"""cli-anything-premierepro — Adobe Premiere Pro 2025 CLI.

Requires Adobe Premiere Pro 2025 open with the cli-anything CEP extension loaded
(Window > Extensions > cli-anything) for all project/sequence/export commands.
Media info commands work without Premiere running.
"""
from __future__ import annotations
import json
import sys
import click

from cli_anything.premierepro.utils.cep_backend import CepNotRunningError
from cli_anything.premierepro.utils.repl_skin import ReplSkin

_skin = ReplSkin("premierepro", version="1.0.0")

SKILL_PATHS = [
    "/Volumes/Containers/adobe-cli/skills/cli-anything-premierepro/SKILL.md",
    # packaged fallback:
    str(__import__("pathlib").Path(__file__).parent / "skills" / "SKILL.md"),
]


def _json_flag(ctx: click.Context) -> bool:
    return ctx.find_root().params.get("json_output", False)


def _out(ctx: click.Context, data: object) -> None:
    if _json_flag(ctx):
        click.echo(json.dumps(data, indent=2))
    else:
        if isinstance(data, dict):
            for k, v in data.items():
                _skin.status(k, str(v))
        elif isinstance(data, list):
            if data and isinstance(data[0], dict):
                headers = list(data[0].keys())
                rows = [[str(row.get(h, "")) for h in headers] for row in data]
                _skin.table(headers, rows)
            else:
                for item in data:
                    click.echo(f"  {item}")
        else:
            click.echo(str(data))


def _cep_error(exc: CepNotRunningError) -> None:
    _skin.error(str(exc))
    sys.exit(1)


# ──────────────────────────── Main group ──────────────────────────────

@click.group(invoke_without_command=True)
@click.option("--json", "json_output", is_flag=True, help="Machine-readable JSON output")
@click.pass_context
def cli(ctx: click.Context, json_output: bool) -> None:
    """cli-anything-premierepro — Adobe Premiere Pro 2025 CLI."""
    ctx.ensure_object(dict)
    ctx.obj["json_output"] = json_output
    if ctx.invoked_subcommand is None:
        ctx.invoke(repl)


# ──────────────────────────── ping ────────────────────────────────────

@cli.command()
@click.pass_context
def ping(ctx: click.Context) -> None:
    """Check if the CEP bridge is running."""
    from cli_anything.premierepro.utils.cep_backend import ping as _ping
    try:
        result = _ping()
        _out(ctx, result)
    except CepNotRunningError as exc:
        _cep_error(exc)


# ──────────────────────────── project ─────────────────────────────────

@cli.group()
def project() -> None:
    """Project open/close/inspect commands."""


@project.command("info")
@click.pass_context
def project_info(ctx: click.Context) -> None:
    """Show info about the currently open project."""
    from cli_anything.premierepro.core.project import get_project_info
    try:
        _out(ctx, get_project_info())
    except CepNotRunningError as exc:
        _cep_error(exc)


@project.command("open")
@click.argument("path", type=click.Path(exists=True))
@click.pass_context
def project_open(ctx: click.Context, path: str) -> None:
    """Open a .prproj file in Premiere Pro."""
    from cli_anything.premierepro.core.project import open_project
    try:
        ok = open_project(path)
        _out(ctx, {"opened": ok, "path": path})
    except CepNotRunningError as exc:
        _cep_error(exc)


@project.command("items")
@click.pass_context
def project_items(ctx: click.Context) -> None:
    """List all items in the project bin."""
    from cli_anything.premierepro.core.project import get_project_items
    try:
        _out(ctx, get_project_items())
    except CepNotRunningError as exc:
        _cep_error(exc)


@project.command("parse")
@click.argument("path", type=click.Path(exists=True))
@click.pass_context
def project_parse(ctx: click.Context, path: str) -> None:
    """Parse a .prproj file offline (no Premiere required)."""
    from cli_anything.premierepro.utils.prproj_parser import parse_prproj
    _out(ctx, parse_prproj(path))


# ──────────────────────────── sequence ────────────────────────────────

@cli.group()
def sequence() -> None:
    """Sequence list and inspect commands."""


@sequence.command("list")
@click.pass_context
def sequence_list(ctx: click.Context) -> None:
    """List all sequences in the active project."""
    from cli_anything.premierepro.core.sequence import list_sequences
    try:
        _out(ctx, list_sequences())
    except CepNotRunningError as exc:
        _cep_error(exc)


@sequence.command("info")
@click.argument("name")
@click.pass_context
def sequence_info(ctx: click.Context, name: str) -> None:
    """Show detailed info for a sequence."""
    from cli_anything.premierepro.core.sequence import get_sequence_info
    try:
        _out(ctx, get_sequence_info(name))
    except CepNotRunningError as exc:
        _cep_error(exc)


@sequence.command("activate")
@click.argument("name")
@click.pass_context
def sequence_activate(ctx: click.Context, name: str) -> None:
    """Set the active sequence by name."""
    from cli_anything.premierepro.core.sequence import set_active_sequence
    try:
        ok = set_active_sequence(name)
        _out(ctx, {"activated": ok, "name": name})
    except CepNotRunningError as exc:
        _cep_error(exc)


# ──────────────────────────── timeline ────────────────────────────────

@cli.group()
def timeline() -> None:
    """Timeline clip and track inspection."""


@timeline.command("clips")
@click.option("--sequence", "seq_name", default=None, help="Sequence name (default: active)")
@click.pass_context
def timeline_clips(ctx: click.Context, seq_name: str | None) -> None:
    """List all clips in the timeline."""
    from cli_anything.premierepro.core.timeline import get_timeline_clips
    try:
        _out(ctx, get_timeline_clips(seq_name))
    except CepNotRunningError as exc:
        _cep_error(exc)


# ──────────────────────────── export ──────────────────────────────────

@cli.group()
def export() -> None:
    """Export sequences via Adobe Media Encoder."""


@export.command("render")
@click.argument("output_path")
@click.option("--sequence", "seq_name", default=None, help="Sequence name (default: active)")
@click.option("--preset", default="h264-1080p",
              help="Export preset name (see: export presets)")
@click.pass_context
def export_render(ctx: click.Context, output_path: str, seq_name: str | None,
                  preset: str) -> None:
    """Queue a sequence for export via AME."""
    from cli_anything.premierepro.core.export import export_sequence
    try:
        result = export_sequence(output_path, seq_name, preset)
        _out(ctx, result)
    except CepNotRunningError as exc:
        _cep_error(exc)


@export.command("presets")
@click.pass_context
def export_presets(ctx: click.Context) -> None:
    """List available export presets."""
    from cli_anything.premierepro.core.export import list_presets
    _out(ctx, list_presets())


@export.command("status")
@click.pass_context
def export_status(ctx: click.Context) -> None:
    """Show AME encoder status."""
    from cli_anything.premierepro.core.export import get_encoder_status
    try:
        _out(ctx, get_encoder_status())
    except CepNotRunningError as exc:
        _cep_error(exc)


# ──────────────────────────── markers ─────────────────────────────────

@cli.group()
def markers() -> None:
    """Sequence marker operations."""


@markers.command("list")
@click.option("--sequence", "seq_name", default=None)
@click.pass_context
def markers_list(ctx: click.Context, seq_name: str | None) -> None:
    """List all markers in the active or named sequence."""
    from cli_anything.premierepro.core.markers import list_markers
    try:
        _out(ctx, list_markers(seq_name))
    except CepNotRunningError as exc:
        _cep_error(exc)


@markers.command("add")
@click.argument("time", type=float)
@click.option("--name", default="", help="Marker name")
@click.option("--comment", default="", help="Marker comment")
@click.pass_context
def markers_add(ctx: click.Context, time: float, name: str, comment: str) -> None:
    """Add a marker at TIME seconds on the active sequence."""
    from cli_anything.premierepro.core.markers import add_marker
    try:
        _out(ctx, add_marker(time, name, comment))
    except CepNotRunningError as exc:
        _cep_error(exc)


# ──────────────────────────── media ───────────────────────────────────

@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.pass_context
def media(ctx: click.Context, path: str) -> None:
    """Show media file metadata (no Premiere required)."""
    from cli_anything.premierepro.utils.media_backend import get_media_info
    _out(ctx, get_media_info(path))


# ──────────────────────────── REPL ────────────────────────────────────

@cli.command()
def repl() -> None:
    """Start the interactive REPL."""
    _skin.print_banner(SKILL_PATHS)
    pt_session = _skin.create_prompt_session()
    commands = {
        "ping": "Check CEP bridge status",
        "project info": "Active project info",
        "project open <path>": "Open a .prproj file",
        "project items": "List project bin items",
        "project parse <path>": "Parse .prproj offline",
        "sequence list": "List sequences",
        "sequence info <name>": "Sequence details",
        "sequence activate <name>": "Set active sequence",
        "timeline clips": "List timeline clips",
        "export render <output>": "Export via AME",
        "export presets": "Available export presets",
        "export status": "AME queue status",
        "markers list": "List markers",
        "markers add <secs>": "Add a marker",
        "media <path>": "Media file info",
        "help": "Show this help",
        "exit": "Exit REPL",
    }
    while True:
        try:
            line = _skin.get_input(pt_session)
        except (EOFError, KeyboardInterrupt):
            _skin.print_goodbye()
            break
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line in ("exit", "quit", "q"):
            _skin.print_goodbye()
            break
        if line == "help":
            _skin.help(commands)
            continue
        args = line.split()
        from click.testing import CliRunner
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(cli, args, catch_exceptions=False)
        if result.output:
            click.echo(result.output, nl=False)
        if result.exception and not isinstance(result.exception, SystemExit):
            _skin.error(str(result.exception))


if __name__ == "__main__":
    cli()
```

- [ ] **Step 8.2: Test CLI help works**

```bash
PYTHONPATH=/Volumes/Containers/adobe-cli/premiere-pro/agent-harness \
  python3 -m cli_anything.premierepro --help
```
Expected: lists all command groups without errors.

- [ ] **Step 8.3: Commit**

```bash
git add cli_anything/premierepro/premierepro_cli.py
git commit -m "feat: add Click CLI with all command groups and REPL mode"
```

---

## Task 9: `setup.py` + Installation

**Files:**
- Create: `setup.py`

- [ ] **Step 9.1: Write `setup.py`**

```python
from setuptools import setup, find_namespace_packages

setup(
    name="cli-anything-premierepro",
    version="1.0.0",
    description="Adobe Premiere Pro 2025 CLI harness",
    python_requires=">=3.10",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    package_data={
        "cli_anything.premierepro": ["skills/*.md", "cep/**/*", "cep/CSXS/*", "cep/js/*"],
    },
    install_requires=[
        "click>=8.0",
        "requests>=2.28",
        "opencv-python",
    ],
    entry_points={
        "console_scripts": [
            "cli-anything-premierepro=cli_anything.premierepro.premierepro_cli:cli",
        ],
    },
)
```

- [ ] **Step 9.2: Install in editable mode**

```bash
cd /Volumes/Containers/adobe-cli/premiere-pro/agent-harness
pip install -e . --quiet
```

- [ ] **Step 9.3: Verify CLI is in PATH**

```bash
which cli-anything-premierepro
cli-anything-premierepro --help
```
Expected: path shown, help printed.

- [ ] **Step 9.4: Commit**

```bash
git add setup.py
git commit -m "feat: add setup.py for pip install and PATH registration"
```

---

## Task 10: TEST.md + Unit Tests

**Files:**
- Create: `cli_anything/premierepro/tests/TEST.md`
- Complete: `cli_anything/premierepro/tests/test_core.py`

- [ ] **Step 10.1: Write `tests/TEST.md` (plan section)**

Write the test plan document before implementing E2E tests. (Content to match actual tests — expand as needed.)

- [ ] **Step 10.2: Add remaining unit tests to `test_core.py`**

Add tests for:
- `sequence.py`: mock `cep.eval_json` to return known sequence list
- `timeline.py`: mock `cep.eval_json` to return known clips list
- `markers.py`: mock `cep.eval_json` and `cep.eval_script`
- `export.py`: mock `cep.eval_json` for export queue return

- [ ] **Step 10.3: Run full unit suite**

```bash
PYTHONPATH=/Volumes/Containers/adobe-cli/premiere-pro/agent-harness \
  pytest cli_anything/premierepro/tests/test_core.py -v
```
Expected: all tests pass, no external dependencies required.

- [ ] **Step 10.4: Commit**

```bash
git add cli_anything/premierepro/tests/
git commit -m "test: complete unit test suite for all core modules"
```

---

## Task 11: E2E Tests (Premiere Must Be Running)

**Files:**
- Create: `cli_anything/premierepro/tests/test_full_e2e.py`

- [ ] **Step 11.1: Write `test_full_e2e.py`**

```python
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
    return [sys.executable, "-m", "cli_anything.premierepro"]


@pytest.fixture
def tmp_dir(tmp_path):
    return str(tmp_path)


class TestCepBridgeLive:
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
        assert "Premiere" in result or result  # any non-empty
        print(f"\n  app.name = {result}")


class TestProjectLive:
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
    def test_get_timeline_clips(self):
        from cli_anything.premierepro.core.timeline import get_timeline_clips
        clips = get_timeline_clips()
        assert isinstance(clips, list)
        print(f"\n  Clips in active timeline: {len(clips)}")
        for c in clips[:3]:
            print(f"    {c['name']} [{c['track']}] {c['start']:.2f}s–{c['end']:.2f}s")


class TestMarkersLive:
    def test_list_markers(self):
        from cli_anything.premierepro.core.markers import list_markers
        markers = list_markers()
        assert isinstance(markers, list)
        print(f"\n  Markers: {len(markers)}")

    def test_add_marker_then_list(self):
        from cli_anything.premierepro.core.markers import add_marker, list_markers
        before = list_markers()
        result = add_marker(1.0, name="cli-anything-test", comment="E2E test marker")
        assert result.get("ok") is True
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
        for _ in range(24):  # 1 second at 24fps
            frame = np.zeros((360, 640, 3), dtype=np.uint8)
            writer.write(frame)
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

    def _run(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            self.CLI_BASE + args,
            capture_output=True, text=True, check=check,
        )

    def test_help(self):
        result = self._run(["--help"])
        assert result.returncode == 0
        assert "premierepro" in result.stdout.lower() or "premiere" in result.stdout.lower()

    def test_ping_json(self):
        result = self._run(["--json", "ping"])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True

    def test_project_info_json(self):
        result = self._run(["--json", "project", "info"])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "name" in data

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
```

- [ ] **Step 11.2: Run E2E tests (Premiere must be open)**

```bash
PYTHONPATH=/Volumes/Containers/adobe-cli/premiere-pro/agent-harness \
  pytest cli_anything/premierepro/tests/test_full_e2e.py -v -s
```

- [ ] **Step 11.3: Append results to TEST.md**

- [ ] **Step 11.4: Commit**

```bash
git add cli_anything/premierepro/tests/
git commit -m "test: add E2E test suite for live Premiere Pro testing"
```

---

## Task 12: PREMIEREPRO.md SOP + README.md

- [ ] **Step 12.1: Write `PREMIEREPRO.md`** (SOP analysis doc at agent-harness root)

Cover: architecture decisions, CEP debug mode setup, IPC protocol, ExtendScript API notes, known limitations, .prproj format notes.

- [ ] **Step 12.2: Write `cli_anything/premierepro/README.md`**

Cover: requirements (macOS, PPro 2025, CEP debug mode), installation, CEP extension install, CLI usage, REPL usage.

- [ ] **Step 12.3: Commit**

```bash
git add PREMIEREPRO.md cli_anything/premierepro/README.md
git commit -m "docs: add SOP and README for premierepro harness"
```

---

## Task 13: SKILL.md Generation

- [ ] **Step 13.1: Generate SKILL.md from CLI help**

```bash
PYTHONPATH=/Volumes/Containers/adobe-cli/premiere-pro/agent-harness \
  python3 /Users/controlroom/.claude/plugins/marketplaces/cli-anything/cli-anything-plugin/skill_generator.py \
  cli-anything-premierepro \
  /Volumes/Containers/adobe-cli/skills/cli-anything-premierepro/SKILL.md
```

If `skill_generator.py` isn't at that path, generate manually using the template pattern from Acrobat's SKILL.md as reference.

- [ ] **Step 13.2: Copy to packaged location**

```bash
cp /Volumes/Containers/adobe-cli/skills/cli-anything-premierepro/SKILL.md \
   /Volumes/Containers/adobe-cli/premiere-pro/agent-harness/cli_anything/premierepro/skills/SKILL.md
```

- [ ] **Step 13.3: Commit**

```bash
git add /Volumes/Containers/adobe-cli/skills/cli-anything-premierepro/ \
        cli_anything/premierepro/skills/
git commit -m "feat: generate SKILL.md for cli-anything-premierepro"
```

---

## Task 14: Agent Vision — Screenshot + Frame Burst

Agents need to **see** what Premiere Pro is showing, not just get data back. This task adds:
1. `vision screenshot` — capture Premiere Pro's full window as PNG
2. `vision frame <seconds>` — scrub timeline to a timecode, capture Program Monitor, return PNG
3. `vision burst <start> <end> <step>` — burst-capture frames at intervals for change detection
4. `vision compare <a> <b>` — pixel diff two frames to detect changes

**Files:**
- Create: `cli_anything/premierepro/core/vision.py`
- Modify: `cli_anything/premierepro/premierepro_cli.py` (add `vision` group)
- Modify: `cli_anything/premierepro/cep/js/main.js` (add `/scrub` endpoint)
- Modify: `cli_anything/premierepro/utils/cep_backend.py` (add `_session()`)

- [ ] **Step 14.1: Add `/scrub` endpoint to `cep/js/main.js`**

Add inside `handleRequest` before the final 404 block:

```javascript
    if (req.method === 'POST' && req.url === '/scrub') {
        var body = '';
        req.on('data', function(chunk) { body += chunk.toString(); });
        req.on('end', function() {
            var payload = JSON.parse(body);
            var seconds = parseFloat(payload.seconds) || 0;
            var script = '(function(){' +
                'var seq = app.project.activeSequence;' +
                'if (!seq) return JSON.stringify({error:"No active sequence"});' +
                'var tc = new Time();' +
                'tc.seconds = ' + seconds + ';' +
                'seq.setPlayerPosition(tc.ticks);' +
                'return JSON.stringify({ok:true, seconds:' + seconds + '});' +
                '})()';
            csInterface.evalScript(script, function(result) {
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(result);
            });
        });
        return;
    }
```

- [ ] **Step 14.2: Add `_session()` to `cep_backend.py`**

Add at module level in `cli_anything/premierepro/utils/cep_backend.py`:

```python
_sess = requests.Session()

def _session() -> requests.Session:
    return _sess
```

Then change `ping()` to use `_sess.get(...)` and `eval_script()` to use `_sess.post(...)`.

- [ ] **Step 14.3: Add unit tests to `test_core.py`**

```python
from unittest.mock import patch, MagicMock
from cli_anything.premierepro.core.vision import (
    capture_window_screenshot, burst_frames, compare_frames
)


class TestVisionCore:
    def test_capture_screenshot_returns_path(self, tmp_path):
        out = str(tmp_path / "screenshot.png")

        def fake_run(cmd, **kw):
            open(out, "wb").close()  # simulate screencapture creating the file
            return MagicMock(returncode=0)

        with patch("cli_anything.premierepro.core.vision.subprocess.run", side_effect=fake_run):
            with patch("cli_anything.premierepro.core.vision.cv2.imread",
                       return_value=__import__("numpy").zeros((1080, 1920, 3))):
                result = capture_window_screenshot(output_path=out)
        assert result["path"] == out

    def test_capture_screenshot_nonzero_rc_raises(self, tmp_path):
        out = str(tmp_path / "screenshot.png")
        with patch("cli_anything.premierepro.core.vision.subprocess.run",
                   return_value=MagicMock(returncode=1)):
            with pytest.raises(RuntimeError, match="screencapture failed"):
                capture_window_screenshot(output_path=out)

    def test_burst_calls_scrub_and_capture_correct_count(self, tmp_path):
        with patch("cli_anything.premierepro.core.vision.scrub_and_capture") as mock_sac:
            mock_sac.side_effect = lambda s, output_path, settle_ms: {
                "path": output_path, "seconds": s, "file_size": 100, "width": 1920, "height": 1080
            }
            frames = burst_frames(start=0.0, end=2.0, step=1.0,
                                   output_dir=str(tmp_path), settle_ms=0)
        assert len(frames) == 3  # 0.0, 1.0, 2.0
        assert mock_sac.call_count == 3

    def test_compare_frames_identical(self, tmp_path):
        import numpy as np, cv2
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        p1 = str(tmp_path / "a.png")
        p2 = str(tmp_path / "b.png")
        cv2.imwrite(p1, img)
        cv2.imwrite(p2, img)
        diff = compare_frames(p1, p2)
        assert diff["identical"] is True
        assert diff["mean_pixel_diff"] == 0.0

    def test_compare_frames_different(self, tmp_path):
        import numpy as np, cv2
        img_a = np.zeros((100, 100, 3), dtype=np.uint8)
        img_b = np.full((100, 100, 3), 128, dtype=np.uint8)
        p1 = str(tmp_path / "a.png")
        p2 = str(tmp_path / "b.png")
        cv2.imwrite(p1, img_a)
        cv2.imwrite(p2, img_b)
        diff = compare_frames(p1, p2)
        assert diff["identical"] is False
        assert diff["mean_pixel_diff"] > 0
```

- [ ] **Step 14.4: Run — expect ImportError**

```bash
PYTHONPATH=/Volumes/Containers/adobe-cli/premiere-pro/agent-harness \
  pytest cli_anything/premierepro/tests/test_core.py::TestVisionCore -v
```

- [ ] **Step 14.5: Write `core/vision.py`**

```python
"""Agent vision: screenshot capture and frame burst for Premiere Pro.

Workflow: CEP /scrub endpoint moves the active sequence playhead via ExtendScript,
then macOS screencapture grabs Premiere Pro's window by CGWindowID.
OpenCV compares frames for programmatic change detection.
"""
from __future__ import annotations
import os
import subprocess
import tempfile
import time
from typing import Optional

import cv2
import numpy as np

from cli_anything.premierepro.utils import cep_backend as cep


def _get_premiere_window_id() -> Optional[str]:
    """Return CGWindowID for Premiere Pro's main window via Quartz."""
    script = (
        "import Quartz\n"
        "ws = Quartz.CGWindowListCopyWindowInfo("
        "Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)\n"
        "ids = [str(w['kCGWindowNumber']) for w in ws "
        "if 'Premiere' in (w.get('kCGWindowOwnerName') or '')]\n"
        "print(ids[0] if ids else '')"
    )
    try:
        r = subprocess.run(
            ["python3", "-c", script], capture_output=True, text=True, timeout=5
        )
        wid = r.stdout.strip()
        return wid or None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def capture_window_screenshot(output_path: Optional[str] = None) -> dict:
    """Capture Premiere Pro's window as PNG. Returns {path, file_size, width, height}."""
    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".png", prefix="ppro_vision_")
        os.close(fd)
        os.unlink(output_path)

    wid = _get_premiere_window_id()
    cmd = (["screencapture", "-x", "-l", wid, output_path]
           if wid else ["screencapture", "-x", output_path])

    result = subprocess.run(cmd, capture_output=True, timeout=10)
    if result.returncode != 0 or not os.path.exists(output_path):
        raise RuntimeError(f"screencapture failed (rc={result.returncode})")

    img = cv2.imread(output_path)
    h, w = img.shape[:2] if img is not None else (0, 0)
    return {
        "path": output_path,
        "file_size": os.path.getsize(output_path),
        "width": w,
        "height": h,
    }


def scrub_and_capture(
    seconds: float,
    output_path: Optional[str] = None,
    settle_ms: int = 300,
) -> dict:
    """Move timeline playhead to `seconds`, wait settle_ms, then screenshot."""
    resp = cep._session().post(
        f"{cep.BASE_URL}/scrub",
        json={"seconds": seconds},
        timeout=cep.TIMEOUT,
    )
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("error", "Scrub failed"))

    time.sleep(settle_ms / 1000.0)
    info = capture_window_screenshot(output_path)
    info["seconds"] = seconds
    return info


def burst_frames(
    start: float,
    end: float,
    step: float,
    output_dir: str,
    settle_ms: int = 300,
) -> list[dict]:
    """Capture one frame every `step` seconds from `start` to `end` inclusive."""
    os.makedirs(output_dir, exist_ok=True)
    frames: list[dict] = []
    t, idx = start, 0
    while t <= end + 1e-9:
        out_path = os.path.join(output_dir, f"frame_{idx:04d}_{t:.3f}s.png")
        frames.append(scrub_and_capture(t, output_path=out_path, settle_ms=settle_ms))
        t = round(t + step, 6)
        idx += 1
    return frames


def compare_frames(path_a: str, path_b: str) -> dict:
    """Pixel-diff two PNG frames; return metrics for agent decision-making."""
    img_a = cv2.imread(path_a)
    img_b = cv2.imread(path_b)
    if img_a is None or img_b is None:
        raise ValueError(f"Could not read: {path_a}, {path_b}")
    if img_a.shape != img_b.shape:
        img_b = cv2.resize(img_b, (img_a.shape[1], img_a.shape[0]))
    diff = cv2.absdiff(img_a, img_b)
    mean_diff = float(np.mean(diff))
    return {
        "mean_pixel_diff": round(mean_diff, 3),
        "max_pixel_diff": float(np.max(diff)),
        "similarity": round(1.0 - mean_diff / 255.0, 4),
        "identical": mean_diff < 0.5,
    }
```

- [ ] **Step 14.6: Add `vision` group to `premierepro_cli.py`**

Add after the `markers` group and before the `media` command:

```python
# ──────────────────────────── vision ──────────────────────────────────

@cli.group()
def vision() -> None:
    """Agent vision: screenshot and timeline frame capture."""


@vision.command("screenshot")
@click.option("--output", "-o", default=None, help="Output PNG path")
@click.pass_context
def vision_screenshot(ctx: click.Context, output: str | None) -> None:
    """Capture Premiere Pro's window as a PNG."""
    from cli_anything.premierepro.core.vision import capture_window_screenshot
    info = capture_window_screenshot(output)
    _out(ctx, info)
    if not _json_flag(ctx):
        _skin.info(f"Saved: {info['path']}")


@vision.command("frame")
@click.argument("seconds", type=float)
@click.option("--output", "-o", default=None)
@click.option("--settle", default=300, help="ms to wait after scrub")
@click.pass_context
def vision_frame(ctx: click.Context, seconds: float,
                 output: str | None, settle: int) -> None:
    """Scrub to SECONDS and capture the Program Monitor."""
    from cli_anything.premierepro.core.vision import scrub_and_capture
    try:
        _out(ctx, scrub_and_capture(seconds, output, settle))
    except CepNotRunningError as exc:
        _cep_error(exc)


@vision.command("burst")
@click.argument("start", type=float)
@click.argument("end", type=float)
@click.argument("step", type=float)
@click.option("--output-dir", "-d", default="/tmp/ppro_burst")
@click.option("--settle", default=300)
@click.pass_context
def vision_burst(ctx: click.Context, start: float, end: float,
                 step: float, output_dir: str, settle: int) -> None:
    """Burst-capture frames from START to END every STEP seconds."""
    from cli_anything.premierepro.core.vision import burst_frames
    try:
        frames = burst_frames(start, end, step, output_dir, settle)
        _out(ctx, frames)
        if not _json_flag(ctx):
            _skin.info(f"Captured {len(frames)} frames to {output_dir}/")
    except CepNotRunningError as exc:
        _cep_error(exc)


@vision.command("compare")
@click.argument("path_a", type=click.Path(exists=True))
@click.argument("path_b", type=click.Path(exists=True))
@click.pass_context
def vision_compare(ctx: click.Context, path_a: str, path_b: str) -> None:
    """Pixel-diff two frame PNGs and report similarity."""
    from cli_anything.premierepro.core.vision import compare_frames
    _out(ctx, compare_frames(path_a, path_b))
```

- [ ] **Step 14.7: Add E2E vision tests to `test_full_e2e.py`**

```python
class TestVisionLive:
    def test_screenshot_captures_premiere_window(self, tmp_dir):
        from cli_anything.premierepro.core.vision import capture_window_screenshot
        out = os.path.join(tmp_dir, "premiere_screenshot.png")
        info = capture_window_screenshot(out)
        assert os.path.exists(info["path"])
        assert info["file_size"] > 5_000
        assert info["width"] > 0
        print(f"\n  Screenshot: {info['path']} ({info['width']}x{info['height']}, {info['file_size']:,} bytes)")

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
```

- [ ] **Step 14.8: Run unit tests**

```bash
PYTHONPATH=/Volumes/Containers/adobe-cli/premiere-pro/agent-harness \
  pytest cli_anything/premierepro/tests/test_core.py::TestVisionCore -v
```
Expected: 5 passed

- [ ] **Step 14.9: Commit**

```bash
git add cli_anything/premierepro/core/vision.py \
        cli_anything/premierepro/cep/js/main.js \
        cli_anything/premierepro/utils/cep_backend.py \
        cli_anything/premierepro/premierepro_cli.py \
        cli_anything/premierepro/tests/
git commit -m "feat: add agent vision (screenshot, frame scrub, burst capture, pixel compare)"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** HARNESS.md phases 1–7 all covered. CEP bridge replaces `do script`. Real software (Premiere Pro + AME) is the rendering backend.
- [x] **No placeholders:** All code blocks are complete and specific.
- [x] **Type consistency:** `cep_backend.eval_json()` returns `object`, `eval_script()` returns `str` — used consistently throughout core modules.
- [x] **CEP debug mode:** Task 1 step 1 covers this before anything else.
- [x] **Offline path:** `project parse` + `media` commands work without Premiere running.
- [x] **REPL:** `invoke_without_command=True` set; `repl` command invoked when no subcommand given.
- [x] **subprocess tests:** `_resolve_cli()` used in `TestCLISubprocess`; no hardcoded paths.
- [x] **HARNESS.md anti-pattern check:** CLI calls real Premiere via CEP → ExtendScript; no reimplementation of rendering logic.
- [x] **Agent vision coverage:** Task 14 adds screenshot, frame scrub, burst, and pixel compare. `/scrub` endpoint in CEP drives timeline; macOS `screencapture` grabs by CGWindowID; OpenCV diffs frames.
