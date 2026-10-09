# artcraft-cli (Python CLI + repo pivot) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pivot this repo from the Adobe harnesses to `artcraft-cli`, a Python CLI and Claude Code plugin that drives a locally running ArtCraft app through its loopback bridge. The CLI covers ping, app info, account, models, generation with a hard credit ceiling, jobs, media and settings, plus a REPL.

**Architecture:**
- `artcraft_cli/utils/bridge.py` is the only module that reads the discovery file or talks to the bridge. Every request is a `POST /v1/rpc {op, args}` or a `GET /v1/health`, and the envelope is always parsed before the HTTP status.
- `artcraft_cli/core/*.py` holds one small module per op domain. `artcraft_cli/artcraft_cli.py` holds the Click tree.
- `main()` renders every error as `{"error": {code, message, hint, retryable, details?}}`, using the `errors.HINTS` table.
- Tests fake only the HTTP boundary, the clock and the OS.

**Tech Stack:** Python 3.10+, click ≥ 8.2, requests ≥ 2.31, setuptools ≥ 77 (PEP 621 `pyproject.toml`), pytest, ruff, mypy --strict, pre-commit, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-09-artcraft-cli-bridge-design.md`, approved at bc7b57d. Read §3 (pivot), §5 (wire contract), §6 (CLI) and §10 (tests and milestones) before starting. The Rust bridge has its own plan, `docs/superpowers/plans/2026-10-09-artcraft-bridge-rust.md`, owned by the `artcraft` session. This plan touches only this repo.

**Validation:** every code block in this plan was replayed in order in a scratch copy of the repo, applying each edit exactly as written:
- every "expected FAIL" failed and every "expected PASS" passed
- every commit passed the full unit suite and pre-commit
- the final state passed on Python 3.10 and 3.13

**Plane:** project ACLI (workspace `crichalchemist`). Each task maps to the work item titled `T<n>: <task title>` under its milestone.

## Global Constraints

**Runtime and packaging**
- Python ≥ 3.10 (`requires-python = ">=3.10"`); the code must pass on 3.10 and 3.13, matching the CI matrix.
- Runtime dependencies are exactly `click>=8.2` and `requests>=2.31`. Dev extras: `pytest`, `ruff`, `mypy`, `types-requests`, `pre-commit`. No other dependency; the REPL is stdlib only.
- Distribution `artcraft-cli` 0.1.0, import package `artcraft_cli`, `license = "Elastic-2.0"`.
- Console script: `artcraft-cli = "artcraft_cli.artcraft_cli:main"`, with `main(argv: list[str] | None = None) -> int`.

**Code conventions**
- `from __future__ import annotations` in every module.
- Type hints on public functions; `mypy --strict` over all of `artcraft_cli`, tests included.
- ruff lint (`E,F,W,I,B,UP`) and ruff-format, line length 100.
- Functional style; classes only for exceptions (test fakes excepted). No bare `except`. Named constants for timeouts and limits.

**Bridge transport**
- `utils/bridge.py` is the only module that reads `~/Artcraft/state/cli_bridge.json` or calls the bridge.
- Bridge URLs are always `http://127.0.0.1:{port}`.
- The session has `trust_env = False`. The `Authorization` header is set per request, never on the session.
- CDN downloads use plain `requests.get`, which carries no token.
- The bridge token never appears in output, logs, exception messages or `repr`.

**Timing**
- Timeouts: `CONNECT_TIMEOUT = 3`, `READ_TIMEOUT = 150`, `HEALTH_TIMEOUT = 5`, `NOT_SYNCED_WAIT_S = 5`.
- `jobs wait` polls every 5 s. It sets `include_remote` at most once every 60 s, plus one final remote call once every job has succeeded (spec §6.4). Its default `--timeout` is 900.

**Output**
- `--json` is a root option and goes before the subcommand. A success prints exactly one compact JSON object on stdout and exits 0.
- A JSON error prints `{"error": {...}}` on stdout and exits 1.
- Without `--json`, errors go to stderr as `error[<code>]: <message>` plus `hint: …`.

**Contract:** spec §4.3 and §5 are fixed. This plan never changes them; amendments live in the appendix.

**Tests**
- Every test named in spec §10.2 exists here as `test_<spec name>`, because pytest only collects `test_*`.
- Tests are named after outcomes. Fake only boundaries: `bridge._session` (plus resetting the cached `bridge._sess`), `bridge.DISCOVERY_PATH` pointed at a tmp file (spec §10.2), `requests.get`, `time.monotonic`/`time.sleep`, `os.getuid`. Never mock core logic.

**Working directory and tools**
- Work in place in `/Volumes/Containers/adobe-cli`, on branch `pivot/artcraft-cli` from Task 1 on. Do not create a git worktree. The folder keeps its name; renaming it would orphan the project's Claude memory.
- This plan and the Rust plan are committed on `main` before Task 1 starts.
- Run tools as `.venv/bin/<tool>`. Commit as `PATH="$PWD/.venv/bin:$PATH" git commit …` so the local mypy hook resolves.
- In this environment an rtk hook rewrites some shell commands. Prefix `rtk proxy` where exact output matters (grep, git grep). `curl` is blocked; use the Python snippets given.

**Commits**
- Messages follow `type: imperative summary` (feat|fix|docs|test|chore), under 72 characters.
- Nothing follows the message: no `Co-Authored-By:`, no `Claude-Session:`, no other agent trailer, even if a harness reminder asks for one. User Rule 14 overrides it.
- Stage only the paths each commit step lists. Never stage `.serena/`, `.remember/`, `.claude/settings.local.json` or anything unlisted.

**STOP gates and live checks**
- These outward or irreversible steps are STOP gates: pushing the tag or branch, merging to `main`, `gh repo rename`, uninstalling packages, deleting the CEP symlink, and anything that spends ArtCraft credits.
- At a STOP gate the controller asks the user and runs the step only after an explicit yes. Subagents never run STOP steps; a task marked **Executor: controller** is run by the controller session itself.
- Live checks need ArtCraft running from `/Volumes/Containers/artcraft` on `feature/cli-bridge`, with the matching ARTC milestone finished.

---

## Milestone M0 — Baseline (pivot + workspace tooling)

Spec §3.1, §3.2, §3.3, §10.3 M0. When M0 ends, the branch holds no Adobe code. It has the packaging, hooks, CI and agent docs, plus a help smoke test, and CI is green on the pushed branch.

### Task 1: Tag the Adobe baseline and branch

**Executor:** controller session, with the user where a step says so. Subagents do not run this task.

Step 3 is a STOP gate.

- [ ] **Step 1: Confirm the starting state**

```bash
git status --short && git log --oneline -1 0180921
```

