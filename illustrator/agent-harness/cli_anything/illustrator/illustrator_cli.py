"""cli-anything-illustrator — Click CLI entry point."""

from __future__ import annotations

import json
import sys
from typing import Optional

import click

from cli_anything.illustrator import __version__
from cli_anything.illustrator.core import (
    artboard as _artboard,
    document as _document,
    export as _export,
    layer as _layer,
    object as _object,
    swatch as _swatch,
    text as _text,
)
from cli_anything.illustrator.utils import ai_backend as _backend
from cli_anything.illustrator.utils.repl_skin import ReplSkin

_skin = ReplSkin("illustrator", version=__version__)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _out(ctx: click.Context, data: object) -> None:
    if ctx.obj.get("json"):
        click.echo(json.dumps(data, ensure_ascii=False))
    else:
        if isinstance(data, list):
            if not data:
                _skin.info("(empty)")
                return
            headers = list(data[0].keys()) if data else []
            rows = [[str(row.get(h, "")) for h in headers] for row in data]
            _skin.table(headers, rows)
        elif isinstance(data, dict):
            for k, v in data.items():
                _skin.status(k, str(v))
        else:
            click.echo(str(data))


def _handle_error(ctx: click.Context, exc: Exception) -> None:
    if ctx.obj.get("json"):
        click.echo(json.dumps({"error": str(exc)}))
    else:
        _skin.error(str(exc))
    sys.exit(1)


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------

