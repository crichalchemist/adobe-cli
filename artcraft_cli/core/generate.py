"""Build Omni requests from flags, price them, submit them, and follow the jobs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from artcraft_cli.core import jobs, media
from artcraft_cli.errors import CliError
from artcraft_cli.utils import bridge

MODALITIES = ("image", "video", "audio", "mesh", "splat")
PLACEHOLDER_FIELD = "image_media_tokens"
ESTIMATE_PLACEHOLDER = "mf_estimate_{}"


def build_request(
    model: str, prompt: str | None, sets: tuple[str, ...], media_specs: tuple[str, ...]
) -> dict[str, Any]:
    """The Omni request. Local files stay as Path values until estimate or submit."""
    request: dict[str, Any] = {"model": model}
    if prompt is not None:
        request["prompt"] = prompt
    for spec in sets:
        key, sep, raw = spec.partition("=")
        if not sep or not key:
            raise CliError("usage_error", f"--set expects KEY=JSON, got {spec!r}")
        try:
            request[key] = json.loads(raw)
        except json.JSONDecodeError:
            request[key] = raw
    for spec in media_specs:
        field, sep, value = spec.partition("=")
        if not sep or not field or not value:
            raise CliError("usage_error", f"--media expects FIELD=PATH|TOKEN, got {spec!r}")
        path = Path(value).expanduser()
        if path.is_file():
            media.read_image(path)  # size and type are checked before any RPC
            item: str | Path = path
        elif media.MEDIA_TOKEN_RE.fullmatch(value):
            item = value
        else:
            raise CliError(
                "usage_error", f"--media {field}: {value!r} is neither a file nor a media token"
            )
        if field.endswith("_tokens"):
            request.setdefault(field, []).append(item)
        elif field.endswith("_token"):
            if field in request:
                raise CliError("usage_error", f"--media {field} takes one value")
            request[field] = item
        else:
            raise CliError("usage_error", f"--media field must end in _token or _tokens: {field}")
    return request


def estimate(modality: str, request: dict[str, Any]) -> dict[str, Any]:
    """generate --dry-run: price only. Never uploads or submits."""
    priced: dict[str, Any] = {}
    omitted: list[str] = []
    for key, value in request.items():
        if modality == "image" and key == PLACEHOLDER_FIELD and isinstance(value, list):
            # Mirror ArtCraft's useImageCostEstimate: each local reference gets a stand-in token.
            stand_ins: list[str] = []
            placeholders = 0
            for item in value:
                if isinstance(item, Path):
                    stand_ins.append(ESTIMATE_PLACEHOLDER.format(placeholders))
                    placeholders += 1
                else:
                    stand_ins.append(item)
            priced[key] = stand_ins
        elif isinstance(value, Path):
            omitted.append(key)
        elif isinstance(value, list) and any(isinstance(item, Path) for item in value):
            omitted.append(key)
            kept = [item for item in value if not isinstance(item, Path)]
            if kept:
                priced[key] = kept
        else:
            priced[key] = value
    data = bridge.rpc("generate.estimate", {"modality": modality, "request": priced})
    return {**data, "omitted_inputs": omitted}


def run(
    modality: str,
    request: dict[str, Any],
    *,
    max_credits: int,
    token: str,
    wait: bool,
    timeout_s: float,
    download_dir: Path | None,
    force: bool,
) -> dict[str, Any]:
    """Submit, then optionally wait and download. Every error echoes the token."""
    job_ids: list[str] | None = None
    submitting = False
    try:
        if download_dir is not None:
            media.prepare_download_dir(download_dir)
        resolved = _upload_local_files(request)
        submitting = True
        result = bridge.rpc(
            "generate.submit",
            {
                "modality": modality,
                "idempotency_token": token,
                "max_credits": max_credits,
                "request": resolved,
            },
        )
        submitted = result.get("job_ids")
        if (
            not isinstance(submitted, list)
            or not submitted
            or not all(isinstance(job_id, str) for job_id in submitted)
        ):
            raise CliError("bridge_protocol_error", "generate.submit reply has no job_ids")
        submitting = False
        job_ids = list(submitted)
        if wait or download_dir is not None:
            finished = jobs.wait_for_jobs(job_ids, timeout_s=timeout_s)
            result["jobs"] = finished
            if download_dir is not None:
                result["downloads"] = jobs.download_files(finished, download_dir, force=force)
        return result
    except KeyboardInterrupt:
        if submitting:
            raise CliError(
                "outcome_unknown",
                "interrupted while submitting; the job may have been created",
                {"idempotency_token": token, "reason": "connection_lost"},
            ) from None
        if job_ids is not None:
            raise CliError(
                "job_wait_timeout",
                "interrupted after submit; the jobs were created",
                {"idempotency_token": token, "job_ids": job_ids},
            ) from None
        raise  # during local uploads: nothing was spent
    except CliError as err:
        err.details.setdefault("idempotency_token", token)
        if job_ids is not None:
            err.details.setdefault("job_ids", job_ids)
        raise


def _upload_local_files(request: dict[str, Any]) -> dict[str, Any]:
    """Replace each local Path with the media token of a fresh upload (new uuid4 key each)."""
    resolved: dict[str, Any] = {}
    for key, value in request.items():
        if isinstance(value, Path):
            resolved[key] = _upload(value)
        elif isinstance(value, list):
            resolved[key] = [_upload(item) if isinstance(item, Path) else item for item in value]
        else:
            resolved[key] = value
    return resolved


def _upload(path: Path) -> str:
    return str(media.upload(path, media.idempotency_token(None))["media_token"])