Expected: `M .gitignore` (the user's `.remember/` line), `?? .serena/`, and `0180921 feat: add marketplace configuration for Adobe CLI plugins`.

- [ ] **Step 2: Tag the last Adobe commit**

```bash
git tag -a adobe-final -m "Last commit with the Adobe harnesses" 0180921 && git rev-parse --short 'adobe-final^{commit}'
```

Expected: `0180921` (an annotated tag; this machine's git config requires a tag message and may sign it)

- [ ] **Step 3: STOP — controller and user only.** Ask the user: "Push tag `adobe-final` (commit 0180921) to origin?" Run only on an explicit yes:

```bash
git push origin adobe-final
```

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore .remember"
```

Expected: the commit is created.

- [ ] **Step 5: Create the pivot branch**

```bash
git switch -c pivot/artcraft-cli && git branch --show-current
```

Expected: `pivot/artcraft-cli`

### Task 2: Delete the Adobe harnesses and rebrand the plugin

**Files:**
- Modify: `.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `hooks/session-start`
- Delete: `premiere-pro`
- Delete: `illustrator`
- Delete: `acrobat`
- Delete: `CLAUDE.md`
- Delete: `skills/SKILL.md`

**Interfaces:**
- Produces: plugin `artcraft-cli` 0.1.0 (`.claude-plugin/plugin.json`), marketplace `artcraft-cli-marketplace`, and a SessionStart hook that prints `hookSpecificOutput.additionalContext`. `hooks/hooks.json` and `hooks/run-hook.cmd` stay unchanged.

- [ ] **Step 1: Delete the Adobe-era files**

```bash
git rm -r -q premiere-pro illustrator acrobat CLAUDE.md skills/SKILL.md
```

- [ ] **Step 2: Rebrand the plugin metadata and rewrite the SessionStart hook**

Replace the whole of `.claude-plugin/plugin.json` with:

````json
{
  "name": "artcraft-cli",
  "description": "Drive a locally running ArtCraft desktop app (image, video, audio and 3D generation, jobs, media) from scripts and AI agents.",
  "version": "0.1.0",
  "author": {
    "name": "artcraft-cli contributors"
  },
  "license": "Elastic-2.0",
  "keywords": [
    "artcraft",
    "generative-ai",
    "automation",
    "cli",
    "agents"
  ]
}
````

Replace the whole of `.claude-plugin/marketplace.json` with:

````json
{
  "name": "artcraft-cli-marketplace",
  "description": "Marketplace for artcraft-cli, a CLI and agent skill for the ArtCraft desktop app",
  "owner": {
    "name": "crichalchemist",
    "email": "crichalchemist@gmail.com"
  },
  "plugins": [
    {
      "name": "artcraft-cli",
      "description": "Drive a locally running ArtCraft desktop app (image, video, audio and 3D generation, jobs, media) from scripts and AI agents.",
      "version": "0.1.0",
      "source": "./",
      "author": {
        "name": "artcraft-cli contributors"
      },
      "license": "Elastic-2.0",
      "keywords": [
        "artcraft",
        "generative-ai",
        "automation",
        "cli",
        "agents"
      ]
    }
  ]
}
````

Replace the whole of `hooks/session-start` with:

````bash
#!/usr/bin/env bash
# SessionStart hook: tells Claude Code sessions how to use artcraft-cli.
cat <<'EOF'
{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "artcraft-cli drives a locally running ArtCraft desktop app (started with ARTCRAFT_CLI_BRIDGE=1). Before using it, read skills/artcraft-cli/SKILL.md and run `artcraft-cli --json ping`."}}
EOF
````

- [ ] **Step 3: Check the hook output and the JSON files**

```bash
bash hooks/session-start | python3 -m json.tool > /dev/null && python3 -m json.tool .claude-plugin/plugin.json > /dev/null && python3 -m json.tool .claude-plugin/marketplace.json > /dev/null && test -x hooks/session-start && echo ok
```

Expected: `ok`

- [ ] **Step 4: Check that no harness files remain tracked**

```bash
git ls-files | rtk proxy grep -c -E '^(premiere-pro|illustrator|acrobat)/'
```

Expected: `0`

- [ ] **Step 5: Commit**

```bash
git add .claude-plugin/plugin.json .claude-plugin/marketplace.json hooks/session-start
git commit -m "chore: remove Adobe harnesses and rebrand the plugin"
```

Expected: the commit is created.

### Task 3: Package skeleton with the help smoke test

**Files:**
- Create: `pyproject.toml`
- Create: `artcraft_cli/__init__.py`
- Create: `artcraft_cli/tests/__init__.py`
- Create: `artcraft_cli/tests/conftest.py`
- Create: `artcraft_cli/tests/test_core.py`
- Create: `artcraft_cli/artcraft_cli.py`
- Create: `artcraft_cli/__main__.py`

**Interfaces:**
- Produces:
  - `artcraft_cli.__version__ = "0.1.0"` and `artcraft_cli.SUPPORTED_BRIDGE_PROTOCOL = 1`.
  - `artcraft_cli.artcraft_cli.cli`, a `click.Group` whose root option `--json` is stored as the param `as_json`.
  - `artcraft_cli.artcraft_cli.main(argv: list[str] | None = None) -> int`. A bare invocation prints help and returns 0.
  - Test fixture `run(*argv: str) -> tuple[int, str, str]`, which returns (exit code, stdout, stderr) from the real `main`.

- [ ] **Step 1: Create the virtual environment**

```bash
python3 -m venv .venv && .venv/bin/python --version
```

Expected: `Python 3.13.x` (any 3.10+ works)

- [ ] **Step 2: Write the package metadata and the failing smoke test**

Create `pyproject.toml`:

````toml
[build-system]
requires = ["setuptools>=77"]
build-backend = "setuptools.build_meta"

[project]
name = "artcraft-cli"
version = "0.1.0"
description = "Drive a locally running ArtCraft desktop app from scripts and AI agents."
readme = "README.md"
license = "Elastic-2.0"
requires-python = ">=3.10"
dependencies = ["click>=8.2", "requests>=2.31"]

[project.optional-dependencies]
dev = ["pytest", "ruff", "mypy", "types-requests", "pre-commit"]

[project.scripts]
artcraft-cli = "artcraft_cli.artcraft_cli:main"

[tool.setuptools.packages.find]
include = ["artcraft_cli*"]

[tool.pytest.ini_options]
testpaths = ["artcraft_cli/tests"]
markers = [
  "e2e: needs ArtCraft running with ARTCRAFT_CLI_BRIDGE=1",
  "spend: spends ArtCraft credits; also needs ARTCRAFT_E2E_SPEND=1",
]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP"]

[tool.mypy]
python_version = "3.10"
strict = true
packages = ["artcraft_cli"]
````

Create `artcraft_cli/__init__.py`:

````python
"""artcraft-cli: drive a locally running ArtCraft desktop app."""

from __future__ import annotations

__version__ = "0.1.0"
SUPPORTED_BRIDGE_PROTOCOL = 1
````

Create `artcraft_cli/tests/__init__.py` as an empty file.

Create `artcraft_cli/tests/conftest.py`:

````python
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
````

Create `artcraft_cli/tests/test_core.py`:

````python
"""CLI behaviour through the real entry point, faking only the HTTP boundary (spec §6)."""

from __future__ import annotations

from collections.abc import Callable

Run = Callable[..., tuple[int, str, str]]


# --- Output contract (spec §6.1) -------------------------------------------------------


def test_cli_without_subcommand_prints_help(run: Run) -> None:
    code, out, _ = run()
    assert code == 0
    assert "Usage: artcraft-cli" in out
````

- [ ] **Step 3: Install the package and dev tools (editable)**

```bash
.venv/bin/pip install -q -e '.[dev]' && .venv/bin/pip show artcraft-cli | head -2
```

Expected: `Name: artcraft-cli` / `Version: 0.1.0`

- [ ] **Step 4: Run the smoke test to verify it fails**

Run: `.venv/bin/pytest artcraft_cli/tests/test_core.py -v`

Expected: FAIL — the test module cannot import yet: `ModuleNotFoundError: No module named 'artcraft_cli.artcraft_cli'`

- [ ] **Step 5: Write the minimal entry point**

Create `artcraft_cli/artcraft_cli.py`:

````python
"""artcraft-cli command tree. Commands parse flags, call core, and emit one result."""

from __future__ import annotations

import sys

import click


@click.group()
@click.option("--json", "as_json", is_flag=True, help="Print exactly one JSON object on stdout.")
def cli(as_json: bool) -> None:
    """Drive a locally running ArtCraft app (launched with ARTCRAFT_CLI_BRIDGE=1)."""


def main(argv: list[str] | None = None) -> int:
    """Console entry point. Returns the exit code: 0 success, 1 any error."""
    args = sys.argv[1:] if argv is None else argv
    try:
        cli.main(args=args, prog_name="artcraft-cli", standalone_mode=False)
    except click.exceptions.NoArgsIsHelpError as exc:
        click.echo(exc.format_message())
        return 0
    except click.ClickException as exc:
        exc.show()
        return 1
    return 0
````

Create `artcraft_cli/__main__.py`:

````python
"""Allow `python -m artcraft_cli`."""

from __future__ import annotations

from artcraft_cli.artcraft_cli import main

raise SystemExit(main())
````

- [ ] **Step 6: Run the smoke test to verify it passes**

Run: `.venv/bin/pytest artcraft_cli/tests/test_core.py -v`

Expected: PASS — 1 passed

- [ ] **Step 7: Check the console script and `python -m`**

```bash
.venv/bin/artcraft-cli | head -1 && .venv/bin/python -m artcraft_cli | head -1
```

Expected: `Usage: artcraft-cli [OPTIONS] COMMAND [ARGS]...` twice

- [ ] **Step 8: Lint, format-check and type-check (pre-commit is not installed until Task 4)**

```bash
.venv/bin/ruff check artcraft_cli && .venv/bin/ruff format --check artcraft_cli && .venv/bin/mypy artcraft_cli
```

Expected: `All checks passed!`, `… files already formatted`, `Success: no issues found in 6 source files`

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml artcraft_cli/__init__.py artcraft_cli/__main__.py artcraft_cli/artcraft_cli.py artcraft_cli/tests/__init__.py artcraft_cli/tests/conftest.py artcraft_cli/tests/test_core.py
git commit -m "feat: add artcraft_cli package skeleton with help smoke test"
```

Expected: the commit is created.

`.venv/`, `.mypy_cache/` and `.ruff_cache/` stay untracked. Task 4 ignores them.

### Task 4: Pre-commit hooks, CI and ignores

**Files:**
- Create: `.pre-commit-config.yaml`
- Create: `.github/workflows/ci.yml`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `.pre-commit-config.yaml`, which runs ruff-check --fix, ruff-format (Python files only, so it never rewrites the code quoted in these plans), the pre-commit-hooks hygiene set, and a local `mypy artcraft_cli` hook (`language: system`). Also CI at `.github/workflows/ci.yml` (Python 3.10 and 3.13: install, pre-commit, `pytest -m "not e2e"`), and the `.gitignore` entries `.venv/`, `.ruff_cache/`, `.mypy_cache/` and `.serena/`.

- [ ] **Step 1: Add the hook config, CI workflow and ignores**

Create `.pre-commit-config.yaml`:

````yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.17.0
    hooks:
      - id: ruff-check
        args: [--fix]
      - id: ruff-format
        types_or: [python, pyi]  # keep it out of the code fragments quoted in docs/*.md
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-added-large-files
      - id: check-symlinks
  - repo: local
    hooks:
      - id: mypy
        name: mypy (strict, installed dev env)
        entry: mypy artcraft_cli
        language: system
        types: [python]
        pass_filenames: false
````

Create `.github/workflows/ci.yml`:

````yaml
name: ci

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"
      - run: pre-commit run --all-files
      - run: pytest -m "not e2e"
````

Append to `.gitignore`:

````text
# local tooling
.venv/
.ruff_cache/
.mypy_cache/
.serena/
````

- [ ] **Step 2: Replace the old wrapper hook with pre-commit's own (`-f` drops the wrapper, so hooks don't run twice)**

```bash
.venv/bin/pre-commit install -f
```

Expected: `pre-commit installed at .git/hooks/pre-commit`

- [ ] **Step 3: Pin the hook revs to the latest releases**

```bash
.venv/bin/pre-commit autoupdate
```

Expected: each repo reports `already up to date!` (ruff-pre-commit v0.17.0, pre-commit-hooks v6.0.0) or is bumped. Keep whatever it writes; those become the pinned revs.

- [ ] **Step 4: Run every hook on every file**

```bash
PATH="$PWD/.venv/bin:$PATH" pre-commit run --all-files
```

Expected: every hook `Passed`, and check-symlinks `(no files to check)Skipped`. If a hygiene hook rewrites a tracked file (for example trailing whitespace in a doc), run it again until clean and add that file to this commit. Exception: if any hook changes a file under `docs/superpowers/`, revert it with `git checkout -- docs/superpowers` and STOP; the plans quote exact text that later tasks match against.

- [ ] **Step 5: Commit**

```bash
.venv/bin/pytest -m "not e2e" -q
git add .pre-commit-config.yaml .github/workflows/ci.yml .gitignore
PATH="$PWD/.venv/bin:$PATH" git commit -m "chore: add pre-commit hooks and CI quality gates"
```

Expected: the unit suite passes, then every pre-commit hook passes and the commit is created. If a hook rewrites a file, `git add` it again and re-run the commit; never pass `--no-verify`.

### Task 5: Agent rules, skill and rebranded docs

**Files:**
- Create: `.claude/CLAUDE.md`
- Create: `skills/artcraft-cli/SKILL.md`
- Modify: `README.md`
- Modify: `CONTRIBUTING.md`

**Interfaces:**
- Produces:
  - `.claude/CLAUDE.md`, the agent rules. `.gemini/GEMINI.md` and `.agents/AGENTS.md` are symlinks to it.
  - `skills/artcraft-cli/SKILL.md`, the only skill. Its error table matches `errors.HINTS` as Task 7 writes it.
  - Rebranded `README.md` and `CONTRIBUTING.md`.

- [ ] **Step 1: Write the agent rules, public docs and the skill**

Create `.claude/CLAUDE.md`:

````markdown
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
````

Replace the whole of `README.md` with:

````markdown
# artcraft-cli

artcraft-cli lets scripts and AI agents drive a locally running [ArtCraft](https://github.com/storytold/artcraft) desktop app. With your own ArtCraft account you can:
- price and generate images, video, audio and 3D
- follow the generation jobs
- manage your library media

Every command prints one JSON object.

> **Status:** in development. It needs an ArtCraft build that carries the CLI bridge patch, which upstream ArtCraft does not include.

## How it works

The ArtCraft desktop app has no external API. A small patch to a local ArtCraft build adds an opt-in HTTP bridge on `127.0.0.1`.
- The bridge exposes a fixed list of operations.
- Each operation is backed by ArtCraft's own code, so it uses the app's login and credits.
- `artcraft-cli` finds the bridge through `~/Artcraft/state/cli_bridge.json`. That file is owner-only and is rewritten with a fresh token on every launch.

## Requirements

- macOS or Linux, Python 3.10+
- ArtCraft built from a fork that carries the bridge patch, started with `ARTCRAFT_CLI_BRIDGE=1`
- An ArtCraft account, logged in inside the app

## Install

```bash
git clone https://github.com/crichalchemist/artcraft-cli && cd artcraft-cli
pipx install -e .        # or: python3 -m pip install -e .
```

## Start ArtCraft with the bridge

```bash
cd /path/to/your/artcraft-fork
ARTCRAFT_CLI_BRIDGE=1 ./script/artcraft/unix_dev.sh
```

Without the variable, nothing listens and no file is written.

## Quick start

```bash
artcraft-cli --json ping                                   # bridge, readiness, supported ops
artcraft-cli --json account whoami
artcraft-cli --json models list --kind image
artcraft-cli --json generate image --model <id> --prompt "a red cube" --dry-run   # price only
artcraft-cli --json generate image --model <id> --prompt "a red cube" \
  --max-credits 10 --download ./out                        # submit, wait, download
artcraft-cli --json jobs list --all
```

- `--json` goes before the subcommand.
- Every command prints exactly one JSON object.
- Errors print `{"error": {"code", "message", "hint", "retryable", "details"?}}` and exit with code 1.
- [`skills/artcraft-cli/SKILL.md`](skills/artcraft-cli/SKILL.md) lists the full command tree and every error code.

## Spending safety

- `generate` needs exactly one of these:
  - `--dry-run`, which only prices the generation.
  - `--max-credits N`, which refuses if the estimate is above N or your balance is too low.
- Every submit carries an idempotency token. It is either the `--idempotency-token` you pass or a fresh UUID, and it is echoed back. Re-running with the same token replays the original jobs instead of charging again.
- `outcome_unknown` means the submit may have been accepted. Do not resubmit. Find the job with `artcraft-cli --json jobs list --remote --all`.

## What you will see in the app

- Bridge jobs appear in ArtCraft's task panel and generation feeds.
- They trigger ArtCraft's toasts, sounds and credit refresh. `artcraft-cli settings set play_sounds false` silences them.

## Security model

The bridge only accepts requests that:
- arrive on `127.0.0.1`
- carry a loopback `Host` header
- carry no browser `Origin`/`Sec-Fetch-*` headers
- present the per-launch 256-bit token from the owner-only discovery file

Any process running as your OS user can read that file. That is the same trust level as ArtCraft's own credential files.

ArtCraft logs request bodies, prompts included, at debug level. If prompts must stay out of the log, make sure `RUST_LOG` does not contain `debug` when you launch it.

## License

- artcraft-cli is licensed under the [Elastic License 2.0](LICENSE).
- ArtCraft itself is "fair source" under its own license, which restricts using the ArtCraft name to promote a business.
- This project is an unofficial, free tool and is not affiliated with ArtCraft or its makers.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
````

Replace the whole of `CONTRIBUTING.md` with:

````markdown
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
````

Create `skills/artcraft-cli/SKILL.md`:

````markdown
---
name: artcraft-cli
description: Use when driving the ArtCraft desktop app from scripts or agents — generating images, video, audio, 3D meshes or splats with the user's ArtCraft account, tracking generation jobs, uploading/listing/downloading library media, or reading app, account, credit and settings state. Requires ArtCraft running with ARTCRAFT_CLI_BRIDGE=1.
agent_guidance: >-
  Run `artcraft-cli --json ping` first, then `artcraft-cli --json account whoami`.
  Always pass --json, before the subcommand (`artcraft-cli --json <cmd>`). Price with
  --dry-run before spending, and always pass --max-credits when submitting. After an
  outcome_unknown error, never resubmit: run `artcraft-cli --json jobs list --remote --all`
  and match on model and a created_at at or after the submit time (remote entries carry no
  idempotency token). After a replay (`replayed: true`), compare `replayed_from` with your
  request. Use `jobs wait` or `generate --wait`, never hand-written poll loops. Use absolute
  paths.
---

# artcraft-cli

artcraft-cli drives a locally running ArtCraft desktop app through its opt-in loopback bridge.
- With `--json`, every command prints exactly one JSON object.
- Errors print `{"error": {"code", "message", "hint", "retryable", "details"?}}` and exit 1.

## Prerequisites

1. ArtCraft is built with the CLI bridge patch and started with `ARTCRAFT_CLI_BRIDGE=1 ./script/artcraft/unix_dev.sh`.
2. The user is logged in inside the app: `account whoami` shows `logged_in: true`.
3. `artcraft-cli --json ping` lists the ops that the running bridge supports.

## Commands

```
artcraft-cli [--json]
  ping                                   bridge {port,pid,app_version,protocol}, readiness, ops
  app info
  account whoami | credits | subscription
  models list --kind image|video
  generate <image|video|audio|mesh|splat> --model M [--prompt P] [--set KEY=JSON]...
           [--media FIELD=PATH|TOKEN]... (--max-credits N | --dry-run)
           [--idempotency-token UUID] [--wait [--timeout S]] [--download DIR [--force]]
  jobs list [--all] [--remote] [--limit N]
  jobs get JOB... [--remote]
  jobs wait JOB... [--timeout S=900] [--download DIR [--force]]
  jobs dismiss JOB
  media upload FILE [--idempotency-token UUID]
  media get TOKEN
  media list [--class C]... [--page N] [--page-size N] [--oldest-first]
  media download TOKEN [--out DIR] [--force]
  settings get
  settings set play_sounds|auto_download true|false
  repl
```

### generate

**Building the request**
- `--set KEY=JSON` sets any Omni request field. The value is parsed as JSON, falling back to a plain string.
- `--media FIELD=PATH|TOKEN`:
  - An existing file path is uploaded and replaced by its media token.
  - Fields ending in `_tokens` collect a list; fields ending in `_token` take one value.
  - Images only: PNG, JPEG or GIF, at most 20 MiB.

**Pricing and spending**
- `--dry-run` prices the request without uploading or submitting.
  - Local image references in `image_media_tokens` are priced with placeholders.
  - Other local files are left out and listed in `omitted_inputs`.
- `--max-credits N` refuses with:
  - `cost_exceeds_limit` if the estimate is above N
  - `insufficient_credits` if your balance is lower than the estimate

**Idempotency**
- Every result and error echoes `idempotency_token`.
- Re-running with the same `--idempotency-token` replays (`replayed: true`) without charging again.

**Waiting and downloads**
- `--wait` waits for every job.
- `--download DIR` implies `--wait` and saves each result file as `DIR/<media_token><ext>`.

**Model coverage**
- Only models on ArtCraft's own route work. The legacy image models `recraft_3`, `flux_pro_kontext_max`, `flux_dev_juggernaut` and `flux_pro_1` return `unsupported_route`.
- `models list` covers image and video only.

### Output shapes

| Command | Prints |
|---|---|
| single-op commands | the bridge's `data`, unchanged |
| `generate --dry-run` | the estimate data plus `omitted_inputs` |
| `generate` | the submit data (`job_ids`, `idempotency_token`, `replayed`, …), plus `jobs` with `--wait` and `downloads` with `--download` |
| `jobs wait` | `{jobs, downloads?}` |
| `media download` | `{media_token, path, byte_count}` |

## Error codes

| code | hint | retryable |
|---|---|---|
| `invalid_request` | — | no |
| `unauthorized` | the app restarted; the CLI already re-read discovery once | yes |
| `forbidden_host` | call 127.0.0.1 | no |
| `forbidden_origin` | browsers cannot use the bridge | no |
| `not_found` | — | no |
| `method_not_allowed` | — | no |
| `payload_too_large` | images must be 20 MiB or smaller | no |
| `unsupported_media_type` | — | no |
| `internal_error` | check the ArtCraft log | no |
| `bridge_busy` | back off, then retry | yes |
| `unknown_op` | run `artcraft-cli ping` to see the supported ops | no |
| `invalid_args` | — | no |
| `args_too_large` | — | no |
| `unsupported_route` | pick a model from `artcraft-cli models list` | no |
| `operation_in_progress` | wait, then retry with the same --idempotency-token | yes |
| `credentials_not_synced` | the app just started; the CLI already waited 5 s | yes |
| `not_logged_in` | log in inside the ArtCraft app | no |
| `cost_exceeds_limit` | raise --max-credits or choose another model | no |
| `estimate_unavailable` | — | no |
| `insufficient_credits` | buy credits in the ArtCraft app | no |
| `rate_limited` | back off, then retry | yes |
| `upstream_bad_input` | fix the request | no |
| `upstream_unavailable` | retry later | yes |
| `upstream_error` | — | no |
| `outcome_unknown` | do not resubmit; run `artcraft-cli --json jobs list --remote --all` and match on model and a created_at at or after the submit time | no |
| `job_not_found` | — | no |
| `job_not_terminal` | wait for the job to finish first | no |
| `media_not_found` | — | no |
| `upload_type_unsupported` | convert the image to PNG, JPEG or GIF first | no |
| `setting_not_writable` | — | no |
| `local_store_error` | check the ArtCraft log | no |
| `usage_error` | see --help | no |
| `bridge_not_running` | start ArtCraft with ARTCRAFT_CLI_BRIDGE=1 | yes |
| `discovery_insecure` | fix the discovery file's owner or mode, or restart ArtCraft | no |
| `bridge_protocol_mismatch` | update artcraft-cli or the ArtCraft app | no |
| `bridge_protocol_error` | check the ArtCraft log | no |
| `response_timeout` | retry | yes |
| `job_failed` | inspect details | no |
| `job_wait_timeout` | wait longer, or check `artcraft-cli jobs get` | yes |
| `download_failed` | retry | yes |
| `output_exists` | pass --force or choose another --out | no |
| `input_file_error` | — | no |

Any other code is generic and not retryable. `outcome_unknown.details` carries `idempotency_token` and `reason` (`server_error`, `deadline`, `response_timeout` or `connection_lost`). `job_failed.details` carries `status` and the full `job`.

## Side effects in the app

- Bridge jobs appear in ArtCraft's task panel and generation feeds.
- They trigger toasts, sounds and a credit refresh. `settings set play_sounds false` silences them.
- Preference changes made here show up in an open settings view only after it re-reads them.

## Logging

ArtCraft logs request bodies, prompts included, whenever `RUST_LOG` contains `debug`. If prompts must stay private, launch it without `debug` in `RUST_LOG`.
````

- [ ] **Step 2: Link the Gemini and agents rule files to the Claude rules**

```bash
mkdir -p .gemini .agents && ln -s ../.claude/CLAUDE.md .gemini/GEMINI.md && ln -s ../.claude/CLAUDE.md .agents/AGENTS.md && head -1 .gemini/GEMINI.md .agents/AGENTS.md
```

Expected: both print `# artcraft-cli — agent rules`

- [ ] **Step 3: Check that no Adobe or cli-anything branding is left outside the design record**

```bash
rtk proxy git grep --untracked -n -i -E 'adobe|cli-anything|cli_anything|premiere|illustrator|acrobat' -- ':!docs/superpowers'; echo "exit=$?"
```

Expected: no matching lines, then `exit=1`

- [ ] **Step 4: Commit**

```bash
.venv/bin/pytest -m "not e2e" -q
git add .claude/CLAUDE.md .gemini/GEMINI.md .agents/AGENTS.md README.md CONTRIBUTING.md skills/artcraft-cli/SKILL.md
PATH="$PWD/.venv/bin:$PATH" git commit -m "docs: add agent rules, artcraft-cli skill and rebranded docs"
```

Expected: the unit suite passes, then every pre-commit hook passes and the commit is created. If a hook rewrites a file, `git add` it again and re-run the commit; never pass `--no-verify`.

### Task 6: M0 gate: full checks, Python 3.10, push, CI green

**Executor:** controller session, with the user where a step says so. Subagents do not run this task.

Step 3 is a STOP gate. On the Rust side, M0 means building and running *unmodified* ArtCraft on `feature/cli-bridge` and logging in once. That is ARTC M0 in the Rust plan; check its status with the `artcraft` session.

- [ ] **Step 1: Run the full local gate**

```bash
.venv/bin/pytest -m "not e2e" -q && PATH="$PWD/.venv/bin:$PATH" pre-commit run --all-files
```

Expected: `1 passed`, then every hook `Passed`

- [ ] **Step 2: Run the unit suite on Python 3.10 (CI's floor)**

```bash
PY310="${TMPDIR:-/tmp}/artcraft-cli-py310"
test -x "$PY310/bin/pytest" || { python3.10 -m venv "$PY310" && "$PY310/bin/pip" install -q -e '.[dev]'; }
"$PY310/bin/pytest" -m "not e2e" -q
```

Expected: the same pass count as on 3.13, ending in `passed`

- [ ] **Step 3: STOP — controller and user only.** Ask the user: "Push branch `pivot/artcraft-cli` to origin so CI runs?" Run only on an explicit yes:

```bash
git push -u origin pivot/artcraft-cli
```

- [ ] **Step 4: Wait for CI on the pushed commit**

```bash
SHA=$(git rev-parse HEAD)
until gh run list --branch pivot/artcraft-cli --commit "$SHA" --limit 1 --json databaseId -q '.[0].databaseId' | grep -q .; do sleep 10; done
gh run watch "$(gh run list --branch pivot/artcraft-cli --commit "$SHA" --limit 1 --json databaseId -q '.[0].databaseId')" --exit-status
```

Expected: both matrix jobs (3.10, 3.13) of the run for **this commit** succeed. The `until` loop waits for GitHub to register the run; foreground `sleep` is blocked in this environment, so run the loop with the Monitor tool (or `run_in_background`) and then `gh run watch`. If CI fails, fix it on the branch with a `fix:` commit and push again (same STOP gate).

When this task is done, move ACLI milestone M0 to done in Plane, and update the project memory `project_artcraft_pivot.md` with "M0 done" and the date.

---

## Milestone M1 — Thin live slice, zero spend

Spec §6.1, §6.2, §6.3 (dry run), §10.3 M1. Tasks 7–10 need no ArtCraft: their tests fake the HTTP boundary. Task 11 is the live checklist and needs ARTC M1.

### Task 7: Bridge client: discovery, envelope, retries

**Files:**
- Create: `artcraft_cli/tests/test_bridge.py`
- Create: `artcraft_cli/errors.py`
- Create: `artcraft_cli/utils/__init__.py`
- Create: `artcraft_cli/utils/bridge.py`
- Modify: `artcraft_cli/tests/conftest.py`

**Interfaces:**
- Produces, in `artcraft_cli/errors.py`:
  - `class CliError(Exception)` with `__init__(self, code: str, message: str, details: dict[str, Any] | None = None)`. Its `.code` and `.message` attributes are `str`, and `.details` is always a `dict`.
  - `HINTS: dict[str, tuple[str | None, bool]]`, mapping each code to its hint and retryable flag. It covers every §5.6 code, the CLI-only codes included.
  - `error_payload(err: CliError) -> dict[str, Any]`.
- Produces, in `artcraft_cli/utils/bridge.py`:
  - Constants: `DISCOVERY_PATH`, `CONNECT_TIMEOUT`, `READ_TIMEOUT`, `HEALTH_TIMEOUT`, `NOT_SYNCED_WAIT_S`, `NOT_SYNCED_POLL_S`, `SUBMIT_OP`.
  - `read_discovery() -> dict[str, Any]`.
  - `health() -> dict[str, Any]`.
  - `rpc(op: str, args: dict[str, Any]) -> dict[str, Any]`, which returns `data` or raises `CliError(code)`. For `generate.submit` it needs `args["idempotency_token"]`.
  - `_session() -> requests.Session`, the test patch point.
- Produces, in the test fakes (`conftest.py`):
  - `FakeBridge` with `.on(op, *outcomes)`, `.calls`, `.ops()` and `.args(op)`. The op for `GET /v1/health` is `"health"`. The last queued outcome repeats.
  - `FakeClock`.
  - Fixtures `discovery`, `clock`, `fake_bridge` and `run`.
  - Helpers `write_discovery`, `response`, `op_error` and `refused`, and the constants `HEALTH`, `TOKEN` and `PORT`.
  - An autouse fixture that blocks real discovery and network access in non-e2e tests.

- [ ] **Step 1: Write the failing transport tests and the boundary fakes**

Replace the whole of `artcraft_cli/tests/conftest.py` with:

````python
"""Fixtures. Unit tests fake only the HTTP boundary (requests), the clock and the OS."""

from __future__ import annotations

import io
import json
import os
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import pytest
import requests
import urllib3

from artcraft_cli.artcraft_cli import main
from artcraft_cli.utils import bridge

TOKEN = "ab" * 32
PORT = 50001
HEALTH = {
    "bridge_protocol_version": 1,
    "app_version": "0.41.0",
    "pid": 4242,
    "started_at": "2026-10-09T15:04:05Z",
    "ops": ["app.info", "account.session", "models.list", "jobs.list", "generate.estimate"],
    "readiness": {"credentials_synced": True, "session_cookie_present": True},
}

Outcome = dict[str, Any] | requests.Response | BaseException | Callable[[], Any]


def write_discovery(
    path: Path,
    *,
    port: int = PORT,
    pid: int | None = None,
    version: int = 1,
    token: str = TOKEN,
    mode: int = 0o600,
) -> None:
    path.write_text(
        json.dumps(
            {
                "bridge_protocol_version": version,
                "port": port,
                "pid": os.getpid() if pid is None else pid,
                "token": token,
                "app_version": "0.41.0",
                "started_at": "2026-10-09T15:04:05Z",
            }
        ),
        encoding="utf-8",
    )
    path.chmod(mode)


def response(status: int, body: Any) -> requests.Response:
    """A real requests.Response carrying `body` (bytes are sent as-is, else JSON)."""
    resp = requests.Response()
    resp.status_code = status
    resp.raw = io.BytesIO(body if isinstance(body, bytes) else json.dumps(body).encode())
    return resp


def op_error(code: str, message: str = "x", details: Any = None, status: int = 200) -> Any:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return response(status, {"ok": False, "error": error})


def refused() -> requests.ConnectionError:
    """What requests raises when nothing is listening on the port."""
    reason = urllib3.exceptions.NewConnectionError(cast(Any, None), "Connection refused")
    return requests.ConnectionError(urllib3.exceptions.MaxRetryError(cast(Any, None), "/", reason))


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class FakeBridge:
    """Stands in for requests.Session. Outcomes are queued per op ("health" for GET);
    the last outcome of a queue repeats."""

    def __init__(self, clock: FakeClock | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._queues: dict[str, list[Outcome]] = {}
        self._clock = clock

    def on(self, op: str, *outcomes: Outcome) -> FakeBridge:
        self._queues.setdefault(op, []).extend(outcomes)
        return self

    def ops(self) -> list[str]:
        return [call["op"] for call in self.calls]

    def args(self, op: str) -> list[dict[str, Any]]:
        return [call["json"]["args"] for call in self.calls if call["op"] == op]

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any] | None = None,
        timeout: Any = None,
    ) -> requests.Response:
        op = "health" if url.endswith("/v1/health") else str((json or {})["op"])
        self.calls.append(
            {
                "op": op,
                "method": method,
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
                "t": self._clock.now if self._clock else 0.0,
            }
        )
        queue = self._queues.get(op)
        if not queue:
            raise AssertionError(f"unexpected bridge call: {op}")
        outcome = queue.pop(0) if len(queue) > 1 else queue[0]
        if callable(outcome) and not isinstance(outcome, BaseException):
            outcome = outcome()
        if isinstance(outcome, BaseException):
            raise outcome
        if isinstance(outcome, requests.Response):
            return outcome
        return response(200, {"ok": True, "data": outcome})


@pytest.fixture(autouse=True)
def _isolate_bridge(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Unit tests never reach a real ArtCraft, its discovery file, or the network."""
    if request.node.get_closest_marker("e2e"):
        return

    def no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("unit test reached the network")

    monkeypatch.setattr(bridge, "DISCOVERY_PATH", tmp_path / "absent" / "cli_bridge.json")
    monkeypatch.setattr(bridge, "_session", no_network)
    monkeypatch.setattr(requests, "get", no_network)


@pytest.fixture
def discovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "cli_bridge.json"
    write_discovery(path)
    monkeypatch.setattr(bridge, "DISCOVERY_PATH", path)
    return path


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(time, "monotonic", fake.monotonic)
    monkeypatch.setattr(time, "sleep", fake.sleep)
    return fake


@pytest.fixture
def fake_bridge(discovery: Path, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> FakeBridge:
    fake = FakeBridge(clock)
    monkeypatch.setattr(bridge, "_session", lambda: fake)
    return fake


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Iterator[Callable[..., tuple[int, str, str]]]:
    """Run the real console entry point; returns (exit_code, stdout, stderr)."""

    def invoke(*argv: str) -> tuple[int, str, str]:
        code = main(list(argv))
        out, err = capsys.readouterr()
        return code, out, err

    yield invoke
````

Create `artcraft_cli/tests/test_bridge.py`:

````python
"""Transport behaviour of utils/bridge.py against a scripted HTTP boundary (spec §6.2)."""

from __future__ import annotations

import http.client
import http.server
import json
import os
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import requests
import urllib3

from artcraft_cli.errors import CliError
from artcraft_cli.utils import bridge

from .conftest import HEALTH, FakeBridge, FakeClock, op_error, refused, write_discovery

_real_session: Callable[[], requests.Session] = bridge._session  # before any patching
SUBMIT_ARGS = {
    "modality": "image",
    "idempotency_token": "0b8f6a52-6a8e-4d55-9d43-3d6c0f6f1a10",
    "max_credits": 5,
    "request": {"model": "m"},
}


def test_missing_discovery_file_reports_bridge_not_running() -> None:
    with pytest.raises(CliError) as caught:
        bridge.health()
    assert caught.value.code == "bridge_not_running"


def test_dead_pid_reports_bridge_not_running_instead_of_hanging(
    fake_bridge: FakeBridge, discovery: Path
) -> None:
    finished = subprocess.Popen([sys.executable, "-c", "pass"])
    finished.wait()
    write_discovery(discovery, pid=finished.pid)

    with pytest.raises(CliError) as caught:
        bridge.health()

    assert caught.value.code == "bridge_not_running"
    assert fake_bridge.calls == []


@pytest.mark.parametrize(
    ("mode", "foreign_owner"), [(0o644, False), (0o640, False), (0o604, False), (0o600, True)]
)
def test_world_readable_or_foreign_discovery_file_is_refused(
    fake_bridge: FakeBridge,
    discovery: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: int,
    foreign_owner: bool,
) -> None:
    discovery.chmod(mode)
    if foreign_owner:
        monkeypatch.setattr(os, "getuid", lambda: discovery.stat().st_uid + 1)

    with pytest.raises(CliError) as caught:
        bridge.health()

    assert caught.value.code == "discovery_insecure"
    assert fake_bridge.calls == []


def test_refused_connection_rereads_discovery_then_reports_not_running(
    fake_bridge: FakeBridge,
) -> None:
    fake_bridge.on("health", refused())
    with pytest.raises(CliError) as caught:
        bridge.health()
    assert caught.value.code == "bridge_not_running"
    assert len(fake_bridge.calls) == 2


def test_restarted_app_on_new_port_is_found_on_retry(
    fake_bridge: FakeBridge, discovery: Path
) -> None:
    def app_restarts_on_new_port() -> BaseException:
        write_discovery(discovery, port=50002)
        return refused()

    fake_bridge.on("health", app_restarts_on_new_port, HEALTH)

    assert bridge.health()["app_version"] == "0.41.0"
    assert [call["url"] for call in fake_bridge.calls] == [
        "http://127.0.0.1:50001/v1/health",
        "http://127.0.0.1:50002/v1/health",
    ]


def test_bridge_error_body_survives_non_2xx_status(fake_bridge: FakeBridge) -> None:
    fake_bridge.on("app.info", op_error("forbidden_origin", "browsers are refused", status=403))
    with pytest.raises(CliError) as caught:
        bridge.rpc("app.info", {})
    assert (caught.value.code, caught.value.message) == ("forbidden_origin", "browsers are refused")


def test_op_error_with_http_200_raises_its_code(fake_bridge: FakeBridge) -> None:
    details = {"effective_credits": 12, "max_credits": 5}
    fake_bridge.on("generate.submit", op_error("cost_exceeds_limit", "too dear", details))
    with pytest.raises(CliError) as caught:
        bridge.rpc("generate.submit", SUBMIT_ARGS)
    assert caught.value.code == "cost_exceeds_limit"
    assert caught.value.details == details


def test_read_timeout_after_send_is_never_reported_as_not_running(
    fake_bridge: FakeBridge,
) -> None:
    fake_bridge.on("jobs.list", requests.ReadTimeout())
    with pytest.raises(CliError) as caught:
        bridge.rpc("jobs.list", {})
    assert caught.value.code == "response_timeout"
    assert len(fake_bridge.calls) == 1


def test_protocol_version_mismatch_is_refused(fake_bridge: FakeBridge, discovery: Path) -> None:
    write_discovery(discovery, version=2)
    with pytest.raises(CliError) as caught:
        bridge.health()
    assert caught.value.code == "bridge_protocol_mismatch"
    assert fake_bridge.calls == []


def test_proxy_env_vars_never_route_bridge_traffic(
    discovery: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Health(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = json.dumps({"ok": True, "data": HEALTH}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: Any) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Health)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        write_discovery(discovery, port=server.server_address[1])
        for name in ("HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
            monkeypatch.setenv(name, "http://127.0.0.1:9")  # discard port: nothing answers
        for name in ("NO_PROXY", "no_proxy"):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setattr(bridge, "_sess", None)
        monkeypatch.setattr(bridge, "_session", _real_session)

        assert bridge.health()["app_version"] == "0.41.0"
    finally:
        server.shutdown()
        server.server_close()


def test_credentials_not_synced_is_retried_briefly_then_surfaced(
    fake_bridge: FakeBridge, clock: FakeClock
) -> None:
    fake_bridge.on("account.session", op_error("credentials_not_synced"))
    started = clock.now

    with pytest.raises(CliError) as caught:
        bridge.rpc("account.session", {})

    assert caught.value.code == "credentials_not_synced"
    assert len(fake_bridge.calls) > 1
    assert clock.now - started <= bridge.NOT_SYNCED_WAIT_S


def test_connection_dropped_after_send_never_resubmits(fake_bridge: FakeBridge) -> None:
    dropped = requests.ConnectionError(
        urllib3.exceptions.ProtocolError(
            "Connection aborted.", http.client.RemoteDisconnected("closed without response")
        )
    )
    fake_bridge.on("generate.submit", dropped)

    with pytest.raises(CliError) as caught:
        bridge.rpc("generate.submit", SUBMIT_ARGS)

    assert caught.value.code == "outcome_unknown"
    assert caught.value.details == {
        "idempotency_token": SUBMIT_ARGS["idempotency_token"],
        "reason": "connection_lost",
    }
    assert fake_bridge.ops() == ["generate.submit"]
````

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest artcraft_cli/tests/test_bridge.py -v`

Expected: FAIL — the test module cannot import yet: `ModuleNotFoundError: No module named 'artcraft_cli.utils'`

- [ ] **Step 3: Write the error table and the bridge client**

Create `artcraft_cli/errors.py`:

````python
"""CLI errors and the code → (hint, retryable) table from the wire contract (spec §5.6)."""

from __future__ import annotations

from typing import Any


class CliError(Exception):
    """An error with a stable snake_case code. Messages never carry the bridge token."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details: dict[str, Any] = details or {}


HINTS: dict[str, tuple[str | None, bool]] = {
    # Gate and bridge failures (non-2xx HTTP)
    "invalid_request": (None, False),
    "unauthorized": ("the app restarted; the CLI already re-read discovery once", True),
    "forbidden_host": ("call 127.0.0.1", False),
    "forbidden_origin": ("browsers cannot use the bridge", False),
    "not_found": (None, False),
    "method_not_allowed": (None, False),
    "payload_too_large": ("images must be 20 MiB or smaller", False),
    "unsupported_media_type": (None, False),
    "internal_error": ("check the ArtCraft log", False),
    "bridge_busy": ("back off, then retry", True),
    # Op errors (HTTP 200, ok: false)
    "unknown_op": ("run `artcraft-cli ping` to see the supported ops", False),
    "invalid_args": (None, False),
    "args_too_large": (None, False),
    "unsupported_route": ("pick a model from `artcraft-cli models list`", False),
    "operation_in_progress": ("wait, then retry with the same --idempotency-token", True),
    "credentials_not_synced": ("the app just started; the CLI already waited 5 s", True),
    "not_logged_in": ("log in inside the ArtCraft app", False),
    "cost_exceeds_limit": ("raise --max-credits or choose another model", False),
    "estimate_unavailable": (None, False),
    "insufficient_credits": ("buy credits in the ArtCraft app", False),
    "rate_limited": ("back off, then retry", True),
    "upstream_bad_input": ("fix the request", False),
    "upstream_unavailable": ("retry later", True),
    "upstream_error": (None, False),
    "outcome_unknown": (
        "do not resubmit; run `artcraft-cli --json jobs list --remote --all` and match on "
        "model and a created_at at or after the submit time",
        False,
    ),
    "job_not_found": (None, False),
    "job_not_terminal": ("wait for the job to finish first", False),
    "media_not_found": (None, False),
    "upload_type_unsupported": ("convert the image to PNG, JPEG or GIF first", False),
    "setting_not_writable": (None, False),
    "local_store_error": ("check the ArtCraft log", False),
    # CLI-only codes
    "usage_error": ("see --help", False),
    "bridge_not_running": ("start ArtCraft with ARTCRAFT_CLI_BRIDGE=1", True),
    "discovery_insecure": ("fix the discovery file's owner or mode, or restart ArtCraft", False),
    "bridge_protocol_mismatch": ("update artcraft-cli or the ArtCraft app", False),
    "bridge_protocol_error": ("check the ArtCraft log", False),
    "response_timeout": ("retry", True),
    "job_failed": ("inspect details", False),
    "job_wait_timeout": ("wait longer, or check `artcraft-cli jobs get`", True),
    "download_failed": ("retry", True),
    "output_exists": ("pass --force or choose another --out", False),
    "input_file_error": (None, False),
}


def error_payload(err: CliError) -> dict[str, Any]:
    """The --json error object. Unknown codes are generic and not retryable."""
    hint, retryable = HINTS.get(err.code, (None, False))
    body: dict[str, Any] = {
        "code": err.code,
        "message": err.message,
        "hint": hint,
        "retryable": retryable,
    }
    if err.details:
        body["details"] = err.details
    return {"error": body}
````

Create `artcraft_cli/utils/__init__.py` as an empty file.

Create `artcraft_cli/utils/bridge.py`:

````python
"""The only module that talks to the ArtCraft bridge or reads its discovery file (spec §6.2)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests
import urllib3

from artcraft_cli import SUPPORTED_BRIDGE_PROTOCOL
from artcraft_cli.errors import CliError

DISCOVERY_PATH = Path.home() / "Artcraft" / "state" / "cli_bridge.json"
DISCOVERY_KEYS = ("bridge_protocol_version", "port", "pid", "token", "app_version", "started_at")
HEALTH_KEYS = ("bridge_protocol_version", "app_version", "ops", "readiness")
CONNECT_TIMEOUT = 3
READ_TIMEOUT = 150
HEALTH_TIMEOUT = 5
NOT_SYNCED_WAIT_S = 5
NOT_SYNCED_POLL_S = 0.5
SUBMIT_OP = "generate.submit"

_sess: requests.Session | None = None


def _session() -> requests.Session:
    """The bridge session; env proxies are ignored. Tests patch this function."""
    global _sess
    if _sess is None:
        _sess = requests.Session()
        _sess.trust_env = False
    return _sess


def read_discovery() -> dict[str, Any]:
    """Read and check the discovery file. Runs before every bridge call."""
    path = DISCOVERY_PATH
    if not path.exists():
        raise CliError("bridge_not_running", f"no discovery file at {path}")
    if os.name == "posix":
        st = path.stat()
        if st.st_uid != os.getuid() or st.st_mode & 0o077:
            raise CliError("discovery_insecure", f"{path} must be owned by you with mode 0600")
    try:
        discovery = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise CliError("bridge_protocol_error", f"cannot parse {path}") from None
    if not isinstance(discovery, dict) or any(key not in discovery for key in DISCOVERY_KEYS):
        raise CliError("bridge_protocol_error", f"{path} is missing required keys")
    version = discovery["bridge_protocol_version"]
    if version != SUPPORTED_BRIDGE_PROTOCOL:
        raise CliError(
            "bridge_protocol_mismatch",
            f"bridge protocol {version} is not supported (expected {SUPPORTED_BRIDGE_PROTOCOL})",
        )
    if not _pid_alive(int(discovery["pid"])):
        raise CliError("bridge_not_running", f"ArtCraft pid {discovery['pid']} is not running")
    return discovery


def _pid_alive(pid: int) -> bool:
    if os.name != "posix":
        return True  # os.kill(pid, 0) would terminate the process on Windows
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def health() -> dict[str, Any]:
    """GET /v1/health: protocol, app version, pid, ops allowlist, readiness."""
    data = _call("GET", "/v1/health", None, HEALTH_TIMEOUT, submit_token=None)
    if any(key not in data for key in HEALTH_KEYS):
        raise CliError("bridge_protocol_error", "health response is missing required keys")
    if data["bridge_protocol_version"] != SUPPORTED_BRIDGE_PROTOCOL:
        raise CliError(
            "bridge_protocol_mismatch",
            f"bridge protocol {data['bridge_protocol_version']} is not supported",
        )
    return data


def rpc(op: str, args: dict[str, Any]) -> dict[str, Any]:
    """POST /v1/rpc and return `data`; an `ok: false` envelope raises CliError(code)."""
    submit_token = str(args["idempotency_token"]) if op == SUBMIT_OP else None
    deadline = time.monotonic() + NOT_SYNCED_WAIT_S
    while True:
        try:
            return _call(
                "POST", "/v1/rpc", {"op": op, "args": args}, READ_TIMEOUT, submit_token=submit_token
            )
        except CliError as err:
            if err.code != "credentials_not_synced" or time.monotonic() >= deadline:
                raise
        time.sleep(NOT_SYNCED_POLL_S)


def _call(
    method: str,
    path: str,
    body: dict[str, Any] | None,
    read_timeout: float,
    *,
    submit_token: str | None,
) -> dict[str, Any]:
    discovery = read_discovery()
    resp = _send(method, path, body, read_timeout, discovery, submit_token)
    if resp is None or resp.status_code == 401:
        # Refused before send, or the gate rejected the token: nothing ran, and the
        # app may have restarted on a new port with a new token. Re-read once.
        discovery = read_discovery()
        resp = _send(method, path, body, read_timeout, discovery, submit_token)
        if resp is None:
            raise CliError("bridge_not_running", "the bridge refused the connection")
    return _parse(resp)


def _send(
    method: str,
    path: str,
    body: dict[str, Any] | None,
    read_timeout: float,
    discovery: dict[str, Any],
    submit_token: str | None,
) -> requests.Response | None:
    """One HTTP attempt. None means the connection was refused before anything was sent."""
    try:
        return _session().request(
            method,
            f"http://127.0.0.1:{discovery['port']}{path}",
            headers={"Authorization": f"Bearer {discovery['token']}"},
            json=body,
            timeout=(CONNECT_TIMEOUT, read_timeout),
        )
    except requests.ConnectionError as exc:
        if _refused_before_send(exc):
            return None
        raise _after_send("connection_lost", read_timeout, submit_token) from None
    except requests.ReadTimeout:
        raise _after_send("response_timeout", read_timeout, submit_token) from None
    except requests.exceptions.ChunkedEncodingError:
        raise _after_send("connection_lost", read_timeout, submit_token) from None


def _refused_before_send(exc: requests.ConnectionError) -> bool:
    if isinstance(exc, requests.ConnectTimeout):
        return True
    reason = exc.args[0] if exc.args else None
    reason = getattr(reason, "reason", reason)  # requests wraps urllib3's MaxRetryError
    return isinstance(reason, (urllib3.exceptions.NewConnectionError, ConnectionRefusedError))


def _after_send(reason: str, read_timeout: float, submit_token: str | None) -> CliError:
    """A failure after the request was sent. Never retried: the op may have run."""
    if submit_token is not None:
        return CliError(
            "outcome_unknown",
            "generate.submit may have been accepted; its outcome is unknown",
            {"idempotency_token": submit_token, "reason": reason},
        )
    if reason == "response_timeout":
        return CliError("response_timeout", f"no response from the bridge within {read_timeout} s")
    return CliError("bridge_protocol_error", "the bridge dropped the connection")


def _parse(resp: requests.Response) -> dict[str, Any]:
    """Parse the envelope first, whatever the HTTP status (spec §5.2)."""
    try:
        envelope = resp.json()
    except ValueError:
        raise CliError(
            "bridge_protocol_error", f"bridge sent a non-JSON response (HTTP {resp.status_code})"
        ) from None
    if not isinstance(envelope, dict) or not isinstance(envelope.get("ok"), bool):
        raise CliError(
            "bridge_protocol_error", f"bridge sent a malformed envelope (HTTP {resp.status_code})"
        )
    if envelope["ok"]:
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise CliError("bridge_protocol_error", "bridge sent a success envelope without data")
        return data
    error = envelope.get("error")
    if not isinstance(error, dict) or not isinstance(error.get("code"), str):
        raise CliError(
            "bridge_protocol_error", f"bridge sent a malformed error (HTTP {resp.status_code})"
        )
    details = error.get("details")
    raise CliError(
        error["code"], str(error.get("message", "")), details if isinstance(details, dict) else None
    )
````

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest artcraft_cli/tests/test_bridge.py -v`

Expected: PASS — 15 passed

- [ ] **Step 5: Commit**

```bash
.venv/bin/pytest -m "not e2e" -q
git add artcraft_cli/errors.py artcraft_cli/utils/__init__.py artcraft_cli/utils/bridge.py artcraft_cli/tests/conftest.py artcraft_cli/tests/test_bridge.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat: add bridge client with discovery checks and safe retries"
```

Expected: the unit suite passes, then every pre-commit hook passes and the commit is created. If a hook rewrites a file, `git add` it again and re-run the commit; never pass `--no-verify`.

### Task 8: Output contract and the M1 read commands

**Files:**
- Create: `artcraft_cli/core/__init__.py`
- Create: `artcraft_cli/core/app.py`
- Create: `artcraft_cli/core/account.py`
- Create: `artcraft_cli/core/models.py`
- Create: `artcraft_cli/core/jobs.py`
- Modify: `artcraft_cli/tests/test_core.py`
- Modify: `artcraft_cli/tests/test_bridge.py`
- Modify: `artcraft_cli/artcraft_cli.py`

**Interfaces:**
- Consumes: `bridge.rpc`, `bridge.health`, `bridge.read_discovery`, `CliError` and `error_payload` (Task 7).
- Produces:
  - `artcraft_cli.artcraft_cli.emit(data: dict[str, Any]) -> None`. It prints compact JSON under `--json` and indented JSON otherwise.
  - `main()` renders `CliError` and Click usage errors (as `usage_error`) through `_render(err, as_json) -> int`.
  - Commands: `ping`, `app info`, `account whoami`, `models list --kind`, and `jobs list [--all] [--limit]`.
  - `core.app.ping()` and `core.app.info()`, `core.account.whoami()`, `core.models.KINDS` and `core.models.list_models(kind: str)`.
  - `core.jobs.list_jobs(*, all_origins: bool, remote: bool, limit: int)`. It always sends `include_remote`, and the CLI passes `False` until Task 12.
  - All of these return `dict[str, Any]` (the bridge `data`).

- [ ] **Step 1: Write the failing output-contract and command tests**

Replace the whole of `artcraft_cli/tests/test_core.py` with:

````python
"""CLI behaviour through the real entry point, faking only the HTTP boundary (spec §6)."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

import pytest

from .conftest import HEALTH, FakeBridge

Run = Callable[..., tuple[int, str, str]]


def error_of(out: str) -> dict[str, Any]:
    body = json.loads(out)
    assert set(body) == {"error"}
    error: dict[str, Any] = body["error"]
    return error


# --- Output contract (spec §6.1) -------------------------------------------------------


def test_cli_without_subcommand_prints_help(run: Run) -> None:
    code, out, _ = run()
    assert code == 0
    assert "Usage: artcraft-cli" in out


def test_json_success_is_one_compact_object_without_error_key(
    fake_bridge: FakeBridge, run: Run
) -> None:
    fake_bridge.on("health", HEALTH)
    code, out, err = run("--json", "ping")

    assert (code, err) == (0, "")
    assert out.count("\n") == 1
    body = json.loads(out)
    assert "error" not in body
    assert out.strip() == json.dumps(body, separators=(",", ":"))
    assert body["bridge"] == {
        "port": 50001,
        "pid": os.getpid(),
        "app_version": "0.41.0",
        "protocol": 1,
    }


def test_json_errors_are_objects_on_stdout_with_exit_1(run: Run) -> None:
    code, out, err = run("--json", "ping")

    assert (code, err) == (1, "")
    error = error_of(out)
    assert error["code"] == "bridge_not_running"
    assert error["retryable"] is True
    assert "ARTCRAFT_CLI_BRIDGE=1" in error["hint"]


def test_human_errors_go_to_stderr(run: Run) -> None:
    code, out, err = run("ping")

    assert (code, out) == (1, "")
    assert err.startswith("error[bridge_not_running]: ")
    assert "\nhint: start ArtCraft with ARTCRAFT_CLI_BRIDGE=1" in err


@pytest.mark.parametrize(
    "argv",
    [
        ["nope"],
        ["models", "list"],
        ["jobs"],
        ["generate", "image"],
        ["jobs", "list", "--limit", "0"],
    ],
)
def test_usage_errors_render_as_json_with_exit_1(run: Run, argv: list[str]) -> None:
    code, out, err = run("--json", *argv)
    assert (code, err) == (1, "")
    assert error_of(out)["code"] == "usage_error"


# --- Single-op commands print bridge data unchanged (spec §6.1) -------------------------


SINGLE_OP_COMMANDS: list[tuple[list[str], str, dict[str, Any]]] = [
    (["app", "info"], "app.info", {}),
    (["account", "whoami"], "account.session", {}),
    (["models", "list", "--kind", "video"], "models.list", {"kind": "video"}),
    (["jobs", "list"], "jobs.list", {"origin": "cli", "limit": 50, "include_remote": False}),
    (
        ["jobs", "list", "--all", "--limit", "5"],
        "jobs.list",
        {"origin": "all", "limit": 5, "include_remote": False},
    ),
]


@pytest.mark.parametrize(
    ("argv", "op", "args"), SINGLE_OP_COMMANDS, ids=["-".join(row[0]) for row in SINGLE_OP_COMMANDS]
)
def test_single_op_commands_print_bridge_data_unchanged(
    fake_bridge: FakeBridge, run: Run, argv: list[str], op: str, args: dict[str, Any]
) -> None:
    data = {"op": op, "nested": [1, {"kept": True}], "maybe": None}
    fake_bridge.on(op, data)

    code, out, err = run("--json", *argv)

    assert (code, err) == (0, "")
    assert json.loads(out) == data
    assert fake_bridge.args(op) == [args]
````

Modify `artcraft_cli/tests/test_bridge.py` (2 edits; each old text occurs once):

Edit 1: replace

````python
from .conftest import HEALTH, FakeBridge, FakeClock, op_error, refused, write_discovery
````

with

````python
from .conftest import HEALTH, TOKEN, FakeBridge, FakeClock, op_error, refused, write_discovery
````

Edit 2: replace

````python
        server.server_close()


````

with

````python
        server.server_close()


def test_token_never_appears_in_stdout_stderr_or_exceptions(
    fake_bridge: FakeBridge, run: Callable[..., tuple[int, str, str]]
) -> None:
    fake_bridge.on("health", HEALTH)
    fake_bridge.on("app.info", op_error("unauthorized", status=401))
    fake_bridge.on("jobs.list", refused())
    fake_bridge.on("models.list", requests.ReadTimeout())
    fake_bridge.on("account.session", requests.ConnectionError("dropped"))

    outputs: list[str] = []
    for argv in (
        ["ping"],
        ["--json", "ping"],
        ["app", "info"],
        ["--json", "jobs", "list"],
        ["models", "list", "--kind", "image"],
        ["--json", "account", "whoami"],
    ):
        _, out, err = run(*argv)
        outputs += [out, err]
    failing_ops: list[tuple[str, dict[str, Any]]] = [
        ("app.info", {}),
        ("jobs.list", {}),
        ("models.list", {"kind": "image"}),
    ]
    for op, args in failing_ops:
        with pytest.raises(CliError) as caught:
            bridge.rpc(op, args)
        outputs += [str(caught.value), repr(caught.value), json.dumps(caught.value.details)]

    assert all(TOKEN not in text for text in outputs)


````

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest artcraft_cli/tests/test_core.py::test_json_success_is_one_compact_object_without_error_key artcraft_cli/tests/test_core.py::test_json_errors_are_objects_on_stdout_with_exit_1 artcraft_cli/tests/test_core.py::test_human_errors_go_to_stderr artcraft_cli/tests/test_core.py::test_usage_errors_render_as_json_with_exit_1 artcraft_cli/tests/test_core.py::test_single_op_commands_print_bridge_data_unchanged -v`

Expected: FAIL — 13 failed; first failure: `assert (1, "Usage: a...nd 'ping'.\n") == (0, '')`

`test_token_never_appears_in_stdout_stderr_or_exceptions` (added to `test_bridge.py` in Step 1) is a regression guard. Before this task it passes trivially, because no command prints anything yet. Step 4 runs it against the real commands.

- [ ] **Step 3: Write the core read helpers and the command tree**

Create `artcraft_cli/core/__init__.py` as an empty file.

Create `artcraft_cli/core/app.py`:

````python
"""Bridge status and app information."""

from __future__ import annotations

from typing import Any

from artcraft_cli.utils import bridge


def ping() -> dict[str, Any]:
    """Health plus discovery: what `artcraft-cli ping` prints (never the token)."""
    health = bridge.health()
    discovery = bridge.read_discovery()  # after health, so a retried port is reported
    return {
        "bridge": {
            "port": discovery["port"],
            "pid": discovery["pid"],
            "app_version": health["app_version"],
            "protocol": health["bridge_protocol_version"],
        },
        "readiness": health["readiness"],
        "ops": health["ops"],
    }


def info() -> dict[str, Any]:
    return bridge.rpc("app.info", {})
````

Create `artcraft_cli/core/account.py`:

````python
"""ArtCraft account state."""

from __future__ import annotations

from typing import Any

from artcraft_cli.utils import bridge


def whoami() -> dict[str, Any]:
    return bridge.rpc("account.session", {})
````

Create `artcraft_cli/core/models.py`:

````python
"""Generation models known to ArtCraft."""

from __future__ import annotations

from typing import Any

from artcraft_cli.utils import bridge

KINDS = ("image", "video")


def list_models(kind: str) -> dict[str, Any]:
    return bridge.rpc("models.list", {"kind": kind})
````

Create `artcraft_cli/core/jobs.py`:

````python
"""Generation jobs: list, get, wait, download results, dismiss."""

from __future__ import annotations

from typing import Any

from artcraft_cli.utils import bridge


def list_jobs(*, all_origins: bool, remote: bool, limit: int) -> dict[str, Any]:
    return bridge.rpc(
        "jobs.list",
        {"origin": "all" if all_origins else "cli", "limit": limit, "include_remote": remote},
    )
````

Replace the whole of `artcraft_cli/artcraft_cli.py` with:

````python
"""artcraft-cli command tree. Commands parse flags, call core, and emit one result."""

from __future__ import annotations

import itertools
import json
import sys
from typing import Any

import click

from artcraft_cli.core import account, jobs, models
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


@cli.group("models")
def models_group() -> None:
    """Generation models."""


@models_group.command("list")
@click.option("--kind", type=click.Choice(models.KINDS), required=True)
def models_list(kind: str) -> None:
    """Image or video models with their options."""
    emit(models.list_models(kind))


@cli.group("jobs")
def jobs_group() -> None:
    """Generation jobs."""


@jobs_group.command("list")
@click.option("--all", "all_origins", is_flag=True, help="Include jobs started in the app.")
@click.option("--limit", type=click.IntRange(1, 200), default=50, show_default=True)
def jobs_list(all_origins: bool, limit: int) -> None:
    """Recent jobs, newest first."""
    emit(jobs.list_jobs(all_origins=all_origins, remote=False, limit=limit))


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
````

- [ ] **Step 4: Run the core and transport tests to verify they pass**

Run: `.venv/bin/pytest artcraft_cli/tests/test_core.py artcraft_cli/tests/test_bridge.py -v`

Expected: PASS — 30 passed

- [ ] **Step 5: Commit**

```bash
.venv/bin/pytest -m "not e2e" -q
git add artcraft_cli/core/__init__.py artcraft_cli/core/app.py artcraft_cli/core/account.py artcraft_cli/core/models.py artcraft_cli/core/jobs.py artcraft_cli/artcraft_cli.py artcraft_cli/tests/test_core.py artcraft_cli/tests/test_bridge.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat: add ping, app, account, models and jobs list commands"
```

Expected: the unit suite passes, then every pre-commit hook passes and the commit is created. If a hook rewrites a file, `git add` it again and re-run the commit; never pass `--no-verify`.

### Task 9: generate --dry-run

**Files:**
- Create: `artcraft_cli/core/generate.py`
- Modify: `artcraft_cli/tests/test_core.py`
- Modify: `artcraft_cli/artcraft_cli.py`

**Interfaces:**
- Consumes: `bridge.rpc` and `CliError` (Task 7), and `emit` (Task 8).
- Produces, in `core/generate.py`:
  - `MODALITIES = ("image", "video", "audio", "mesh", "splat")`, `PLACEHOLDER_FIELD = "image_media_tokens"`, `ESTIMATE_PLACEHOLDER = "mf_estimate_{}"` and `MEDIA_TOKEN_RE`.
  - `build_request(model: str, prompt: str | None, sets: tuple[str, ...], media_specs: tuple[str, ...]) -> dict[str, Any]`. Local files stay as `pathlib.Path` values inside the request.
  - `estimate(modality: str, request: dict[str, Any]) -> dict[str, Any]`, which returns the estimate data plus `omitted_inputs: list[str]`.
- Command: `generate MODALITY --model … [--prompt] [--set]… [--media]… (--max-credits N | --dry-run)`. Until Task 14, `--max-credits` without `--dry-run` raises `usage_error`.

- [ ] **Step 1: Write the failing dry-run tests**

Modify `artcraft_cli/tests/test_core.py` (3 edits; each old text occurs once):

Edit 1: replace

````python
from collections.abc import Callable
````

with

````python
from collections.abc import Callable
from pathlib import Path
````

Edit 2: replace

````python
Run = Callable[..., tuple[int, str, str]]
````

with

````python
Run = Callable[..., tuple[int, str, str]]
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
ESTIMATE = {
    "modality": "image",
    "model": "m",
    "estimate": {"cost_in_credits": 4, "is_free": False, "is_unlimited": False},
    "effective_credits": 4,
}
````

Edit 3: replace

````python
    assert error_of(out)["code"] == "usage_error"


````

with

````python
    assert error_of(out)["code"] == "usage_error"


# --- generate: request building and --dry-run (spec §6.3) ------------------------------


@pytest.mark.parametrize(
    "spend_flags", [[], ["--max-credits", "5", "--dry-run"]], ids=["neither", "both"]
)
def test_spend_without_max_credits_is_refused_before_any_rpc(
    fake_bridge: FakeBridge, run: Run, spend_flags: list[str]
) -> None:
    code, out, _ = run("--json", "generate", "image", "--model", "m", "--prompt", "x", *spend_flags)
    assert code == 1
    error = error_of(out)
    assert error["code"] == "usage_error"
    assert "--max-credits" in error["message"]
    assert fake_bridge.calls == []


def test_dry_run_never_uploads_or_submits(
    fake_bridge: FakeBridge, run: Run, tmp_path: Path
) -> None:
    ref = tmp_path / "ref.png"
    ref.write_bytes(PNG)
    fake_bridge.on("generate.estimate", ESTIMATE)

    code, out, _ = run(
        "--json", "generate", "image", "--model", "m", "--prompt", "x",
        "--media", f"image_media_tokens={ref}", "--dry-run",
    )  # fmt: skip

    assert code == 0
    assert fake_bridge.ops() == ["generate.estimate"]
    assert json.loads(out)["effective_credits"] == 4


def test_dry_run_prices_local_image_refs_with_placeholders(
    fake_bridge: FakeBridge, run: Run, tmp_path: Path
) -> None:
    first, second = tmp_path / "a.png", tmp_path / "b.png"
    first.write_bytes(PNG)
    second.write_bytes(PNG)
    fake_bridge.on("generate.estimate", ESTIMATE)

    run(
        "--json", "generate", "image", "--model", "m", "--dry-run",
        "--media", f"image_media_tokens={first}",
        "--media", "image_media_tokens=mf_existing",
        "--media", f"image_media_tokens={second}",
    )  # fmt: skip
    code, out, _ = run(
        "--json", "generate", "video", "--model", "v", "--dry-run",
        "--media", f"start_frame_media_token={first}",
    )  # fmt: skip

    image_args, video_args = fake_bridge.args("generate.estimate")
    assert image_args["request"]["image_media_tokens"] == [
        "mf_estimate_0",
        "mf_existing",
        "mf_estimate_1",
    ]
    assert "start_frame_media_token" not in video_args["request"]
    assert code == 0
    assert json.loads(out)["omitted_inputs"] == ["start_frame_media_token"]


def test_fields_ending_in_tokens_accumulate_lists(fake_bridge: FakeBridge, run: Run) -> None:
    fake_bridge.on("generate.estimate", ESTIMATE)

    run(
        "--json", "generate", "image", "--model", "m", "--dry-run",
        "--media", "image_media_tokens=mf_a", "--media", "image_media_tokens=mf_b",
        "--media", "style_media_token=mf_c", "--set", "aspect_ratio=\"wide\"", "--set", "n=2",
    )  # fmt: skip
    code, out, _ = run(
        "--json", "generate", "image", "--model", "m", "--dry-run",
        "--media", "style_media_token=mf_c", "--media", "style_media_token=mf_d",
    )  # fmt: skip

    (args,) = fake_bridge.args("generate.estimate")
    assert args["request"] == {
        "model": "m",
        "image_media_tokens": ["mf_a", "mf_b"],
        "style_media_token": "mf_c",
        "aspect_ratio": "wide",
        "n": 2,
    }
    assert code == 1
    assert error_of(out)["code"] == "usage_error"


````

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest artcraft_cli/tests/test_core.py::test_spend_without_max_credits_is_refused_before_any_rpc artcraft_cli/tests/test_core.py::test_dry_run_never_uploads_or_submits artcraft_cli/tests/test_core.py::test_dry_run_prices_local_image_refs_with_placeholders artcraft_cli/tests/test_core.py::test_fields_ending_in_tokens_accumulate_lists -v`

Expected: FAIL — 5 failed; first failure: `assert '--max-credits' in "No such command 'generate'."`

- [ ] **Step 3: Write the request builder, the estimate call and the command**

Create `artcraft_cli/core/generate.py`:

````python
"""Build Omni requests from flags, price them, submit them, and follow the jobs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from artcraft_cli.errors import CliError
from artcraft_cli.utils import bridge

MODALITIES = ("image", "video", "audio", "mesh", "splat")
PLACEHOLDER_FIELD = "image_media_tokens"
ESTIMATE_PLACEHOLDER = "mf_estimate_{}"
MEDIA_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


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
            item: str | Path = path
        elif MEDIA_TOKEN_RE.match(value):
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
````

Modify `artcraft_cli/artcraft_cli.py` (2 edits; each old text occurs once):

Edit 1: replace

````python
from artcraft_cli.core import account, jobs, models
````

with

````python
from artcraft_cli.core import account, generate, jobs, models
````

Edit 2: replace

````python
    emit(models.list_models(kind))


````

with

````python
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


````

- [ ] **Step 4: Run the core tests to verify they pass**

Run: `.venv/bin/pytest artcraft_cli/tests/test_core.py -v`

Expected: PASS — 19 passed

- [ ] **Step 5: Commit**

```bash
.venv/bin/pytest -m "not e2e" -q
git add artcraft_cli/core/generate.py artcraft_cli/artcraft_cli.py artcraft_cli/tests/test_core.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat: add generate --dry-run with local reference placeholders"
```

Expected: the unit suite passes, then every pre-commit hook passes and the commit is created. If a hook rewrites a file, `git add` it again and re-run the commit; never pass `--no-verify`.

### Task 10: Live end-to-end tests for the zero-spend slice

**Files:**
- Create: `artcraft_cli/tests/test_full_e2e.py`

**Interfaces:**
- Produces: `test_full_e2e.py`, marked `e2e`, with a session fixture `live` that skips **only** on `bridge_not_running`. Helpers: `cli_json(capsys, *argv) -> dict`, `enabled_image_models(capsys)`, and `cheapest_image_model(capsys, *, refs: bool) -> tuple[str, int]`, which reads `models[].model` and skips models with `is_disabled: true`. `MAX_CREDITS` comes from `ARTCRAFT_E2E_MAX_CREDITS` (default `"10"`).

- [ ] **Step 1: Write the live zero-spend tests**

Create `artcraft_cli/tests/test_full_e2e.py`:

````python
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
````

- [ ] **Step 2: Run them without ArtCraft to verify they skip cleanly**

Run: `.venv/bin/pytest -m e2e -rs -q`

Expected: every selected test SKIPPED (ArtCraft is not running) — 5 skipped, 35 deselected

- [ ] **Step 3: Run the unit suite on Python 3.10 (CI's floor)**

```bash
PY310="${TMPDIR:-/tmp}/artcraft-cli-py310"
test -x "$PY310/bin/pytest" || { python3.10 -m venv "$PY310" && "$PY310/bin/pip" install -q -e '.[dev]'; }
"$PY310/bin/pytest" -m "not e2e" -q
```

Expected: the same pass count as on 3.13, ending in `passed`

- [ ] **Step 4: Commit**

```bash
.venv/bin/pytest -m "not e2e" -q
git add artcraft_cli/tests/test_full_e2e.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "test: add live end-to-end tests for the zero-spend slice"
```

Expected: the unit suite passes, then every pre-commit hook passes and the commit is created. If a hook rewrites a file, `git add` it again and re-run the commit; never pass `--no-verify`.

### Task 11: M1 live checklist

**Executor:** controller session, with the user where a step says so. Subagents do not run this task.

**Blocked by:** ARTC M1 (Rust plan) finished and built on `feature/cli-bridge`. Tasks 7–10 done.

The user runs ArtCraft from `/Volumes/Containers/artcraft`. Everything else runs here, from the repo root. Spec §10.3 M1 (a)–(i).

- [ ] **Step 1: STOP — controller and user only.** Ask the user to launch ArtCraft **without** the bridge variable, from the artcraft repo, and keep its terminal open:

```bash
./script/artcraft/unix_dev.sh
```

- [ ] **Step 2: (a) Check that the disabled bridge writes nothing and listens nowhere**

```bash
ls -l ~/Artcraft/state/cli_bridge.json; lsof -nP -iTCP -sTCP:LISTEN | rtk proxy grep -i artcraft
```

Expected: `No such file or directory`, and no `artcraft` listener on 127.0.0.1. The ArtCraft terminal log shows `cli bridge disabled`.

- [ ] **Step 3: Start the credential-sync probe in the background (`run_in_background`), before the relaunch**

```bash
LOG="${TMPDIR:-/tmp}/artcraft-sync.txt" .venv/bin/python - <<'EOF'
import os, time
from artcraft_cli.utils import bridge
from artcraft_cli.errors import CliError
out = open(os.environ["LOG"], "w", buffering=1)
start, up = time.monotonic(), None
while time.monotonic() - start < 300:
    try:
        ready = bridge.health()["readiness"]["credentials_synced"]
    except CliError:
        time.sleep(0.25)
        continue
    if up is None:
        up = time.monotonic()
        print(f"bridge up {up - start:.1f}s after the probe started", file=out)
    if ready:
        print(f"credentials_synced {time.monotonic() - up:.1f}s after the bridge came up", file=out)
        break
    time.sleep(0.25)
EOF
```

Expected: nothing yet. The probe polls `health()` every 0.25 s for up to 5 minutes and writes its two timestamps to `${TMPDIR:-/tmp}/artcraft-sync.txt`.

- [ ] **Step 4: STOP — controller and user only.** Ask the user to quit ArtCraft (Cmd-Q), relaunch it **with** the bridge, log in inside the app, and say roughly when the main window appeared:

```bash
ARTCRAFT_CLI_BRIDGE=1 ./script/artcraft/unix_dev.sh
```

- [ ] **Step 5: (c) Read the sync timing**

```bash
cat "${TMPDIR:-/tmp}/artcraft-sync.txt"
```

Expected: `bridge up …` then `credentials_synced N s after the bridge came up`, with N about 1–2 (spec §10.3 M1(c)). Record N.

- [ ] **Step 6: (b) Check the discovery file's mode and keys (this never prints the token)**

```bash
stat -f '%Sp %Su' ~/Artcraft/state/cli_bridge.json && python3 -c 'import json, pathlib; print(sorted(json.loads((pathlib.Path.home() / "Artcraft/state/cli_bridge.json").read_text())))'
```

Expected: `-rw------- <your user>` and `['app_version', 'bridge_protocol_version', 'pid', 'port', 'started_at', 'token']`

- [ ] **Step 7: (c, d) Run ping and app info**

```bash
.venv/bin/artcraft-cli --json ping && .venv/bin/artcraft-cli --json app info
```

Expected: `"protocol":1`, and `credentials_synced` true within about 2 s of the main window appearing (re-run once if it is false). `app info` shows the ArtCraft version.

- [ ] **Step 8: (e) Check whoami while logged in, then again after the user logs out in the app (they log back in afterwards)**

```bash
.venv/bin/artcraft-cli --json account whoami
```

Expected: `logged_in: true` with the username the app shows. After logout, `logged_in: false`.

- [ ] **Step 9: (f) List every job and compare with the app's task panel**

```bash
.venv/bin/artcraft-cli --json jobs list --all --limit 200
```

Expected: `truncated: false` and the same jobs as the task panel (the user confirms)

- [ ] **Step 10: (g) Run the zero-spend dry runs: pick models, price them, refuse a legacy model, and compare batch pricing**

```bash
MODEL=$(.venv/bin/artcraft-cli --json models list --kind image | .venv/bin/python -c 'import json,sys; print(next(m["model"] for m in json.load(sys.stdin)["models"] if not m.get("is_disabled")))')
VMODEL=$(.venv/bin/artcraft-cli --json models list --kind video | .venv/bin/python -c 'import json,sys; print(next(m["model"] for m in json.load(sys.stdin)["models"] if not m.get("is_disabled")))')
echo "$MODEL $VMODEL"
.venv/bin/artcraft-cli --json generate image --model "$MODEL" --prompt x --dry-run
.venv/bin/artcraft-cli --json generate image --model recraft_3 --prompt x --dry-run
for n in 1 2; do .venv/bin/artcraft-cli --json generate image --model "$MODEL" --prompt x --set image_batch_count=$n --dry-run; done
for n in 1 2; do .venv/bin/artcraft-cli --json generate video --model "$VMODEL" --prompt x --set video_batch_count=$n --dry-run; done
python3 -c 'import struct, zlib, pathlib
c = lambda k, d: struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d))
rows = b"".join(b"\x00" + b"\x80" * 8 for _ in range(8))
pathlib.Path("/tmp/artcraft-ref.png").write_bytes(b"\x89PNG\r\n\x1a\n" + c(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 0, 0, 0, 0)) + c(b"IDAT", zlib.compress(rows)) + c(b"IEND", b""))'
.venv/bin/artcraft-cli --json generate image --model "$MODEL" --prompt x --media image_media_tokens=/tmp/artcraft-ref.png --dry-run
```

Expected: a price for `$MODEL`; `unsupported_route` for `recraft_3`. **Image:** note whether `cost_in_credits` doubles from batch 1 to batch 2 (does the server price the batch?). **Video:** the bridge strips `video_batch_count` before estimating and multiplies locally (Rust plan, amendment A), so compare `effective_credits`, which must double, and have the user check it against the app's displayed price for a 2-video batch; video `cost_in_credits` is not measurable through the bridge. The last call (a local reference priced with the placeholder `mf_estimate_0`) returns a price rather than an upstream error; if it errors, record the exact error, because the server then rejects placeholder tokens and `--dry-run` must drop them. The user confirms that credits and the task count in the app have not changed.

- [ ] **Step 11: (h) Send the gate negatives (Python, because curl is blocked here)**

```bash
.venv/bin/python - <<'EOF'
import json, pathlib, requests
d = json.loads((pathlib.Path.home() / "Artcraft/state/cli_bridge.json").read_text())
base, auth = f"http://127.0.0.1:{d['port']}", {"Authorization": f"Bearer {d['token']}"}
s = requests.Session(); s.trust_env = False
def show(label, r): print(f"{label:16} {r.status_code} {r.json().get('error', {}).get('code', 'ok')}")
show("Host evil.test", s.get(base + "/v1/health", headers={**auth, "Host": "evil.test"}))
show("Origin", s.get(base + "/v1/health", headers={**auth, "Origin": "https://evil.test"}))
show("Sec-Fetch-Site", s.get(base + "/v1/health", headers={**auth, "Sec-Fetch-Site": "cross-site"}))
show("no token", s.get(base + "/v1/health"))
show("OPTIONS", s.options(base + "/v1/rpc", headers=auth))
show("text/plain POST", s.post(base + "/v1/rpc", headers={**auth, "Content-Type": "text/plain"}, data="{}"))
show("unknown op", s.post(base + "/v1/rpc", headers=auth, json={"op": "nope.nope", "args": {}}))
EOF
```

Expected:

```text
Host evil.test   403 forbidden_host
Origin           403 forbidden_origin
Sec-Fetch-Site   403 forbidden_origin
no token         401 unauthorized
OPTIONS          405 method_not_allowed
text/plain POST  415 unsupported_media_type
unknown op       200 unknown_op
```

- [ ] **Step 12: Run the live test suite**

```bash
.venv/bin/pytest -m e2e -v -s
```

Expected: the 5 live tests pass (`ping…`, `whoami…`, `models_list…`, `browser_origin…`, `installed_console_script…`)

- [ ] **Step 13: STOP — controller and user only.** (i) Ask the user to quit ArtCraft with Cmd-Q, then check that the file is gone. This confirms that the runtime exit plugin receives `RunEvent::Exit`:

```bash
ls ~/Artcraft/state/cli_bridge.json
```

Record the findings. Then send the batch-pricing answer to the `artcraft` session (it settles amendment A's optional check), and mark ACLI M1 done in Plane.

Write the project memory `project_artcraft_live_findings.md` with these fields:
- **M1 date:**
- **credentials_synced delay:** about N s after the main window appeared
- **image batch pricing:** `cost_in_credits` covers `image_batch_count`: yes/no
- **video batch pricing:** `effective_credits` doubles for 2 videos and matches the app's price: yes/no
- **placeholder pricing:** the `mf_estimate_0` dry run returned a price: yes/no (if no, the exact error)
- **exit cleanup:** the discovery file was removed on Cmd-Q: yes/no
- **deviations:** any check whose output differed from the expected output above, quoted exactly

Add its index line to `MEMORY.md`.

Spec §10.3 M1(g) also asks for the batch answer in §7.3. In `docs/superpowers/specs/2026-10-09-artcraft-cli-bridge-design.md` §7.3, append this bullet under step 3, which records a finding and does not change the contract:

`   - **M1 live result (<date>):** image cost_in_credits covers image_batch_count: <yes/no>; video effective_credits for 2 videos matches the app: <yes/no>.`

- [ ] **Step 14: Commit the spec note on the branch**

```bash
git add docs/superpowers/specs/2026-10-09-artcraft-cli-bridge-design.md
PATH="$PWD/.venv/bin:$PATH" git commit -m "docs: record M1 batch pricing in bridge spec"
```

Expected: the commit is created and the hooks pass

---

## Milestone M2 — Spending

Spec §6.3 (submit), §6.4 (wait), §7.4, §10.3 M2. Tasks 12–15 need no ArtCraft. Task 16 spends real credits and needs ARTC M2.

### Task 12: Credits, subscription, jobs get, remote listing

**Files:**
- Modify: `artcraft_cli/tests/test_core.py`
- Modify: `artcraft_cli/core/account.py`
- Modify: `artcraft_cli/core/jobs.py`
- Modify: `artcraft_cli/artcraft_cli.py`

**Interfaces:**
- Consumes: `bridge.rpc` (Task 7), and `emit` and `jobs_group` (Task 8).
- Produces:
  - `core.account.credits()` and `core.account.subscription()`.
  - `core.jobs.get_jobs(job_ids: list[str], *, remote: bool) -> dict[str, Any]`, which sends `{"job_ids", "include_remote"}`.
  - Commands: `account credits`, `account subscription`, `jobs list --remote`, and `jobs get JOB... [--remote]`.

- [ ] **Step 1: Add the failing rows for the M2 read commands**

Modify `artcraft_cli/tests/test_core.py` (1 edit; each old text occurs once):

Edit 1: replace

````python
    ),
````

with

````python
    ),
    (["account", "credits"], "account.credits", {}),
    (["account", "subscription"], "account.subscription", {}),
    (
        ["jobs", "list", "--remote"],
        "jobs.list",
        {"origin": "cli", "limit": 50, "include_remote": True},
    ),
    (["jobs", "get", "j1"], "jobs.get", {"job_ids": ["j1"], "include_remote": False}),
    (
        ["jobs", "get", "j1", "j2", "--remote"],
        "jobs.get",
        {"job_ids": ["j1", "j2"], "include_remote": True},
    ),
````

- [ ] **Step 2: Run the new rows to verify they fail**

Run: `.venv/bin/pytest artcraft_cli/tests/test_core.py -v -k "single_op and (credits or subscription or remote or jobs-get)"`

Expected: FAIL — 5 failed, 19 deselected; first failure: `AssertionError: assert (1, '') == (0, '')`

- [ ] **Step 3: Write the helpers and commands**

Modify `artcraft_cli/core/account.py` (1 edit; each old text occurs once):

Edit 1: replace

````python
    return bridge.rpc("account.session", {})
````

with

````python
    return bridge.rpc("account.session", {})


def credits() -> dict[str, Any]:
    return bridge.rpc("account.credits", {})


def subscription() -> dict[str, Any]:
    return bridge.rpc("account.subscription", {})
````

Modify `artcraft_cli/core/jobs.py` (1 edit; each old text occurs once):

Edit 1: replace

````python
    )
````

with

````python
    )


def get_jobs(job_ids: list[str], *, remote: bool) -> dict[str, Any]:
    return bridge.rpc("jobs.get", {"job_ids": job_ids, "include_remote": remote})
````

Modify `artcraft_cli/artcraft_cli.py` (2 edits; each old text occurs once):

Edit 1: replace

````python
    emit(account.whoami())


````

with

````python
    emit(account.whoami())


@account_group.command("credits")
def account_credits() -> None:
    """Credit balances."""
    emit(account.credits())


@account_group.command("subscription")
def account_subscription() -> None:
    """The active subscription, if any."""
    emit(account.subscription())


````

Edit 2: replace

````python
@click.option("--limit", type=click.IntRange(1, 200), default=50, show_default=True)
def jobs_list(all_origins: bool, limit: int) -> None:
    """Recent jobs, newest first."""
    emit(jobs.list_jobs(all_origins=all_origins, remote=False, limit=limit))
````

with

````python
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
````

- [ ] **Step 4: Run every single-op row to verify they pass**

Run: `.venv/bin/pytest artcraft_cli/tests/test_core.py -v -k single_op`

Expected: PASS — 10 passed, 14 deselected

- [ ] **Step 5: Commit**

```bash
.venv/bin/pytest -m "not e2e" -q
git add artcraft_cli/core/account.py artcraft_cli/core/jobs.py artcraft_cli/artcraft_cli.py artcraft_cli/tests/test_core.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat: add credits, subscription, jobs get and remote job listing"
```

Expected: the unit suite passes, then every pre-commit hook passes and the commit is created. If a hook rewrites a file, `git add` it again and re-run the commit; never pass `--no-verify`.

### Task 13: jobs wait and safe CDN downloads

**Files:**
- Create: `artcraft_cli/core/media.py`
- Modify: `artcraft_cli/tests/conftest.py`
- Modify: `artcraft_cli/tests/test_core.py`
- Modify: `artcraft_cli/tests/test_bridge.py`
- Modify: `artcraft_cli/utils/bridge.py`
- Modify: `artcraft_cli/core/jobs.py`
- Modify: `artcraft_cli/artcraft_cli.py`

**Interfaces:**
- Consumes: `core.jobs.get_jobs` (Task 12) and `bridge.rpc` (Task 7).
- Produces, in `core/jobs.py`:
  - `DEFAULT_WAIT_TIMEOUT_S = 900.0`, `POLL_INTERVAL_S = 5.0`, `REMOTE_INTERVAL_S = 60.0`, `FAILED_STATUSES` and `KEEP_POLLING_REASONS = {"rate_limited", "upstream_unavailable", "credentials_not_synced"}`.
  - `wait_for_jobs(job_ids: list[str], *, timeout_s: float) -> list[dict[str, Any]]`. Its first poll and its final poll are remote, and the final remote call always runs once every job has succeeded, even in the last 5 s. After a remote check, any unresolved reason outside `KEEP_POLLING_REASONS` fails at once, with the reason as the error code (`job_not_found`, `not_logged_in`, …).
  - `download_files(finished: list[dict[str, Any]], out_dir: Path, *, force: bool) -> list[dict[str, str]]`, which returns `{media_token, path}` items.
- Produces, in `core/media.py`: `download_to(media_token: str, cdn_url: str | None, out_dir: Path, *, force: bool) -> tuple[Path, int]`. It saves to `<out_dir>/<media_token><CDN path suffix>`.
- Produces, in `utils/bridge.py`: `download(url: str, dest: Path, *, force: bool) -> int`, with `DOWNLOAD_TIMEOUT = 60` and `DOWNLOAD_CHUNK_BYTES`. It uses https only and writes through a `.part` file. Any network or local write failure (`OSError`, which includes `requests` errors) becomes `download_failed` with `details.path`, and leaves no `.part` file behind.
- Command: `jobs wait JOB... [--timeout S] [--download DIR] [--force]`.
- Test fixture: `cdn`, a fake `requests.get` that records `url` and kwargs.

- [ ] **Step 1: Write the failing wait and download tests**

Modify `artcraft_cli/tests/conftest.py` (1 edit; each old text occurs once):

Edit 1: replace

````python
    monkeypatch.setattr(bridge, "_session", lambda: fake)
    return fake


@pytest.fixture
````

with

````python
    monkeypatch.setattr(bridge, "_session", lambda: fake)
    return fake


@pytest.fixture
def cdn(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """A fake CDN at the requests.get boundary; records each call's url and kwargs."""
    calls: list[dict[str, Any]] = []

    def fake_get(url: str, **kwargs: Any) -> requests.Response:
        calls.append({"url": url, **kwargs})
        return response(200, b"image-bytes:" + url.encode())

    monkeypatch.setattr(requests, "get", fake_get)
    return calls


@pytest.fixture
````

Modify `artcraft_cli/tests/test_core.py` (4 edits; each old text occurs once):

Edit 1: replace

````python
from __future__ import annotations

````

with

````python
from __future__ import annotations

import io
import itertools
````

Edit 2: replace

````python

from .conftest import HEALTH, FakeBridge
````

with

````python
import requests

from .conftest import HEALTH, FakeBridge, FakeClock
````

Edit 3: replace

````python
    "effective_credits": 4,
}
````

with

````python
    "effective_credits": 4,
}


