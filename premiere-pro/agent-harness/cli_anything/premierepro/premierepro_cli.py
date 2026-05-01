"""cli-anything-premierepro — Adobe Premiere Pro 2025 CLI.

Requires Adobe Premiere Pro 2025 open with the cli-anything CEP extension loaded
(Window > Extensions > cli-anything) for all project/sequence/export commands.
Media info commands work without Premiere running.
"""
from __future__ import annotations
import json
import sys
import click
from click.testing import CliRunner

from cli_anything.premierepro.utils.cep_backend import CepNotRunningError
from cli_anything.premierepro.utils.repl_skin import ReplSkin

_skin = ReplSkin("premierepro", version="1.0.0")

SKILL_PATHS = [
    "/Volumes/Containers/adobe-cli/skills/cli-anything-premierepro/SKILL.md",
    str(__import__("pathlib").Path(__file__).parent / "skills" / "SKILL.md"),
]


def _json_flag(ctx: click.Context) -> bool:
    return ctx.find_root().params.get("json_output", False)


def _out(ctx: click.Context, data: object) -> None:
    if _json_flag(ctx):
        click.echo(json.dumps(data, indent=2))
    else:
        if isinstance(data, dict):
            for k, v in data.items():
                _skin.status(k, str(v))
        elif isinstance(data, list):
            if data and isinstance(data[0], dict):
                headers = list(data[0].keys())
                rows = [[str(row.get(h, "")) for h in headers] for row in data]
                _skin.table(headers, rows)
            else:
                for item in data:
                    click.echo(f"  {item}")
        else:
            click.echo(str(data))


def _cep_error(exc: CepNotRunningError) -> None:
    _skin.error(str(exc))
    sys.exit(1)


@click.group(invoke_without_command=True)
@click.option("--json", "json_output", is_flag=True, help="Machine-readable JSON output")
@click.pass_context
def cli(ctx: click.Context, json_output: bool) -> None:
    """cli-anything-premierepro — Adobe Premiere Pro 2025 CLI."""
    ctx.ensure_object(dict)
    ctx.obj["json_output"] = json_output
    if ctx.invoked_subcommand is None:
        ctx.invoke(repl)


@cli.command()
@click.pass_context
def ping(ctx: click.Context) -> None:
    """Check if the CEP bridge is running."""
    from cli_anything.premierepro.utils.cep_backend import ping as _ping
    try:
        result = _ping()
        _out(ctx, result)
    except CepNotRunningError as exc:
        _cep_error(exc)


@cli.group()
def project() -> None:
    """Project open/close/inspect commands."""


@project.command("info")
@click.pass_context
def project_info(ctx: click.Context) -> None:
    """Show info about the currently open project."""
    from cli_anything.premierepro.core.project import get_project_info
    try:
        _out(ctx, get_project_info())
    except CepNotRunningError as exc:
        _cep_error(exc)


@project.command("open")
@click.argument("path", type=click.Path(exists=True))
@click.pass_context
def project_open(ctx: click.Context, path: str) -> None:
    """Open a .prproj file in Premiere Pro."""
    from cli_anything.premierepro.core.project import open_project
    try:
        ok = open_project(path)
        _out(ctx, {"opened": ok, "path": path})
    except CepNotRunningError as exc:
        _cep_error(exc)


@project.command("items")
@click.pass_context
def project_items(ctx: click.Context) -> None:
    """List all items in the project bin."""
    from cli_anything.premierepro.core.project import get_project_items
    try:
        _out(ctx, get_project_items())
    except CepNotRunningError as exc:
        _cep_error(exc)


@project.command("parse")
@click.argument("path", type=click.Path(exists=True))
@click.pass_context
def project_parse(ctx: click.Context, path: str) -> None:
    """Parse a .prproj file offline (no Premiere required)."""
    from cli_anything.premierepro.utils.prproj_parser import parse_prproj
    _out(ctx, parse_prproj(path))


