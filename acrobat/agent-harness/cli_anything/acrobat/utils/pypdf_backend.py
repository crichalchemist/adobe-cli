"""pypdf/PyMuPDF backend for headless PDF operations.

Used for operations that don't require Acrobat: merge, split, rotate,
fast metadata reads, text extraction, and page-to-image rendering.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence


def _get_reader(pdf_path: str):
    from pypdf import PdfReader
    return PdfReader(pdf_path)


def _get_writer():
    from pypdf import PdfWriter
    return PdfWriter()


def get_info(pdf_path: str) -> dict:
    """Fast metadata + page count via pypdf (no Acrobat required)."""
    reader = _get_reader(pdf_path)
    meta = reader.metadata or {}
    return {
        "path": str(Path(pdf_path).resolve()),
        "page_count": len(reader.pages),
        "title": meta.get("/Title", ""),
        "author": meta.get("/Author", ""),
        "subject": meta.get("/Subject", ""),
        "creator": meta.get("/Creator", ""),
        "producer": meta.get("/Producer", ""),
        "creation_date": str(meta.get("/CreationDate", "")),
        "mod_date": str(meta.get("/ModDate", "")),
        "keywords": meta.get("/Keywords", ""),
        "file_size": Path(pdf_path).stat().st_size,
        "encrypted": reader.is_encrypted,
    }


def merge_pdfs(input_paths: Sequence[str], output_path: str) -> dict:
    """Merge multiple PDFs into one, in order.

    Returns dict with output path, file size, and total page count.
    """
    from pypdf import PdfWriter
    writer = PdfWriter()
    total_pages = 0
    for path in input_paths:
        reader = _get_reader(path)
        for page in reader.pages:
            writer.add_page(page)
            total_pages += 1

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        writer.write(f)

    return {
        "output": str(out),
        "file_size": out.stat().st_size,
        "total_pages": total_pages,
        "merged_files": len(input_paths),
    }


def split_pdf(
    pdf_path: str,
    output_dir: str,
    page_ranges: list[tuple[int, int]] | None = None,
    pages_per_chunk: int | None = None,
) -> list[dict]:
    """Split a PDF into multiple files.

    Args:
        page_ranges: List of (start, end) 0-indexed inclusive ranges.
                     If None, splits by pages_per_chunk.
        pages_per_chunk: Pages per output file. Used only if page_ranges is None.

    Returns:
        List of dicts with output, file_size, pages.
    """
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(pdf_path)
    total = len(reader.pages)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(pdf_path).stem

    if page_ranges is None:
        chunk = pages_per_chunk or total
        page_ranges = [
            (i, min(i + chunk - 1, total - 1))
            for i in range(0, total, chunk)
        ]

    results = []
    for idx, (start, end) in enumerate(page_ranges):
        writer = PdfWriter()
        for p in range(start, end + 1):
            if p < total:
                writer.add_page(reader.pages[p])

        out_file = out_dir / f"{stem}_part{idx + 1:03d}.pdf"
        with open(out_file, "wb") as f:
            writer.write(f)

        results.append({
            "output": str(out_file),
            "file_size": out_file.stat().st_size,
            "pages": f"{start + 1}-{end + 1}",
            "part": idx + 1,
        })

    return results


def rotate_pages(
    pdf_path: str,
    output_path: str,
    degrees: int,
    pages: list[int] | None = None,
) -> dict:
    """Rotate pages in a PDF using pypdf (no Acrobat required).

    Args:
        degrees: Clockwise rotation: 90, 180, or 270.
        pages: 0-indexed list of pages. None rotates all.
    """
    from pypdf import PdfReader, PdfWriter

    if degrees not in (90, 180, 270):
        raise ValueError(f"degrees must be 90, 180, or 270, got {degrees}")

    reader = PdfReader(pdf_path)
    writer = PdfWriter()
    target_pages = set(pages) if pages is not None else set(range(len(reader.pages)))

    for i, page in enumerate(reader.pages):
        if i in target_pages:
            page.rotate(degrees)
        writer.add_page(page)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        writer.write(f)

    return {"output": str(out), "file_size": out.stat().st_size}


def extract_pages_pypdf(
    pdf_path: str,
    output_path: str,
    start_page: int,
    end_page: int,
) -> dict:
    """Extract page range (0-indexed, inclusive) to a new PDF via pypdf."""
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(pdf_path)
    writer = PdfWriter()
    for i in range(start_page, end_page + 1):
        if i < len(reader.pages):
            writer.add_page(reader.pages[i])

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        writer.write(f)

    return {"output": str(out), "file_size": out.stat().st_size}


def delete_pages_pypdf(
    pdf_path: str,
    output_path: str,
    pages: list[int],
) -> dict:
    """Delete specified pages (0-indexed) via pypdf."""
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(pdf_path)
    writer = PdfWriter()
    skip = set(pages)
    kept = 0
    for i, page in enumerate(reader.pages):
        if i not in skip:
            writer.add_page(page)
            kept += 1

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        writer.write(f)

    return {
        "output": str(out),
        "file_size": out.stat().st_size,
        "remaining_pages": kept,
    }


def extract_text(pdf_path: str, pages: list[int] | None = None) -> str:
    """Extract text from PDF (all pages or specified 0-indexed pages) via PyMuPDF."""
    import fitz  # PyMuPDF

    doc = fitz.open(pdf_path)
    target = pages if pages is not None else list(range(doc.page_count))
    chunks = []
    for i in target:
        if 0 <= i < doc.page_count:
            chunks.append(doc[i].get_text())
    doc.close()
    return "\n\n".join(chunks)


def render_page_to_image(
    pdf_path: str,
    page: int,
    output_path: str,
    dpi: int = 150,
) -> dict:
    """Render a single PDF page to PNG/JPEG via PyMuPDF.

    Args:
        page: 0-indexed page number.
        dpi: Render resolution (default 150).
    """
    import fitz

    doc = fitz.open(pdf_path)
    if page >= doc.page_count:
        raise ValueError(f"Page {page} out of range (0-{doc.page_count - 1})")

    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = doc[page].get_pixmap(matrix=mat)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    pix.save(str(out))
    doc.close()
    return {"output": str(out), "file_size": out.stat().st_size, "dpi": dpi}
