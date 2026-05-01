"""cli-anything-acrobat — CLI harness for Adobe Acrobat DC.

Provides a stateful CLI + REPL for PDF operations:
  - info / inspect PDF documents
  - pages (delete, extract, rotate, reorder)
  - export (PDF → DOCX, XLSX, PPTX, PNG, JPEG, etc.)
  - merge / split PDFs
  - metadata get/set

All export/conversion commands require Adobe Acrobat DC (licensed).
Page manipulation and merge/split work without Acrobat (uses pypdf/PyMuPDF).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import click

from cli_anything.acrobat.core import export as export_mod
from cli_anything.acrobat.core import merge as merge_mod
from cli_anything.acrobat.core import metadata as meta_mod
from cli_anything.acrobat.core import pages as pages_mod
from cli_anything.acrobat.core import project as proj_mod
from cli_anything.acrobat.core import session as sess_mod
from cli_anything.acrobat.utils.repl_skin import ReplSkin

VERSION = "1.0.0"
_repl_mode = False


def _skin() -> ReplSkin:
    return ReplSkin("acrobat", version=VERSION)


def _out(data: dict | list, use_json: bool) -> None:
    if use_json:
        click.echo(json.dumps(data, indent=2))
    else:
        if isinstance(data, list):
            for item in data:
                _print_dict(item)
        else:
            _print_dict(data)


def _print_dict(d: dict) -> None:
    skin = _skin()
    for k, v in d.items():
        skin.status(k.replace("_", " ").title(), str(v))


def handle_error(msg: str, use_json: bool = False) -> None:
    if use_json:
        click.echo(json.dumps({"error": msg}))
    else:
        _skin().error(msg)
    sys.exit(1)


# ── Main CLI group ──────────────────────────────────────────────────────

@click.group(invoke_without_command=True)
@click.option("--json", "use_json", is_flag=True, help="Output as JSON")
@click.option(
    "--project", "project_path", type=str, default=None,
    help="Path to session project JSON file"
)
@click.option(
    "--dry-run", "dry_run", is_flag=True, default=False,
    help="Run without saving session changes to disk"
)
@click.version_option(VERSION, prog_name="cli-anything-acrobat")
@click.pass_context
def cli(ctx: click.Context, use_json: bool, project_path: str | None, dry_run: bool) -> None:
    """cli-anything-acrobat — Adobe Acrobat DC command-line interface.

    PDF operations: info, pages, export, merge, split, metadata.

    Run without arguments to enter interactive REPL mode.
    Prefix commands with --json for machine-readable output.
    """
    ctx.ensure_object(dict)
    ctx.obj["use_json"] = use_json
    ctx.obj["project_path"] = project_path
    ctx.obj["dry_run"] = dry_run

    if project_path and Path(project_path).exists():
        try:
            sess_mod.load_session(project_path)
        except Exception as e:
            if not use_json:
                _skin().warning(f"Could not load project: {e}")

    if ctx.invoked_subcommand is None:
        ctx.invoke(repl, project_path=project_path)


@cli.result_callback()
def _auto_save_on_exit(
    result: object,
    use_json: bool,
    project_path: str | None,
    dry_run: bool,
    **kwargs: object,
) -> None:
    """Auto-save session after one-shot mutations."""
    if _repl_mode or dry_run:
        return
    sess = sess_mod.get_session()
    if sess.has_project and sess.dirty and project_path:
        try:
            sess_mod.save_session(project_path)
        except Exception as e:
            click.echo(f"Warning: auto-save failed: {e}", err=True)


# ── REPL ────────────────────────────────────────────────────────────────

@cli.command(hidden=True)
@click.argument("project_path", required=False)
@click.pass_context
def repl(ctx: click.Context, project_path: str | None) -> None:
    """Interactive REPL mode (default when no subcommand given)."""
    global _repl_mode
    _repl_mode = True

    skin = _skin()
    skin.print_banner()

    use_json = ctx.obj.get("use_json", False) if ctx.obj else False
    sess = sess_mod.get_session()
    pt_session = skin.create_prompt_session()

    while True:
        try:
            proj_name = Path(sess.source_pdf).name if sess.source_pdf else ""
            line = skin.get_input(pt_session, project_name=proj_name, modified=sess.dirty)
        except (EOFError, KeyboardInterrupt):
            skin.print_goodbye()
            break

        if not line:
            continue
        if line.lower() in ("quit", "exit", "q"):
            skin.print_goodbye()
            break
        if line.lower() in ("help", "?", "h"):
            skin.help({
                "project new <pdf> -o <session.json>": "Open PDF in new session",
                "project info <session.json>":         "Show session + PDF info",
                "info <pdf>":                          "Quick PDF info (no session needed)",
                "pages delete <pages>":                "Delete pages (e.g. 1,3-5)",
                "pages extract <pages> -o <out.pdf>":  "Extract pages to new PDF",
                "pages rotate <degrees> [--pages N]":  "Rotate pages (90/180/270)",
                "pages reorder <1,3,2,...>":            "Reorder pages",
                "export to <out> [--format docx]":     "Convert PDF to another format",
                "export formats":                      "List all supported formats",
                "merge <a.pdf> <b.pdf> -o <out.pdf>":  "Merge PDFs",
                "split <pdf> --pages-per-chunk N":     "Split PDF into chunks",
                "metadata get <pdf>":                  "Show PDF metadata",
                "metadata set --title 'X' --author Y": "Set metadata fields",
                "quit / exit":                         "Exit REPL",
            })
            continue

        # Run command through Click's test runner for REPL dispatch
        parts = line.split()
        try:
            cli.main(
                args=parts,
                standalone_mode=False,
                obj={"use_json": use_json, "project_path": project_path, "dry_run": False},
            )
        except SystemExit:
            pass
        except Exception as e:
            skin.error(str(e))


# ── info ────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("pdf_path")
@click.pass_context
def info(ctx: click.Context, pdf_path: str) -> None:
    """Show PDF information without a session (quick probe)."""
    use_json = ctx.obj.get("use_json", False)
    try:
        from cli_anything.acrobat.utils import pypdf_backend as pypdf
        data = pypdf.get_info(pdf_path)
        _out(data, use_json)
    except Exception as e:
        handle_error(str(e), use_json)


# ── project ─────────────────────────────────────────────────────────────

@cli.group()
def project() -> None:
    """Manage PDF work sessions."""


@project.command("new")
@click.argument("source_pdf")
@click.option("-o", "--output", "project_path", required=True, help="Session JSON file path")
@click.option("--out-pdf", default=None, help="Output PDF path (defaults to source)")
@click.pass_context
def project_new(
    ctx: click.Context,
    source_pdf: str,
    project_path: str,
    out_pdf: str | None,
) -> None:
    """Create a new session for SOURCE_PDF."""
    use_json = ctx.obj.get("use_json", False)
    try:
        result = proj_mod.create_project(source_pdf, project_path, out_pdf)
        if not use_json:
            _skin().success(f"Session created: {project_path}")
        _out(result, use_json)
    except Exception as e:
        handle_error(str(e), use_json)


@project.command("info")
@click.argument("project_path")
@click.pass_context
def project_info(ctx: click.Context, project_path: str) -> None:
    """Show project and PDF info for a session file."""
    use_json = ctx.obj.get("use_json", False)
    try:
        result = proj_mod.project_info(project_path)
        _out(result, use_json)
    except Exception as e:
        handle_error(str(e), use_json)


# ── pages ────────────────────────────────────────────────────────────────

@cli.group()
def pages() -> None:
    """Page manipulation operations."""


@pages.command("info")
@click.argument("pdf_path")
@click.pass_context
def pages_info(ctx: click.Context, pdf_path: str) -> None:
    """Show page count and file info for a PDF."""
    use_json = ctx.obj.get("use_json", False)
    try:
        result = pages_mod.get_page_info(pdf_path)
        _out(result, use_json)
    except Exception as e:
        handle_error(str(e), use_json)


@pages.command("delete")
@click.argument("pdf_path")
@click.argument("page_spec")
@click.option("-o", "--output", required=True, help="Output PDF path")
@click.option("--overwrite", is_flag=True)
@click.pass_context
def pages_delete(
    ctx: click.Context,
    pdf_path: str,
    page_spec: str,
    output: str,
    overwrite: bool,
) -> None:
    """Delete pages from PDF_PATH. PAGE_SPEC: '1', '1,3', '2-5', 'last'."""
    use_json = ctx.obj.get("use_json", False)
    out = Path(output)
    if out.exists() and not overwrite:
        handle_error(f"Output exists: {output} (use --overwrite)", use_json)
    try:
        result = pages_mod.delete_pages(pdf_path, output, page_spec)
        if not use_json:
            _skin().success(f"Pages deleted → {output}")
        _out(result, use_json)
    except Exception as e:
        handle_error(str(e), use_json)


@pages.command("extract")
@click.argument("pdf_path")
@click.argument("page_spec")
@click.option("-o", "--output", required=True, help="Output PDF path")
@click.option("--overwrite", is_flag=True)
@click.pass_context
def pages_extract(
    ctx: click.Context,
    pdf_path: str,
    page_spec: str,
    output: str,
    overwrite: bool,
) -> None:
    """Extract pages from PDF_PATH into a new PDF. PAGE_SPEC: '1-3', '2,4,6'."""
    use_json = ctx.obj.get("use_json", False)
    out = Path(output)
    if out.exists() and not overwrite:
        handle_error(f"Output exists: {output} (use --overwrite)", use_json)
    try:
        result = pages_mod.extract_pages(pdf_path, output, page_spec)
        if not use_json:
            _skin().success(f"Pages extracted → {output}")
        _out(result, use_json)
    except Exception as e:
        handle_error(str(e), use_json)


@pages.command("rotate")
@click.argument("pdf_path")
@click.argument("degrees", type=int)
@click.option("-o", "--output", required=True, help="Output PDF path")
@click.option("--pages", "page_spec", default=None, help="Pages to rotate (default: all)")
@click.option("--overwrite", is_flag=True)
@click.pass_context
def pages_rotate(
    ctx: click.Context,
    pdf_path: str,
    degrees: int,
    output: str,
    page_spec: str | None,
    overwrite: bool,
) -> None:
    """Rotate pages in PDF_PATH by DEGREES (90, 180, or 270)."""
    use_json = ctx.obj.get("use_json", False)
    out = Path(output)
    if out.exists() and not overwrite:
        handle_error(f"Output exists: {output} (use --overwrite)", use_json)
    try:
        result = pages_mod.rotate_pages(pdf_path, output, degrees, page_spec)
        if not use_json:
            _skin().success(f"Pages rotated {degrees}° → {output}")
        _out(result, use_json)
    except Exception as e:
        handle_error(str(e), use_json)


@pages.command("reorder")
@click.argument("pdf_path")
@click.argument("order")
@click.option("-o", "--output", required=True, help="Output PDF path")
@click.option("--overwrite", is_flag=True)
@click.pass_context
def pages_reorder(
    ctx: click.Context,
    pdf_path: str,
    order: str,
    output: str,
    overwrite: bool,
) -> None:
    """Reorder pages in PDF_PATH. ORDER is comma-separated 1-indexed page numbers.

    Example: '3,1,2' puts page 3 first, then page 1, then page 2.
    """
    use_json = ctx.obj.get("use_json", False)
    out = Path(output)
    if out.exists() and not overwrite:
        handle_error(f"Output exists: {output} (use --overwrite)", use_json)
    try:
        order_list = [int(x.strip()) for x in order.split(",")]
        result = pages_mod.reorder_pages(pdf_path, output, order_list)
        if not use_json:
            _skin().success(f"Pages reordered → {output}")
        _out(result, use_json)
    except Exception as e:
        handle_error(str(e), use_json)


# ── export ────────────────────────────────────────────────────────────────

@cli.group()
def export() -> None:
    """Export PDF to other formats using Acrobat DC's engine."""