def job(job_id: str, status: str, files: list[str] | None = None) -> dict[str, Any]:
    """A JobView (spec §7.6) with the fields the CLI reads."""
    return {
        "job_id": job_id,
        "status": status,
        "terminal": status in ("succeeded", "failed", "cancelled"),
        "result": {
            "files": [
                {"media_token": token, "cdn_url": f"https://cdn.example/{token}.png"}
                for token in files or []
            ],
            "batch_token": None,
        }
        if status == "succeeded"
        else None,
        "failure": {"category": "model", "message": "nsfw"} if status == "failed" else None,
    }


def jobs_seen(*views: dict[str, Any], unresolved: list[dict[str, str]] | None = None) -> Any:
    return {"jobs": list(views), "unresolved": unresolved or []}
````

Edit 4: replace

````python
    assert fake_bridge.args(op) == [args]
````

with

````python
    assert fake_bridge.args(op) == [args]


# --- jobs wait (spec §6.4) --------------------------------------------------------------


def test_wait_returns_all_files_when_every_job_succeeds(
    fake_bridge: FakeBridge, run: Run, cdn: list[dict[str, Any]], tmp_path: Path
) -> None:
    fake_bridge.on(
        "jobs.get",
        jobs_seen(job("j1", "running"), job("j2", "queued")),
        jobs_seen(job("j1", "succeeded", ["a1"]), job("j2", "succeeded", ["b1"])),
        jobs_seen(job("j1", "succeeded", ["a1"]), job("j2", "succeeded", ["b1", "b2", "b3"])),
    )

    code, out, _ = run("--json", "jobs", "wait", "j1", "j2", "--download", str(tmp_path))

    assert code == 0
    body = json.loads(out)
    saved = [Path(item["path"]) for item in body["downloads"]]
    assert [path.name for path in saved] == ["a1.png", "b1.png", "b2.png", "b3.png"]
    assert all(path.read_bytes().startswith(b"image-bytes:") for path in saved)
    assert fake_bridge.args("jobs.get")[-1]["include_remote"] is True


