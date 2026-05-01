"""Acrobat backend: invokes Adobe Acrobat via AppleScript + Acrobat JavaScript.

All operations use app.openDoc({bHidden: true}) to avoid modal dialog blocking.
The AppleScript 'open ... with invisible' command blocks on payment/license dialogs;
the JS path is dialog-immune.

Acrobat DC is a required hard dependency. Install from:
    https://get.adobe.com/reader/ (free Reader)
    https://www.adobe.com/acrobat/acrobat-pro.html (Pro, required for conversion)
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


BUNDLE_ID = "com.adobe.Acrobat.Pro"

CONV_IDS: dict[str, str] = {
    "docx":         "com.adobe.acrobat.docx",
    "doc":          "com.adobe.acrobat.doc",
    "xlsx":         "com.adobe.acrobat.xlsx",
    "spreadsheet":  "com.adobe.acrobat.spreadsheet",
    "pptx":         "com.adobe.acrobat.pptx",
    "jpeg":         "com.adobe.acrobat.jpeg",
    "jpg":          "com.adobe.acrobat.jpeg",
    "jp2":          "com.adobe.acrobat.jp2k",
    "tiff":         "com.adobe.acrobat.tiff",
    "tif":          "com.adobe.acrobat.tiff",
    "png":          "com.adobe.acrobat.png",
    "html":         "com.adobe.acrobat.html",
    "rtf":          "com.adobe.acrobat.rtf",
    "eps":          "com.adobe.acrobat.eps",
    "ps":           "com.adobe.acrobat.ps",
    "txt":          "com.adobe.acrobat.plain-text",
    "text":         "com.adobe.acrobat.plain-text",
    "accesstext":   "com.adobe.acrobat.accesstext",
    "xml":          "com.adobe.acrobat.xml-1-00",
}


def _acrobat_tmp(suffix: str = ".pdf") -> str:
    """Return a unique temp path in /tmp that Acrobat's sandbox can write to.

    Does NOT pre-create the file — Acrobat won't overwrite an existing file
    for some format converters. The caller is responsible for cleanup.
    """
    fd, path = tempfile.mkstemp(prefix="cli_acrobat_", suffix=suffix, dir="/tmp")
    import os
    os.close(fd)
    os.unlink(path)  # remove so Acrobat can create it fresh
    return path


def find_acrobat() -> str:
    """Return the Acrobat bundle path, raising RuntimeError if not found."""
    bundle = Path("/Applications/Adobe Acrobat DC/Adobe Acrobat.app")
    if bundle.exists():
        return str(bundle)
    raise RuntimeError(
        "Adobe Acrobat DC is not installed.\n"
        "Install it from: https://www.adobe.com/acrobat/acrobat-pro.html\n"
        "A valid subscription or license is required for PDF conversion."
    )


def _escape_js_string(s: str) -> str:
    """Escape a Python string for embedding inside a JS string inside osascript."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("'", "\\'")


def _run_js(js_code: str, timeout: int = 60) -> str:
    """Execute JavaScript in Acrobat's context via osascript do script.

    Returns stdout text. Raises RuntimeError on Acrobat errors or timeout.
    """
    find_acrobat()
    js_single = js_code.replace("\n", " ")
    escaped = _escape_js_string(js_single)
    script = f'tell application id "{BUNDLE_ID}" to do script "{escaped}"'
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Acrobat JS execution failed:\n{result.stderr.strip()}"
        )
    return result.stdout.strip()


