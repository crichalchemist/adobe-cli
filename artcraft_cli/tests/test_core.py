"""CLI behaviour through the real entry point, faking only the HTTP boundary (spec §6)."""

from __future__ import annotations

from collections.abc import Callable

Run = Callable[..., tuple[int, str, str]]


# --- Output contract (spec §6.1) -------------------------------------------------------


def test_cli_without_subcommand_prints_help(run: Run) -> None:
    code, out, _ = run()
    assert code == 0
    assert "Usage: artcraft-cli" in out
