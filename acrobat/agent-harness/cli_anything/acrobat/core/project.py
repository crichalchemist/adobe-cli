"""PDF project creation and loading for cli-anything-acrobat.

Projects are JSON session files that track the source PDF, output target,
and operation log. They are NOT the PDF itself — they're working state.
"""

from __future__ import annotations

from pathlib import Path

from cli_anything.acrobat.core.session import (
    AcrobatSession,
    load_session,
    new_session,
    save_session,
)
from cli_anything.acrobat.utils import pypdf_backend as pypdf


def create_project(
    source_pdf: str,
    project_path: str,
    output_pdf: str | None = None,
) -> dict:
    """Create a new session project file pointing at a source PDF.

    Args:
        source_pdf: Existing PDF to work on.
        project_path: Where to save the .json session file.
        output_pdf: Where to write results. Defaults to source_pdf.

    Returns:
        dict with project info.
    """
    src = Path(source_pdf).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Source PDF not found: {source_pdf}")

    sess = new_session(str(src), output_pdf)
    save_session(project_path)

    info = pypdf.get_info(str(src))
    return {
        "project": str(Path(project_path).resolve()),
        "source_pdf": str(src),
        "output_pdf": sess.output_pdf,
        "page_count": info["page_count"],
        "title": info["title"],
        "file_size": info["file_size"],
    }


def open_project(project_path: str) -> AcrobatSession:
    """Load an existing session project file.

    Raises FileNotFoundError if project_path doesn't exist.
    """
    path = Path(project_path)
    if not path.exists():
        raise FileNotFoundError(f"Project file not found: {project_path}")
    return load_session(str(path))


def project_info(project_path: str) -> dict:
    """Return human-readable info about a project and its source PDF."""
    sess = open_project(project_path)
    src = sess.source_pdf
    if not Path(src).exists():
        return {
            "project": str(Path(project_path).resolve()),
            "source_pdf": src,
            "error": "Source PDF not found on disk",
        }

    info = pypdf.get_info(src)
    return {
        "project": str(Path(project_path).resolve()),
        "source_pdf": src,
        "output_pdf": sess.output_pdf,
        "dirty": sess.dirty,
        "operations_count": len(sess.operations),
        "page_count": info["page_count"],
        "title": info["title"],
        "author": info["author"],
        "file_size": info["file_size"],
        "encrypted": info["encrypted"],
    }