@cli.group()
def sequence() -> None:
    """Sequence list and inspect commands."""


@sequence.command("list")
@click.pass_context
def sequence_list(ctx: click.Context) -> None:
    """List all sequences in the active project."""
    from cli_anything.premierepro.core.sequence import list_sequences
    try:
        _out(ctx, list_sequences())
    except CepNotRunningError as exc:
        _cep_error(exc)


@sequence.command("info")
@click.argument("name")
@click.pass_context
def sequence_info(ctx: click.Context, name: str) -> None:
    """Show detailed info for a sequence."""
    from cli_anything.premierepro.core.sequence import get_sequence_info
    try:
        _out(ctx, get_sequence_info(name))
    except CepNotRunningError as exc:
        _cep_error(exc)


@sequence.command("activate")
@click.argument("name")
@click.pass_context
def sequence_activate(ctx: click.Context, name: str) -> None:
    """Set the active sequence by name."""
    from cli_anything.premierepro.core.sequence import set_active_sequence
    try:
        ok = set_active_sequence(name)
        _out(ctx, {"activated": ok, "name": name})
    except CepNotRunningError as exc:
        _cep_error(exc)


@cli.group()
def timeline() -> None:
    """Timeline clip and track inspection."""


@timeline.command("clips")
@click.option("--sequence", "seq_name", default=None, help="Sequence name (default: active)")
@click.pass_context
def timeline_clips(ctx: click.Context, seq_name: str | None) -> None:
    """List all clips in the timeline."""
    from cli_anything.premierepro.core.timeline import get_timeline_clips
    try:
        _out(ctx, get_timeline_clips(seq_name))
    except CepNotRunningError as exc:
        _cep_error(exc)


@cli.group()
def export() -> None:
    """Export sequences via Adobe Media Encoder."""


@export.command("render")
@click.argument("output_path")
@click.option("--sequence", "seq_name", default=None, help="Sequence name (default: active)")
@click.option("--preset", default="h264-1080p", help="Export preset name (see: export presets)")
@click.pass_context
def export_render(ctx: click.Context, output_path: str, seq_name: str | None,
                  preset: str) -> None:
    """Queue a sequence for export via AME."""
    from cli_anything.premierepro.core.export import export_sequence
    try:
        result = export_sequence(output_path, seq_name, preset)
        _out(ctx, result)
    except (CepNotRunningError, ValueError) as exc:
        _skin.error(str(exc))
        sys.exit(1)


@export.command("presets")
@click.pass_context
def export_presets(ctx: click.Context) -> None:
    """List available export presets."""
    from cli_anything.premierepro.core.export import list_presets
    _out(ctx, list_presets())


@export.command("status")
@click.pass_context
def export_status(ctx: click.Context) -> None:
    """Show AME encoder status."""
    from cli_anything.premierepro.core.export import get_encoder_status
    try:
        _out(ctx, get_encoder_status())
    except CepNotRunningError as exc:
        _cep_error(exc)


@cli.group()
def markers() -> None:
    """Sequence marker operations."""


@markers.command("list")
@click.option("--sequence", "seq_name", default=None)
@click.pass_context
def markers_list(ctx: click.Context, seq_name: str | None) -> None:
    """List all markers in the active or named sequence."""
    from cli_anything.premierepro.core.markers import list_markers
    try:
        _out(ctx, list_markers(seq_name))
    except CepNotRunningError as exc:
        _cep_error(exc)


@markers.command("add")
@click.argument("time", type=float)
@click.option("--name", default="", help="Marker name")
@click.option("--comment", default="", help="Marker comment")
@click.pass_context
def markers_add(ctx: click.Context, time: float, name: str, comment: str) -> None:
    """Add a marker at TIME seconds on the active sequence."""
    from cli_anything.premierepro.core.markers import add_marker
    try:
        _out(ctx, add_marker(time, name, comment))
    except CepNotRunningError as exc:
        _cep_error(exc)


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.pass_context
def media(ctx: click.Context, path: str) -> None:
    """Show media file metadata (no Premiere required)."""
    from cli_anything.premierepro.utils.media_backend import get_media_info
    _out(ctx, get_media_info(path))


