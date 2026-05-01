"""PDF metadata read/write for cli-anything-acrobat.

Reads via pypdf (fast, headless). Writes via Acrobat JS (preserves PDF integrity).
"""

from __future__ import annotations

from cli_anything.acrobat.utils import acrobat_backend as acrobat
from cli_anything.acrobat.utils import pypdf_backend as pypdf


WRITABLE_FIELDS = ("title", "author", "subject", "keywords", "creator")


def get_metadata(pdf_path: str) -> dict:
    """Return all metadata fields for a PDF (fast, no Acrobat required)."""
    info = pypdf.get_info(pdf_path)
    return {
        "title": info.get("title", ""),
        "author": info.get("author", ""),
        "subject": info.get("subject", ""),
        "creator": info.get("creator", ""),
        "producer": info.get("producer", ""),
        "keywords": info.get("keywords", ""),
        "creation_date": info.get("creation_date", ""),
        "mod_date": info.get("mod_date", ""),
        "page_count": info.get("page_count", 0),
        "file_size": info.get("file_size", 0),
        "encrypted": info.get("encrypted", False),
    }


def set_metadata(
    pdf_path: str,
    output_path: str,
    title: str | None = None,
    author: str | None = None,
    subject: str | None = None,
    keywords: str | None = None,
    creator: str | None = None,
) -> dict:
    """Set metadata fields on a PDF using Acrobat's engine.

    Only provided (non-None) fields are updated. Writes to output_path.
    Requires Adobe Acrobat DC.
    """
    fields = {}
    if title is not None:
        fields["title"] = title
    if author is not None:
        fields["author"] = author
    if subject is not None:
        fields["subject"] = subject
    if keywords is not None:
        fields["keywords"] = keywords
    if creator is not None:
        fields["creator"] = creator

    if not fields:
        raise ValueError(f"At least one metadata field required: {WRITABLE_FIELDS}")

    return acrobat.set_metadata(pdf_path, output_path, **fields)
