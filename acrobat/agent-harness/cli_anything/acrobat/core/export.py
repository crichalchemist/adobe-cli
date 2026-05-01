"""PDF export and format conversion using Acrobat's native engine.

All conversions invoke Adobe Acrobat DC via the acrobat_backend.
Acrobat DC is a required hard dependency for this module.
"""

from __future__ import annotations

from pathlib import Path

from cli_anything.acrobat.utils import acrobat_backend as acrobat


SUPPORTED_FORMATS = sorted(set(acrobat.CONV_IDS.keys()))

FORMAT_ALIASES: dict[str, str] = {
    "word":       "docx",
    "word97":     "doc",
    "excel":      "xlsx",
    "powerpoint": "pptx",
    "image":      "png",
    "text":       "txt",
    "postscript": "ps",
}


def _resolve_format(fmt: str) -> str:
    """Normalize format string to a CONV_IDS key."""
    key = fmt.lower().lstrip(".")
    return FORMAT_ALIASES.get(key, key)


def export_to_format(
    source_pdf: str,
    output_path: str,
    fmt: str | None = None,
    page_range: tuple[int, int] | None = None,
    overwrite: bool = False,
) -> dict:
    """Convert a PDF to another format using Acrobat DC's engine.

    Args:
        source_pdf: Input PDF path.
        output_path: Destination file path.
        fmt: Format string (e.g. 'docx', 'png', 'xlsx'). Auto-detected from
             output_path extension if None.
        page_range: Optional (start, end) 0-indexed for image formats.
        overwrite: Allow overwriting existing output file.

    Returns:
        dict with output, file_size, format.

    Raises:
        FileNotFoundError: Source PDF not found.
        FileExistsError: Output exists and overwrite=False.
        ValueError: Unsupported format.
        RuntimeError: Acrobat conversion failed.
    """
    src = Path(source_pdf).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Source PDF not found: {source_pdf}")

    out = Path(output_path).resolve()
    if out.exists() and not overwrite:
        raise FileExistsError(
            f"Output file already exists: {output_path}\nUse --overwrite to replace."
        )
    out.parent.mkdir(parents=True, exist_ok=True)

    if fmt is None:
        fmt = out.suffix.lstrip(".") or "pdf"
    fmt_key = _resolve_format(fmt)

    return acrobat.export_pdf(str(src), str(out), fmt_key, page_range=page_range)


def list_formats() -> list[dict]:
    """Return all supported export formats with their descriptions."""
    descriptions = {
        "docx": "Microsoft Word Document (.docx)",
        "doc": "Word 97-2003 Document (.doc)",
        "xlsx": "Microsoft Excel Workbook (.xlsx)",
        "spreadsheet": "XML Spreadsheet 2003",
        "pptx": "Microsoft PowerPoint (.pptx)",
        "jpeg": "JPEG Image",
        "jpg": "JPEG Image (alias)",
        "jp2": "JPEG 2000 Image",
        "tiff": "TIFF Image",
        "tif": "TIFF Image (alias)",
        "png": "PNG Image",
        "html": "HTML Document",
        "rtf": "Rich Text Format",
        "eps": "Encapsulated PostScript",
        "ps": "PostScript",
        "txt": "Plain Text",
        "text": "Plain Text (alias)",
        "accesstext": "Accessible Text",
        "xml": "XML 1.0",
    }
    return [
        {"format": k, "conv_id": v, "description": descriptions.get(k, "")}
        for k, v in acrobat.CONV_IDS.items()
    ]
