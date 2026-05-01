# Contributing to adobe-cli

Contributions welcome. This document covers the conventions and workflow for adding new harnesses or extending existing ones.

## What This Project Is

`adobe-cli` implements the **[CLI-Anything](https://github.com/HKUDS/CLI-Anything)** pattern by [HKUDS](https://github.com/HKUDS): wrapping stateful GUI desktop applications behind a local HTTP or IPC bridge so that scripts and AI agents can drive them programmatically. Each Adobe application gets its own Python package under the `cli_anything.*` namespace.

The upstream project defines the methodology, directory conventions, and namespace package structure used here. If you build a harness worth sharing, consider submitting it to the [CLI Hub](https://hkuds.github.io/CLI-Anything/).

## Conventions

### Code Style

- **Functional paradigm** — pure functions, no global state, no classes unless forced by a framework.
- **Type hints on all public functions** (PEP 484). `from __future__ import annotations` at the top of every module.
- **No magic numbers** — named constants only.
- **No bare `except`** — use specific exception types.
- Validate inputs at system boundaries (user input, IPC results); trust internal calls.

### Testing

Follow strict TDD — write the failing test first, watch it fail, then implement.

```bash
# Unit tests (no Adobe app required)
PYTHONPATH=<harness-root> pytest cli_anything/<app>/tests/test_core.py -v

# Single test class
PYTHONPATH=<harness-root> pytest cli_anything/<app>/tests/test_core.py::TestMarkersCore -v

# E2E tests (app must be running)
PYTHONPATH=<harness-root> pytest cli_anything/<app>/tests/test_full_e2e.py -v -s
```

E2E tests must use `pytest.mark.skipif(not _bridge_reachable(), ...)` so they skip cleanly when the app is not running. Never let an E2E test fail just because the host app is closed.

### Commit Messages

```
type: short imperative description

Longer explanation if non-obvious.
```

Types: `feat`, `fix`, `docs`, `test`, `chore`. Keep the subject line under 72 chars.

---

## Adding a New Harness

### 1. Directory structure

```
<app-name>/agent-harness/
  setup.py
  <APP-NAME>.md                       # Developer SOP (architecture, gotchas, API quirks)
  cli_anything/                       # NO __init__.py (PEP 420 namespace package)
    <app>/
      __init__.py
      <app>_cli.py                    # Click entry point
      core/                           # Business logic
      utils/
        <transport>_backend.py        # IPC/transport layer
      tests/
        TEST.md
        test_core.py
        test_full_e2e.py
      skills/SKILL.md
skills/
  cli-anything-<app>/SKILL.md         # Canonical skill descriptor (keep in sync with packaged copy)
```

### 2. Package setup

`setup.py` must use `find_namespace_packages(include=["cli_anything.*"])` so the namespace is shared across all harnesses:

```python
from setuptools import setup, find_namespace_packages

setup(
    name="cli-anything-<app>",
    version="1.0.0",
    python_requires=">=3.10",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    install_requires=[...],
    entry_points={
        "console_scripts": [
            "cli-anything-<app>=cli_anything.<app>.<app>_cli:cli",
        ],
    },
)
```

The `cli_anything/` directory must **not** have an `__init__.py`. The app subdirectory must have one.

### 3. CLI structure

Every harness CLI must:

- Accept `--json` as a root-level flag for machine-readable output.
- Raise `CepNotRunningError` (or equivalent) when the bridge is unreachable, and exit with code 1.
- Support a REPL mode when invoked with no subcommand.
- Use absolute paths everywhere.

### 4. IPC bridge options

| Strategy | When to use |
|----------|-------------|
| CEP panel (Node.js HTTP) | Adobe apps that support CEP extensions (Premiere Pro, After Effects, Animate) |
| `osascript` + AppleScript | Apps with a scriptable AppleScript dictionary (Acrobat, Illustrator) |
| COM/UXP | UXP-native apps (newer Photoshop, InDesign 2024+) |

### 5. SKILL.md

Every harness needs two copies of its SKILL.md:

- `skills/cli-anything-<app>/SKILL.md` — canonical (tracked here)
- `cli_anything/<app>/skills/SKILL.md` — packaged copy (installed with `pip install`)

Both must be kept in sync. The `description` field must start with `"Use when..."` and describe triggering tasks, not capabilities.

### 6. SOP document

`<APP-NAME>.md` at the harness root must document:

- Architecture diagram (IPC stack)
- All non-obvious setup steps (the ones that cost debug time)
- App-specific API quirks
- Proof-of-life diagnostic method

---

## Pull Requests

1. One PR per harness or per feature. Don't mix harness work.
2. All unit tests must pass with no Premiere Pro / Acrobat running.
3. SKILL.md descriptions must start with `"Use when..."`.
4. Include a brief `<APP>.md` update if you discovered a new API quirk.

## Disclaimer

This project is not affiliated with, endorsed by, or sponsored by Adobe Inc. Adobe, Acrobat, and Premiere Pro are trademarks of Adobe Inc.
