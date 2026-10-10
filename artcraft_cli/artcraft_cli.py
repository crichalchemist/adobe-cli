"""artcraft-cli command tree. Commands parse flags, call core, and emit one result."""

from __future__ import annotations

import itertools
import json
import sys
from typing import Any

import click

from artcraft_cli.core import account, generate, jobs, models
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


@account_group.command("credits")
def account_credits() -> None:
    """Credit balances."""
    emit(account.credits())


@account_group.command("subscription")
def account_subscription() -> None:
    """The active subscription, if any."""
    emit(account.subscription())


@cli.group("models")
def models_group() -> None:
    """Generation models."""


@models_group.command("list")
@click.option("--kind", type=click.Choice(models.KINDS), required=True)
def models_list(kind: str) -> None:
    """Image or video models with their options."""
    emit(models.list_models(kind))


@cli.command("generate")
@click.argument("modality", type=click.Choice(generate.MODALITIES))
@click.option("--model", required=True, help="A model id from `models list`.")
@click.option("--prompt")
@click.option("--set", "sets", multiple=True, metavar="KEY=JSON", help="Any Omni request field.")
@click.option("--media", "media_specs", multiple=True, metavar="FIELD=PATH|TOKEN")
@click.option("--max-credits", type=click.IntRange(min=0), help="Refuse if it would cost more.")
@click.option("--dry-run", is_flag=True, help="Price only; never uploads or submits.")
def generate_cmd(
    modality: str,
    model: str,
    prompt: str | None,
    sets: tuple[str, ...],
    media_specs: tuple[str, ...],
    max_credits: int | None,
    dry_run: bool,
) -> None:
    """Price (--dry-run) or submit a generation through ArtCraft's own route."""
    if dry_run == (max_credits is not None):
        raise CliError("usage_error", "pass exactly one of --max-credits N or --dry-run")
    request = generate.build_request(model, prompt, sets, media_specs)
    if max_credits is None:
        emit(generate.estimate(modality, request))
        return
    raise CliError("usage_error", "submitting arrives with generate.submit (M2); use --dry-run")


@cli.group("jobs")
def jobs_group() -> None:
    """Generation jobs."""


@jobs_group.command("list")
@click.option("--all", "all_origins", is_flag=True, help="Include jobs started in the app.")
@click.option("--remote", is_flag=True, help="Merge the server's newest 100 jobs.")
@click.option("--limit", type=click.IntRange(1, 200), default=50, show_default=True)
def jobs_list(all_origins: bool, remote: bool, limit: int) -> None:
    """Recent jobs, newest first."""
    emit(jobs.list_jobs(all_origins=all_origins, remote=remote, limit=limit))


@jobs_group.command("get")
@click.argument("job_ids", nargs=-1, required=True)
@click.option("--remote", is_flag=True, help="Ask the server too (expands batches).")
def jobs_get(job_ids: tuple[str, ...], remote: bool) -> None:
    """Status and results of specific jobs."""
    emit(jobs.get_jobs(list(job_ids), remote=remote))


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
