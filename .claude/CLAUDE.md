# artcraft-cli — agent rules

artcraft-cli is a Python CLI and Claude Code plugin. It drives a locally running ArtCraft desktop app through a loopback bridge that is patched into the user's ArtCraft fork.

- Design: `docs/superpowers/specs/2026-10-09-artcraft-cli-bridge-design.md`. The wire contract is §4.3 (discovery file) and §5 (ops, envelope, error codes). Change it only together with the user and the `artcraft` session.
- Plans: `docs/superpowers/plans/`.

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'   # once
.venv/bin/pre-commit install -f                               # once; replaces the old wrapper hook
.venv/bin/pytest -m "not e2e"                                 # unit tests, no ArtCraft needed
.venv/bin/pytest -m e2e -v -s                                 # live; needs ArtCraft with ARTCRAFT_CLI_BRIDGE=1
ARTCRAFT_E2E_SPEND=1 .venv/bin/pytest -m spend -v -s          # spends credits; cap ARTCRAFT_E2E_MAX_CREDITS (default 10)
PATH="$PWD/.venv/bin:$PATH" pre-commit run --all-files        # ruff, ruff-format, hygiene hooks, mypy --strict
```

Commit with `PATH="$PWD/.venv/bin:$PATH" git commit …`. Without it, the local mypy hook can't find the venv.

## Module map

```
artcraft_cli/
  artcraft_cli.py    Click root `cli` and every command; main() renders errors (exit 0 or 1)
  errors.py          CliError(code, message, details) and HINTS {code: (hint, retryable)}
  repl.py            stdlib REPL behind `artcraft-cli repl`
  utils/bridge.py    the ONLY module that reads the discovery file or calls the bridge
  core/              one module per op domain: app, account, models, generate, jobs, media, settings
  tests/             conftest (fakes), test_bridge, test_core, test_full_e2e (auto-skips)
```

## Conventions

**Code**
- `from __future__ import annotations` in every module.
- Type hints on public functions. mypy --strict covers the tests too.
- Functional style. Classes only for exceptions; tests may use small fakes.
- No bare `except`.
- Named constants for timeouts and limits.
- Validate at boundaries.

**Commands and errors**
- Commands stay thin: parse flags, call `core`, then `emit()`.
- Errors are `CliError(code, …)`, and every code must appear in `errors.HINTS`.
- The bridge token never appears in output, logs, exception messages or reprs.

**Tests**
- Name tests after outcomes.
- Fake only the boundaries: the requests session via `bridge._session`, `requests.get`, `time`, `os`. Never fake core logic.

**Commits**
- `type: imperative summary`, under 72 characters.
- No `Co-Authored-By` or other agent trailer.

**MCP:** no project MCP server is needed; the user's global servers cover this repo.

## Bridge SOP

1. The user launches ArtCraft from `/Volumes/Containers/artcraft` (branch `feature/cli-bridge`) with `ARTCRAFT_CLI_BRIDGE=1 ./script/artcraft/unix_dev.sh`, then logs in inside the app.
2. The bridge writes `~/Artcraft/state/cli_bridge.json` (mode 0600, with port, pid, token and protocol 1). The CLI reads it on every call.
3. Run `artcraft-cli --json ping`, then `artcraft-cli --json account whoami`.
4. Generation:
   - Always run `--dry-run` first, then submit with `--max-credits N`.
   - After `outcome_unknown`, never resubmit. Reconcile with `jobs list --remote --all`.
5. Each milestone's live checklist is in spec §10.3 and in `docs/superpowers/plans/2026-10-09-artcraft-cli-python.md`.

## Collaboration

- The `artcraft` Claude session owns the Rust bridge in `/Volumes/Containers/artcraft`. This repo owns the CLI, the plugin and the skill.
- Plane workspace `crichalchemist`: project ACLI (this repo) and ARTC (the fork).
