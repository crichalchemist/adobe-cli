"""artcraft-cli command tree. Commands parse flags, call core, and emit one result."""

from __future__ import annotations

import sys

import click


@click.group()
@click.option("--json", "as_json", is_flag=True, help="Print exactly one JSON object on stdout.")
def cli(as_json: bool) -> None:
    """Drive a locally running ArtCraft app (launched with ARTCRAFT_CLI_BRIDGE=1)."""


def main(argv: list[str] | None = None) -> int:
    """Console entry point. Returns the exit code: 0 success, 1 any error."""
    args = sys.argv[1:] if argv is None else argv
    try:
        cli.main(args=args, prog_name="artcraft-cli", standalone_mode=False)
    except click.exceptions.NoArgsIsHelpError as exc:
        click.echo(exc.format_message())
        return 0
    except click.ClickException as exc:
        exc.show()
        return 1
    return 0
