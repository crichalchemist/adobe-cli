"""Live tests against a running ArtCraft (ARTCRAFT_CLI_BRIDGE=1). Skip only when it is not
running. Spend tests also need ARTCRAFT_E2E_SPEND=1 and are capped by
ARTCRAFT_E2E_MAX_CREDITS (default 10)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import requests

from artcraft_cli.artcraft_cli import main
from artcraft_cli.errors import CliError
from artcraft_cli.utils import bridge

pytestmark = pytest.mark.e2e
MAX_CREDITS = os.environ.get("ARTCRAFT_E2E_MAX_CREDITS", "10")


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
