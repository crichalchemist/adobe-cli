"""E2E tests for cli-anything-acrobat.

Requires:
- Adobe Acrobat DC installed at /Applications/Adobe Acrobat DC/
- A valid Acrobat license (no modal dialogs blocking JS execution)
- The cli-anything-acrobat package installed (pip install -e .)

Run with:
    PYTHONPATH=/path/to/agent-harness pytest test_full_e2e.py -v
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# CLI resolver — never hardcodes paths (HARNESS.md requirement)
# ---------------------------------------------------------------------------

def _resolve_cli(name: str) -> str:
    """Find the installed CLI binary by name.

    Checks PATH first; if CLI_ANYTHING_FORCE_INSTALLED=1 is set, also
    searches common user-local install locations so CI can find it after
    `pip install -e .` even without a new shell.
    """
    found = shutil.which(name)
    if found:
        return found
    if os.environ.get("CLI_ANYTHING_FORCE_INSTALLED"):
        for candidate in [
            Path.home() / ".local" / "bin" / name,
            Path("/usr/local/bin") / name,
            Path("/opt/local/bin") / name,
        ]:
            if candidate.exists():
                return str(candidate)
    raise FileNotFoundError(
        f"CLI '{name}' not found in PATH. "
        "Run 'pip install -e .' in agent-harness/ first, "
        "or set CLI_ANYTHING_FORCE_INSTALLED=1."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pdf(num_pages: int = 4) -> bytes:
    from pypdf import PdfWriter
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _write_pdf(directory: str, name: str = "test.pdf", pages: int = 4) -> str:
    path = os.path.join(directory, name)
    with open(path, "wb") as f:
        f.write(_make_pdf(pages))
    return path


def _is_valid_zip(path: str) -> bool:
    try:
        with zipfile.ZipFile(path) as z:
            return len(z.namelist()) > 0
    except Exception:
        return False


def _is_ooxml(path: str, entry_prefix: str) -> bool:
    try:
        with zipfile.ZipFile(path) as z:
            return any(n.startswith(entry_prefix) for n in z.namelist())
    except Exception:
        return False


ACROBAT_PATH = Path("/Applications/Adobe Acrobat DC/Adobe Acrobat.app")
ACROBAT_MISSING = not ACROBAT_PATH.exists()
SKIP_IF_NO_ACROBAT = pytest.mark.skipif(
    ACROBAT_MISSING,
    reason="Adobe Acrobat DC not installed at /Applications/Adobe Acrobat DC/",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tmp_module(tmp_path_factory):
    return str(tmp_path_factory.mktemp("e2e"))


@pytest.fixture
def tmp(tmp_path):
    return str(tmp_path)


@pytest.fixture
def sample_pdf(tmp):
    """4-page synthetic PDF."""
    return _write_pdf(tmp, pages=4)


@pytest.fixture
def multi_pdf(tmp):
    """8-page synthetic PDF."""
    return _write_pdf(tmp, name="multi.pdf", pages=8)


# ===========================================================================
# Backend probe — 2 tests
# ===========================================================================

class TestAcrobatBackendProbe:
    @SKIP_IF_NO_ACROBAT
    def test_acrobat_version(self) -> None:
        from cli_anything.acrobat.utils.acrobat_backend import get_version

        version = get_version()
        assert isinstance(version, str)
        assert version.startswith("24."), f"Expected 24.x.x, got: {version}"

    @SKIP_IF_NO_ACROBAT
    def test_acrobat_doc_info_js(self, sample_pdf: str) -> None:
        from cli_anything.acrobat.utils.acrobat_backend import get_doc_info

        info = get_doc_info(sample_pdf)
        assert isinstance(info, dict)
        assert "numPages" in info or "page_count" in info
        page_count = info.get("numPages") or info.get("page_count")
        assert int(page_count) == 4


# ===========================================================================
# Format conversion — 8 tests (all require Acrobat)
# ===========================================================================

class TestFormatConversion:
    """Converts a synthetic PDF using Acrobat's native engine."""

    def _export(self, sample_pdf: str, tmp: str, fmt: str, ext: str) -> str:
        from cli_anything.acrobat.utils.acrobat_backend import export_pdf
        out = os.path.join(tmp, f"output.{ext}")
        export_pdf(sample_pdf, out, fmt)
        return out

    @SKIP_IF_NO_ACROBAT
    def test_export_to_docx(self, sample_pdf: str, tmp: str) -> None:
        out = self._export(sample_pdf, tmp, "docx", "docx")
        assert Path(out).exists()
        assert Path(out).stat().st_size > 1000
        assert _is_ooxml(out, "word/")

    @SKIP_IF_NO_ACROBAT
    def test_export_to_xlsx(self, sample_pdf: str, tmp: str) -> None:
        out = self._export(sample_pdf, tmp, "xlsx", "xlsx")
        assert Path(out).exists()
        assert Path(out).stat().st_size > 1000
        assert _is_valid_zip(out)

    @SKIP_IF_NO_ACROBAT
    def test_export_to_pptx(self, sample_pdf: str, tmp: str) -> None:
        out = self._export(sample_pdf, tmp, "pptx", "pptx")
        assert Path(out).exists()
        assert Path(out).stat().st_size > 1000
        assert _is_valid_zip(out)

    @SKIP_IF_NO_ACROBAT
    def test_export_to_png(self, sample_pdf: str, tmp: str) -> None:
        out = self._export(sample_pdf, tmp, "png", "png")
        assert Path(out).exists()
        with open(out, "rb") as f:
            magic = f.read(8)
        assert magic[:4] == b"\x89PNG", "Not a valid PNG"

    @SKIP_IF_NO_ACROBAT
    def test_export_to_jpeg(self, sample_pdf: str, tmp: str) -> None:
        out = self._export(sample_pdf, tmp, "jpeg", "jpg")
        assert Path(out).exists()
        with open(out, "rb") as f:
            magic = f.read(3)
        assert magic == b"\xff\xd8\xff", "Not a valid JPEG"

    @SKIP_IF_NO_ACROBAT
    def test_export_to_txt(self, sample_pdf: str, tmp: str) -> None:
        out = self._export(sample_pdf, tmp, "txt", "txt")
        assert Path(out).exists()
        text = Path(out).read_text(errors="replace")
        assert len(text) >= 0  # blank PDF may produce empty text — just check file exists

    @SKIP_IF_NO_ACROBAT
    def test_export_to_rtf(self, sample_pdf: str, tmp: str) -> None:
        out = self._export(sample_pdf, tmp, "rtf", "rtf")
        assert Path(out).exists()
        with open(out, "rb") as f:
            header = f.read(5)
        assert header.startswith(b"{\\rtf"), f"Not RTF, got: {header!r}"

    @SKIP_IF_NO_ACROBAT
    def test_export_to_html(self, sample_pdf: str, tmp: str) -> None:
        out = self._export(sample_pdf, tmp, "html", "html")
        assert Path(out).exists()
        text = Path(out).read_text(errors="replace").lower()
        assert "<html" in text or "<!doctype" in text


