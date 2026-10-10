"""A line-oriented REPL: each line runs as one artcraft-cli invocation (spec §3.6)."""

from __future__ import annotations

import shlex
from collections.abc import Callable

import click

PROMPT = "artcraft> "
EXIT_WORDS = frozenset({"exit", "quit"})


def run_repl(dispatch: Callable[[list[str]], int], read_line: Callable[[str], str] = input) -> None:
    """Read lines until exit, quit or EOF. Errors print and the loop continues."""
    try:
        import readline  # noqa: F401  # line editing and in-memory history for input()
    except ImportError:  # not available on Windows
        pass
    while True:
        try:
            line = read_line(PROMPT).strip()
        except EOFError:
            click.echo()
            return
        except KeyboardInterrupt:
            click.echo()
            continue
        if line in EXIT_WORDS:
            return
        if not line:
            continue
        try:
            argv = shlex.split(line)
        except ValueError as exc:
            click.echo(f"error[usage_error]: {exc}", err=True)
            continue
        dispatch(argv)