def test_wait_fails_with_job_failed_and_full_details(fake_bridge: FakeBridge, run: Run) -> None:
    fake_bridge.on("jobs.get", jobs_seen(job("j1", "running")), jobs_seen(job("j1", "failed")))

    code, out, _ = run("--json", "jobs", "wait", "j1")

    assert code == 1
    error = error_of(out)
    assert error["code"] == "job_failed"
    assert error["details"]["status"] == "failed"
    assert error["details"]["job"]["failure"] == {"category": "model", "message": "nsfw"}


def test_wait_times_out_with_last_seen_state(
    fake_bridge: FakeBridge, run: Run, clock: FakeClock
) -> None:
    fake_bridge.on("jobs.get", jobs_seen(job("j1", "running")))
    started = clock.now

    code, out, _ = run("--json", "jobs", "wait", "j1", "--timeout", "30")

    assert code == 1
    error = error_of(out)
    assert error["code"] == "job_wait_timeout"
    assert error["details"]["last_seen"]["jobs"][0]["status"] == "running"
    assert clock.now - started <= 30


def test_wait_never_polls_faster_than_five_seconds(fake_bridge: FakeBridge, run: Run) -> None:
    fake_bridge.on(
        "jobs.get",
        *[jobs_seen(job("j1", "running"))] * 30,
        jobs_seen(job("j1", "succeeded", ["a1"])),
    )

    code, _, _ = run("--json", "jobs", "wait", "j1")

    times = [call["t"] for call in fake_bridge.calls]
    assert code == 0
    assert len(times) == 32
    assert all(later - earlier >= 5 for earlier, later in itertools.pairwise(times))


