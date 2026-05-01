"""Page manipulation operations for PDF documents.

Uses Acrobat backend (for extract/insert via Acrobat JS) and pypdf backend
(for merge-and-delete operations that don't need Acrobat running).
"""

from __future__ import annotations

from pathlib import Path

from cli_anything.acrobat.utils import acrobat_backend as acrobat
from cli_anything.acrobat.utils import pypdf_backend as pypdf


def _resolve_pages(spec: str, total_pages: int) -> list[int]:
    """Parse a page spec string into 0-indexed page numbers.

    Supports: "1", "1,3,5", "2-5", "1,3-6,9", "last", "all"
    User-facing input is 1-indexed; returns 0-indexed.
    """
    if spec.lower() == "all":
        return list(range(total_pages))
    if spec.lower() == "last":
        return [total_pages - 1]

    result: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start = int(start_s.strip()) - 1
            end = int(end_s.strip()) - 1
            result.extend(range(max(0, start), min(total_pages, end + 1)))
        else:
            p = int(part) - 1
            if 0 <= p < total_pages:
                result.append(p)
    return sorted(set(result))


def get_page_info(pdf_path: str) -> dict:
    """Return basic page info for a PDF."""
    info = pypdf.get_info(pdf_path)
    return {
        "page_count": info["page_count"],
        "file_size": info["file_size"],
        "path": info["path"],
    }


def delete_pages(
    pdf_path: str,
    output_path: str,
    page_spec: str,
) -> dict:
    """Delete pages from a PDF.

    Args:
        page_spec: Human-readable page spec (1-indexed): "1", "1,3", "2-5", "all".

    Returns:
        dict with output, remaining_pages, file_size.
    """
    info = pypdf.get_info(pdf_path)
    total = info["page_count"]
    pages_0indexed = _resolve_pages(page_spec, total)

    if not pages_0indexed:
        raise ValueError(f"No valid pages in spec '{page_spec}' for {total}-page document")
    if len(pages_0indexed) >= total:
        raise ValueError("Cannot delete all pages — at least one must remain")

    return pypdf.delete_pages_pypdf(pdf_path, output_path, pages_0indexed)


def extract_pages(
    pdf_path: str,
    output_path: str,
    page_spec: str,
) -> dict:
    """Extract specified pages into a new PDF.

    Uses Acrobat backend for contiguous ranges, pypdf for arbitrary selections.
    """
    info = pypdf.get_info(pdf_path)
    total = info["page_count"]
    pages_0indexed = _resolve_pages(page_spec, total)

    if not pages_0indexed:
        raise ValueError(f"No valid pages in spec '{page_spec}' for {total}-page document")

    # Contiguous range: use Acrobat for fidelity (preserves layers, annotations)
    is_contiguous = pages_0indexed == list(range(pages_0indexed[0], pages_0indexed[-1] + 1))
    if is_contiguous:
        try:
            return acrobat.extract_pages(
                pdf_path, output_path,
                pages_0indexed[0], pages_0indexed[-1]
            )
        except RuntimeError:
            pass

    # Fallback: pypdf for non-contiguous or if Acrobat unavailable
    return pypdf.extract_pages_pypdf(pdf_path, output_path, pages_0indexed[0], pages_0indexed[-1])


def rotate_pages(
    pdf_path: str,
    output_path: str,
    degrees: int,
    page_spec: str | None = None,
) -> dict:
    """Rotate pages in a PDF.

    Args:
        degrees: 90, 180, or 270 (clockwise).
        page_spec: Pages to rotate. None rotates all pages.
    """
    if degrees not in (90, 180, 270):
        raise ValueError(f"degrees must be 90, 180, or 270, got {degrees}")

    pages_0indexed: list[int] | None = None
    if page_spec is not None:
        info = pypdf.get_info(pdf_path)
        pages_0indexed = _resolve_pages(page_spec, info["page_count"])

    return pypdf.rotate_pages(pdf_path, output_path, degrees, pages_0indexed)


def reorder_pages(
    pdf_path: str,
    output_path: str,
    order: list[int],
) -> dict:
    """Reorder pages in a PDF.

    Args:
        order: New page order as 1-indexed page numbers.
               e.g. [3, 1, 2] puts page 3 first, then 1, then 2.

    Returns:
        dict with output and file_size.
    """
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(pdf_path)
    total = len(reader.pages)
    writer = PdfWriter()

    order_0 = [p - 1 for p in order]
    for idx in order_0:
        if not 0 <= idx < total:
            raise ValueError(f"Page {idx + 1} out of range (1-{total})")
        writer.add_page(reader.pages[idx])

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        writer.write(f)

    return {"output": str(out), "file_size": out.stat().st_size, "page_count": len(order_0)}
