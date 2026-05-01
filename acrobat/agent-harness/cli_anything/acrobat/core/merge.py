"""PDF merging and splitting operations (headless via pypdf)."""

from __future__ import annotations

from pathlib import Path

from cli_anything.acrobat.utils import pypdf_backend as pypdf


def merge_pdfs(
    input_paths: list[str],
    output_path: str,
    overwrite: bool = False,
) -> dict:
    """Merge multiple PDFs into one.

    Args:
        input_paths: Ordered list of PDF file paths.
        output_path: Where to write the merged PDF.
        overwrite: Allow overwriting existing output.

    Returns:
        dict with output, file_size, total_pages, merged_files.
    """
    if len(input_paths) < 2:
        raise ValueError("Merge requires at least 2 input PDF files")

    for p in input_paths:
        if not Path(p).exists():
            raise FileNotFoundError(f"Input PDF not found: {p}")

    out = Path(output_path)
    if out.exists() and not overwrite:
        raise FileExistsError(
            f"Output file already exists: {output_path}\nUse --overwrite to replace."
        )
    out.parent.mkdir(parents=True, exist_ok=True)

    return pypdf.merge_pdfs(input_paths, output_path)


def split_pdf(
    pdf_path: str,
    output_dir: str,
    pages_per_chunk: int | None = None,
    page_ranges: list[str] | None = None,
) -> list[dict]:
    """Split a PDF into multiple parts.

    Args:
        pages_per_chunk: Pages per output file (e.g. 1 = one-per-page).
        page_ranges: List of range strings like ["1-3", "4-6", "7"] (1-indexed).

    Returns:
        List of dicts with output, file_size, pages, part.
    """
    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"Input PDF not found: {pdf_path}")

    if page_ranges is not None:
        info = pypdf.get_info(pdf_path)
        total = info["page_count"]
        parsed: list[tuple[int, int]] = []
        for spec in page_ranges:
            spec = spec.strip()
            if "-" in spec:
                s, e = spec.split("-", 1)
                parsed.append((int(s.strip()) - 1, int(e.strip()) - 1))
            else:
                p = int(spec) - 1
                parsed.append((p, p))
        return pypdf.split_pdf(pdf_path, output_dir, page_ranges=parsed)

    return pypdf.split_pdf(pdf_path, output_dir, pages_per_chunk=pages_per_chunk)
