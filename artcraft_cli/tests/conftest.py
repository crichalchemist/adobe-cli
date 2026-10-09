"""Fixtures. Unit tests fake only the HTTP boundary (requests), the clock and the OS."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest

from artcraft_cli.artcraft_cli import main


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Iterator[Callable[..., tuple[int, str, str]]]:
    """Run the real console entry point; returns (exit_code, stdout, stderr)."""

    def invoke(*argv: str) -> tuple[int, str, str]:
        code = main(list(argv))
        out, err = capsys.readouterr()
        return code, out, err

    yield invoke
