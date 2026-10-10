"""artcraft-cli command tree. Commands parse flags, call core, and emit one result."""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path
from typing import Any

import click

from artcraft_cli.core import account, generate, jobs, media, models
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
@click.option("--idempotency-token", metavar="UUID")
@click.option("--wait", is_flag=True, help="Wait for the jobs to finish.")
@click.option(
    "--timeout",
    type=click.FloatRange(min=0),
    default=jobs.DEFAULT_WAIT_TIMEOUT_S,
    show_default=True,
)
@click.option("--download", "download_dir", type=click.Path(file_okay=False, path_type=Path))
@click.option("--force", is_flag=True, help="Overwrite existing downloads.")
def generate_cmd(
    modality: str,
    model: str,
    prompt: str | None,
    sets: tuple[str, ...],
    media_specs: tuple[str, ...],
    max_credits: int | None,
    dry_run: bool,
    idempotency_token: str | None,
    wait: bool,
    timeout: float,
    download_dir: Path | None,
    force: bool,
) -> None:
    """Price (--dry-run) or submit a generation through ArtCraft's own route."""
    if dry_run == (max_credits is not None):
        raise CliError("usage_error", "pass exactly one of --max-credits N or --dry-run")
    request = generate.build_request(model, prompt, sets, media_specs)
    if max_credits is None:
        emit(generate.estimate(modality, request))
        return
    token = media.idempotency_token(idempotency_token)
    emit(
        generate.run(
            modality,
            request,
            max_credits=max_credits,
            token=token,
            wait=wait,
            timeout_s=timeout,
            download_dir=download_dir,
            force=force,
        )
    )


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


@jobs_group.command("wait")
@click.argument("job_ids", nargs=-1, required=True)
@click.option(
    "--timeout",
    type=click.FloatRange(min=0),
    default=jobs.DEFAULT_WAIT_TIMEOUT_S,
    show_default=True,
)
@click.option("--download", "download_dir", type=click.Path(file_okay=False, path_type=Path))
@click.option("--force", is_flag=True, help="Overwrite existing downloads.")
def jobs_wait(
    job_ids: tuple[str, ...], timeout: float, download_dir: Path | None, force: bool
) -> None:
    """Wait until every job succeeds; fail on the first failed or cancelled job."""
    finished = jobs.wait_for_jobs(list(job_ids), timeout_s=timeout)
    result: dict[str, Any] = {"jobs": finished}
    if download_dir is not None:
        result["downloads"] = jobs.download_files(finished, download_dir, force=force)
    emit(result)


@cli.group("media")
def media_group() -> None:
    """Media in the ArtCraft library."""


@media_group.command("upload")
@click.argument("file", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--idempotency-token", metavar="UUID")
def media_upload(file: Path, idempotency_token: str | None) -> None:
    """Upload a PNG, JPEG or GIF (at most 20 MiB) to the library."""
    emit(media.upload(file, media.idempotency_token(idempotency_token)))


@media_group.command("get")
@click.argument("media_token")
def media_get(media_token: str) -> None:
    """One media file's details."""
    emit(media.get(media_token))


@media_group.command("list")
@click.option("--class", "classes", multiple=True, help="Filter by media class (repeatable).")
@click.option("--page", type=click.IntRange(min=0), default=0, show_default=True)
@click.option("--page-size", type=click.IntRange(1, 100), default=25, show_default=True)
@click.option("--oldest-first", is_flag=True)
def media_list(classes: tuple[str, ...], page: int, page_size: int, oldest_first: bool) -> None:
    """Your library, newest first; pages are 0-based."""
    emit(
        media.list_media(
            classes=list(classes), page=page, page_size=page_size, oldest_first=oldest_first
        )
    )


@media_group.command("download")
@click.argument("media_token")
@click.option(
    "--out", "out_dir", type=click.Path(file_okay=False, path_type=Path), default=Path(".")
)
@click.option("--force", is_flag=True, help="Overwrite an existing file.")
def media_download(media_token: str, out_dir: Path, force: bool) -> None:
    """Download a media file from the CDN."""
    emit(media.download(media_token, out_dir, force=force))


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