@export.command("to")
@click.argument("pdf_path")
@click.argument("output_path")
@click.option("--format", "fmt", default=None, help="Format (auto-detected from extension)")
@click.option("--overwrite", is_flag=True)
@click.pass_context
def export_to(
    ctx: click.Context,
    pdf_path: str,
    output_path: str,
    fmt: str | None,
    overwrite: bool,
) -> None:
    """Convert PDF_PATH to OUTPUT_PATH using Acrobat DC.

    Format is auto-detected from the output file extension.
    Supported: docx, xlsx, pptx, png, jpeg, tiff, html, txt, rtf, eps, ps, xml
    """
    use_json = ctx.obj.get("use_json", False)
    try:
        result = export_mod.export_to_format(pdf_path, output_path, fmt, overwrite=overwrite)
        if not use_json:
            size = result["file_size"]
            _skin().success(f"Exported → {output_path} ({size:,} bytes)")
        _out(result, use_json)
    except Exception as e:
        handle_error(str(e), use_json)


@export.command("formats")
@click.pass_context
def export_formats(ctx: click.Context) -> None:
    """List all supported export formats."""
    use_json = ctx.obj.get("use_json", False)
    fmts = export_mod.list_formats()
    if use_json:
        click.echo(json.dumps(fmts, indent=2))
    else:
        skin = _skin()
        skin.section("Supported Export Formats")
        skin.table(
            ["Format", "Conv ID", "Description"],
            [[f["format"], f["conv_id"], f["description"]] for f in fmts],
        )


