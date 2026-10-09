"""artcraft-cli command tree. Commands parse flags, call core, and emit one result."""

from __future__ import annotations

import itertools
import json
import sys
from typing import Any

import click

from artcraft_cli.core import account, jobs, models
from artcraft_cli.core import app as app_core
from artcraft_cli.errors import CliError, error_payload


def _json_mode() -> bool:
    return bool(click.get_current_context().find_root().params.get("as_json"))


def emit(data: dict[str, Any]) -> None:
    """One result on stdout: compact JSON under --json, indented JSON otherwise."""
    if _json_mode():
        click.echo(json.dumps(data, separators=(",", ":")))
    else:
        click.echo(json.dumps(data, indent=2))


@click.group()
@click.option("--json", "as_json", is_flag=True, help="Print exactly one JSON object on stdout.")
def cli(as_json: bool) -> None:
    """Drive a locally running ArtCraft app (launched with ARTCRAFT_CLI_BRIDGE=1)."""


@cli.command()
def ping() -> None:
    """Check the bridge: discovery file, health, readiness and supported ops."""
    emit(app_core.ping())


@cli.group("app")
def app_group() -> None:
    """ArtCraft app information."""


@app_group.command("info")
def app_info() -> None:
    """Version, build, platform and directories."""
    emit(app_core.info())


@cli.group("account")
def account_group() -> None:
    """The ArtCraft account logged in inside the app."""


@account_group.command("whoami")
def account_whoami() -> None:
    """Login state, checked with the server."""
    emit(account.whoami())


@cli.group("models")
def models_group() -> None:
    """Generation models."""


@models_group.command("list")
@click.option("--kind", type=click.Choice(models.KINDS), required=True)
def models_list(kind: str) -> None:
    """Image or video models with their options."""
    emit(models.list_models(kind))


@cli.group("jobs")
def jobs_group() -> None:
    """Generation jobs."""


@jobs_group.command("list")
@click.option("--all", "all_origins", is_flag=True, help="Include jobs started in the app.")
@click.option("--limit", type=click.IntRange(1, 200), default=50, show_default=True)
def jobs_list(all_origins: bool, limit: int) -> None:
    """Recent jobs, newest first."""
    emit(jobs.list_jobs(all_origins=all_origins, remote=False, limit=limit))


def main(argv: list[str] | None = None) -> int:
    """Console entry point. Returns the exit code: 0 success, 1 any error."""
    args = sys.argv[1:] if argv is None else argv
    as_json = "--json" in itertools.takewhile(lambda arg: arg.startswith("-"), args)
    try:
        cli.main(args=args, prog_name="artcraft-cli", standalone_mode=False)
    except click.exceptions.NoArgsIsHelpError as exc:
        if as_json:
            return _render(CliError("usage_error", "missing command"), as_json)
        click.echo(exc.format_message())
        return 0
    except click.ClickException as exc:
        return _render(CliError("usage_error", exc.format_message()), as_json)
    except CliError as err:
        return _render(err, as_json)
    except click.Abort:
        click.echo("Aborted!", err=True)
        return 1
    return 0


def _render(err: CliError, as_json: bool) -> int:
    payload = error_payload(err)
    if as_json:
        click.echo(json.dumps(payload, separators=(",", ":")))
    else:
        click.echo(f"error[{err.code}]: {err.message}", err=True)
        if payload["error"]["hint"]:
            click.echo(f"hint: {payload['error']['hint']}", err=True)
    return 1