@cli.group()
def vision() -> None:
    """Agent vision: screenshot and timeline frame capture."""


@vision.command("screenshot")
@click.option("--output", "-o", default=None, help="Output PNG path")
@click.pass_context
def vision_screenshot(ctx: click.Context, output: str | None) -> None:
    """Capture Premiere Pro's window as a PNG."""
    from cli_anything.premierepro.core.vision import capture_window_screenshot
    info = capture_window_screenshot(output)
    _out(ctx, info)
    if not _json_flag(ctx):
        _skin.info(f"Saved: {info['path']}")


@vision.command("frame")
@click.argument("seconds", type=float)
@click.option("--output", "-o", default=None)
@click.option("--settle", default=300, help="ms to wait after scrub")
@click.pass_context
def vision_frame(ctx: click.Context, seconds: float,
                 output: str | None, settle: int) -> None:
    """Scrub to SECONDS and capture the Program Monitor."""
    from cli_anything.premierepro.core.vision import scrub_and_capture
    try:
        _out(ctx, scrub_and_capture(seconds, output, settle))
    except CepNotRunningError as exc:
        _cep_error(exc)


@vision.command("burst")
@click.argument("start", type=float)
@click.argument("end", type=float)
@click.argument("step", type=float)
@click.option("--output-dir", "-d", default="/tmp/ppro_burst")
@click.option("--settle", default=300)
@click.pass_context
def vision_burst(ctx: click.Context, start: float, end: float,
                 step: float, output_dir: str, settle: int) -> None:
    """Burst-capture frames from START to END every STEP seconds."""
    from cli_anything.premierepro.core.vision import burst_frames
    try:
        frames = burst_frames(start, end, step, output_dir, settle)
        _out(ctx, frames)
        if not _json_flag(ctx):
            _skin.info(f"Captured {len(frames)} frames to {output_dir}/")
    except CepNotRunningError as exc:
        _cep_error(exc)


@vision.command("compare")
@click.argument("path_a", type=click.Path(exists=True))
@click.argument("path_b", type=click.Path(exists=True))
@click.pass_context
def vision_compare(ctx: click.Context, path_a: str, path_b: str) -> None:
    """Pixel-diff two frame PNGs and report similarity."""
    from cli_anything.premierepro.core.vision import compare_frames
    _out(ctx, compare_frames(path_a, path_b))


@cli.command()
def repl() -> None:
    """Start the interactive REPL."""
    _skin.print_banner()
    pt_session = _skin.create_prompt_session()
    commands = {
        "ping": "Check CEP bridge status",
        "project info": "Active project info",
        "project open <path>": "Open a .prproj file",
        "project items": "List project bin items",
        "project parse <path>": "Parse .prproj offline",
        "sequence list": "List sequences",
        "sequence info <name>": "Sequence details",
        "sequence activate <name>": "Set active sequence",
        "timeline clips": "List timeline clips",
        "export render <output>": "Export via AME",
        "export presets": "Available export presets",
        "export status": "AME queue status",
        "markers list": "List markers",
        "markers add <secs>": "Add a marker",
        "media <path>": "Media file info",
        "help": "Show this help",
        "exit": "Exit REPL",
    }
    while True:
        try:
            line = _skin.get_input(pt_session)
        except (EOFError, KeyboardInterrupt):
            _skin.print_goodbye()
            break
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line in ("exit", "quit", "q"):
            _skin.print_goodbye()
            break
        if line == "help":
            _skin.help(commands)
            continue
        args = line.split()
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(cli, args, catch_exceptions=True)
        if result.output:
            click.echo(result.output, nl=False)
        if result.exception and not isinstance(result.exception, SystemExit):
            _skin.error(str(result.exception))


if __name__ == "__main__":
    cli()
