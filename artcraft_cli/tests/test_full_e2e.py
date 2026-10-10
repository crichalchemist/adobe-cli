"""Live tests against a running ArtCraft (ARTCRAFT_CLI_BRIDGE=1). Skip only when it is not
running. Spend tests also need ARTCRAFT_E2E_SPEND=1 and are capped by
ARTCRAFT_E2E_MAX_CREDITS (default 10)."""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import uuid
import zlib
from pathlib import Path
from typing import Any

import pytest
import requests

from artcraft_cli.artcraft_cli import main
from artcraft_cli.errors import CliError
from artcraft_cli.utils import bridge

pytestmark = pytest.mark.e2e
MAX_CREDITS = os.environ.get("ARTCRAFT_E2E_MAX_CREDITS", "10")
spend = pytest.mark.skipif(
    os.environ.get("ARTCRAFT_E2E_SPEND") != "1", reason="set ARTCRAFT_E2E_SPEND=1 to spend credits"
)


@pytest.fixture(scope="session")
def live() -> dict[str, Any]:
    try:
        bridge.read_discovery()
        return bridge.health()
    except CliError as err:
        if err.code == "bridge_not_running":
            pytest.skip(f"ArtCraft bridge is not running: {err.message}")
        raise


def cli_json(capsys: pytest.CaptureFixture[str], *argv: str) -> dict[str, Any]:
    """Run `artcraft-cli --json ARGV` and return its object; fail on any error."""
    code = main(["--json", *argv])
    out, _ = capsys.readouterr()
    body: dict[str, Any] = json.loads(out)
    assert code == 0, body
    return body


def enabled_image_models(capsys: pytest.CaptureFixture[str]) -> list[dict[str, Any]]:
    listed = cli_json(capsys, "models", "list", "--kind", "image")["models"]
    return [model for model in listed if not model.get("is_disabled")]


def cheapest_image_model(capsys: pytest.CaptureFixture[str], *, refs: bool) -> tuple[str, int]:
    """(model id, effective credits) of the cheapest priced image model under the cap."""
    priced: list[tuple[int, str]] = []
    refused: list[str] = []
    for model in enabled_image_models(capsys):
        if refs and not model.get("image_refs_supported"):
            continue
        code = main(
            ["--json", "generate", "image", "--model", model["model"], "--prompt", "a red cube"]
            + ["--dry-run"]
        )
        out, _ = capsys.readouterr()
        body = json.loads(out)
        if code != 0:
            refused.append(f"{model['model']}: {body['error']['code']}")
            continue
        effective = body.get("effective_credits")
        if isinstance(effective, int) and effective <= int(MAX_CREDITS):
            priced.append((effective, model["model"]))
    assert priced, f"no image model priced at or under {MAX_CREDITS} credits; refused: {refused}"
    effective, model_id = min(priced)
    return model_id, effective


def tiny_png(path: Path) -> Path:
    """Write a valid 8x8 grey PNG using only the standard library."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    rows = b"".join(b"\x00" + b"\x80" * 8 for _ in range(8))
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )
    return path


# --- Free ------------------------------------------------------------------------------


def test_ping_reports_protocol_1_and_readiness(
    live: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    body = cli_json(capsys, "ping")
    assert body["bridge"]["protocol"] == 1
    assert isinstance(body["readiness"]["credentials_synced"], bool)
    assert isinstance(body["readiness"]["session_cookie_present"], bool)
    assert "app.info" in body["ops"]


def test_whoami_matches_app_login(live: dict[str, Any], capsys: pytest.CaptureFixture[str]) -> None:
    session = cli_json(capsys, "account", "whoami")
    assert isinstance(session["logged_in"], bool)
    if session["logged_in"]:
        assert session["username"]
    print(f"\nwhoami: logged_in={session['logged_in']} username={session.get('username')}")


def test_models_list_includes_ids_estimate_accepts(
    live: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    model_id, _ = cheapest_image_model(capsys, refs=False)
    assert model_id


def test_browser_origin_is_refused(live: dict[str, Any]) -> None:
    discovery = bridge.read_discovery()
    resp = requests.get(
        f"http://127.0.0.1:{discovery['port']}/v1/health",
        headers={
            "Authorization": f"Bearer {discovery['token']}",
            "Origin": "https://evil.example",
        },
        timeout=5,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden_origin"


def test_installed_console_script_emits_parseable_json(live: dict[str, Any]) -> None:
    script = Path(sys.executable).parent / "artcraft-cli"
    done = subprocess.run(
        [str(script), "--json", "ping"], capture_output=True, text=True, timeout=30, check=False
    )
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["bridge"]["protocol"] == 1


def test_estimate_changes_no_credits_and_creates_no_job(
    live: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    before_credits = cli_json(capsys, "account", "credits")["sum_total_credits"]
    before_jobs = cli_json(capsys, "jobs", "list", "--all", "--limit", "200")["jobs"]

    cheapest_image_model(capsys, refs=False)

    assert cli_json(capsys, "account", "credits")["sum_total_credits"] == before_credits
    assert cli_json(capsys, "jobs", "list", "--all", "--limit", "200")["jobs"] == before_jobs


# --- Spend -----------------------------------------------------------------------------


@spend
@pytest.mark.spend
def test_cheapest_image_completes_and_downloads_every_file(
    live: dict[str, Any], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    model_id, _ = cheapest_image_model(capsys, refs=False)
    body = cli_json(
        capsys, "generate", "image", "--model", model_id, "--prompt", "a red cube",
        "--max-credits", MAX_CREDITS, "--download", str(tmp_path),
    )  # fmt: skip
    assert body["jobs"] and all(job["status"] == "succeeded" for job in body["jobs"])
    expected = len({file["media_token"] for job in body["jobs"] for file in job["result"]["files"]})
    assert len(body["downloads"]) == expected > 0
    assert all(Path(item["path"]).stat().st_size > 0 for item in body["downloads"])


@spend
@pytest.mark.spend
def test_retry_with_returned_token_replays_without_second_charge(
    live: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    model_id, _ = cheapest_image_model(capsys, refs=False)
    token = str(uuid.uuid4())
    argv = ["generate", "image", "--model", model_id, "--prompt", "a blue cube"]
    argv += ["--max-credits", MAX_CREDITS, "--idempotency-token", token, "--wait"]

    first = cli_json(capsys, *argv)
    balance = cli_json(capsys, "account", "credits")["sum_total_credits"]
    again = cli_json(capsys, *argv)

    assert first["replayed"] is False
    assert again["replayed"] is True
    assert again["job_ids"] == first["job_ids"]
    assert again["replayed_from"] == {"modality": "image", "model": model_id}
    assert cli_json(capsys, "account", "credits")["sum_total_credits"] == balance


@spend
@pytest.mark.spend
def test_uploaded_image_is_usable_as_generation_reference(
    live: dict[str, Any], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    model_id, _ = cheapest_image_model(capsys, refs=True)
    reference = tiny_png(tmp_path / "ref.png")
    body = cli_json(
        capsys, "generate", "image", "--model", model_id, "--prompt", "same, but red",
        "--media", f"image_media_tokens={reference}", "--max-credits", MAX_CREDITS, "--wait",
    )  # fmt: skip
    assert all(job["status"] == "succeeded" for job in body["jobs"])