# ===========================================================================
# Page operations — 3 tests
# ===========================================================================

class TestPageOperations:
    @SKIP_IF_NO_ACROBAT
    def test_extract_pages_acrobat(self, multi_pdf: str, tmp: str) -> None:
        from cli_anything.acrobat.utils.acrobat_backend import extract_pages
        from pypdf import PdfReader

        out = os.path.join(tmp, "extracted.pdf")
        extract_pages(multi_pdf, out, 0, 2)  # pages 1-3 (0-indexed)

        assert Path(out).exists()
        reader = PdfReader(out)
        assert len(reader.pages) == 3

    @SKIP_IF_NO_ACROBAT
    def test_delete_pages_acrobat(self, multi_pdf: str, tmp: str) -> None:
        from cli_anything.acrobat.core.pages import delete_pages
        from pypdf import PdfReader

        out = os.path.join(tmp, "deleted.pdf")
        result = delete_pages(multi_pdf, out, "1,2")

        assert Path(out).exists()
        assert result["remaining_pages"] == 6
        reader = PdfReader(out)
        assert len(reader.pages) == 6

    def test_rotate_pages_pypdf(self, sample_pdf: str, tmp: str) -> None:
        from cli_anything.acrobat.utils.pypdf_backend import rotate_pages
        from pypdf import PdfReader

        out = os.path.join(tmp, "rotated.pdf")
        result = rotate_pages(sample_pdf, out, degrees=90)

        assert Path(out).exists()
        assert result["file_size"] > 0
        reader = PdfReader(out)
        assert len(reader.pages) == 4


# ===========================================================================
# CLI subprocess tests — 5 tests (use _resolve_cli, never hardcode paths)
# ===========================================================================