# ── merge ─────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("input_pdfs", nargs=-1, required=True)
@click.option("-o", "--output", required=True, help="Output merged PDF path")
@click.option("--overwrite", is_flag=True)
@click.pass_context
def merge(
    ctx: click.Context,
    input_pdfs: tuple[str, ...],
    output: str,
    overwrite: bool,
) -> None:
    """Merge two or more PDFs into one. INPUT_PDFS are combined in order."""
    use_json = ctx.obj.get("use_json", False)
    try:
        result = merge_mod.merge_pdfs(list(input_pdfs), output, overwrite=overwrite)
        if not use_json:
            _skin().success(
                f"Merged {result['merged_files']} PDFs → {output} "
                f"({result['total_pages']} pages)"
            )
        _out(result, use_json)
    except Exception as e:
        handle_error(str(e), use_json)


# ── split ─────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("pdf_path")
@click.option("-d", "--output-dir", required=True, help="Directory for output files")
@click.option("--pages-per-chunk", type=int, default=None)
@click.option(
    "--ranges", default=None,
    help="Comma-separated page ranges, e.g. '1-3,4-6,7'"
)
@click.pass_context
def split(
    ctx: click.Context,
    pdf_path: str,
    output_dir: str,
    pages_per_chunk: int | None,
    ranges: str | None,
) -> None:
    """Split PDF_PATH into multiple files."""
    use_json = ctx.obj.get("use_json", False)
    page_ranges = [r.strip() for r in ranges.split(",")] if ranges else None
    try:
        parts = merge_mod.split_pdf(pdf_path, output_dir, pages_per_chunk, page_ranges)
        if not use_json:
            _skin().success(f"Split into {len(parts)} files in {output_dir}")
        _out(parts, use_json)
    except Exception as e:
        handle_error(str(e), use_json)


