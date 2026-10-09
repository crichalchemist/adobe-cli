# Contributing to artcraft-cli

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pre-commit install -f
```

## Checks

```bash
.venv/bin/pytest -m "not e2e"                            # unit tests, no ArtCraft needed
PATH="$PWD/.venv/bin:$PATH" pre-commit run --all-files   # ruff, ruff-format, hygiene hooks, mypy --strict
```

CI runs the same checks on Python 3.10 and 3.13 for every push and pull request.

Live tests need ArtCraft running with `ARTCRAFT_CLI_BRIDGE=1`. They skip when it isn't running:

```bash
.venv/bin/pytest -m e2e -v -s
ARTCRAFT_E2E_SPEND=1 ARTCRAFT_E2E_MAX_CREDITS=10 .venv/bin/pytest -m spend -v -s   # spends credits
```

## Conventions

**Code**
- `from __future__ import annotations` in every module.
- Type hints on public functions; mypy --strict covers the tests too.
- Functional style. Classes only for exceptions.
- No bare `except`.
- Named constants for timeouts and limits.

**Structure**
- `artcraft_cli/utils/bridge.py` is the only module that talks to the bridge.
- Commands in `artcraft_cli.py` stay thin and call into `artcraft_cli/core/`.
- Every error is a `CliError` with a stable snake_case code listed in `errors.HINTS`.

**Tests:** name each test after the outcome it protects. Fake only boundaries: the HTTP session, `requests.get`, the clock and the OS.

**Commit messages:** `type: imperative summary` (feat, fix, docs, test, chore), under 72 characters, with no agent co-author trailers.

## Changing the bridge contract

The wire contract covers the ops, args, error codes and the discovery file. It is defined in §4.3 and §5 of `docs/superpowers/specs/2026-10-09-artcraft-cli-bridge-design.md`, and both sides implement it: the Rust bridge in the ArtCraft fork, and this CLI.

- **No protocol bump:** adding new ops, codes or fields.
- **Protocol bump required:** renaming or removing anything, or changing what something means.

Change the spec first, then both sides.