@click.group(invoke_without_command=True)
@click.option("--json", "use_json", is_flag=True, help="Machine-readable JSON output.")
@click.pass_context
def cli(ctx: click.Context, use_json: bool) -> None:
    """Adobe Illustrator 2026 CLI. Drives Illustrator via osascript + do javascript."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = use_json
    if ctx.invoked_subcommand is None:
        ctx.invoke(repl)


@cli.command()
@click.pass_context
def ping(ctx: click.Context) -> None:
    """Check that Illustrator is running and responding."""
    try:
        result = _backend.ping()
        _out(ctx, result)
    except Exception as exc:
        _handle_error(ctx, exc)


@cli.command()
@click.pass_context
def repl(ctx: click.Context) -> None:
    """Start an interactive REPL session."""
    _skin.print_banner()
    pt_session = _skin.create_prompt_session()
    commands = {g.name: g.help or "" for g in cli.commands.values()}

    while True:
        try:
            line = _skin.get_input(pt_session)
        except (EOFError, KeyboardInterrupt):
            break

        line = line.strip()
        if not line or line in ("exit", "quit"):
            break
        if line == "help":
            _skin.help(commands)
            continue

        args = line.split()
        try:
            standalone = cli.make_context("cli", args, parent=ctx, standalone_mode=False)
            cli.invoke(standalone)
        except SystemExit:
            pass
        except Exception as exc:
            _skin.error(str(exc))

    _skin.print_goodbye()


# ---------------------------------------------------------------------------
# document
# ---------------------------------------------------------------------------

@cli.group()
def document() -> None:
    """Document commands — open, close, save, info."""


@document.command("info")
@click.pass_context
def document_info(ctx: click.Context) -> None:
    """Show info about the active document."""
    try:
        _out(ctx, _document.get_document_info(_backend))
    except Exception as exc:
        _handle_error(ctx, exc)


@document.command("list")
@click.pass_context
def document_list(ctx: click.Context) -> None:
    """List all open documents."""
    try:
        _out(ctx, _document.list_documents(_backend))
    except Exception as exc:
        _handle_error(ctx, exc)


@document.command("open")
@click.argument("path")
@click.pass_context
def document_open(ctx: click.Context, path: str) -> None:
    """Open a .ai / .eps / .pdf / .svg file."""
    try:
        _out(ctx, _document.open_document(path, _backend))
    except Exception as exc:
        _handle_error(ctx, exc)


@document.command("close")
@click.option("--save", is_flag=True, help="Save before closing.")
@click.pass_context
def document_close(ctx: click.Context, save: bool) -> None:
    """Close the active document."""
    try:
        _out(ctx, _document.close_document(_backend, save=save))
    except Exception as exc:
        _handle_error(ctx, exc)


@document.command("save")
@click.pass_context
def document_save(ctx: click.Context) -> None:
    """Save the active document."""
    try:
        _out(ctx, _document.save_document(_backend))
    except Exception as exc:
        _handle_error(ctx, exc)


# ---------------------------------------------------------------------------
# layer
# ---------------------------------------------------------------------------

@cli.group()
def layer() -> None:
    """Layer commands — list, visible, locked."""


@layer.command("list")
@click.pass_context
def layer_list(ctx: click.Context) -> None:
    """List all layers in the active document."""
    try:
        _out(ctx, _layer.list_layers(_backend))
    except Exception as exc:
        _handle_error(ctx, exc)


@layer.command("visible")
@click.argument("name")
@click.argument("state", type=click.Choice(["on", "off"]))
@click.pass_context
def layer_visible(ctx: click.Context, name: str, state: str) -> None:
    """Set layer visibility. STATE is 'on' or 'off'."""
    try:
        _out(ctx, _layer.set_layer_visible(name, state == "on", _backend))
    except Exception as exc:
        _handle_error(ctx, exc)


@layer.command("locked")
@click.argument("name")
@click.argument("state", type=click.Choice(["on", "off"]))
@click.pass_context
def layer_locked(ctx: click.Context, name: str, state: str) -> None:
    """Set layer locked state. STATE is 'on' or 'off'."""
    try:
        _out(ctx, _layer.set_layer_locked(name, state == "on", _backend))
    except Exception as exc:
        _handle_error(ctx, exc)


# ---------------------------------------------------------------------------
# artboard
# ---------------------------------------------------------------------------

@cli.group()
def artboard() -> None:
    """Artboard commands — list, set-active."""


@artboard.command("list")
@click.pass_context
def artboard_list(ctx: click.Context) -> None:
    """List all artboards in the active document."""
    try:
        _out(ctx, _artboard.list_artboards(_backend))
    except Exception as exc:
        _handle_error(ctx, exc)


@artboard.command("set-active")
@click.argument("index", type=int)
@click.pass_context
def artboard_set_active(ctx: click.Context, index: int) -> None:
    """Set the active artboard by zero-based INDEX."""
    try:
        _out(ctx, _artboard.set_active_artboard(index, _backend))
    except Exception as exc:
        _handle_error(ctx, exc)


# ---------------------------------------------------------------------------
# object
# ---------------------------------------------------------------------------

@cli.group()
def object() -> None:
    """Page item commands — list, selection."""


@object.command("list")
@click.option("--layer", "layer_name", default=None, help="Filter by layer name.")
@click.pass_context
def object_list(ctx: click.Context, layer_name: Optional[str]) -> None:
    """List page items in the active document."""
    try:
        _out(ctx, _object.list_objects(_backend, layer=layer_name))
    except Exception as exc:
        _handle_error(ctx, exc)


@object.command("selection")
@click.pass_context
def object_selection(ctx: click.Context) -> None:
    """Show the currently selected items."""
    try:
        _out(ctx, _object.get_selection(_backend))
    except Exception as exc:
        _handle_error(ctx, exc)


# ---------------------------------------------------------------------------
# text
# ---------------------------------------------------------------------------

@cli.group()
def text() -> None:
    """Text frame commands — list, set."""


@text.command("list")
@click.pass_context
def text_list(ctx: click.Context) -> None:
    """List all text frames in the active document."""
    try:
        _out(ctx, _text.list_text_frames(_backend))
    except Exception as exc:
        _handle_error(ctx, exc)


@text.command("set")
@click.argument("index", type=int)
@click.argument("content")
@click.pass_context
def text_set(ctx: click.Context, index: int, content: str) -> None:
    """Replace the contents of text frame at INDEX."""
    try:
        _out(ctx, _text.set_text_content(index, content, _backend))
    except Exception as exc:
        _handle_error(ctx, exc)


# ---------------------------------------------------------------------------
# swatch
# ---------------------------------------------------------------------------

@cli.group()
def swatch() -> None:
    """Swatch commands — list."""


@swatch.command("list")
@click.option("--all", "include_none", is_flag=True, help="Include [None] and [Registration] swatches.")
@click.pass_context
def swatch_list(ctx: click.Context, include_none: bool) -> None:
    """List swatches in the active document."""
    try:
        _out(ctx, _swatch.list_swatches(_backend, include_none=include_none))
    except Exception as exc:
        _handle_error(ctx, exc)


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

@cli.group()
def export() -> None:
    """Export commands — png, jpeg, svg, pdf."""


@export.command("png")
@click.argument("output")
@click.option("--artboard", "-a", type=int, default=None, help="Zero-based artboard index.")
@click.option("--resolution", "-r", type=float, default=150.0, help="Resolution in DPI (default: 150).")
@click.pass_context
def export_png(ctx: click.Context, output: str, artboard: Optional[int], resolution: float) -> None:
    """Export active document as PNG."""
    try:
        _out(ctx, _export.export_png(output, _backend, artboard=artboard, resolution=resolution))
    except Exception as exc:
        _handle_error(ctx, exc)


@export.command("jpeg")
@click.argument("output")
@click.option("--artboard", "-a", type=int, default=None, help="Zero-based artboard index.")
@click.option("--quality", "-q", type=int, default=8, help="JPEG quality 1–10 (default: 8).")
@click.option("--resolution", "-r", type=float, default=150.0, help="Resolution in DPI (default: 150).")
@click.pass_context
def export_jpeg(ctx: click.Context, output: str, artboard: Optional[int], quality: int, resolution: float) -> None:
    """Export active document as JPEG."""
    try:
        _out(ctx, _export.export_jpeg(output, _backend, artboard=artboard, quality=quality, resolution=resolution))
    except Exception as exc:
        _handle_error(ctx, exc)


@export.command("svg")
@click.argument("output")
@click.pass_context
def export_svg(ctx: click.Context, output: str) -> None:
    """Export active document as SVG."""
    try:
        _out(ctx, _export.export_svg(output, _backend))
    except Exception as exc:
        _handle_error(ctx, exc)


@export.command("pdf")
@click.argument("output")
@click.pass_context
def export_pdf(ctx: click.Context, output: str) -> None:
    """Save active document as PDF."""
    try:
        _out(ctx, _export.export_pdf(output, _backend))
    except Exception as exc:
        _handle_error(ctx, exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    cli(obj={})


if __name__ == "__main__":
    main()
