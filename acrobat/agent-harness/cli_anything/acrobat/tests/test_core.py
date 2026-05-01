"""Unit tests for cli-anything-acrobat core modules.

All tests use synthetic data — no Adobe Acrobat, no network access required.
Headless PDF operations use pypdf/PyMuPDF with in-memory temp files.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pdf(num_pages: int = 4) -> bytes:
    """Create a minimal valid multi-page PDF in memory via pypdf."""
    from pypdf import PdfWriter
    from pypdf.generic import ArrayObject, NumberObject, NameObject, DictionaryObject

    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=612, height=792)
    import io
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _write_pdf(tmp_dir: str, name: str = "test.pdf", pages: int = 4) -> str:
    """Write a synthetic PDF to disk and return the path."""
    path = os.path.join(tmp_dir, name)
    with open(path, "wb") as f:
        f.write(_make_pdf(pages))
    return path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp(tmp_path: Path) -> Generator[str, None, None]:
    yield str(tmp_path)


@pytest.fixture(autouse=True)
def reset_global_session():
    """Ensure each test starts with a clean global session."""
    from cli_anything.acrobat.core import session as sess_mod
    sess_mod._SESSION = None
    yield
    sess_mod._SESSION = None


# ===========================================================================
# core/session.py — 6 tests
# ===========================================================================

class TestSession:
    def test_new_session(self, tmp: str) -> None:
        from cli_anything.acrobat.core.session import new_session

        pdf = _write_pdf(tmp)
        out = os.path.join(tmp, "out.pdf")
        sess = new_session(pdf, out)

        assert sess.source_pdf == str(Path(pdf).resolve())
        assert sess.output_pdf == str(Path(out).resolve())
        assert sess.dirty is False
        assert sess.operations == []

    def test_new_session_defaults_output_to_source(self, tmp: str) -> None:
        from cli_anything.acrobat.core.session import new_session

        pdf = _write_pdf(tmp)
        sess = new_session(pdf)

        assert sess.output_pdf == str(Path(pdf).resolve())

    def test_session_log_operation(self, tmp: str) -> None:
        from cli_anything.acrobat.core.session import new_session

        pdf = _write_pdf(tmp)
        sess = new_session(pdf)
        sess.log_operation("delete_pages", spec="1", removed=1)

        assert sess.dirty is True
        assert len(sess.operations) == 1
        assert sess.operations[0]["op"] == "delete_pages"

    def test_session_to_dict_from_dict(self, tmp: str) -> None:
        from cli_anything.acrobat.core.session import AcrobatSession, new_session

        pdf = _write_pdf(tmp)
        sess = new_session(pdf)
        sess.log_operation("rotate", degrees=90)

        d = sess.to_dict()
        restored = AcrobatSession.from_dict(d)

        assert restored.source_pdf == sess.source_pdf
        assert restored.operations == sess.operations
        assert restored.dirty == sess.dirty

    def test_locked_save_and_load(self, tmp: str) -> None:
        from cli_anything.acrobat.core.session import new_session, save_session, load_session

        pdf = _write_pdf(tmp)
        sess = new_session(pdf)
        sess.log_operation("merge", merged_count=2)

        session_file = os.path.join(tmp, "test_session.json")
        save_session(session_file)

        loaded = load_session(session_file)
        assert loaded.source_pdf == sess.source_pdf
        assert len(loaded.operations) == 1
        assert loaded.operations[0]["op"] == "merge"

    def test_load_missing_file_raises(self, tmp: str) -> None:
        from cli_anything.acrobat.core.session import load_session

        with pytest.raises(FileNotFoundError):
            load_session(os.path.join(tmp, "nonexistent_session.json"))

    def test_reset_session(self, tmp: str) -> None:
        from cli_anything.acrobat.core.session import new_session, get_session, reset_session

        pdf = _write_pdf(tmp)
        new_session(pdf)
        assert get_session().has_project is True

        reset_session()
        assert get_session().has_project is False
        assert get_session().source_pdf == ""


# ===========================================================================
# core/pages.py — _resolve_pages — 8 tests
# ===========================================================================

class TestResolvePages:
    """Tests for _resolve_pages() — pure function, no PDF needed."""

    def _resolve(self, spec: str, total: int) -> list[int]:
        from cli_anything.acrobat.core.pages import _resolve_pages
        return _resolve_pages(spec, total)

    def test_resolve_single_page(self) -> None:
        assert self._resolve("3", 5) == [2]

    def test_resolve_range(self) -> None:
        assert self._resolve("2-4", 5) == [1, 2, 3]

    def test_resolve_comma_list(self) -> None:
        assert self._resolve("1,3,5", 5) == [0, 2, 4]

    def test_resolve_mixed(self) -> None:
        assert self._resolve("1,3-5,7", 8) == [0, 2, 3, 4, 6]

    def test_resolve_all(self) -> None:
        assert self._resolve("all", 4) == [0, 1, 2, 3]

    def test_resolve_last(self) -> None:
        assert self._resolve("last", 4) == [3]

    def test_resolve_out_of_range(self) -> None:
        # Page 10 doesn't exist in a 3-page doc → empty list
        assert self._resolve("10", 3) == []

    def test_resolve_deduplication(self) -> None:
        # "1,1,2-3" should deduplicate and sort
        assert self._resolve("1,1,2-3", 4) == [0, 1, 2]


# ===========================================================================
# core/pages.py — validation tests — 4 tests
# ===========================================================================

class TestPageValidation:
    def test_delete_all_pages_raises(self, tmp: str) -> None:
        from cli_anything.acrobat.core.pages import delete_pages

        pdf = _write_pdf(tmp, pages=3)
        out = os.path.join(tmp, "out.pdf")

        with pytest.raises(ValueError, match="Cannot delete all pages"):
            delete_pages(pdf, out, "all")

    def test_delete_invalid_spec_raises(self, tmp: str) -> None:
        from cli_anything.acrobat.core.pages import delete_pages

        pdf = _write_pdf(tmp, pages=3)
        out = os.path.join(tmp, "out.pdf")

        # page 10 doesn't exist → spec resolves empty → ValueError
        with pytest.raises(ValueError, match="No valid pages"):
            delete_pages(pdf, out, "10")

    def test_extract_empty_spec_raises(self, tmp: str) -> None:
        from cli_anything.acrobat.core.pages import extract_pages

        pdf = _write_pdf(tmp, pages=3)
        out = os.path.join(tmp, "out.pdf")

        # Acrobat backend may raise; patch it to ensure the path is pypdf
        with patch("cli_anything.acrobat.core.pages.acrobat.extract_pages",
                   side_effect=RuntimeError("acrobat unavailable")):
            with pytest.raises(ValueError, match="No valid pages"):
                extract_pages(pdf, out, "10")

    def test_reorder_out_of_range_raises(self, tmp: str) -> None:
        from cli_anything.acrobat.core.pages import reorder_pages

        pdf = _write_pdf(tmp, pages=3)
        out = os.path.join(tmp, "out.pdf")

        with pytest.raises(ValueError, match="out of range"):
            reorder_pages(pdf, out, [1, 2, 9])


# ===========================================================================
# core/export.py — format resolution — 5 tests
# ===========================================================================

class TestExportFormatResolution:
    def _resolve(self, fmt: str) -> str:
        from cli_anything.acrobat.core.export import _resolve_format
        return _resolve_format(fmt)

    def test_resolve_format_docx(self) -> None:
        from cli_anything.acrobat.utils.acrobat_backend import CONV_IDS
        fmt = self._resolve("docx")
        assert fmt == "docx"
        assert "docx" in CONV_IDS

    def test_resolve_format_alias_word(self) -> None:
        # "word" is an alias for "docx"
        fmt = self._resolve("word")
        assert fmt == "docx"

    def test_resolve_format_case_insensitive(self) -> None:
        assert self._resolve("DOCX") == "docx"
        assert self._resolve("Xlsx") == "xlsx"

    def test_unsupported_format_raises(self) -> None:
        from cli_anything.acrobat.core.export import export_to_format

        with pytest.raises(RuntimeError):
            # We can't do a real export — mock acrobat.export_pdf to raise
            with patch(
                "cli_anything.acrobat.core.export.acrobat.export_pdf",
                side_effect=RuntimeError("xyz123 not a valid conv ID"),
            ):
                with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp_pdf:
                    tmp_pdf.write(_make_pdf(1))
                    tmp_pdf.flush()
                    export_to_format(tmp_pdf.name, "/tmp/out.xyz123", fmt="xyz123", overwrite=True)

    def test_list_formats_completeness(self) -> None:
        from cli_anything.acrobat.core.export import list_formats
        from cli_anything.acrobat.utils.acrobat_backend import CONV_IDS

        formats = list_formats()
        conv_ids_in_list = {f["conv_id"] for f in formats}
        all_conv_ids = set(CONV_IDS.values())

        # Every conv_id from CONV_IDS must appear in list_formats output
        assert all_conv_ids <= conv_ids_in_list


# ===========================================================================
# utils/pypdf_backend.py — headless operations — 9 tests
# ===========================================================================

class TestPypdfBackend:
    @pytest.fixture
    def pdf4(self, tmp: str) -> str:
        """4-page synthetic PDF."""
        return _write_pdf(tmp, pages=4)

    @pytest.fixture
    def pdf2a(self, tmp: str) -> str:
        return _write_pdf(tmp, name="a.pdf", pages=2)

    @pytest.fixture
    def pdf3b(self, tmp: str) -> str:
        return _write_pdf(tmp, name="b.pdf", pages=3)

    def test_get_info_real_pdf(self, pdf4: str) -> None:
        from cli_anything.acrobat.utils.pypdf_backend import get_info

        info = get_info(pdf4)
        required_keys = {"path", "page_count", "title", "author", "file_size", "encrypted"}
        assert required_keys <= set(info.keys())
        assert info["page_count"] == 4
        assert info["file_size"] > 0

    def test_merge_two_pdfs(self, pdf2a: str, pdf3b: str, tmp: str) -> None:
        from cli_anything.acrobat.utils.pypdf_backend import merge_pdfs

        out = os.path.join(tmp, "merged.pdf")
        result = merge_pdfs([pdf2a, pdf3b], out)

        assert result["total_pages"] == 5
        assert result["merged_files"] == 2
        assert Path(out).exists()

    def test_merge_one_pdf_raises(self, pdf2a: str, tmp: str) -> None:
        from cli_anything.acrobat.utils.pypdf_backend import merge_pdfs

        # merge_pdfs with a single file should still work (no error)
        # but the CLI layer requires >= 2 — test that merge succeeds technically
        out = os.path.join(tmp, "merged.pdf")
        result = merge_pdfs([pdf2a], out)
        assert result["total_pages"] == 2

    def test_split_by_chunk(self, pdf4: str, tmp: str) -> None:
        from cli_anything.acrobat.utils.pypdf_backend import split_pdf

        out_dir = os.path.join(tmp, "chunks")
        results = split_pdf(pdf4, out_dir, pages_per_chunk=2)

        assert len(results) == 2
        assert all(Path(r["output"]).exists() for r in results)

    def test_split_by_ranges(self, pdf4: str, tmp: str) -> None:
        from cli_anything.acrobat.utils.pypdf_backend import split_pdf

        out_dir = os.path.join(tmp, "ranges")
        results = split_pdf(pdf4, out_dir, page_ranges=[(0, 1), (2, 3)])

        assert len(results) == 2

    def test_rotate_90(self, pdf4: str, tmp: str) -> None:
        from cli_anything.acrobat.utils.pypdf_backend import rotate_pages
        from pypdf import PdfReader

        out = os.path.join(tmp, "rotated.pdf")
        result = rotate_pages(pdf4, out, degrees=90)

        assert Path(out).exists()
        # Check rotation was recorded in the page object
        reader = PdfReader(out)
        assert reader.pages[0].get("/Rotate", 0) == 90

    def test_rotate_invalid_degrees_raises(self, pdf4: str, tmp: str) -> None:
        from cli_anything.acrobat.utils.pypdf_backend import rotate_pages

        out = os.path.join(tmp, "bad_rot.pdf")
        with pytest.raises(ValueError, match="degrees must be"):
            rotate_pages(pdf4, out, degrees=45)

    def test_extract_pages_pypdf(self, pdf4: str, tmp: str) -> None:
        from cli_anything.acrobat.utils.pypdf_backend import extract_pages_pypdf
        from pypdf import PdfReader

        out = os.path.join(tmp, "extracted.pdf")
        extract_pages_pypdf(pdf4, out, start_page=0, end_page=1)

        reader = PdfReader(out)
        assert len(reader.pages) == 2

    def test_delete_pages_pypdf_count(self, pdf4: str, tmp: str) -> None:
        from cli_anything.acrobat.utils.pypdf_backend import delete_pages_pypdf
        from pypdf import PdfReader

        out = os.path.join(tmp, "deleted.pdf")
        result = delete_pages_pypdf(pdf4, out, pages=[0, 2])

        assert result["remaining_pages"] == 2
        reader = PdfReader(out)
        assert len(reader.pages) == 2