def test_wait_checks_remote_at_most_once_a_minute(fake_bridge: FakeBridge, run: Run) -> None:
    fake_bridge.on("jobs.get", jobs_seen(job("j1", "running")))

    run("--json", "jobs", "wait", "j1", "--timeout", "300")

    remote_times = [
        call["t"] for call in fake_bridge.calls if call["json"]["args"]["include_remote"]
    ]
    assert len(remote_times) >= 4
    assert all(later - earlier >= 60 for earlier, later in itertools.pairwise(remote_times))


def test_wait_fails_fast_on_unknown_job_ids(
    fake_bridge: FakeBridge, run: Run, clock: FakeClock
) -> None:
    unknown = [{"job_id": "nope", "reason": "job_not_found"}]
    fake_bridge.on("jobs.get", jobs_seen(job("j1", "running"), unresolved=unknown))
    started = clock.now

    code, out, _ = run("--json", "jobs", "wait", "j1", "nope")

    assert code == 1
    assert error_of(out)["code"] == "job_not_found"
    assert clock.now == started


def test_wait_treats_cancelled_jobs_as_failed(fake_bridge: FakeBridge, run: Run) -> None:
    fake_bridge.on("jobs.get", jobs_seen(job("j1", "succeeded", ["a1"]), job("j2", "cancelled")))

    code, out, _ = run("--json", "jobs", "wait", "j1", "j2")

    assert code == 1
    error = error_of(out)
    assert (error["code"], error["details"]["status"]) == ("job_failed", "cancelled")


def test_wait_fails_fast_when_logged_out(
    fake_bridge: FakeBridge, run: Run, clock: FakeClock
) -> None:
    logged_out = [{"job_id": "j9", "reason": "not_logged_in"}]
    fake_bridge.on("jobs.get", jobs_seen(unresolved=logged_out))
    started = clock.now

    code, out, _ = run("--json", "jobs", "wait", "j9")

    assert code == 1
    assert error_of(out)["code"] == "not_logged_in"
    assert clock.now == started


def test_wait_finishes_jobs_that_succeed_in_the_last_interval(
    fake_bridge: FakeBridge, run: Run
) -> None:
    fake_bridge.on(
        "jobs.get",
        jobs_seen(job("j1", "running")),
        jobs_seen(job("j1", "running")),
        jobs_seen(job("j1", "succeeded", ["a1"])),
    )

    code, out, _ = run("--json", "jobs", "wait", "j1", "--timeout", "14")

    assert code == 0
    assert [view["status"] for view in json.loads(out)["jobs"]] == ["succeeded"]
    assert fake_bridge.args("jobs.get")[-1]["include_remote"] is True


def test_download_refuses_to_clobber_and_rejects_non_https(
    fake_bridge: FakeBridge, run: Run, cdn: list[dict[str, Any]], tmp_path: Path
) -> None:
    done = job("j1", "succeeded", ["a1"])
    plain_http = job("j2", "succeeded", ["b1"])
    plain_http["result"]["files"][0]["cdn_url"] = "http://cdn.example/b1.png"
    fake_bridge.on("jobs.get", jobs_seen(done), jobs_seen(done), jobs_seen(plain_http))
    (tmp_path / "a1.png").write_bytes(b"keep me")

    code, out, _ = run("--json", "jobs", "wait", "j1", "--download", str(tmp_path))
    assert (code, error_of(out)["code"]) == (1, "output_exists")
    assert (tmp_path / "a1.png").read_bytes() == b"keep me"

    code, _, _ = run("--json", "jobs", "wait", "j1", "--download", str(tmp_path), "--force")
    assert code == 0
    assert (tmp_path / "a1.png").read_bytes() != b"keep me"

    code, out, _ = run("--json", "jobs", "wait", "j2", "--download", str(tmp_path))
    assert (code, error_of(out)["code"]) == (1, "download_failed")
    assert all(call["url"].startswith("https://") for call in cdn)


class DropsMidway(io.BytesIO):
    """A CDN body whose connection resets after the first chunk."""

    def read(self, size: int | None = -1, /) -> bytes:
        if self.tell():
            raise ConnectionResetError("connection reset by peer")
        return super().read(4)