class TestCLISubprocess:
    """Tests the installed CLI binary via subprocess."""

    @pytest.fixture(autouse=True)
    def cli_path(self) -> str:
        try:
            return _resolve_cli("cli-anything-acrobat")
        except FileNotFoundError as exc:
            pytest.skip(str(exc))

    def _run(self, cli: str, args: list[str], **kwargs) -> subprocess.CompletedProcess:
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[3])}
        return subprocess.run(
            [cli] + args,
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
            **kwargs,
        )

    def test_cli_help(self, cli_path: str) -> None:
        result = self._run(cli_path, ["--help"])
        assert result.returncode == 0
        assert "acrobat" in result.stdout.lower() or "Usage" in result.stdout

    def test_cli_info(self, cli_path: str, tmp: str) -> None:
        pdf = _write_pdf(tmp)
        result = self._run(cli_path, ["info", pdf])
        assert result.returncode == 0
        assert "page" in result.stdout.lower() or "4" in result.stdout

    def test_cli_info_json(self, cli_path: str, tmp: str) -> None:
        pdf = _write_pdf(tmp)
        result = self._run(cli_path, ["--json", "info", pdf])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "page_count" in data
        assert data["page_count"] == 4

    @SKIP_IF_NO_ACROBAT
    def test_cli_export_to_docx(self, cli_path: str, tmp: str) -> None:
        pdf = _write_pdf(tmp)
        out = os.path.join(tmp, "out.docx")
        result = self._run(cli_path, ["export", "to", pdf, out])
        assert result.returncode == 0
        assert Path(out).exists()
        assert _is_valid_zip(out)

    def test_cli_merge_json(self, cli_path: str, tmp: str) -> None:
        a = _write_pdf(tmp, "a.pdf", pages=2)
        b = _write_pdf(tmp, "b.pdf", pages=3)
        out = os.path.join(tmp, "merged.pdf")
        result = self._run(cli_path, ["--json", "merge", a, b, "-o", out])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "total_pages" in data
        assert data["total_pages"] == 5
        assert Path(out).exists()


# ===========================================================================
# Workflow Scenarios — realistic multi-step pipelines
# ===========================================================================

class TestWorkflowScenarios:
    """Workflow tests simulating real-world usage chains."""

    def test_scenario_info_then_merge(self, tmp: str) -> None:
        """Scenario 2: PDF assembly — combine cover + body + appendix."""
        from cli_anything.acrobat.utils.pypdf_backend import get_info, merge_pdfs
        from pypdf import PdfReader

        cover = _write_pdf(tmp, "cover.pdf", pages=1)
        body = _write_pdf(tmp, "body.pdf", pages=5)
        appendix = _write_pdf(tmp, "appendix.pdf", pages=2)
        out = os.path.join(tmp, "final.pdf")

        merged = merge_pdfs([cover, body, appendix], out)
        assert merged["total_pages"] == 8

        info = get_info(out)
        assert info["page_count"] == 8

        reader = PdfReader(out)
        assert len(reader.pages) == 8

    def test_scenario_archival_split(self, tmp: str) -> None:
        """Scenario 3: Split large report into per-chapter files."""
        from cli_anything.acrobat.utils.pypdf_backend import split_pdf

        report = _write_pdf(tmp, "report.pdf", pages=10)
        chunks_dir = os.path.join(tmp, "chapters")

        results = split_pdf(report, chunks_dir, pages_per_chunk=5)
        assert len(results) == 2
        total = sum(
            int(r["pages"].split("-")[1]) - int(r["pages"].split("-")[0]) + 1
            for r in results
        )
        assert total == 10

    def test_scenario_page_cleanup(self, tmp: str) -> None:
        """Scenario 4 (partial): Remove back cover, extract chapters via pypdf."""
        from cli_anything.acrobat.utils.pypdf_backend import delete_pages_pypdf, extract_pages_pypdf
        from pypdf import PdfReader

        source = _write_pdf(tmp, "source.pdf", pages=6)
        clean = os.path.join(tmp, "clean.pdf")
        ch1 = os.path.join(tmp, "ch1.pdf")

        # Delete last page (back cover)
        delete_result = delete_pages_pypdf(source, clean, pages=[5])
        assert delete_result["remaining_pages"] == 5

        # Extract first 3 pages as chapter 1
        extract_pages_pypdf(clean, ch1, start_page=0, end_page=2)
        reader = PdfReader(ch1)
        assert len(reader.pages) == 3

    def test_scenario_metadata_roundtrip(self, tmp: str) -> None:
        """Scenario 5: Get → Set metadata."""
        from cli_anything.acrobat.core.metadata import get_metadata
        from pypdf import PdfReader, PdfWriter

        source = _write_pdf(tmp, "meta.pdf", pages=2)

        # Initial metadata — blank PDF has no title
        meta_before = get_metadata(source)
        assert "title" in meta_before

        # Write metadata via pypdf (no Acrobat needed for this test)
        reader = PdfReader(source)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        writer.add_metadata({"/Title": "Test Document", "/Author": "Test Author"})
        out = os.path.join(tmp, "meta_out.pdf")
        with open(out, "wb") as f:
            writer.write(f)

        meta_after = get_metadata(out)
        assert meta_after["title"] == "Test Document"
        assert meta_after["author"] == "Test Author"