def get_version() -> str:
    """Return Acrobat version string."""
    result = subprocess.run(
        ["osascript", "-e",
         f'tell application id "{BUNDLE_ID}" to get version'],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        raise RuntimeError("Adobe Acrobat is not running or not accessible.")
    return result.stdout.strip()


def get_doc_info(pdf_path: str) -> dict:
    """Open PDF (hidden), extract metadata and page count, then close.

    Returns dict with: name, page_count, title, author, subject, creator,
    producer, creation_date, mod_date, keywords, file_size.
    """
    abs_path = str(Path(pdf_path).resolve())
    escaped_path = _escape_js_string(abs_path)

    js = f"""
var doc = app.openDoc({{cPath: "{escaped_path}", bHidden: true}});
var info = doc.info;
var result = {{
    name: doc.documentFileName,
    page_count: doc.numPages,
    title: info.Title || "",
    author: info.Author || "",
    subject: info.Subject || "",
    creator: info.Creator || "",
    producer: info.Producer || "",
    creation_date: info.CreationDate || "",
    mod_date: info.ModDate || "",
    keywords: info.Keywords || ""
}};
doc.closeDoc(false);
JSON.stringify(result);
"""
    raw = _run_js(js)
    data = json.loads(raw)
    data["file_size"] = Path(pdf_path).stat().st_size
    data["path"] = abs_path
    return data


def export_pdf(
    pdf_path: str,
    output_path: str,
    format_key: str,
    page_range: tuple[int, int] | None = None,
) -> dict:
    """Export PDF to another format using Acrobat's native conversion engine.

    Args:
        pdf_path: Source PDF path.
        output_path: Destination file path (extension determines format hint).
        format_key: One of the keys in CONV_IDS (e.g. 'docx', 'png').
        page_range: Optional (start, end) 0-indexed page range for image exports.

    Returns:
        dict with output path and file size.

    Raises:
        ValueError: If format_key is not supported.
        RuntimeError: If Acrobat fails.
    """
    conv_id = CONV_IDS.get(format_key.lower())
    if conv_id is None:
        supported = ", ".join(sorted(set(CONV_IDS.keys())))
        raise ValueError(f"Unsupported format '{format_key}'. Supported: {supported}")

    abs_in = str(Path(pdf_path).resolve())
    abs_out = str(Path(output_path).resolve())
    escaped_in = _escape_js_string(abs_in)
    escaped_out = _escape_js_string(abs_out)
    escaped_conv = _escape_js_string(conv_id)

    # Page range params for image/per-page exports
    range_js = ""
    if page_range is not None:
        nStart, nEnd = page_range
        range_js = f", nStart: {nStart}, nEnd: {nEnd}"

    # Stage through /tmp/ — Acrobat's sandbox cannot write to arbitrary paths
    # (e.g. /private/var/folders/ per-process temp dirs are restricted).
    out_suffix = Path(output_path).suffix or f".{format_key}"
    tmp_out = _acrobat_tmp(suffix=out_suffix)
    escaped_tmp = _escape_js_string(tmp_out)

    js = f"""
var doc = app.openDoc({{cPath: "{escaped_in}", bHidden: true}});
doc.saveAs({{cPath: "{escaped_tmp}", cConvID: "{escaped_conv}"{range_js}}});
doc.closeDoc(false);
"ok";
"""
    _run_js(js, timeout=120)

    # Image formats (png, jpeg, tiff) create per-page files: {stem}_Page_N.{ext}
    # Single-format exports create the file at the exact path.
    tmp_path = Path(tmp_out)
    image_formats = {"png", "jpeg", "jpg", "tiff", "tif", "jp2"}
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if format_key.lower() in image_formats and not tmp_path.exists():
        # Find paged files: stem_Page_1.ext, stem_Page_2.ext, ...
        stem = tmp_path.stem
        suffix = tmp_path.suffix
        parent = tmp_path.parent
        paged = sorted(parent.glob(f"{stem}_Page_*{suffix}"))
        if paged:
            shutil.move(str(paged[0]), str(out_path))
            for extra in paged[1:]:
                extra.unlink(missing_ok=True)
            return {"output": str(out_path), "file_size": out_path.stat().st_size, "format": format_key}

    if not tmp_path.exists():
        raise RuntimeError(
            f"Export appeared to succeed but output file not found.\n"
            f"This may indicate an inactive Adobe Acrobat Pro subscription.\n"
            f"Format conversion requires an active subscription."
        )

    shutil.move(tmp_out, str(out_path))
    return {"output": str(out_path), "file_size": out_path.stat().st_size, "format": format_key}


def delete_pages(pdf_path: str, output_path: str, pages: list[int]) -> dict:
    """Delete specified pages (0-indexed) from a PDF and save to output_path.

    Acrobat JS deletePages takes 0-indexed page numbers.
    Pages are deleted in reverse order to preserve indices.
    """
    abs_in = str(Path(pdf_path).resolve())
    abs_out = str(Path(output_path).resolve())
    escaped_in = _escape_js_string(abs_in)
    escaped_out = _escape_js_string(abs_out)

    sorted_pages = sorted(set(pages), reverse=True)
    delete_calls = "".join(
        f"doc.deletePages({{nStart: {p}, nEnd: {p}}});"
        for p in sorted_pages
    )

    tmp_out = _acrobat_tmp(suffix=".pdf")
    escaped_tmp = _escape_js_string(tmp_out)

    js = f"""
var doc = app.openDoc({{cPath: "{escaped_in}", bHidden: true}});
{delete_calls}
doc.saveAs({{cPath: "{escaped_tmp}"}});
var remaining = doc.numPages;
doc.closeDoc(false);
JSON.stringify({{remaining_pages: remaining}});
"""
    raw = _run_js(js, timeout=60)
    result = json.loads(raw)
    Path(abs_out).parent.mkdir(parents=True, exist_ok=True)
    shutil.move(tmp_out, abs_out)
    result["output"] = abs_out
    return result


def extract_pages(
    pdf_path: str,
    output_path: str,
    start_page: int,
    end_page: int,
) -> dict:
    """Extract a page range (0-indexed, inclusive) into a new PDF."""
    abs_in = str(Path(pdf_path).resolve())
    abs_out = str(Path(output_path).resolve())
    escaped_in = _escape_js_string(abs_in)
    escaped_out = _escape_js_string(abs_out)

    tmp_out = _acrobat_tmp(suffix=".pdf")
    escaped_tmp = _escape_js_string(tmp_out)

    js = f"""
var doc = app.openDoc({{cPath: "{escaped_in}", bHidden: true}});
doc.extractPages({{nStart: {start_page}, nEnd: {end_page}, cPath: "{escaped_tmp}"}});
doc.closeDoc(false);
"ok";
"""
    _run_js(js, timeout=60)
    if not Path(tmp_out).exists():
        raise RuntimeError(f"extractPages produced no output at {tmp_out}")
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(tmp_out, str(out))
    return {"output": str(out), "file_size": out.stat().st_size}


def rotate_pages_acrobat(
    pdf_path: str,
    output_path: str,
    degrees: int,
    pages: list[int] | None = None,
) -> dict:
    """Rotate pages in a PDF using Acrobat JS.

    Args:
        degrees: Rotation in degrees (90, 180, 270).
        pages: 0-indexed page list. None rotates all pages.
    """
    abs_in = str(Path(pdf_path).resolve())
    abs_out = str(Path(output_path).resolve())
    escaped_in = _escape_js_string(abs_in)
    escaped_out = _escape_js_string(abs_out)

    if degrees not in (90, 180, 270):
        raise ValueError(f"degrees must be 90, 180, or 270, got {degrees}")

    if pages is None:
        rotate_js = f"""
for (var i = 0; i < doc.numPages; i++) {{
    doc.setPageRotations({{nStart: i, nEnd: i, nRotate: {degrees}}});
}}
"""
    else:
        rotate_js = "".join(
            f"doc.setPageRotations({{nStart: {p}, nEnd: {p}, nRotate: {degrees}}});"
            for p in pages
        )

    tmp_out = _acrobat_tmp(suffix=".pdf")
    escaped_tmp = _escape_js_string(tmp_out)
    js = f"""
var doc = app.openDoc({{cPath: "{escaped_in}", bHidden: true}});
{rotate_js}
doc.saveAs({{cPath: "{escaped_tmp}"}});
doc.closeDoc(false);
"ok";
"""
    _run_js(js, timeout=60)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(tmp_out, str(out))
    return {"output": str(out), "file_size": out.stat().st_size}


def set_metadata(pdf_path: str, output_path: str, **fields: str) -> dict:
    """Set metadata fields on a PDF.

    Supported fields: title, author, subject, keywords, creator.
    """
    abs_in = str(Path(pdf_path).resolve())
    abs_out = str(Path(output_path).resolve())
    escaped_in = _escape_js_string(abs_in)
    escaped_out = _escape_js_string(abs_out)

    field_map = {
        "title": "Title",
        "author": "Author",
        "subject": "Subject",
        "keywords": "Keywords",
        "creator": "Creator",
    }
    set_calls = []
    for key, val in fields.items():
        js_key = field_map.get(key.lower())
        if js_key:
            escaped_val = _escape_js_string(str(val))
            set_calls.append(f'doc.info.{js_key} = "{escaped_val}";')

    if not set_calls:
        raise ValueError(f"No valid metadata fields. Supported: {list(field_map)}")

    assignments = " ".join(set_calls)
    tmp_out = _acrobat_tmp(suffix=".pdf")
    escaped_tmp = _escape_js_string(tmp_out)
    js = f"""
var doc = app.openDoc({{cPath: "{escaped_in}", bHidden: true}});
{assignments}
doc.saveAs({{cPath: "{escaped_tmp}"}});
doc.closeDoc(false);
"ok";
"""
    _run_js(js, timeout=60)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(tmp_out, str(out))
    return {"output": str(out), "file_size": out.stat().st_size}


def get_page_text(pdf_path: str, page: int) -> str:
    """Extract text from a single page (0-indexed) using Acrobat JS."""
    abs_in = str(Path(pdf_path).resolve())
    escaped_in = _escape_js_string(abs_in)

    js = f"""
var doc = app.openDoc({{cPath: "{escaped_in}", bHidden: true}});
var numWords = doc.getPageNumWords({page});
var words = [];
for (var i = 0; i < numWords; i++) {{
    words.push(doc.getPageNthWord({page}, i));
}}
doc.closeDoc(false);
words.join(' ');
"""
    return _run_js(js, timeout=30)