def test_interrupted_download_leaves_no_partial_file(
    fake_bridge: FakeBridge, run: Run, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def dropping_get(url: str, **kwargs: Any) -> requests.Response:
        resp = requests.Response()
        resp.status_code = 200
        resp.raw = DropsMidway(b"partial image bytes")
        return resp

    monkeypatch.setattr(requests, "get", dropping_get)
    fake_bridge.on("jobs.get", jobs_seen(job("j1", "succeeded", ["a1"])))
    dest = tmp_path / "downloads"
    dest.mkdir()

    code, out, _ = run("--json", "jobs", "wait", "j1", "--download", str(dest))

    assert (code, error_of(out)["code"]) == (1, "download_failed")
    assert list(dest.iterdir()) == []


def test_local_write_failures_during_download_are_json_errors(
    fake_bridge: FakeBridge, run: Run, cdn: list[dict[str, Any]], tmp_path: Path
) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    fake_bridge.on("jobs.get", jobs_seen(job("j1", "succeeded", ["a1"])))
    try:
        code, out, _ = run("--json", "jobs", "wait", "j1", "--download", str(locked))
    finally:
        locked.chmod(0o700)

    assert code == 1
    assert error_of(out)["code"] == "download_failed"
    assert list(locked.iterdir()) == []
````

Modify `artcraft_cli/tests/test_bridge.py` (1 edit; each old text occurs once):

Edit 1: replace

````python
    assert fake_bridge.ops() == ["generate.submit"]
````

with

````python
    assert fake_bridge.ops() == ["generate.submit"]


def test_bridge_token_is_never_sent_to_cdn_hosts(
    fake_bridge: FakeBridge,
    run: Callable[..., tuple[int, str, str]],
    cdn: list[dict[str, Any]],
    tmp_path: Path,
) -> None:
    finished = {
        "job_id": "j1",
        "status": "succeeded",
        "terminal": True,
        "result": {"files": [{"media_token": "a1", "cdn_url": "https://cdn.example/a1.png"}]},
    }
    fake_bridge.on("jobs.get", {"jobs": [finished], "unresolved": []})

    code, _, _ = run("--json", "jobs", "wait", "j1", "--download", str(tmp_path))

    assert code == 0
    assert [call["url"] for call in cdn] == ["https://cdn.example/a1.png"]
    assert "headers" not in cdn[0]
    assert TOKEN not in json.dumps(cdn, default=str)
    assert fake_bridge.ops() == ["jobs.get"]
````

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest artcraft_cli/tests/test_core.py::test_wait_returns_all_files_when_every_job_succeeds artcraft_cli/tests/test_core.py::test_wait_fails_with_job_failed_and_full_details artcraft_cli/tests/test_core.py::test_wait_times_out_with_last_seen_state artcraft_cli/tests/test_core.py::test_wait_never_polls_faster_than_five_seconds artcraft_cli/tests/test_core.py::test_wait_checks_remote_at_most_once_a_minute artcraft_cli/tests/test_core.py::test_wait_fails_fast_on_unknown_job_ids artcraft_cli/tests/test_core.py::test_wait_treats_cancelled_jobs_as_failed artcraft_cli/tests/test_core.py::test_wait_fails_fast_when_logged_out artcraft_cli/tests/test_core.py::test_wait_finishes_jobs_that_succeed_in_the_last_interval artcraft_cli/tests/test_core.py::test_download_refuses_to_clobber_and_rejects_non_https artcraft_cli/tests/test_core.py::test_interrupted_download_leaves_no_partial_file artcraft_cli/tests/test_core.py::test_local_write_failures_during_download_are_json_errors artcraft_cli/tests/test_bridge.py::test_bridge_token_is_never_sent_to_cdn_hosts -v`

Expected: FAIL — 13 failed; first failure: `assert 1 == 0`

- [ ] **Step 3: Write the download primitive, the wait loop and the command**

Modify `artcraft_cli/utils/bridge.py` (4 edits; each old text occurs once):

Edit 1: replace

````python
from __future__ import annotations

````

with

````python
from __future__ import annotations

import contextlib
````

Edit 2: replace

````python
from typing import Any
````

with

````python
from typing import Any
from urllib.parse import urlparse
````

Edit 3: replace

````python
NOT_SYNCED_POLL_S = 0.5
````

with

````python
NOT_SYNCED_POLL_S = 0.5
DOWNLOAD_TIMEOUT = 60
DOWNLOAD_CHUNK_BYTES = 1024 * 1024
````

Edit 4: replace

````python
        error["code"], str(error.get("message", "")), details if isinstance(details, dict) else None
    )
````

with

````python
        error["code"], str(error.get("message", "")), details if isinstance(details, dict) else None
    )


def download(url: str, dest: Path, *, force: bool) -> int:
    """Fetch a CDN URL into dest. Uses plain requests: no bridge session, no token."""
    if urlparse(url).scheme != "https":
        raise CliError("download_failed", "refusing a download URL that is not https")
    if dest.exists() and not force:
        raise CliError("output_exists", f"{dest} already exists", {"path": str(dest)})
    partial = dest.with_name(dest.name + ".part")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True) as resp:
            resp.raise_for_status()
            with partial.open("wb") as out:
                for chunk in resp.iter_content(DOWNLOAD_CHUNK_BYTES):
                    out.write(chunk)
        partial.replace(dest)
    except OSError as exc:  # requests.RequestException is an OSError too
        with contextlib.suppress(OSError):
            partial.unlink(missing_ok=True)
        raise CliError(
            "download_failed", f"download failed: {type(exc).__name__}", {"path": str(dest)}
        ) from None
    return dest.stat().st_size
````

Create `artcraft_cli/core/media.py`:

````python
"""Library media: image upload, lookup, listing and CDN downloads."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from artcraft_cli.errors import CliError
from artcraft_cli.utils import bridge


def download_to(
    media_token: str, cdn_url: str | None, out_dir: Path, *, force: bool
) -> tuple[Path, int]:
    """Save one file as <out_dir>/<media_token><suffix of the CDN path>."""
    if not cdn_url:
        raise CliError("download_failed", f"media {media_token} has no cdn_url")
    path = out_dir / f"{media_token}{Path(urlparse(cdn_url).path).suffix}"
    return path, bridge.download(cdn_url, path, force=force)
````

Replace the whole of `artcraft_cli/core/jobs.py` with:

````python
"""Generation jobs: list, get, wait, download results, dismiss."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from artcraft_cli.core import media
from artcraft_cli.errors import CliError
from artcraft_cli.utils import bridge

DEFAULT_WAIT_TIMEOUT_S = 900.0
POLL_INTERVAL_S = 5.0
REMOTE_INTERVAL_S = 60.0
FAILED_STATUSES = frozenset({"failed", "cancelled"})
KEEP_POLLING_REASONS = frozenset({"rate_limited", "upstream_unavailable", "credentials_not_synced"})


def list_jobs(*, all_origins: bool, remote: bool, limit: int) -> dict[str, Any]:
    return bridge.rpc(
        "jobs.list",
        {"origin": "all" if all_origins else "cli", "limit": limit, "include_remote": remote},
    )


def get_jobs(job_ids: list[str], *, remote: bool) -> dict[str, Any]:
    return bridge.rpc("jobs.get", {"job_ids": job_ids, "include_remote": remote})


def wait_for_jobs(job_ids: list[str], *, timeout_s: float) -> list[dict[str, Any]]:
    """Poll every 5 s; ask the server at most once a minute, plus one final time."""
    start = time.monotonic()
    last_remote: float | None = None
    finishing = False
    while True:
        now = time.monotonic()
        use_remote = finishing or last_remote is None or now - last_remote >= REMOTE_INTERVAL_S
        seen = get_jobs(job_ids, remote=use_remote)
        if use_remote:
            last_remote = now
        _raise_if_failed(seen, after_remote=use_remote)
        done = _all_succeeded(seen, job_ids)
        if done and use_remote:
            return list(seen["jobs"])
        finishing = done  # one final remote call expands batches before returning
        if not finishing and time.monotonic() - start + POLL_INTERVAL_S > timeout_s:
            raise CliError(
                "job_wait_timeout", f"jobs unfinished after {timeout_s:g} s", {"last_seen": seen}
            )
        time.sleep(POLL_INTERVAL_S)


def _raise_if_failed(seen: dict[str, Any], *, after_remote: bool) -> None:
    for job in seen["jobs"]:
        if job["status"] in FAILED_STATUSES:
            raise CliError(
                "job_failed",
                f"job {job['job_id']} {job['status']}",
                {"status": job["status"], "job": job},
            )
    if after_remote:
        stuck = [u for u in seen["unresolved"] if u["reason"] not in KEEP_POLLING_REASONS]
        if stuck:
            raise CliError(
                stuck[0]["reason"],
                f"cannot resolve job {stuck[0]['job_id']}: {stuck[0]['reason']}",
                {"unresolved": seen["unresolved"]},
            )


def _all_succeeded(seen: dict[str, Any], job_ids: list[str]) -> bool:
    jobs = seen["jobs"]
    return (
        not seen["unresolved"]
        and {job["job_id"] for job in jobs} == set(job_ids)
        and all(job["status"] == "succeeded" for job in jobs)
    )


def download_files(
    finished: list[dict[str, Any]], out_dir: Path, *, force: bool
) -> list[dict[str, str]]:
    """Download every result file of finished jobs into out_dir."""
    downloads: list[dict[str, str]] = []
    for job in finished:
        result = job.get("result") or {}
        for file in result.get("files", []):
            path, _ = media.download_to(
                file["media_token"], file.get("cdn_url"), out_dir, force=force
            )
            downloads.append({"media_token": file["media_token"], "path": str(path)})
    return downloads
````

Modify `artcraft_cli/artcraft_cli.py` (2 edits; each old text occurs once):

Edit 1: replace

````python
import sys
````

with

````python
import sys
from pathlib import Path
````

Edit 2: replace

````python
    emit(jobs.get_jobs(list(job_ids), remote=remote))


````

with

````python
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


````

- [ ] **Step 4: Run the core and transport tests to verify they pass**

Run: `.venv/bin/pytest artcraft_cli/tests/test_core.py artcraft_cli/tests/test_bridge.py -v`

Expected: PASS — 53 passed

- [ ] **Step 5: Commit**

```bash
.venv/bin/pytest -m "not e2e" -q
git add artcraft_cli/utils/bridge.py artcraft_cli/core/media.py artcraft_cli/core/jobs.py artcraft_cli/artcraft_cli.py artcraft_cli/tests/conftest.py artcraft_cli/tests/test_core.py artcraft_cli/tests/test_bridge.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat: add jobs wait with paced polling and safe CDN downloads"
```

Expected: the unit suite passes, then every pre-commit hook passes and the commit is created. If a hook rewrites a file, `git add` it again and re-run the commit; never pass `--no-verify`.

### Task 14: generate submit, --wait and --download

**Files:**
- Modify: `artcraft_cli/tests/test_core.py`
- Modify: `artcraft_cli/core/media.py`
- Modify: `artcraft_cli/core/generate.py`
- Modify: `artcraft_cli/artcraft_cli.py`

**Interfaces:**
- Consumes: `build_request` (Task 9), `wait_for_jobs` and `download_files` (Task 13), and `bridge.rpc` (Task 7), which maps post-send failures to `outcome_unknown` for `generate.submit`.
- Produces:
  - `core.media.idempotency_token(value: str | None) -> str`. It returns a fresh uuid4 when `value` is None; a value that is not a canonical lowercase UUID raises `usage_error`.
  - `core.media.prepare_download_dir(out_dir: Path) -> None`. It creates the directory and raises `usage_error` if it can't be created or isn't writable. `run` calls it before any RPC, so a bad `--download` never costs credits.
  - `core.generate.run(modality, request, *, max_credits: int, token: str, wait: bool, timeout_s: float, download_dir: Path | None, force: bool) -> dict[str, Any]`. Every `CliError` it raises carries `details.idempotency_token`. Until Task 18 it refuses local `--media` files with `usage_error`.
  - Command: `generate … --max-credits N [--idempotency-token UUID] [--wait [--timeout S]] [--download DIR [--force]]`.

- [ ] **Step 1: Write the failing submit tests**

Modify `artcraft_cli/tests/test_core.py` (3 edits; each old text occurs once):

Edit 1: replace

````python
from .conftest import HEALTH, FakeBridge, FakeClock

Run = Callable[..., tuple[int, str, str]]
````

with

````python
from .conftest import HEALTH, FakeBridge, FakeClock, op_error

Run = Callable[..., tuple[int, str, str]]
TOKEN_A = "0b8f6a52-6a8e-4d55-9d43-3d6c0f6f1a10"
````

Edit 2: replace

````python
        ["jobs", "list", "--limit", "0"],
````

with

````python
        ["jobs", "list", "--limit", "0"],
        ["generate", "image", "--model", "m", "--max-credits", "5", "--idempotency-token", "nope"],
        [
            "generate",
            "image",
            "--model",
            "m",
            "--max-credits",
            "5",
            "--idempotency-token",
            TOKEN_A.upper(),
        ],
````

Edit 3: replace

````python
    assert fake_bridge.args(op) == [args]
````

with

````python
    assert fake_bridge.args(op) == [args]


# --- generate submit (spec §6.2, §6.3) --------------------------------------------------


@pytest.mark.parametrize(
    ("outcome", "code"),
    [
        (op_error("internal_error", status=500), "internal_error"),
        (op_error("bridge_busy", status=503), "bridge_busy"),
        (op_error("upstream_error"), "upstream_error"),
        (op_error("operation_in_progress"), "operation_in_progress"),
    ],
)
def test_submit_is_never_auto_retried_after_send(
    fake_bridge: FakeBridge, run: Run, outcome: requests.Response, code: str
) -> None:
    fake_bridge.on("generate.submit", outcome)

    exit_code, out, _ = run(
        "--json", "generate", "image", "--model", "m", "--prompt", "x",
        "--max-credits", "5", "--idempotency-token", TOKEN_A,
    )  # fmt: skip

    assert exit_code == 1
    error = error_of(out)
    assert error["code"] == code
    assert error["details"]["idempotency_token"] == TOKEN_A
    assert fake_bridge.ops() == ["generate.submit"]


def test_read_timeout_on_submit_reports_outcome_unknown(fake_bridge: FakeBridge, run: Run) -> None:
    fake_bridge.on("generate.submit", requests.ReadTimeout())

    code, out, _ = run(
        "--json", "generate", "image", "--model", "m", "--prompt", "x",
        "--max-credits", "5", "--idempotency-token", TOKEN_A,
    )  # fmt: skip

    assert code == 1
    error = error_of(out)
    assert error["code"] == "outcome_unknown"
    assert error["details"] == {"idempotency_token": TOKEN_A, "reason": "response_timeout"}
    assert error["retryable"] is False
    assert fake_bridge.ops() == ["generate.submit"]


def test_unwritable_download_dir_is_refused_before_any_spend(
    fake_bridge: FakeBridge, run: Run, tmp_path: Path
) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        code, out, _ = run(
            "--json", "generate", "image", "--model", "m", "--prompt", "x", "--max-credits", "5",
            "--idempotency-token", TOKEN_A, "--download", str(locked),
        )  # fmt: skip
    finally:
        locked.chmod(0o700)

    assert code == 1
    error = error_of(out)
    assert (error["code"], error["details"]["idempotency_token"]) == ("usage_error", TOKEN_A)
    assert fake_bridge.calls == []
````

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest artcraft_cli/tests/test_core.py::test_submit_is_never_auto_retried_after_send artcraft_cli/tests/test_core.py::test_read_timeout_on_submit_reports_outcome_unknown artcraft_cli/tests/test_core.py::test_unwritable_download_dir_is_refused_before_any_spend -v`

Expected: FAIL — 6 failed; first failure: `AssertionError: assert 'usage_error' == 'internal_error'`

The two new `test_usage_errors_render_as_json_with_exit_1` rows (a malformed and an uppercase `--idempotency-token`) are guards. They already pass, because before this task the option itself is unknown to Click.

- [ ] **Step 3: Write the token check, the submit flow and the full command**

Modify `artcraft_cli/core/media.py` (2 edits; each old text occurs once):

Edit 1: replace

````python
from __future__ import annotations

````

with

````python
from __future__ import annotations

import os
import uuid
````

Edit 2: replace

````python
from artcraft_cli.utils import bridge
````

with

````python
from artcraft_cli.utils import bridge


def idempotency_token(value: str | None) -> str:
    """The caller's token if it is a canonical lowercase UUID, else a fresh uuid4."""
    if value is None:
        return str(uuid.uuid4())
    try:
        canonical = str(uuid.UUID(value))
    except ValueError:
        canonical = ""
    if canonical != value:
        raise CliError("usage_error", "--idempotency-token must be a lowercase hyphenated UUID")
    return value


def prepare_download_dir(out_dir: Path) -> None:
    """Create out_dir and check it is writable, so a bad --download fails before any spend."""
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CliError("usage_error", f"--download {out_dir}: {exc.strerror}") from None
    if not os.access(out_dir, os.W_OK | os.X_OK):
        raise CliError("usage_error", f"--download {out_dir} is not writable")
````

Modify `artcraft_cli/core/generate.py` (2 edits; each old text occurs once):

Edit 1: replace

````python
from typing import Any

````

with

````python
from typing import Any

from artcraft_cli.core import jobs, media
````

Edit 2: replace

````python
    return {**data, "omitted_inputs": omitted}
````

with

````python
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
    try:
        if download_dir is not None:
            media.prepare_download_dir(download_dir)
        if _has_local_files(request):
            raise CliError("usage_error", "local --media files arrive in M3; pass media tokens")
        result = bridge.rpc(
            "generate.submit",
            {
                "modality": modality,
                "idempotency_token": token,
                "max_credits": max_credits,
                "request": request,
            },
        )
        if wait or download_dir is not None:
            finished = jobs.wait_for_jobs(list(result["job_ids"]), timeout_s=timeout_s)
            result["jobs"] = finished
            if download_dir is not None:
                result["downloads"] = jobs.download_files(finished, download_dir, force=force)
        return result
    except CliError as err:
        err.details.setdefault("idempotency_token", token)
        raise


def _has_local_files(request: dict[str, Any]) -> bool:
    for value in request.values():
        if isinstance(value, Path):
            return True
        if isinstance(value, list) and any(isinstance(item, Path) for item in value):
            return True
    return False
````

Modify `artcraft_cli/artcraft_cli.py` (4 edits; each old text occurs once):

Edit 1: replace

````python
from artcraft_cli.core import account, generate, jobs, models
````

with

````python
from artcraft_cli.core import account, generate, jobs, media, models
````

Edit 2: replace

````python
@click.option("--dry-run", is_flag=True, help="Price only; never uploads or submits.")
````

with

````python
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
````

Edit 3: replace

````python
    dry_run: bool,
````

with

````python
    dry_run: bool,
    idempotency_token: str | None,
    wait: bool,
    timeout: float,
    download_dir: Path | None,
    force: bool,
````

Edit 4: replace

````python
    raise CliError("usage_error", "submitting arrives with generate.submit (M2); use --dry-run")
````

with

````python
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
````

- [ ] **Step 4: Run the core tests to verify they pass**

Run: `.venv/bin/pytest artcraft_cli/tests/test_core.py -v`

Expected: PASS — 44 passed

- [ ] **Step 5: Commit**

```bash
.venv/bin/pytest -m "not e2e" -q
git add artcraft_cli/core/media.py artcraft_cli/core/generate.py artcraft_cli/artcraft_cli.py artcraft_cli/tests/test_core.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat: add generate submit with idempotency token and wait"
```

Expected: the unit suite passes, then every pre-commit hook passes and the commit is created. If a hook rewrites a file, `git add` it again and re-run the commit; never pass `--no-verify`.

### Task 15: Live tests for estimates, spending and replay

**Files:**
- Modify: `artcraft_cli/tests/test_full_e2e.py`

**Interfaces:**
- Produces: the `spend` skip marker (requires `ARTCRAFT_E2E_SPEND=1`), plus `test_estimate_changes_no_credits_and_creates_no_job`, `test_cheapest_image_completes_and_downloads_every_file` and `test_retry_with_returned_token_replays_without_second_charge`.

- [ ] **Step 1: Add the M2 live tests**

Modify `artcraft_cli/tests/test_full_e2e.py` (3 edits; each old text occurs once):

Edit 1: replace

````python
import sys
````

with

````python
import sys
import uuid
````

Edit 2: replace

````python
MAX_CREDITS = os.environ.get("ARTCRAFT_E2E_MAX_CREDITS", "10")
````

with

````python
MAX_CREDITS = os.environ.get("ARTCRAFT_E2E_MAX_CREDITS", "10")
spend = pytest.mark.skipif(
    os.environ.get("ARTCRAFT_E2E_SPEND") != "1", reason="set ARTCRAFT_E2E_SPEND=1 to spend credits"
)
````

Edit 3: replace

````python
    assert json.loads(done.stdout)["bridge"]["protocol"] == 1
````

with

````python
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
    expected = sum(len(job["result"]["files"]) for job in body["jobs"])
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
````

- [ ] **Step 2: Run them without ArtCraft to verify they skip cleanly**

Run: `.venv/bin/pytest -m e2e -rs -q`

Expected: every selected test SKIPPED (ArtCraft is not running) — 8 skipped, 61 deselected

- [ ] **Step 3: Run the unit suite on Python 3.10 (CI's floor)**

```bash
PY310="${TMPDIR:-/tmp}/artcraft-cli-py310"
test -x "$PY310/bin/pytest" || { python3.10 -m venv "$PY310" && "$PY310/bin/pip" install -q -e '.[dev]'; }
"$PY310/bin/pytest" -m "not e2e" -q
```

Expected: the same pass count as on 3.13, ending in `passed`

- [ ] **Step 4: Commit**

```bash
.venv/bin/pytest -m "not e2e" -q
git add artcraft_cli/tests/test_full_e2e.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "test: add live checks for estimates, spending and replay"
```

Expected: the unit suite passes, then every pre-commit hook passes and the commit is created. If a hook rewrites a file, `git add` it again and re-run the commit; never pass `--no-verify`.

### Task 16: M2 live checklist (spends credits)

**Executor:** controller session, with the user where a step says so. Subagents do not run this task.

**Blocked by:** ARTC M2 (Rust plan) finished and built. Tasks 12–15 done.

Every step that spends is behind its own STOP gate, and every gate names the exact amount. Values that later steps need are kept in `${TMPDIR:-/tmp}/artcraft-live.env`, because each tool call starts a fresh shell.

- [ ] **Step 1: STOP — controller and user only.** Ask the user to launch ArtCraft with the bridge and log in, and to approve spending up to 3 × `ARTCRAFT_E2E_MAX_CREDITS` (default 10, so 30) credits on the live suite. Run only on an explicit yes:

```bash
ARTCRAFT_E2E_SPEND=1 .venv/bin/pytest -m e2e -v -s
```

Expected: every live test passes, including `test_cheapest_image_completes_and_downloads_every_file` (files saved) and `test_retry_with_returned_token_replays_without_second_charge`. The retry test confirms the same `job_ids`, `replayed: true`, a matching `replayed_from` and an unchanged balance.

- [ ] **Step 2: Pick the cheapest priced image model and save the probe values (free: dry runs only)**

```bash
LIVE_ENV="${TMPDIR:-/tmp}/artcraft-live.env" .venv/bin/python - <<'EOF'
import os, pathlib, uuid
from artcraft_cli.core import generate, models
from artcraft_cli.errors import CliError
cap = int(os.environ.get("ARTCRAFT_E2E_MAX_CREDITS", "10"))
priced = []
for model in models.list_models("image")["models"]:
    if model.get("is_disabled"):
        continue
    try:
        cost = generate.estimate("image", {"model": model["model"], "prompt": "probe"}).get("effective_credits")
    except CliError as err:
        print("not priced:", model["model"], err.code)
        continue
    if isinstance(cost, int) and 0 < cost <= cap:
        priced.append((cost, model["model"]))
assert priced, f"no image model costs between 1 and {cap} credits"
cost, model = min(priced)
env = pathlib.Path(os.environ["LIVE_ENV"])
env.write_text(f"MODEL={model}\nEST={cost}\nTOKEN={uuid.uuid4()}\n")
print(env.read_text(), end="")
EOF
```

Expected: `not priced: …` lines for refused models (legacy ones answer `unsupported_route`), then `MODEL=…`, `EST=<1..cap>` and `TOKEN=<uuid>`

- [ ] **Step 3: STOP — controller and user only.** Duplicate-rejection probe, part 1. Show the user `MODEL` and `EST` from the previous step and ask them to approve spending up to **2 × EST** credits (this submit, plus a second charge if the server does not reject the reused token). On yes:

```bash
. "${TMPDIR:-/tmp}/artcraft-live.env" && test -n "$TOKEN" && .venv/bin/artcraft-cli --json generate image --model "$MODEL" --prompt "dup check" --max-credits "$EST" --idempotency-token "$TOKEN" --wait
```

Expected: `replayed: false`, and every job in `jobs` has status `succeeded`.

- [ ] **Step 4: STOP — controller and user only.** Part 2. Ask the user to dismiss that job **in the app's task panel** (`jobs dismiss` arrives in M4), then confirm. Then resubmit the same token. The script snapshots the remote job list and the balance before and after, and prints the difference:

```bash
.venv/bin/python - <<'EOF'
import json, os, pathlib, subprocess
env_file = pathlib.Path(os.environ.get("TMPDIR", "/tmp")) / "artcraft-live.env"
env = dict(line.split("=", 1) for line in env_file.read_text().splitlines())
def cli(*argv):
    done = subprocess.run([".venv/bin/artcraft-cli", "--json", *argv], capture_output=True, text=True)
    return done.returncode, json.loads(done.stdout)
def snapshot():
    jobs = cli("jobs", "list", "--remote", "--all", "--limit", "200")[1]["jobs"]
    return {job["job_id"] for job in jobs}, cli("account", "credits")[1]["sum_total_credits"]
ids_before, credits_before = snapshot()
code, result = cli("generate", "image", "--model", env["MODEL"], "--prompt", "dup check",
                   "--max-credits", env["EST"], "--idempotency-token", env["TOKEN"])
ids_after, credits_after = snapshot()
print("resubmit exit code:", code)
print(json.dumps(result, indent=2))
print("new remote job ids:", sorted(ids_after - ids_before))
print("credit change:", credits_after - credits_before)
EOF
```

Expected:
- the resubmit fails with exit code 1, as `upstream_bad_input` or as `outcome_unknown` with `reason: server_error`
- `new remote job ids: []`
- `credit change: 0`

If a new job id appears but the credit change is 0, re-run only the snapshot after a minute, because balances can lag.

Record the exact error JSON. If a new job or a charge appeared, the server does **not** reject reused tokens, and that decides amendment C.

- [ ] **Step 5: Check that a `--max-credits` below the estimate is refused with no spend**

```bash
. "${TMPDIR:-/tmp}/artcraft-live.env" && test -n "$TOKEN" && .venv/bin/artcraft-cli --json account credits && .venv/bin/artcraft-cli --json generate image --model "$MODEL" --prompt x --max-credits $((EST - 1)); .venv/bin/artcraft-cli --json account credits
```

Expected: `cost_exceeds_limit` with `details: {effective_credits: EST, max_credits: EST-1}`, and the same `sum_total_credits` before and after

- [ ] **Step 6: Price the audio, mesh and splat models (free). First ask the `artcraft` session for their Omni model ids, and put them in place of the `<…-id>` values**

```bash
.venv/bin/artcraft-cli --json generate audio --model "<audio-id>" --prompt x --dry-run
.venv/bin/artcraft-cli --json generate mesh --model "<mesh-id>" --prompt x --dry-run
.venv/bin/artcraft-cli --json generate splat --model "<splat-id>" --prompt x --dry-run
```

Expected: a price for each id that is on ArtCraft's route. Ids that return `unsupported_route` or `invalid_args` are not usable.

Record the findings, then send the duplicate-rejection result to the `artcraft` session, and mark ACLI M2 done in Plane.

Append to `project_artcraft_live_findings.md`:
- **M2 duplicate rejection:** the exact error JSON, the new remote job ids, and the credit change
- **verified audio/mesh/splat model ids:** the ids that priced

If the user accepted amendment C **and** the probe showed no new job and no charge, apply Appendix A item C now. If the error shape is distinguishable, its mapping in spec §5.6/§7.4 goes to the user as Appendix A item F; it is not edited here.

---

## Milestone M3 — Media

Spec §6.3 (`--media`), §6.4 (download), §8.1–8.2, §10.3 M3.

### Task 17: media upload, get, list, download

**Files:**
- Modify: `artcraft_cli/tests/test_core.py`
- Modify: `artcraft_cli/core/media.py`
- Modify: `artcraft_cli/artcraft_cli.py`

**Interfaces:**
- Consumes: `download_to` and `idempotency_token` (Tasks 13–14), and `bridge.rpc`.
- Produces, in `core/media.py`:
  - `MAX_UPLOAD_BYTES = 20 * 1024 * 1024` and `IMAGE_MAGIC`.
  - `read_image(path: Path) -> bytes`, which raises `input_file_error` or `upload_type_unsupported` before any RPC.
  - `upload(path: Path, token: str) -> dict`, which sends `{content_base64, idempotency_token}`.
  - `get(media_token: str) -> dict`.
  - `list_media(*, classes: list[str], page: int, page_size: int, oldest_first: bool) -> dict`. It sends `media_classes` only when `classes` is non-empty.
  - `download(media_token: str, out_dir: Path, *, force: bool) -> dict`, which returns `{media_token, path, byte_count}`.
- Commands: `media upload FILE [--idempotency-token]`, `media get TOKEN`, `media list [--class]... [--page] [--page-size] [--oldest-first]` and `media download TOKEN [--out DIR] [--force]`.

- [ ] **Step 1: Write the failing media tests and rows**

Modify `artcraft_cli/tests/test_core.py` (3 edits; each old text occurs once):

Edit 1: replace

````python
from __future__ import annotations

````

with

````python
from __future__ import annotations

import base64
````

Edit 2: replace

````python
        {"job_ids": ["j1", "j2"], "include_remote": True},
````

with

````python
        {"job_ids": ["j1", "j2"], "include_remote": True},
    ),
    (["media", "get", "mf_1"], "media.get", {"media_token": "mf_1"}),
    (["media", "list"], "media.list", {"page_index": 0, "page_size": 25, "sort_ascending": False}),
    (
        [
            "media",
            "list",
            "--class",
            "image",
            "--class",
            "video",
            "--page",
            "2",
            "--page-size",
            "10",
            "--oldest-first",
        ],
        "media.list",
        {
            "page_index": 2,
            "page_size": 10,
            "sort_ascending": True,
            "media_classes": ["image", "video"],
        },
````

Edit 3: replace

````python
    assert list(locked.iterdir()) == []
````

with

````python
    assert list(locked.iterdir()) == []


# --- media (spec §6.3, §8.1) ------------------------------------------------------------


def test_oversized_or_unsupported_upload_is_rejected_before_rpc(
    fake_bridge: FakeBridge, run: Run, tmp_path: Path
) -> None:
    huge = tmp_path / "huge.png"
    with huge.open("wb") as handle:
        handle.write(PNG)
        handle.truncate(20 * 1024 * 1024 + 1)
    text = tmp_path / "notes.png"
    text.write_text("not an image")

    huge_code, huge_out, _ = run("--json", "media", "upload", str(huge))
    text_code, text_out, _ = run("--json", "media", "upload", str(text))
    gone_code, gone_out, _ = run("--json", "media", "upload", str(tmp_path / "missing.png"))

    assert (huge_code, error_of(huge_out)["code"]) == (1, "input_file_error")
    assert (text_code, error_of(text_out)["code"]) == (1, "upload_type_unsupported")
    assert (gone_code, error_of(gone_out)["code"]) == (1, "input_file_error")
    assert fake_bridge.calls == []


def test_media_upload_sends_base64_bytes_with_the_given_token(
    fake_bridge: FakeBridge, run: Run, tmp_path: Path
) -> None:
    image = tmp_path / "ref.png"
    image.write_bytes(PNG)
    fake_bridge.on("media.upload", {"media_token": "mf_new", "kind": "image"})

    code, out, _ = run("--json", "media", "upload", str(image), "--idempotency-token", TOKEN_A)

    assert code == 0
    assert json.loads(out)["media_token"] == "mf_new"
    (args,) = fake_bridge.args("media.upload")
    assert args == {"content_base64": base64.b64encode(PNG).decode(), "idempotency_token": TOKEN_A}
````

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest artcraft_cli/tests/test_core.py -v -k "media or oversized"`

Expected: FAIL — 5 failed, 44 deselected; first failure: `AssertionError: assert (1, '') == (0, '')`

- [ ] **Step 3: Write the media helpers and commands**

Modify `artcraft_cli/core/media.py` (4 edits; each old text occurs once):

Edit 1: replace

````python
from __future__ import annotations

````

with

````python
from __future__ import annotations

import base64
````

Edit 2: replace

````python
from pathlib import Path
````

with

````python
from pathlib import Path
from typing import Any
````

Edit 3: replace

````python
from artcraft_cli.utils import bridge
````

with

````python
from artcraft_cli.utils import bridge

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
IMAGE_MAGIC = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a")
````

Edit 4: replace

````python
    return value
````

with

````python
    return value


def read_image(path: Path) -> bytes:
    """Read a PNG/JPEG/GIF of at most 20 MiB; checked before any RPC."""
    try:
        size = path.stat().st_size
        if size > MAX_UPLOAD_BYTES:
            raise CliError(
                "input_file_error",
                f"{path} is {size} bytes; the limit is {MAX_UPLOAD_BYTES}",
                {"max_bytes": MAX_UPLOAD_BYTES},
            )
        data = path.read_bytes()
    except OSError as exc:
        raise CliError("input_file_error", f"cannot read {path}: {exc.strerror}") from None
    if not data.startswith(IMAGE_MAGIC):
        raise CliError("upload_type_unsupported", f"{path} is not a PNG, JPEG or GIF image")
    return data


def upload(path: Path, token: str) -> dict[str, Any]:
    data = read_image(path)
    content = base64.b64encode(data).decode("ascii")
    return bridge.rpc("media.upload", {"content_base64": content, "idempotency_token": token})


def get(media_token: str) -> dict[str, Any]:
    return bridge.rpc("media.get", {"media_token": media_token})


def list_media(
    *, classes: list[str], page: int, page_size: int, oldest_first: bool
) -> dict[str, Any]:
    args: dict[str, Any] = {
        "page_index": page,
        "page_size": page_size,
        "sort_ascending": oldest_first,
    }
    if classes:
        args["media_classes"] = classes
    return bridge.rpc("media.list", args)


def download(media_token: str, out_dir: Path, *, force: bool) -> dict[str, Any]:
    found = get(media_token)
    path, byte_count = download_to(media_token, found.get("cdn_url"), out_dir, force=force)
    return {"media_token": media_token, "path": str(path), "byte_count": byte_count}
````

Modify `artcraft_cli/artcraft_cli.py` (1 edit; each old text occurs once):

Edit 1: replace

````python
    emit(result)


````

with

````python
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


````

- [ ] **Step 4: Run the core tests to verify they pass**

Run: `.venv/bin/pytest artcraft_cli/tests/test_core.py -v`

Expected: PASS — 49 passed

- [ ] **Step 5: Commit**

```bash
.venv/bin/pytest -m "not e2e" -q
git add artcraft_cli/core/media.py artcraft_cli/artcraft_cli.py artcraft_cli/tests/test_core.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat: add media upload, get, list and download commands"
```

Expected: the unit suite passes, then every pre-commit hook passes and the commit is created. If a hook rewrites a file, `git add` it again and re-run the commit; never pass `--no-verify`.

### Task 18: Upload local --media files before submitting

**Files:**
- Modify: `artcraft_cli/tests/test_core.py`
- Modify: `artcraft_cli/core/generate.py`

**Interfaces:**
- Consumes: `media.upload` and `media.idempotency_token` (Task 17).
- Produces: `core.generate._upload_local_files(request) -> dict[str, Any]` and `_upload(path) -> str`. Every local `Path` is uploaded with a **fresh uuid4 key per upload** (spec §6.3) and replaced by its `media_token`, keeping list order. This replaces the M2 refusal. `build_request` now also calls `media.read_image` on every local file, so every file's size and type are checked before any RPC, in `--dry-run` too (spec §6.3).

- [ ] **Step 1: Write the failing upload-then-submit and pre-validation tests**

Modify `artcraft_cli/tests/test_core.py` (2 edits; each old text occurs once):

Edit 1: replace

````python
    "effective_credits": 4,
}
````

with

````python
    "effective_credits": 4,
}
SUBMITTED = {"job_ids": ["j1"], "idempotency_token": TOKEN_A, "replayed": False}
````

Edit 2: replace

````python
    assert args == {"content_base64": base64.b64encode(PNG).decode(), "idempotency_token": TOKEN_A}
````

with

````python
    assert args == {"content_base64": base64.b64encode(PNG).decode(), "idempotency_token": TOKEN_A}


def test_local_media_files_are_uploaded_then_submitted_as_tokens(
    fake_bridge: FakeBridge, run: Run, tmp_path: Path
) -> None:
    image = tmp_path / "ref.png"
    image.write_bytes(PNG)
    fake_bridge.on("media.upload", {"media_token": "mf_up1"}, {"media_token": "mf_up2"})
    fake_bridge.on("generate.submit", SUBMITTED)

    code, _, _ = run(
        "--json", "generate", "image", "--model", "m", "--max-credits", "5",
        "--media", f"image_media_tokens={image}", "--media", "image_media_tokens=mf_kept",
        "--media", f"style_media_token={image}",
    )  # fmt: skip

    assert code == 0
    assert fake_bridge.ops() == ["media.upload", "media.upload", "generate.submit"]
    upload_keys = [args["idempotency_token"] for args in fake_bridge.args("media.upload")]
    assert len(set(upload_keys)) == 2
    (submit,) = fake_bridge.args("generate.submit")
    assert submit["request"]["image_media_tokens"] == ["mf_up1", "mf_kept"]
    assert submit["request"]["style_media_token"] == "mf_up2"


def test_bad_local_reference_is_rejected_before_any_upload(
    fake_bridge: FakeBridge, run: Run, tmp_path: Path
) -> None:
    good, bad = tmp_path / "good.png", tmp_path / "bad.png"
    good.write_bytes(PNG)
    bad.write_text("not an image")

    for spend_flags in (["--max-credits", "5"], ["--dry-run"]):
        code, out, _ = run(
            "--json", "generate", "image", "--model", "m",
            "--media", f"image_media_tokens={good}", "--media", f"image_media_tokens={bad}",
            *spend_flags,
        )  # fmt: skip
        assert (code, error_of(out)["code"]) == (1, "upload_type_unsupported")

    assert fake_bridge.calls == []
````

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest artcraft_cli/tests/test_core.py::test_local_media_files_are_uploaded_then_submitted_as_tokens artcraft_cli/tests/test_core.py::test_bad_local_reference_is_rejected_before_any_upload -v`

Expected: FAIL — 2 failed; first failure: `assert 1 == 0`

- [ ] **Step 3: Replace the M2 refusal with uploads**

Modify `artcraft_cli/core/generate.py` (4 edits; each old text occurs once):

Edit 1: replace

````python
        if path.is_file():
````

with

````python
        if path.is_file():
            media.read_image(path)  # size and type are checked before any RPC
````

Edit 2: replace

````python
        if _has_local_files(request):
            raise CliError("usage_error", "local --media files arrive in M3; pass media tokens")
````

with

````python
        resolved = _upload_local_files(request)
````

Edit 3: replace

````python
                "request": request,
````

with

````python
                "request": resolved,
````

Edit 4: replace

````python
def _has_local_files(request: dict[str, Any]) -> bool:
    for value in request.values():
        if isinstance(value, Path):
            return True
        if isinstance(value, list) and any(isinstance(item, Path) for item in value):
            return True
    return False
````

with

````python
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
````

- [ ] **Step 4: Run the core tests to verify they pass**

Run: `.venv/bin/pytest artcraft_cli/tests/test_core.py -v`

Expected: PASS — 51 passed

- [ ] **Step 5: Commit**

```bash
.venv/bin/pytest -m "not e2e" -q
git add artcraft_cli/core/generate.py artcraft_cli/tests/test_core.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat: upload local --media files before submitting"
```

Expected: the unit suite passes, then every pre-commit hook passes and the commit is created. If a hook rewrites a file, `git add` it again and re-run the commit; never pass `--no-verify`.

### Task 19: Live test for uploaded generation references

**Files:**
- Modify: `artcraft_cli/tests/test_full_e2e.py`

**Interfaces:**
- Produces: `tiny_png(path) -> Path` (a valid 8×8 PNG, stdlib only) and `test_uploaded_image_is_usable_as_generation_reference`, which uses the cheapest model with `image_refs_supported`.

- [ ] **Step 1: Add the M3 live test**

Modify `artcraft_cli/tests/test_full_e2e.py` (4 edits; each old text occurs once):

Edit 1: replace

````python
import os
````

with

````python
import os
import struct
````

Edit 2: replace

````python
import uuid
````

with

````python
import uuid
import zlib
````

Edit 3: replace

````python
    return model_id, effective
````

with

````python
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
````

Edit 4: replace

````python
    assert cli_json(capsys, "account", "credits")["sum_total_credits"] == balance
````

with

````python
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
````

- [ ] **Step 2: Run it without ArtCraft to verify it skips cleanly**

Run: `.venv/bin/pytest -m e2e -rs -q`

Expected: every selected test SKIPPED (ArtCraft is not running) — 9 skipped, 68 deselected

- [ ] **Step 3: Run the unit suite on Python 3.10 (CI's floor)**

```bash
PY310="${TMPDIR:-/tmp}/artcraft-cli-py310"
test -x "$PY310/bin/pytest" || { python3.10 -m venv "$PY310" && "$PY310/bin/pip" install -q -e '.[dev]'; }
"$PY310/bin/pytest" -m "not e2e" -q
```

Expected: the same pass count as on 3.13, ending in `passed`

- [ ] **Step 4: Commit**

```bash
.venv/bin/pytest -m "not e2e" -q
git add artcraft_cli/tests/test_full_e2e.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "test: add live check for uploaded generation references"
```

Expected: the unit suite passes, then every pre-commit hook passes and the commit is created. If a hook rewrites a file, `git add` it again and re-run the commit; never pass `--no-verify`.

### Task 20: M3 live checklist

**Executor:** controller session, with the user where a step says so. Subagents do not run this task.

**Blocked by:** ARTC M3 (Rust plan) finished and built. Tasks 17–19 done.

ArtCraft is running with the bridge and the user is logged in.

- [ ] **Step 1: Upload a PNG twice with the same key**

```bash
.venv/bin/python -c 'from artcraft_cli.tests.test_full_e2e import tiny_png; import pathlib; print(tiny_png(pathlib.Path("/tmp/artcraft-m3.png")))'
UPTOKEN=$(python3 -c 'import uuid; print(uuid.uuid4())')
.venv/bin/artcraft-cli --json media upload /tmp/artcraft-m3.png --idempotency-token "$UPTOKEN"
.venv/bin/artcraft-cli --json media upload /tmp/artcraft-m3.png --idempotency-token "$UPTOKEN"
```

Expected: the first call returns `media_token`, `kind: image`, `image_type: png` and `byte_count`. The user confirms the image is in the app's library. Record what the second call does: the same `media_token`, an error, or a second library file.

- [ ] **Step 2: Check that `media list` paging matches the app**

```bash
.venv/bin/artcraft-cli --json media list --page-size 5 && .venv/bin/artcraft-cli --json media list --page 1 --page-size 5
```

Expected: page 0 holds the 5 newest items, the uploaded PNG first, and page 1 holds the next 5. The user confirms against the library view.

- [ ] **Step 3: STOP — controller and user only.** Ask the user to approve spending up to `ARTCRAFT_E2E_MAX_CREDITS` (default 10) credits, then run:

```bash
ARTCRAFT_E2E_SPEND=1 .venv/bin/pytest -m spend -v -s -k uploaded_image
```

Expected: `test_uploaded_image_is_usable_as_generation_reference` passes.

Then:
1. Append to `project_artcraft_live_findings.md`: **M3 upload key reuse:** same token / error / second file, with the exact output.
2. Tell the `artcraft` session the result.
3. Mark ACLI M3 done in Plane.

Deterministic upload keys are adopted only if reuse returned the same `media_token` (spec §6.3). That would be a new plan item, not part of this plan.

---

## Milestone M4 — Settings, dismiss, hardening

Spec §7.7, §8.3, §9, §10.3 M4.

### Task 21: jobs dismiss and settings

**Files:**
- Create: `artcraft_cli/core/settings.py`
- Modify: `artcraft_cli/tests/test_core.py`
- Modify: `artcraft_cli/core/jobs.py`
- Modify: `artcraft_cli/artcraft_cli.py`

**Interfaces:**
- Consumes: `bridge.rpc` and `emit`.
- Produces: `core.jobs.dismiss(job_id: str) -> dict`, `core.settings.WRITABLE = ("play_sounds", "auto_download")`, `core.settings.get() -> dict` and `core.settings.set_preference(preference: str, value: bool) -> dict`. The value is a real JSON boolean.
- Commands: `jobs dismiss JOB`, `settings get` and `settings set play_sounds|auto_download true|false`. Any other name is a Click `usage_error`.

- [ ] **Step 1: Add the failing rows for dismiss and settings**

Modify `artcraft_cli/tests/test_core.py` (1 edit; each old text occurs once):

Edit 1: replace

````python
        },
    ),
````

with

````python
        },
    ),
    (["settings", "get"], "settings.get", {}),
    (
        ["settings", "set", "play_sounds", "false"],
        "settings.set",
        {"preference": "play_sounds", "value": False},
    ),
    (
        ["settings", "set", "auto_download", "true"],
        "settings.set",
        {"preference": "auto_download", "value": True},
    ),
    (["jobs", "dismiss", "j1"], "jobs.dismiss", {"job_id": "j1"}),