# ── metadata ──────────────────────────────────────────────────────────────

@cli.group()
def metadata() -> None:
    """PDF metadata operations."""


@metadata.command("get")
@click.argument("pdf_path")
@click.pass_context
def metadata_get(ctx: click.Context, pdf_path: str) -> None:
    """Show all metadata for a PDF."""
    use_json = ctx.obj.get("use_json", False)
    try:
        result = meta_mod.get_metadata(pdf_path)
        _out(result, use_json)
    except Exception as e:
        handle_error(str(e), use_json)


@metadata.command("set")
@click.argument("pdf_path")
@click.option("-o", "--output", required=True, help="Output PDF path")
@click.option("--title", default=None)
@click.option("--author", default=None)
@click.option("--subject", default=None)
@click.option("--keywords", default=None)
@click.option("--creator", default=None)
@click.option("--overwrite", is_flag=True)
@click.pass_context
def metadata_set(
    ctx: click.Context,
    pdf_path: str,
    output: str,
    title: str | None,
    author: str | None,
    subject: str | None,
    keywords: str | None,
    creator: str | None,
    overwrite: bool,
) -> None:
    """Set metadata fields on PDF_PATH, write result to OUTPUT."""
    use_json = ctx.obj.get("use_json", False)
    out = Path(output)
    if out.exists() and not overwrite:
        handle_error(f"Output exists: {output} (use --overwrite)", use_json)
    try:
        result = meta_mod.set_metadata(
            pdf_path, output,
            title=title, author=author, subject=subject,
            keywords=keywords, creator=creator,
        )
        if not use_json:
            _skin().success(f"Metadata updated → {output}")
        _out(result, use_json)
    except Exception as e:
        handle_error(str(e), use_json)


# ── text extraction ───────────────────────────────────────────────────────

@cli.command()
@click.argument("pdf_path")
@click.option("--pages", "page_spec", default=None, help="Pages to extract (1-indexed, e.g. '1-3')")
@click.option("-o", "--output", default=None, help="Write text to file instead of stdout")
@click.pass_context
def text(ctx: click.Context, pdf_path: str, page_spec: str | None, output: str | None) -> None:
    """Extract text from a PDF."""
    use_json = ctx.obj.get("use_json", False)
    try:
        pages_list: list[int] | None = None
        if page_spec is not None:
            from cli_anything.acrobat.core.pages import _resolve_pages
            from cli_anything.acrobat.utils import pypdf_backend as pypdf
            info = pypdf.get_info(pdf_path)
            pages_list = _resolve_pages(page_spec, info["page_count"])

        from cli_anything.acrobat.utils import pypdf_backend as pypdf
        extracted = pypdf.extract_text(pdf_path, pages_list)

        if use_json:
            click.echo(json.dumps({"text": extracted, "pages": page_spec or "all"}))
        elif output:
            Path(output).write_text(extracted, encoding="utf-8")
            _skin().success(f"Text written to {output}")
        else:
            click.echo(extracted)
    except Exception as e:
        handle_error(str(e), use_json)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