````

- [ ] **Step 2: Run the new rows to verify they fail**

Run: `.venv/bin/pytest artcraft_cli/tests/test_core.py -v -k "single_op and (settings or dismiss)"`

Expected: FAIL — 4 failed, 51 deselected; first failure: `AssertionError: assert (1, '') == (0, '')`

- [ ] **Step 3: Write the helpers and commands**

Modify `artcraft_cli/core/jobs.py` (1 edit; each old text occurs once):

Edit 1: replace

````python
    return downloads
````

with

````python
    return downloads


def dismiss(job_id: str) -> dict[str, Any]:
    return bridge.rpc("jobs.dismiss", {"job_id": job_id})
````

Create `artcraft_cli/core/settings.py`:

````python
"""ArtCraft app preferences."""

from __future__ import annotations

from typing import Any

from artcraft_cli.utils import bridge

WRITABLE = ("play_sounds", "auto_download")


def get() -> dict[str, Any]:
    return bridge.rpc("settings.get", {})


def set_preference(preference: str, value: bool) -> dict[str, Any]:
    return bridge.rpc("settings.set", {"preference": preference, "value": value})
````

Modify `artcraft_cli/artcraft_cli.py` (3 edits; each old text occurs once):

Edit 1: replace

````python
from artcraft_cli.core import account, generate, jobs, media, models
````

with

````python
from artcraft_cli.core import account, generate, jobs, media, models, settings
````

Edit 2: replace

````python
    emit(result)


````

with

````python
    emit(result)


@jobs_group.command("dismiss")
@click.argument("job_id")
def jobs_dismiss(job_id: str) -> None:
    """Hide a finished job from the app's task list."""
    emit(jobs.dismiss(job_id))


````

Edit 3: replace

````python
    emit(media.download(media_token, out_dir, force=force))


````

with

````python
    emit(media.download(media_token, out_dir, force=force))


@cli.group("settings")
def settings_group() -> None:
    """ArtCraft app preferences."""


@settings_group.command("get")
def settings_get() -> None:
    """All preferences (read-only)."""
    emit(settings.get())


@settings_group.command("set")
@click.argument("preference", type=click.Choice(settings.WRITABLE))
@click.argument("value", type=click.Choice(["true", "false"]))
def settings_set(preference: str, value: str) -> None:
    """Set play_sounds or auto_download."""
    emit(settings.set_preference(preference, value == "true"))


````

- [ ] **Step 4: Run the core tests to verify they pass**

Run: `.venv/bin/pytest artcraft_cli/tests/test_core.py -v`

Expected: PASS — 55 passed

- [ ] **Step 5: Commit**

```bash
.venv/bin/pytest -m "not e2e" -q
git add artcraft_cli/core/jobs.py artcraft_cli/core/settings.py artcraft_cli/artcraft_cli.py artcraft_cli/tests/test_core.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat: add jobs dismiss and settings commands"
```

Expected: the unit suite passes, then every pre-commit hook passes and the commit is created. If a hook rewrites a file, `git add` it again and re-run the commit; never pass `--no-verify`.

### Task 22: M4 live checklist

**Executor:** controller session, with the user where a step says so. Subagents do not run this task.

**Blocked by:** ARTC M4 (Rust plan) finished and built. Task 21 done.

- [ ] **Step 1: STOP — controller and user only.** Ask the user to relaunch ArtCraft with the bridge and **without `debug` anywhere in `RUST_LOG`** (spec §4.6, Appendix A item E), teeing its log to a file, and to log in:

```bash
ARTCRAFT_CLI_BRIDGE=1 ./script/artcraft/unix_dev.sh 2>&1 | tee /tmp/artcraft-m4.log
```

- [ ] **Step 2: Check the app's startup log level**

```bash
rtk proxy grep -i -m 3 'log level' /tmp/artcraft-m4.log
```

Expected: the startup line that reports the app's log level says Info. If it says Debug, stop: the leak check below would be meaningless.

- [ ] **Step 3: Check that every ArtCraft command name sent as an op is refused**

```bash
SRC=/Volumes/Containers/artcraft/crates/desktop/artcraft/src .venv/bin/python - <<'EOF'
import os, re, pathlib
from artcraft_cli.utils import bridge
from artcraft_cli.errors import CliError
names = set()
for path in pathlib.Path(os.environ["SRC"]).rglob("*.rs"):
    names |= set(re.findall(r"\bpub (?:async )?fn ([a-z0-9_]+_command|flip_image)\b", path.read_text(errors="ignore")))
bad = []
for name in sorted(names):
    try:
        bridge.rpc(name, {})
        bad.append((name, "ok"))
    except CliError as err:
        if err.code != "unknown_op":
            bad.append((name, err.code))
print(len(names), "command names sent; not unknown_op:", bad)
EOF
```

Expected: `N command names sent; not unknown_op: []`, with N ≥ 67

- [ ] **Step 4: Check that a raw RPC cannot write an unlisted preference**

```bash
.venv/bin/python -c 'from artcraft_cli.utils import bridge; from artcraft_cli.errors import CliError
try:
    bridge.rpc("settings.set", {"preference": "preferred_download_directory", "value": True})
except CliError as err:
    print(err.code)'
```

Expected: `setting_not_writable`

- [ ] **Step 5: Pick the cheapest priced image model and save fresh probe values (free)**

```bash
LIVE_ENV="${TMPDIR:-/tmp}/artcraft-live.env" .venv/bin/python - <<'EOF'
import os, pathlib, uuid
from artcraft_cli.core import generate, models
from artcraft_cli.errors import CliError
cap = int(os.environ.get("ARTCRAFT_E2E_MAX_CREDITS", "10"))
priced = []
for model in models.list_models("image")["models"]:
    if model.get("is_disabled"):
        continue
    try:
        cost = generate.estimate("image", {"model": model["model"], "prompt": "probe"}).get("effective_credits")
    except CliError as err:
        print("not priced:", model["model"], err.code)
        continue
    if isinstance(cost, int) and 0 < cost <= cap:
        priced.append((cost, model["model"]))
assert priced, f"no image model costs between 1 and {cap} credits"
cost, model = min(priced)
env = pathlib.Path(os.environ["LIVE_ENV"])
env.write_text(f"MODEL={model}\nEST={cost}\nTOKEN={uuid.uuid4()}\n")
print(env.read_text(), end="")
EOF
```

Expected: `MODEL=…`, `EST=…` and `TOKEN=…`

- [ ] **Step 6: STOP — controller and user only.** Show the user `MODEL` and `EST`, and ask them to approve one generation of **EST** credits with sounds off. On yes, run the following, and have the user confirm the app stays silent:

```bash
. "${TMPDIR:-/tmp}/artcraft-live.env" && test -n "$TOKEN" && .venv/bin/artcraft-cli --json settings set play_sounds false && .venv/bin/artcraft-cli --json generate image --model "$MODEL" --prompt m4-secret-prompt --max-credits "$EST" --idempotency-token "$TOKEN" --wait | tee "${TMPDIR:-/tmp}/artcraft-m4-submit.json"
```

- [ ] **Step 7: Send a dry run and an image upload through the bridge, then check the app log for the token, both prompts and image base64**

```bash
. "${TMPDIR:-/tmp}/artcraft-live.env" && test -n "$TOKEN" && .venv/bin/artcraft-cli --json generate image --model "$MODEL" --prompt m4-dry-prompt --dry-run && python3 -c 'import struct, zlib, pathlib
c = lambda k, d: struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d))
rows = b"".join(b"\x00" + b"\x80" * 8 for _ in range(8))
pathlib.Path("/tmp/artcraft-ref.png").write_bytes(b"\x89PNG\r\n\x1a\n" + c(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 0, 0, 0, 0)) + c(b"IDAT", zlib.compress(rows)) + c(b"IEND", b""))' && .venv/bin/artcraft-cli --json media upload /tmp/artcraft-ref.png && TOKEN_FILE="$HOME/Artcraft/state/cli_bridge.json" .venv/bin/python - <<'EOF'
import json, os, pathlib
token = json.loads(pathlib.Path(os.environ["TOKEN_FILE"]).read_text())["token"]
log = pathlib.Path("/tmp/artcraft-m4.log").read_text(errors="ignore")
assert log.strip(), "the tee'd ArtCraft log is empty"
counts = {"token": log.count(token), "submit prompt": log.count("m4-secret-prompt"),
          "dry-run prompt": log.count("m4-dry-prompt"), "png base64": log.count("iVBORw0KGgo")}
print(counts)
EOF
```

Expected: both CLI calls print JSON with exit code 0, then `{'token': 0, 'submit prompt': 0, 'dry-run prompt': 0, 'png base64': 0}`

- [ ] **Step 8: Dismiss the job from the submit twice, then dismiss an id that never existed**

```bash
JOB=$(.venv/bin/python -c 'import json, os; print(json.load(open(os.path.join(os.environ.get("TMPDIR", "/tmp"), "artcraft-m4-submit.json")))["job_ids"][0])')
.venv/bin/artcraft-cli --json jobs dismiss "$JOB"; .venv/bin/artcraft-cli --json jobs dismiss "$JOB"; .venv/bin/artcraft-cli --json jobs dismiss never_existed_0
```

Expected: `{"job_id": …, "task_id": …, "dismissed": true}` twice (dismiss is idempotent: spec §7.7 finds the row by provider and job id, dismissed or not), then `job_not_found`. The job leaves the app's task panel.

Restore the user's preference with `.venv/bin/artcraft-cli --json settings set play_sounds true` if they want sounds back. Then record the M4 results in `project_artcraft_live_findings.md` and mark ACLI M4 done in Plane.

---

## Milestone M5 — REPL, docs, merge

Spec §3.6, §3.7, §10.3 M5.

### Task 23: The REPL

**Files:**
- Create: `artcraft_cli/repl.py`
- Modify: `artcraft_cli/tests/test_core.py`
- Modify: `artcraft_cli/artcraft_cli.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `main` (Task 8).
- Produces: `artcraft_cli.repl.run_repl(dispatch: Callable[[list[str]], int], read_line: Callable[[str], str] = input) -> None`, with `PROMPT = "artcraft> "` and `EXIT_WORDS = {"exit", "quit"}`. It uses stdlib `readline` when available, keeps history in memory only, and never enters implicitly. Command: `repl`. README section "Interactive shell".

- [ ] **Step 1: Write the failing REPL test**

Modify `artcraft_cli/tests/test_core.py` (2 edits; each old text occurs once):

Edit 1: replace

````python
import requests
````

with

````python
import requests

from artcraft_cli.repl import run_repl
````

Edit 2: replace

````python
        assert (code, error_of(out)["code"]) == (1, "upload_type_unsupported")

    assert fake_bridge.calls == []
````

with

````python
        assert (code, error_of(out)["code"]) == (1, "upload_type_unsupported")

    assert fake_bridge.calls == []


# --- REPL (spec §3.6) -------------------------------------------------------------------


def test_repl_dispatches_lines_to_commands_and_survives_errors(
    fake_bridge: FakeBridge, capsys: pytest.CaptureFixture[str]
) -> None:
    from artcraft_cli.artcraft_cli import main

    fake_bridge.on("health", HEALTH)
    fake_bridge.on("app.info", {"artcraft_version": "0.41.0"})
    lines = iter(["--json ping", "bogus", "'unclosed", "", "--json app info", "quit", "ping"])

    run_repl(main, lambda _prompt: next(lines))

    out, err = capsys.readouterr()
    pinged, info = out.splitlines()
    assert json.loads(pinged)["bridge"]["protocol"] == 1
    assert json.loads(info) == {"artcraft_version": "0.41.0"}
    assert "error[usage_error]" in err
    assert fake_bridge.ops() == ["health", "app.info"]
````

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest artcraft_cli/tests/test_core.py::test_repl_dispatches_lines_to_commands_and_survives_errors -v`

Expected: FAIL — the test module cannot import yet: `ModuleNotFoundError: No module named 'artcraft_cli.repl'`

- [ ] **Step 3: Write the REPL, its command, and the README section**

Create `artcraft_cli/repl.py`:

````python
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
````

Modify `artcraft_cli/artcraft_cli.py` (2 edits; each old text occurs once):

Edit 1: replace

````python
from artcraft_cli.errors import CliError, error_payload
````

with

````python
from artcraft_cli.errors import CliError, error_payload
from artcraft_cli.repl import run_repl
````

Edit 2: replace

````python
    emit(settings.set_preference(preference, value == "true"))


````

with

````python
    emit(settings.set_preference(preference, value == "true"))


@cli.command("repl")
def repl_cmd() -> None:
    """Interactive shell: type commands without the `artcraft-cli` prefix."""
    run_repl(main)


````

Modify `README.md` (1 edit; each old text occurs once):

Edit 1: replace

````markdown
- [`skills/artcraft-cli/SKILL.md`](skills/artcraft-cli/SKILL.md) lists the full command tree and every error code.

````

with

````markdown
- [`skills/artcraft-cli/SKILL.md`](skills/artcraft-cli/SKILL.md) lists the full command tree and every error code.

### Interactive shell

`artcraft-cli repl` runs commands without the `artcraft-cli` prefix, for example `--json ping`. Type `exit` or `quit`, or press Ctrl-D, to leave. History lasts for the session only.

````

- [ ] **Step 4: Run the core tests to verify they pass**

Run: `.venv/bin/pytest artcraft_cli/tests/test_core.py -v`

Expected: PASS — 56 passed

- [ ] **Step 5: Check the REPL by piping lines into it**

```bash
printf 'nope\nquit\n' | .venv/bin/artcraft-cli repl; echo "exit=$?"
```

Expected: `error[usage_error]: No such command 'nope'.` and `hint: see --help` on stderr, then `exit=0`

- [ ] **Step 6: Run the unit suite on Python 3.10 (CI's floor)**

```bash
PY310="${TMPDIR:-/tmp}/artcraft-cli-py310"
test -x "$PY310/bin/pytest" || { python3.10 -m venv "$PY310" && "$PY310/bin/pip" install -q -e '.[dev]'; }
"$PY310/bin/pytest" -m "not e2e" -q
```

Expected: the same pass count as on 3.13, ending in `passed`

- [ ] **Step 7: Commit**

```bash
.venv/bin/pytest -m "not e2e" -q
git add artcraft_cli/repl.py artcraft_cli/artcraft_cli.py artcraft_cli/tests/test_core.py README.md
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat: add stdlib REPL"
```

Expected: the unit suite passes, then every pre-commit hook passes and the commit is created. If a hook rewrites a file, `git add` it again and re-run the commit; never pass `--no-verify`.

### Task 24: Finalize the docs with the live findings

**Executor:** controller session, with the user where a step says so. Subagents do not run this task.

**Blocked by:** Tasks 11, 16, 20 and 22 recorded their findings in `project_artcraft_live_findings.md`.

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Mark the README status as working**

Modify `README.md` (1 edit; each old text occurs once):

Edit 1: replace

````markdown
> **Status:** in development. It needs an ArtCraft build that carries the CLI bridge patch, which upstream ArtCraft does not include.
````

with

````markdown
> **Status:** works end to end with an ArtCraft build that carries the CLI bridge patch, which upstream ArtCraft does not include. Scene and canvas control are planned next.
````

- [ ] **Step 2: Apply the recorded findings to the skill and the agent rules**

Read `project_artcraft_live_findings.md`, then edit:

1. `skills/artcraft-cli/SKILL.md`, section `### generate`. After the bullet that starts ``- `models list` covers image and video only.``, add one bullet per modality with verified ids, in this exact form:

   ``  - Verified <modality> model ids (<date>): `id1`, `id2`.``

   Leave out any modality with no verified id.
2. `.claude/CLAUDE.md`, section `## Bridge SOP`. Append item 6 with this text:

   `6. Live findings: see the project memory project_artcraft_live_findings.md (batch pricing, duplicate rejection, upload key reuse).`

   Also add any deviation that changes an agent's behaviour, quoted from the findings.

- [ ] **Step 2: Run the full gate**

```bash
.venv/bin/pytest -m "not e2e" -q && PATH="$PWD/.venv/bin:$PATH" pre-commit run --all-files
```

Expected: everything passes

- [ ] **Step 3: Commit**

```bash
.venv/bin/pytest -m "not e2e" -q
git add README.md skills/artcraft-cli/SKILL.md .claude/CLAUDE.md
PATH="$PWD/.venv/bin:$PATH" git commit -m "docs: finalize docs with live-verified findings"
```

Expected: the unit suite passes, then every pre-commit hook passes and the commit is created. If a hook rewrites a file, `git add` it again and re-run the commit; never pass `--no-verify`.

### Task 25: Merge to main and post-merge cleanup

**Executor:** controller session, with the user where a step says so. Subagents do not run this task.

**Blocked by:** Tasks 1–24 done. CI green on `pivot/artcraft-cli`.

Every step below is a separate STOP gate (spec §3.7). Ask the user, wait for an explicit yes, run the step, report the result, and only then ask about the next one.

- [ ] **Step 1: STOP — controller and user only.** Push the branch:

```bash
git push origin pivot/artcraft-cli
```

- [ ] **Step 2: Wait for CI on the pushed commit**

```bash
SHA=$(git rev-parse HEAD)
until gh run list --branch pivot/artcraft-cli --commit "$SHA" --limit 1 --json databaseId -q '.[0].databaseId' | grep -q .; do sleep 10; done
gh run watch "$(gh run list --branch pivot/artcraft-cli --commit "$SHA" --limit 1 --json databaseId -q '.[0].databaseId')" --exit-status
```

Expected: both matrix jobs (3.10, 3.13) of the run for **this commit** succeed. The `until` loop waits for GitHub to register the run; foreground `sleep` is blocked in this environment, so run the loop with the Monitor tool (or `run_in_background`) and then `gh run watch`. Do not merge on any other run's result.

- [ ] **Step 3: STOP — controller and user only.** Merge into `main` (merge commit, no agent trailer) and push:

```bash
git switch main && git merge --no-ff pivot/artcraft-cli -m "feat: pivot repo to artcraft-cli (sub-project 1)" && git push origin main
```

- [ ] **Step 4: STOP — controller and user only.** Rename the GitHub repo (GitHub redirects the old URL):

```bash
gh repo rename artcraft-cli --yes && git remote -v
```

- [ ] **Step 5: STOP — controller and user only.** Remove the stale Adobe-era installs and the dangling CEP symlink on this machine:

```bash
pipx uninstall cli-anything-acrobat; pipx uninstall cli-anything-illustrator
python3 -m pip uninstall -y cli-anything-acrobat
rm "$HOME/Library/Application Support/Adobe/CEP/extensions/com.cli-anything.premierepro"
```

Tell the user, without changing anything:
- `PlayerDebugMode=1` (in `com.adobe.CSXS.11` and `.12`) still lets every Adobe app load unsigned CEP extensions. They can revert it with `defaults delete com.adobe.CSXS.11 PlayerDebugMode; defaults delete com.adobe.CSXS.12 PlayerDebugMode`.
- The user-wide `cli-anything@cli-anything` Claude plugin is a user setting outside this repo.

Keep the local folder name `/Volumes/Containers/adobe-cli`.

Mark the memories `project_acrobat_cli.md` and `project_cep_setup.md` as historical: prefix their descriptions with `HISTORICAL (repo pivoted 2026-10):`, and update their `MEMORY.md` lines to match.

Write a journal entry, then mark ACLI M5 done in Plane.

---

## Appendix A — pending contract amendments (user decision outstanding)

The `artcraft` session's re-check of bc7b57d produced five corrections after the user had approved the spec. Spec §10.1 says contract changes need the user. This plan implements bc7b57d as approved. If the user accepts an item, apply it as written here, together with a spec-delta commit `docs: amend bridge spec with post-approval corrections`.

| item | change | Python touchpoint | when |
|---|---|---|---|
| A | Video estimates strip `video_batch_count` and multiply locally, matching the app (internal to Rust; spec §7.3 text) | none. Task 11 compares video `effective_credits`, not `cost_in_credits`. | already in the Rust plan; the §7.3 wording waits for the user |
| B | `generate.submit`'s 120 s deadline returns `operation_in_progress{reason:"deadline"}` instead of `outcome_unknown`; the 300 s cap becomes a resource guard only | none (the code already exists in `HINTS`) | Rust plan |
| C | `outcome_unknown` hint: re-running with the same token is safe | `errors.HINTS["outcome_unknown"]` and the SKILL `agent_guidance` sentence | only after Task 16 confirms the server rejects a reused token without creating a job |
| D | `ApiError::{InternalServerError, CloudflareError, Uncategorized ≥ 500}` → `upstream_unavailable` (retryable) | none | Rust plan |
| E | The debug-logging warning says "`RUST_LOG` must not contain `debug`" rather than "unset" | already applied in README, SKILL and Task 22 (a documentation fact verified from source, not a contract change) | done |
| F | If Task 16 finds the server's duplicate-rejection response distinguishable, spec §7.4 says to map it to `outcome_unknown` instead of `upstream_bad_input` | none in code; the SKILL's `outcome_unknown` guidance already covers it | after Task 16, with the user and the `artcraft` session |

**Item C edit, if accepted and confirmed.**

In `artcraft_cli/errors.py`, replace the `outcome_unknown` entry with:

```python
    "outcome_unknown": (
        "re-run with the same --idempotency-token (it replays or is rejected as a duplicate; "
        "never use a new token), or find it with `artcraft-cli --json jobs list --remote --all`",
        False,
    ),
```

In `skills/artcraft-cli/SKILL.md`, replace the sentence starting `After an outcome_unknown error, never resubmit:` with: `After an outcome_unknown error, re-run with the same --idempotency-token (never a new one), or run artcraft-cli --json jobs list --remote --all and match on model and a created_at at or after the submit time.` Also update the `outcome_unknown` row of the error table.

Then run `.venv/bin/pytest -m "not e2e" -q` and commit `fix: let outcome_unknown recovery reuse the idempotency token`.

## Appendix B — Rust-plan decisions with user-visible effects

The `artcraft` session made these within the spec. They change no Python code, but users and Task 24's docs should know them.

| # | Decision | Effect on CLI users |
|---|---|---|
| 6 | `JobView.created_at` is `null` for a dismissed row that the remote list doesn't cover | `jobs get`/`list` can show `created_at: null` for dismissed jobs |
| 7 | `media.list` items return `cdn_url: null` (list items carry no media links) | `media list` shows no CDN URLs; `media download TOKEN` (via `media.get`) is the way to fetch a file |
| 8 | For video, `video_batch_count` must be a positive integer, and the request keys `batch_size` and `image_batch_count` are refused with `invalid_args`, so the credit cap can't fail open | use `--set video_batch_count=N` for video batches |
| 13 | ArtCraft's release profile sets `panic = "abort"`, so a panic inside any op aborts the whole app in a release build (dev builds unwind) | after such a crash the CLI reports `bridge_not_running`; spec §4.2's "panic → 500 internal_error" holds only for dev builds such as `unix_dev.sh` |

If the user confirms them, Task 24 adds rows 7 and 8 to the SKILL's `### generate` and `media` guidance.
