# artcraft-cli: local ArtCraft bridge + CLI — design (sub-project 1)

- **Date:** 2026-10-09
- **Status:** design approved section by section (sections 1–6); this written spec is pending user review
- **Repos:**
  - this repo, `crichalchemist/adobe-cli` → renamed `artcraft-cli` after merge
  - the user's ArtCraft fork at `/Volumes/Containers/artcraft` (`crichalchemist/artcraft`, upstream `storytold/artcraft`, base commit `3e5793b`)
- **Owners:**
  - CLI + repo pivot: the `cli=api` Claude session (this repo)
  - ArtCraft patch: the `artcraft` Claude session
  - live checks and outward-facing steps: the user

## 0. Summary

This repo stops being three Adobe harnesses and becomes **artcraft-cli**. It is a Python CLI and Claude Code plugin that lets scripts and AI agents drive the **ArtCraft desktop app** (Tauri 2, source-available).

ArtCraft has no external control surface: no localhost server, deep links, AppleScript dictionary or CLI plugin. Its cloud Omni API needs API keys that ArtCraft staff enable per account. So we patch the user's local ArtCraft build to add an **opt-in, loopback-only, token-gated HTTP bridge**. The bridge exposes a fixed allowlist of operations ("ops"). Each op calls ArtCraft's existing Rust command code, so it reuses the app's own login session and credits.

**Sub-project 1 (this spec):**
- the repo pivot
- the bridge
- 15 ops covering app info, account, models, generation through ArtCraft's own server-side route, jobs, media, and settings
- the CLI for those ops

**Sub-project 2 (separate spec, later):** scene and 2D/3D canvas control. That state lives in the webview, so it needs a Rust↔webview round trip. This spec reserves room for it but implements none of it.

### Goals

- An agent can check readiness, price a generation, submit it under a hard credit ceiling, wait for it, and download the results, entirely through `artcraft-cli --json`.
- No retry can double-charge.
- No web page, other OS user, or wrong-token caller can use the bridge.
- The ArtCraft patch is small, additive, and follows ArtCraft's conventions, so it can be rebased onto upstream and could later be offered as an upstream PR.

### Non-goals (sub-project 1)

- Scene and canvas control.
- Native-provider generation: Fal, Sora, Midjourney, WorldLabs and similar.
- Background removal and inpainting.
- Deleting media.
- Writing credentials or logging in through the bridge.
- An in-app "bridge active" indicator.
- Uploading video or audio as generation inputs.
- Any change to ArtCraft's frontend, `lib.rs`, Tauri config, capabilities or SQL.

## 1. Context and findings

All of these were verified against ArtCraft `3e5793b` and pinned `tauri-2.11.2`. Verification was by reading source plus adversarial review; the app has not been run yet.

**Commands and state**
- There are 67 `#[tauri::command]` fns; 63 are registered in `generate_handler!` (`crates/desktop/artcraft/src/lib.rs:227–291`).
- The 4 unregistered ones are `enqueue_text_to_image_command`, `enqueue_edit_image_command`, `enqueue_image_inpaint_command` and `reset_artcraft_command`.
- Commands take only deserializable args, `AppHandle` and `State<'_, T>`. None takes `Window` or `Webview`.
- Rust code can call them directly, passing `app.state()`. The codebase already does this, e.g. `generate_splat_command.rs:14`.
- `TaskDatabase` and `ProviderPriorityStore` are managed inside `handle_tauri_startup`, not in the Builder.
  - `app.state::<T>()` panics on an unmanaged `T`.
  - So the bridge starts at the end of `handle_tauri_startup` (after `:133`).

**Login**
- `StorytellerCredentialManager` starts empty (`lib.rs:120`).
- A ~1 s task syncs it from the HTTP-plugin cookie jar, starting once the main window is first seen.
- After the first sync, `get_credentials()` returns `Some` **even when logged out**.
- Login must therefore be checked with `creds.session.is_some()` (local) or `storyteller_get_login_session_command` (server).

**Generation**
- Omni-routed generation returns `inference_job_token`s, and task rows are inserted per token (`generate/omni/dispatch.rs:76–84`).
- Native-provider paths return `payload: {}` with no id.
- `dispatch::job_tokens` (`:161`) is private.

**Task database**
- It is SQLite at `~/Artcraft/state/tasks_v7.sqlite`.
- It is recreated on migration failure or a schema bump.
- The local `TaskStatus` enum has 9 variants (`enums/src/tauri/tasks/task_status.rs:14–22`): `pending`, `started`, `complete_success`, `complete_failure`, `attempt_failed`, `dead`, `cancelled_by_user`, `cancelled_by_provider`, `cancelled_by_us`. It has no `Unknown` variant.
- Only these are currently written: `pending`, `complete_success`, `complete_failure`, `cancelled_by_user`.
- `updated_at` and `completed_at` are never updated.
- The local poller mirrors only success and failure from the server (`storyteller_task_polling_thread.rs:106–124`).

**`frontend_subscriber_id`**
- It is persisted on the task row for both Omni and native paths, and `sqlite_tasks::list_tasks_for_frontend` exposes it.
- A **null** subscriber id makes the UI (`PageDraw.tsx:74`, `AnglesStore.ts:279`) resolve the user's first pending UI generation with the incoming result. So bridge submits must always set one.

**Events**
- They are one-way Rust→webview (`app.emit`).
- Rust `listen`/`listen_any` does receive `app.emit` events (`tauri-2.11.2 manager/mod.rs:548–549`).
- There is no request/response round trip today.

**HTTP and dependencies**
- No HTTP server crate is in the lockfile.
- `tower-http 0.6.8` and `subtle 2.5.0` are locked.
- tokio `net`/`time` are enabled only by feature unification.
- `artcraft_client` sets **no request timeout** (`storyteller_client_builder.rs:9–17`).

**Panics:** the desktop crate's `panic = "abort"` is ignored, because it is a non-root workspace member. Release builds unwind, so a panic in a spawned task is caught per task.

**Other limits**
- The remote session-jobs list (`GET /v1/jobs/session`) returns at most the newest 100 jobs, with no pagination (`artcraft_api_defs jobs/list_session_jobs.rs:37`).
- The Omni guide (`_docs/artcraft_omni_api.md`, Notes) says a reused `idempotency_token` is **rejected as a duplicate**, not replayed.
- `provider_list_command` returns full plaintext API keys (`maybe_full_key`).

**License:** ArtCraft is "fair source", not OSI.
- Modifying it for personal use is allowed.
- Clause 4 restricts using the ArtCraft name to promote a business, so the name `artcraft-cli` is fine for a free tool and should be revisited before any commercial use.
- Publishing the patch is safest as an upstream PR.

## 2. Decisions log

| # | Decision | Choice | Why |
|---|---|---|---|
| D1 | Integration approach | Patch the local ArtCraft app with a bridge | No external IPC exists; cloud API keys are staff-gated |
| D2 | Repo fate | Pivot to `artcraft-cli`; tag `adobe-final`; delete Adobe harnesses | User: remove all Adobe and cli-anything branding |
| D3 | Name | `artcraft-cli` (package `artcraft_cli`) | User choice |
| D4 | Bridge shape | Op-allowlist RPC (`POST /v1/rpc {op,args}` + `GET /v1/health`) | Smallest surface for a bridge that spends credits; webview ops slot in later; no arbitrary code |
| D5 | Opt-in | `ARTCRAFT_CLI_BRIDGE=1` at launch; off by default | User will launch via the dev script; a preference toggle is YAGNI |
| D6 | Generation scope | Omni (ArtCraft-routed) models only | Only path that yields trackable job ids |
| D7 | Spend guard | `max_credits` required per submit; fail-closed estimate + balance check | User choice; no per-launch cap |
| D8 | Media delete | Not in sub-project 1 | Irreversible; not needed |
| D9 | REPL | A fresh one we write (stdlib only), built last | User: no Apache cli-anything port |
| D10 | Hooks | Keep `hooks/` with a rewritten `session-start` | User choice |
| D11 | Idempotency | Look up rows tagged `cli_bridge:<token>` **before** POSTing; no ledger | Server rejects duplicates rather than replaying; rows exist only after a successful POST; avoids error toasts |
| D12 | Job status | Local first; server only on request or every 60 s during `wait` | Avoids rate limits that would also stall the app's own poller |
| D13 | Build timing | ArtCraft is not built until this spec is approved | User choice |

## 3. Section 1 — repo pivot and workspace (this repo)

### 3.1 Git sequence (milestone M0)

1. Tag the current last-Adobe commit `0180921` as `adobe-final`.
   - The tag goes on that exact commit, so it excludes this spec and the later `.gitignore` commit.
   - Push the tag: `git push origin adobe-final`.
2. Commit the pending `.gitignore` change (`.remember/`) on `main` as `chore: ignore .remember`.
3. Create the branch `pivot/artcraft-cli`. All the work below happens there and merges once CI is green.
4. Delete `premiere-pro/`, `illustrator/` and `acrobat/`.
   - History is not rewritten, so old commits and the tag keep the Adobe content. That includes `premiere-pro/.../CSInterface.js`, which was copied from the Premiere app bundle.

Commit messages follow `type: imperative summary` (feat/fix/docs/test/chore, under 72 characters) and carry **no** agent co-author trailer (user Rule 14).

### 3.2 Layout after the pivot

```
.claude/CLAUDE.md               agent rules: commands, module map, conventions, bridge SOP, live checklists
.gemini/GEMINI.md  -> ../.claude/CLAUDE.md   (symlink)
.agents/AGENTS.md  -> ../.claude/CLAUDE.md   (symlink)
.claude-plugin/plugin.json      name artcraft-cli, v0.1.0, license Elastic-2.0, new description/keywords
.claude-plugin/marketplace.json artcraft-cli-marketplace, single plugin entry (owner unchanged)
hooks/hooks.json                unchanged (SessionStart startup|clear|compact)
hooks/run-hook.cmd              unchanged
hooks/session-start             rewritten (3.4)
skills/artcraft-cli/SKILL.md    the one canonical skill (3.5)
artcraft_cli/
  __init__.py                   __version__ = "0.1.0", SUPPORTED_BRIDGE_PROTOCOL = 1
  __main__.py                   python -m artcraft_cli
  artcraft_cli.py               Click root group `cli` + main()
  errors.py                     CliError + HINTS {code: (hint, retryable)}
  repl.py                       M5 (3.6)
  utils/__init__.py
  utils/bridge.py               the ONLY module touching HTTP or the discovery file (6.6)
  core/__init__.py
  core/{app,account,models,generate,jobs,media,settings}.py
  tests/__init__.py
  tests/conftest.py             discovery/session fixtures; e2e bridge fixture
  tests/test_bridge.py          transport unit tests
  tests/test_core.py            command/core unit tests
  tests/test_full_e2e.py        live tests (auto-skip)
pyproject.toml
.pre-commit-config.yaml
.github/workflows/ci.yml
README.md  CONTRIBUTING.md  LICENSE (Elastic-2.0, unchanged)  .gitignore
docs/superpowers/specs/…        this spec and later specs and plans
```

**Removed:**
- the root `CLAUDE.md` (its content moves, rewritten, into `.claude/CLAUDE.md`)
- the root `skills/SKILL.md` router
- the three harness directories

**`.gitignore` additions:** `.venv/`, `.ruff_cache/`, `.mypy_cache/`, `.serena/` (untracked local tool state that still names the project `adobe-cli`).

**Discovery risk with the symlinks:** Claude Code reads `.claude/CLAUDE.md`. Gemini CLI and Codex mainly look for `GEMINI.md`/`AGENTS.md` at the repo root or ancestors, so they may not find the dot-folder copies. The layout follows the user's Rule 0 as written.

### 3.3 Packaging and tooling

**`pyproject.toml` (PEP 621)**
- name `artcraft-cli`, version `0.1.0`, `license = "Elastic-2.0"`, `requires-python = ">=3.10"`.
- `dependencies = ["click>=8.2", "requests>=2.31"]`.
- `[project.optional-dependencies] dev = ["pytest", "ruff", "mypy", "types-requests", "pre-commit"]`.
- `[project.scripts] artcraft-cli = "artcraft_cli.artcraft_cli:main"`.
- `[tool.pytest.ini_options]`: `testpaths = ["artcraft_cli/tests"]`, markers `e2e` and `spend`.
- `[tool.ruff]` with lint and format; `[tool.mypy]` strict on `artcraft_cli`.

**`.pre-commit-config.yaml`**
- ruff (lint with `--fix`, then format)
- mypy
- pre-commit-hooks: trailing-whitespace, end-of-file-fixer, check-yaml, check-json, check-added-large-files, check-symlinks
- Revs are pinned to the latest stable at implementation time.
- `pre-commit install` replaces the current no-op `.git/hooks/pre-commit` wrapper.

**`.github/workflows/ci.yml`:** on `push` and `pull_request`:
- `pre-commit run --all-files`
- `pip install -e .[dev]`
- `pytest -m "not e2e"` on Python 3.10 and 3.13
- Uses `actions/checkout@v4` and `actions/setup-python@v5`.

**MCP:** no project-specific MCP server is required. It is a small Python CLI, and the user's global servers cover it. This decision is recorded in `.claude/CLAUDE.md`.

**Python conventions (kept from the old harnesses)**
- `from __future__ import annotations` in every module, and type hints on public functions.
- Functional style; classes only for exceptions.
- No bare `except`.
- Named constants for timeouts.
- Validate at boundaries.

### 3.4 `hooks/session-start` (rewritten)

It emits the standard SessionStart schema and nothing else:

```json
{"hookSpecificOutput": {"hookEventName": "SessionStart",
  "additionalContext": "artcraft-cli drives a locally running ArtCraft desktop app (started with ARTCRAFT_CLI_BRIDGE=1). Before using it, read skills/artcraft-cli/SKILL.md and run `artcraft-cli --json ping`."}}
```

### 3.5 `skills/artcraft-cli/SKILL.md`

**Frontmatter**
- `name: artcraft-cli`
- `description: Use when driving the ArtCraft desktop app from scripts or agents — generating images, video, audio, 3D meshes or splats with the user's ArtCraft account, tracking generation jobs, uploading/listing/downloading library media, or reading app, account, credit and settings state. Requires ArtCraft running with ARTCRAFT_CLI_BRIDGE=1.`

**`agent_guidance`**
- run `ping` first, then `account whoami`
- always pass `--json`
- run `--dry-run` before spending, and always pass `--max-credits`
- on retry, reuse the returned `idempotency_token`; never retry after `outcome_unknown`, check `jobs list --remote` instead
- use `jobs wait`, not hand-written poll loops
- use absolute paths

**Body:** the command tree (6.5), error codes with hints (5.6), and the live prerequisites.

### 3.6 REPL (milestone M5)

- `artcraft-cli repl` reads lines with stdlib `readline`, splits them with `shlex`, and dispatches each to the Click group with `standalone_mode=False`.
- Errors print and the loop continues.
- `exit`, `quit` or EOF ends it.
- History is in-memory only.
- No new dependency.
- Running `artcraft-cli` with no subcommand prints help; it never enters the REPL implicitly, which keeps agents non-interactive.

### 3.7 After merge (each confirmed with the user at the time)

- `gh repo rename artcraft-cli`. GitHub redirects the old URL.
- On the user's machine: `pipx uninstall cli-anything-acrobat cli-anything-illustrator`. Both are editable installs pointing at the deleted code.
- Keep the local folder `/Volumes/Containers/adobe-cli` as it is. Renaming it orphans this project's Claude memory.
- Mark the memories `project_acrobat_cli.md` and `project_cep_setup.md` as historical.
- The user-wide `cli-anything@cli-anything` plugin is a user setting outside this repo; it is mentioned, not changed.

## 4. Section 2 — bridge transport and security (ArtCraft repo, branch `feature/cli-bridge`)

### 4.1 Opt-in and startup

- `spawn_cli_bridge_server(&app, &root)` is called from `handle_tauri_startup.rs` after `initially_size_and_position_windows` (`:133`) and before `Ok(())`.
- It reads `ARTCRAFT_CLI_BRIDGE` once.
  - Anything other than exactly `"1"` logs `info!("cli bridge disabled")` and returns `Ok(())`. Nothing binds and no file is written.
  - Otherwise it calls `tauri::async_runtime::spawn(run_cli_bridge_server(app.clone(), root.clone()))`, mirroring `spawn_main_window_thread.rs`. It never blocks app launch.
- A bridge startup failure is logged and leaves the app running normally; `spawn_cli_bridge_server` always returns `Ok(())`. Failure cases are an OS RNG failure, a bind failure, or a discovery-file write failure.
- `unix_dev.sh` passes the shell environment through to cargo, so `ARTCRAFT_CLI_BRIDGE=1 ./script/artcraft/unix_dev.sh` enables the bridge.

### 4.2 Server

- **Stack:** axum 0.8 on HTTP/1.1, bound to `127.0.0.1:0`: an ephemeral port, IPv4 loopback only, with no host option.
- **Routes:** exactly two, `GET /v1/health` and `POST /v1/rpc`.
- **Panics:** no `unwrap`/`expect` in bridge code.
  - Op bodies run as spawned tasks, so a panic there (`JoinError::is_panic`) becomes **500** `internal_error`.
  - A panic in gate or handler code runs on hyper's connection task and drops the connection with no envelope; the CLI reports `bridge_protocol_error`.
  - `tower-http`'s `catch-panic` is deliberately not added.

### 4.3 Token and discovery file

**Token**
- 32 bytes from `rand::rngs::OsRng` (workspace `rand 0.9.1`), hex-encoded to 64 lowercase characters.
- Regenerated every launch.
- Accepted only as `Authorization: Bearer <token>`, never from a query string.
- Compared with `subtle::ConstantTimeEq`.
- Never logged, never echoed.

**Discovery file:** `~/Artcraft/state/cli_bridge.json`, i.e. `root.state_dir()` + `cli_bridge.json`. No `app_state_dir.rs` change is needed.

```json
{"bridge_protocol_version": 1, "port": 53817, "pid": 4242,
 "token": "<64 hex>", "app_version": "0.41.0", "started_at": "2026-10-09T15:04:05Z"}
```

- **Writing:** only after bind succeeds. `NamedTempFile::new_in(state_dir)`, write, `set_permissions(0o600)` on Unix, then `persist()` (an atomic rename).
- **Removal:** on `RunEvent::Exit`, by a plugin registered at runtime with `app.plugin(tauri::plugin::Builder::new("cli_bridge").on_event(..).build())`. So `lib.rs` is not edited.
  - It removes the file only if the file still holds this process's pid and token.
- **Stale files:** after `kill -9` or a dev-watcher restart, the file is stale. The CLI detects the dead pid or refused connection and reports `bridge_not_running`.

### 4.4 Gate (single axum middleware over the whole router, fallbacks included; headers only, before any body is buffered)

Checks run in this order:

1. `Host` must byte-equal `127.0.0.1:PORT`, `localhost:PORT` or `[::1]:PORT`. Otherwise **403** `forbidden_host`, which blocks DNS rebinding. There is no suffix matching.
2. Any `Origin`, `Sec-Fetch-Site` or `Sec-Fetch-Mode` header gives **403** `forbidden_origin`. This blocks browser and CSRF requests, including CORS preflights. Python `requests` sends none of these, and the ArtCraft webview uses Tauri IPC, never this port.
3. The method and path must be `GET /v1/health` or `POST /v1/rpc`. An unknown path gives **404** `not_found`; another method on a known path, or an Origin-less `OPTIONS`, gives **405** `method_not_allowed`.
4. `Authorization: Bearer <64 hex>` must match. Otherwise **401** `unauthorized`.
5. A POST must carry `Content-Type: application/json` (parameters allowed). Otherwise **415** `unsupported_media_type`.
6. `Semaphore(8).try_acquire_owned()`. The permit is held for the whole HTTP request. Otherwise **503** `bridge_busy`.

**After the gate**
- The body is limited to **29,010,604 bytes**: 20 MiB decoded upload × 4/3 for base64 + 1 MiB envelope headroom.
  - The RPC handler extracts `Result<Bytes, BytesRejection>` and maps a length-limit rejection to **413** `payload_too_large` with an envelope body.
  - A `Content-Length` over the cap may also be rejected in the gate.
- No CORS headers are ever sent.

### 4.5 Execution, deadlines and timeouts

- `op_dispatch` runs each op inside `tauri::async_runtime::spawn` and awaits the `JoinHandle` under a per-op deadline:
  - **30 s** for read and local ops
  - **120 s** for `generate.submit` and `media.upload`
- Because ops are spawned, a client that disconnects or a per-op deadline that expires **never cancels an op halfway through**. A paid POST therefore gets to its task-row insert, with one exception: the 300 s hard cap below.
- Every outbound ArtCraft API call is wrapped in `tokio::time::timeout`, because `artcraft_client` has none.
- Inside the detached submit task, the `generate_*_command` call has a hard cap of **300 s**.
  - On expiry the future is dropped, possibly between POST acceptance and the task-row insert loop (`dispatch.rs:56–84`).
  - The result is `outcome_unknown`. The job may then exist **without a local row**, so replay cannot find it and no enqueue or credits events fire. It is visible only through `jobs list --remote`.
- A deadline that expires on submit returns `outcome_unknown` with `details.reason = "deadline"`.

### 4.6 Logging

- There is no `TraceLayer` and no logging of headers, bodies or args. So no redaction layer is needed, and `tower-http` is not a dependency.
- If request tracing is ever added, `SetSensitiveRequestHeadersLayer(AUTHORIZATION)` must go in first.
- One `info!` line per request records the op, result code and `duration_ms`.
- `generate.submit` additionally logs modality, model, idempotency token and job ids, **never the prompt**.
- Log macros only, with the default module-path target (no custom `target:`).
- Wire messages never carry tokens, cookies, prompts or Rust `{:?}` dumps. Upstream `bad_input` text is relayed truncated to 500 characters.

### 4.7 Trust boundary

- **Blocked:** web pages, other OS users, and callers without the token.
- **Not blocked:** any process running as the **same macOS user**, because it can read the `0600` file. ArtCraft already stores provider credentials as plain files under `~/Artcraft/credentials`, so this is the same level of trust.

### 4.8 ArtCraft code changes

**Edits to existing files (6, all additive)**
1. `crates/desktop/artcraft/Cargo.toml`:
   - `axum = { version = "0.8", default-features = false, features = ["http1", "json", "tokio"] }`
   - `subtle = "2.5"`
   - The token uses the existing workspace `rand` (0.9, `os_rng`): `use rand::TryRngCore; OsRng.try_fill_bytes(..)`.
   - tokio features `+ ["net", "time", "sync", "macros"]`
   - Deps stay local to their consumer, per `crates/CLAUDE.md`.
2. `src/core/mod.rs`: `+ pub mod cli_bridge;`
3. `src/core/lifecycle/startup/tasks/mod.rs`: `+ pub (super) mod spawn_cli_bridge_server;`
4. `src/core/lifecycle/startup/handle_tauri_startup.rs`: one `use` line and one call after `:133`.
5. `src/core/commands/generate/omni/dispatch.rs:161`: `fn job_tokens` → `pub(crate) fn job_tokens`. This is the only change to existing logic.
6. `crates/api_clients/artcraft/artcraft_client/src/endpoints/media_files/mod.rs`: `+ pub mod list_user_media_files;`

**New files.** The ArtCraft session may adjust names and placement within ArtCraft conventions without changing the wire contract.
```
src/core/lifecycle/startup/tasks/spawn_cli_bridge_server.rs   env gate + spawn
src/core/cli_bridge/mod.rs                                    declarations only
src/core/cli_bridge/cli_bridge_server.rs                      bind, token, discovery file, exit plugin, axum::serve
src/core/cli_bridge/cli_bridge_gate.rs                        gate middleware, router, envelope types, BridgeErrorCode,
                                                              get_health_handler, post_rpc_handler
src/core/cli_bridge/op_dispatch.rs                            allowlist, per-op deadlines, spawn
src/core/cli_bridge/native_result_mapping.rs                  OmniResult / ResponseOrErrorMessage / DesktopLoginError /
                                                              StorytellerError → BridgeErrorCode
src/core/cli_bridge/ops/mod.rs
src/core/cli_bridge/ops/{app,account,models,generate,jobs,media,settings}_ops.rs
crates/api_clients/artcraft/artcraft_client/src/endpoints/media_files/list_user_media_files.rs
```

**Unchanged:** `lib.rs`, `generate_handler!`, `tauri*.conf.json`, capabilities, CSP, `sqlite_tasks`, `.sqlx`, `artcraft_api_defs`, the frontend. Sub-project 1 adds **no** `#[tauri::command]`.

**ArtCraft conventions the patch follows**
- 2-space indent.
- Log macros, never `println!`.
- `mod.rs` holds declarations only.
- Files run top to bottom: constants → primary type → `{Action}Request`/`{Action}Response`/error → impls, with callers above callees.
- Handlers are named `{verb}_{noun}_handler`.
- `maybe_` prefix for optionals.
- `use serde_derive::{Deserialize, Serialize};` and `errors::AnyhowResult`.
- `impl_enum_display_and_debug_using_to_str!` for enum `Display`.
- Wire enums the bridge *consumes* carry an `Unknown(String)` catch-all.
- Tests sit in a bottom `#[cfg(test)] mod tests`.

## 5. Section 3 — wire contract

### 5.1 Envelope

```
POST /v1/rpc
Host: 127.0.0.1:PORT
Authorization: Bearer <64 hex>
Content-Type: application/json

{"op": "<domain>.<verb>", "args": {...}}
```

- The top level is `deny_unknown_fields`. `args` is required and is always an object (`{}` when empty).
- Each op decodes its args into its own `#[serde(deny_unknown_fields)]` struct.
- The one exception is `generate.*.args.request`, a pass-through map of Omni fields guarded by a deny-list (7.2). This keeps upstream's deliberate pass-through design.

**Responses (every response, gate failures included, is a JSON envelope)**
- Success: `{"ok": true, "data": {...}}`. `data` is always an object; lists are wrapped.
- Failure: `{"ok": false, "error": {"code": "<stable_snake_code>", "message": "<text>", "details": {...}}}`. `details` is omitted when empty.

### 5.2 HTTP status policy (fixed; sub-project 2 inherits it)

- **Non-2xx** only when the request never reached an op handler, or the bridge itself failed: 400, 401, 403, 404, 405, 413, 415, 500, 503.
- **Everything else** is **HTTP 200** with `ok: false`.
- Clients parse the JSON body before looking at the status.

### 5.3 Versioning

- `bridge_protocol_version` is `1`.
- **No bump needed:** new ops, codes or fields.
- **Bump required:** renaming or removing an op or field, or changing a code's meaning or its HTTP status.
- The CLI refuses any other version with `bridge_protocol_mismatch`.

### 5.4 `GET /v1/health`

It passes through the same gate, token included. It makes no network call.

```json
{"ok": true, "data": {"bridge_protocol_version": 1, "app_version": "0.41.0", "pid": 4242,
  "started_at": "2026-10-09T15:04:05Z",
  "ops": ["app.info","account.session","account.credits","account.subscription","models.list",
          "generate.estimate","generate.submit","jobs.get","jobs.list","jobs.dismiss",
          "media.upload","media.get","media.list","settings.get","settings.set"],
  "readiness": {"credentials_synced": true, "session_cookie_present": true}}}
```

- `credentials_synced`: `StorytellerCredentialManager::get_credentials()` returns `Ok(Some(_))`.
- `session_cookie_present`: `.session.is_some()` on that set. This is a local check, not server-validated.
- `ops` is the allowlist; the CLI feature-detects from it.

### 5.5 Ops

`S` = `crates/desktop/artcraft/src`. "AC" = `crates/api_clients/artcraft/artcraft_client/src`. Every arg struct is `deny_unknown_fields`.

| op | args | data | implementation |
|---|---|---|---|
| `app.info` | `{}` | `AppInfoResponse` payload passed through: `artcraft_version`, `build_timestamp`, `git_commit_id?`, `git_commit_short_id?`, `git_commit_timestamp?`, `os_platform`, `os_version`, `storyteller_host`, `artcraft_root_directory`, `download_directory` | `get_app_info_command(app.state()×4)` (`S/core/commands/get_app_info_command.rs:47`, sync) |
| `account.session` | `{}` | `{logged_in, username?, display_name?, user_token?}` | `storyteller_get_login_session_command(app, app.state())` (`S/services/storyteller/commands/storyteller_get_login_session_command.rs:11`). `Ok(Some)` → logged in. `Ok(None)` or `Err{status: 401/403}` → `logged_in: false`. `Err{status: None, retryable}` → `upstream_unavailable`. `Err{status: None, !retryable}` → `internal_error`. Other status → `upstream_error`. No message-text matching. |
| `account.credits` | `{}` | `{free_credits, monthly_credits, banked_credits, sum_total_credits}` | `require_session` → AC `get_session_credits(&host, Some(&creds), PaymentsNamespace::Artcraft)` (`AC/endpoints/credits/get_session_credits.rs:8`), called **directly**, because the command's `ResponseOrErrorMessage` flattens every error to `bad_request` |
| `account.subscription` | `{}` | `{active_subscription: null \| {product_slug, namespace, next_bill_at?, subscription_end_at?}}`. `subscription_token` is dropped. | `require_session` → AC `get_session_subscription(...)` (`AC/endpoints/subscriptions/get_session_subscription.rs:9`) directly. Replicates the command's `ArtcraftSubscriptionSlug::from_str` filter, so unknown slugs give `null`. |
| `models.list` | `{kind: "image"\|"video"}` | `{kind, models: [object]}`, the command's model detail objects passed through unchanged | `list_image_models_command` / `list_video_models_command` (`S/core/commands/generate/models/…:34`). They take only `State<AppEnvConfigs>`, serve a process-wide cached response (`:37`), and return `ResponseOrErrorMessage`. Errors are therefore flattened and map to `upstream_error`, with no `rate_limited` or `not_logged_in` distinction. |
| `generate.estimate` | `{modality, request}` | `{modality, model, estimate: {cost_in_credits?, cost_in_usd_cents?, is_free, is_unlimited, is_rate_limited, has_watermark, failures_are_refunded?}, effective_credits?}` | 7.3 |
| `generate.submit` | `{modality, idempotency_token, max_credits, request}` | `{job_ids: [..], idempotency_token, estimate, replayed, replayed_from?}` | 7.4 |
| `jobs.get` | `{job_ids: [1..50], include_remote?: bool=false}` | `{jobs: [JobView], unresolved: [{job_id, reason}]}` | 7.6 |
| `jobs.list` | `{origin?: "cli"\|"all"="cli", limit?: 1..200=50, include_remote?: bool=false}` | `{jobs: [JobView], truncated}` | 7.6 |
| `jobs.dismiss` | `{job_id}` | `{job_id, task_id, dismissed: true}` | 7.7 |
| `media.upload` | `{filename, content_base64, idempotency_token}` | `{media_token, kind: "image", image_type: "png"\|"jpeg"\|"gif", byte_count}` | 8.1 |
| `media.get` | `{media_token}` | `{media_token, media_class?, media_type?, cdn_url?, thumbnail_url_template?, batch_token?}` | AC `get_media_file` (`AC/endpoints/media_files/get_media_file.rs:27`) |
| `media.list` | `{media_classes?: [..], page_index?: u32=0, page_size?: 1..100=25, sort_ascending?: bool=false}` | `{username, items: [{media_token, media_class?, media_type?, created_at?, title?, original_filename?, batch_token?, duration_millis?, cdn_url?}], page: {index, size, total_pages?}}` | 8.2 |
| `settings.get` | `{}` | `{preferences: {…}}`, the preferences passed through | `get_app_preferences_command(app.state())` (`S/core/commands/app_preferences/get_app_preferences_command.rs:48`) |
| `settings.set` | `{preference: "play_sounds"\|"auto_download", value: bool}` | same as `settings.get` | `update_app_preferences_command(UpdateAppPreferencesRequest{preference, value: Some(ValueType::Bool(v))}, app.state(), app.state())` (`S/core/commands/app_preferences/update_app_preference_command.rs:48`, file name singular; returns `Result<_, String>`). Any other preference gives `setting_not_writable`. |

**Arg constraints**
- Ids and tokens are 1–128 characters of `[A-Za-z0-9_-]`.
- `idempotency_token` is a canonical lowercase UUID.
- `modality` is one of `image | video | audio | mesh | splat`.

**`require_session(&app)`**
- `get_credentials()` is `Ok(None)` or `Err` → `credentials_not_synced`.
- `.session.is_none()` → `not_logged_in`.

### 5.6 Error codes

Every code appears in `BridgeErrorCode` (Rust) and in `HINTS` (CLI); the CLI-only codes appear in `HINTS` alone. An unknown code is treated as generic and not retryable.

| code | HTTP | when | hint | retryable |
|---|---|---|---|---|
| `invalid_request` | 400 | body is not the envelope | — | no |
| `unauthorized` | 401 | bridge token missing or wrong (never the ArtCraft login) | the app restarted; the CLI re-reads discovery once automatically | yes (once) |
| `forbidden_host` | 403 | `Host` is not loopback | call `127.0.0.1` | no |
| `forbidden_origin` | 403 | `Origin`/`Sec-Fetch-*` present | browsers cannot use the bridge | no |
| `not_found` / `method_not_allowed` | 404/405 | wrong path or method | — | no |
| `payload_too_large` | 413 | body over the cap | images ≤ 20 MiB | no |
| `unsupported_media_type` | 415 | POST is not JSON | — | no |
| `internal_error` | 500 | bridge bug or panic | check the ArtCraft log | no |
| `bridge_busy` | 503 | 8 requests in flight | back off | yes |
| `unknown_op` | 200 | op not in the allowlist | see `ping` ops | no |
| `invalid_args` | 200 | args failed validation | — | no |
| `args_too_large` | 200 | args over 1 MiB on a non-upload op | — | no |
| `unsupported_route` | 200 | model or field not on ArtCraft's route (legacy image models, inpainting masks) | pick a model from `models list` | no |
| `operation_in_progress` | 200 | same idempotency token already running | wait, then retry with the same token | yes |
| `credentials_not_synced` | 200 | app just started | the CLI waits up to 5 s automatically | yes |
| `not_logged_in` | 200 | no ArtCraft session | log in inside the app | no |
| `cost_exceeds_limit` | 200 | estimate > `max_credits` (`details{effective_credits, max_credits}`) | raise `--max-credits` or change model | no |
| `estimate_unavailable` | 200 | cost unknown, so refused | — | no |
| `insufficient_credits` | 200 | balance < estimate, or Omni `billing_issue` | buy credits in the app | no |
| `rate_limited` | 200 | upstream 429 / `too_many_requests` | back off | yes |
| `upstream_bad_input` | 200 | ArtCraft API rejected the request (message relayed) | fix the request | no |
| `upstream_unavailable` | 200 | network or timeout on a read op | retry later | yes |
| `upstream_error` | 200 | other upstream failure | — | no |
| `outcome_unknown` | 200 | submit may have been accepted (`details{idempotency_token, reason}`) | check `jobs list --remote`; do **not** resubmit | no |
| `job_not_found` | 200 | no local row and not in the remote list | — | no |
| `job_not_terminal` | 200 | dismiss before the job finished | wait first | no |
| `media_not_found` | 200 | unknown media token | — | no |
| `upload_type_unsupported` | 200 | not PNG/JPEG/GIF | convert first | no |
| `setting_not_writable` | 200 | preference not in the writable set | — | no |
| `local_store_error` | 200 | task DB or temp-file failure | check the ArtCraft log | no |
| `webview_unavailable` / `webview_timeout` / `webview_error` | 200 | **reserved** for sub-project 2 | — | — |

**CLI-only codes** (no HTTP status):

| code | when |
|---|---|
| `bridge_not_running` | no discovery file, dead pid, or connection refused. Hint: start ArtCraft with `ARTCRAFT_CLI_BRIDGE=1`. |
| `discovery_insecure` | the file is not owned by the current user, or is group/other-accessible |
| `bridge_protocol_mismatch` | version ≠ 1 |
| `bridge_protocol_error` | malformed response |
| `response_timeout` | no response within the read timeout. For a submit, rerun with the same `--idempotency-token` to replay. |
| `job_failed` | `wait` saw a failed job |
| `job_wait_timeout` | `wait` hit `--timeout` |
| `download_failed` | CDN fetch failed |
| `output_exists` | download target exists and `--force` was not given |
| `input_file_error` | local input unreadable or too large |

### 5.7 Native result mapping (`native_result_mapping.rs`)

**OmniResult errors (`{status, error_type, error_message}`)**
- `needs_storyteller_credentials` or `unauthorized` → `not_logged_in`
- `billing_issue` → `insufficient_credits`
- `too_many_requests` → `rate_limited`
- `bad_input` → `upstream_bad_input`
- `server_error`:
  - in `generate.submit` → `outcome_unknown`. This is conservative: it covers the "accepted but no job tokens" case (`dispatch.rs:72–74`) and also pre-send failures, which dispatch does not tell apart.
  - in other ops → `upstream_error`

**`StorytellerError`** (calls made directly through `artcraft_client`)
- `Unauthorized`/`Forbidden` → `not_logged_in`
- `TooManyRequests` → `rate_limited`
- `Client(_)` (local setup, file or IO) → `local_store_error`
- `ApiError::DeserializationError` → `upstream_error`
- a network or timeout error → `upstream_unavailable` (read ops)
- else → `upstream_error`

**`String` errors** from commands → `upstream_error`, with a generic message (no `{:?}`).

## 6. CLI (this repo)

### 6.1 Output contract

- **`--json` success:** exactly one compact JSON object on stdout (`separators=(",", ":")`), exit 0. The top level never has an `error` key.
- **`--json` failure:** `{"error": {"code", "message", "hint", "retryable", "details"?}}` on stdout, exit 1. `hint` and `retryable` come from `errors.HINTS`.
- **Without `--json`:** text on stdout; errors go to stderr as `error[<code>]: <message>` plus `hint: …`, exit 1.
- The token never appears in output, logs, exception messages or `repr`.

### 6.2 Transport — `utils/bridge.py`

**Constants**
- `DISCOVERY_PATH = Path.home() / "Artcraft" / "state" / "cli_bridge.json"`
- `CONNECT_TIMEOUT = 3`, `READ_TIMEOUT = 150` (longer than the 120 s bridge deadlines), `HEALTH_TIMEOUT = 5`
- `NOT_SYNCED_WAIT_S = 5`

**Session:** `_sess = requests.Session()` with `trust_env = False` (env proxies are ignored), reached through `_session()`, which is the test patch point.

**`read_discovery()`** runs on every call and checks, in order:
1. The file exists, otherwise `bridge_not_running`.
2. On POSIX: the owner is the current uid and `mode & 0o077 == 0`, otherwise `discovery_insecure`.
3. The required keys are present.
4. The protocol is 1.
5. The pid is alive: `os.kill(pid, 0)`. `ProcessLookupError` means dead; `PermissionError` means alive.

**Calls:** `health()` is `GET /v1/health`; `rpc(op, args)` is `POST /v1/rpc`. Both use URL `http://127.0.0.1:{port}`, never `localhost`.

**Response handling:** the client always parses the JSON body first, whatever the HTTP status.
- `ok: false` raises `CliError(code, message, details)`.
- A non-JSON body gives `bridge_protocol_error`.

**Retries**
- Connection refused before send: re-read discovery once (the app may have restarted on a new port) and retry once, else `bridge_not_running`.
- 401: re-read discovery once and retry once. The gate rejected it, so nothing ran.
- `credentials_not_synced`: retry for up to 5 s, then surface it.
- A read timeout after sending gives `response_timeout`, never `bridge_not_running`.
- `generate.submit` is **never** retried automatically except in the connection-refused-before-send case.

### 6.3 Generate flow on the CLI side (`core/generate.py`)

**Building the request**
- `--prompt P` sets `prompt`.
- `--set KEY=JSON` sets an Omni field, parsed as JSON and falling back to a string.
- `--media FIELD=PATH|TOKEN`:
  - A value that is an existing file path is uploaded (8.1) and replaced with its media token.
  - Fields ending in `_tokens` accumulate lists; fields ending in `_token` take one value.

**Keys and validation**
- Idempotency token: `--idempotency-token` or `str(uuid.uuid4())`. It is echoed in every result and error.
- Upload keys inside a generate: `uuid5(UUID(submit_token), sha256(bytes))`. A rerun with the same token therefore reuses the same uploads.
- Images over 20 MiB or not PNG/JPEG/GIF are rejected locally before any RPC: `input_file_error` or `upload_type_unsupported`.

**`--dry-run`**
- Calls only `generate.estimate`. It never uploads or submits.
- Local-path media fields are left out of the estimate request and listed in the output as `omitted_inputs`.

**Otherwise**
- `--max-credits N` is required; it is refused before any RPC if missing.
- Call `generate.submit`.
- `--wait [--timeout S=900]` then calls `jobs wait`.
- `--download DIR [--force]` then downloads every result file.

### 6.4 Jobs and media on the CLI side

**`jobs wait JOB… [--timeout S] [--download DIR]`**
- Polls `jobs.get` every 5 s; it never polls faster.
- Sets `include_remote: true` at most once every 60 s.
- Returns when every job is terminal.
- Raises `job_failed` (with full details) or `job_wait_timeout` (with the last seen state).

**`media download TOKEN [--out DIR] [--force]`**
- Calls `media.get`, then fetches `cdn_url` directly.
- Requires `https`.
- Refuses to overwrite without `--force` (`output_exists`).

### 6.5 Command tree (every command accepts the root `--json`)

```
artcraft-cli [--json]
  ping                                   discovery + health; bridge {port,pid,app_version,protocol}, readiness, ops
  app info
  account whoami | credits | subscription
  models list --kind image|video
  generate <image|video|audio|mesh|splat> --model M [--prompt P] [--set KEY=JSON]...
           [--media FIELD=PATH|TOKEN]... (--max-credits N | --dry-run)
           [--idempotency-token UUID] [--wait [--timeout S]] [--download DIR [--force]]
  jobs list [--all] [--remote] [--limit N]
  jobs get JOB... [--remote]
  jobs wait JOB... [--timeout S] [--download DIR [--force]]
  jobs dismiss JOB
  media upload FILE [--idempotency-token UUID]
  media get TOKEN
  media list [--class C]... [--page N] [--page-size N] [--oldest-first]
  media download TOKEN [--out DIR] [--force]
  settings get
  settings set play_sounds|auto_download true|false
  repl                                   (M5)
```

With no subcommand, it prints help.

## 7. Section 4 — generating and tracking jobs (bridge side)

### 7.1 Route guard

- A request is accepted only if it will take ArtCraft's Omni route, judged by the app's own public predicates (`request.rs:29–42`).
- The bridge never sets `provider` (it is not part of the upstream request on this route). With `provider: None`, `uses_artcraft()` is always true (`request.rs:30–32`), so for the bridge the guard **reduces to `!uses_legacy_image_endpoint()` for images**.
  - Video and splat take Omni under the same predicate (`generate_video_command.rs:35`, `generate_splat_command.rs:8`).
  - Audio and mesh are Omni-only by construction (`generate_audio_command.rs:7`, `generate_mesh_command.rs:7`).
  - No test targets the unreachable non-Omni branch for those modalities.
- Legacy image models fail the guard with `unsupported_route` before any spend: `recraft_3`, `flux_pro_kontext_max`, `flux_dev_juggernaut`, `flux_pro_1`.

### 7.2 Request deny-list (in this order)

1. `inpainting_mask_image_*` → `unsupported_route`.
2. These keys → `invalid_args`: `provider`, `frontend_caller`, `frontend_subscriber_id`, `frontend_subscriber_payload`, `idempotency_token`, any `*_raw_bytes`, `canvas_image_*`, `scene_image_*`.
3. `model` missing → `invalid_args`.

`estimate_only` is allowed: it is the API's cost-hint struct.

### 7.3 `generate.estimate`

1. Build an `OmniRequest`: `provider: None`, every `frontend_*` field `None`, and `fields` from the request.
2. Call `estimate_<modality>_cost_command`. It works without login and creates no task.
3. Compute `effective_credits`: `0` if `is_free` or `is_unlimited`, otherwise `cost_in_credits`. If `cost_in_credits` is not an integer, `effective_credits` is `null`.

### 7.4 `generate.submit`

1. Validate (7.1, 7.2).
2. **In-flight set:** if the token is already present → `operation_in_progress`. Otherwise insert it. A drop guard removes it however the task ends: success, error, panic or hard cap.
3. **Replay pre-check:** `sqlite_tasks::list_tasks_for_frontend` rows with `frontend_subscriber_id == "cli_bridge:<token>"` → return their job ids (`provider_job_id`), **every** row for a batch, with `replayed: true` and `replayed_from: {modality, model}` from the rows (`task_type`/`model_type`). No POST.
4. `require_session` (5.5). This also avoids the login modal the command would otherwise trigger.
5. **Estimate** as in 7.3, with the same request. If `effective_credits` is null → `estimate_unavailable`; if `effective > max_credits` → `cost_exceeds_limit`.
6. **Balance:** if `effective > 0`, call AC `get_session_credits`. If `effective > sum_total_credits` → `insufficient_credits`.
7. **Submit:** spawn a detached task that calls `generate_<modality>_command` with `OmniRequest{provider: None, frontend_caller: None, frontend_subscriber_id: Some("cli_bridge:<token>"), frontend_subscriber_payload: None, fields: request + {idempotency_token: token}}`. The 300 s hard cap applies.
8. Job ids come from `dispatch::job_tokens(&payload)`: `inference_job_token` first, then `all_job_tokens`, deduped. These are exactly the tokens that got task rows.
9. Respond `{job_ids, idempotency_token, estimate, replayed: false}`. Errors map as in 5.7.

**Edge cases (documented, not engineered around)**
- **Dismissed jobs** (UI or `jobs.dismiss`) are filtered out of `list_tasks_for_frontend`. A resubmit with their token therefore POSTs and hits the server's duplicate rejection, which surfaces as `upstream_bad_input`.
- **A failed task-row insert** is logged and not returned (`dispatch.rs:77–80`). The job is real but not replayable, and it is visible via `jobs list --remote`.
- **The 300 s hard cap** (4.5) can expire after the server accepted the POST but before the row insert. The result is `outcome_unknown`, with the same consequence: no local row, so it can't be replayed and shows only in `jobs list --remote`.
- **The duplicate-rejection response shape** is unverified. M2 captures it. If it is clearly distinguishable, it is mapped to `outcome_unknown`; otherwise it stays `upstream_bad_input`.

### 7.5 UI side effects (disclosed to users in README and SKILL)

- Bridge jobs appear in the app's task panel and in the image and video generation feeds (`useDesktopGenerationFeed.ts:167–205`).
- They emit `generation-enqueue-success-event` per job and `credits_balance_changed_event`, which cause toasts, sounds and a credits refresh.
- Errors on the POST call `notify_frontend_of_errors`.
- The `cli_bridge:` subscriber tag ensures a bridge result never resolves a pending UI generation.
- `settings set play_sounds false` silences them.

### 7.6 `jobs.get` / `jobs.list` (in `jobs_ops.rs`)

**JobView**
```
{job_id, task_id|null, origin: "cli"|"app"|"unknown", modality|null, model|null,
 status: "queued"|"running"|"succeeded"|"failed"|"cancelled"|"unknown", terminal: bool,
 progress_percent: 0..100|null, native_status: {local|null, remote|null},
 result: null|{files: [{media_token, cdn_url|null, thumbnail_url_template|null, media_class|null}], batch_token|null},
 failure: null|{category|null, message|null},
 created_at, remote_updated_at|null, dismissed: bool,
 sources: {local: bool, remote: bool, remote_error: code|null}}
```

**Local lookup:** `list_tasks_for_frontend` filtered by `provider_job_id`. It keeps the subscriber id and the `on_complete_*`/`on_failure_*` fields. For dismissed rows it falls back to `get_task_by_provider_and_provider_job_id` (status only).

**origin**
- `cli` when the subscriber id starts with `cli_bridge:`.
- `app` for a local row without that tag.
- `unknown` for a remote-only job.

**Local status mapping** (an exhaustive match over all 9 `TaskStatus` variants)
- `pending` → `queued`
- `started`, `attempt_failed` → `running`
- `complete_success` → `succeeded` (terminal)
- `complete_failure`, `dead` → `failed` (terminal)
- `cancelled_by_provider`, `cancelled_by_us` → `cancelled` (terminal)
- `cancelled_by_user` → `unknown`, non-terminal. The app's cancel is local only.

**Remote merge** (only when `include_remote: true`)
- Source: AC `list_session_jobs` (`GET /v1/jobs/session`) under a 10 s timeout.
- Mapping:
  - `pending` → `queued`
  - `started` / `attempt_failed` → `running`
  - `complete_success` → `succeeded`
  - `complete_failure` / `dead` → `failed`
  - `cancelled_by_user` / `cancelled_by_system` → `cancelled`
- A remote terminal status wins over local.
- A decode failure (the list's enums have no `Unknown` variant) or a network failure sets `sources.remote_error` and falls back to local data.
- Remote-only jobs appear in `jobs.list` with `origin: "unknown"`.

**Results**
- Taken from the local row's completion fields.
- If a `batch_token` is present, files are expanded with AC `list_batch_generated_redux_media_files`, as `auto_download.rs:42–54` does.
- If expansion fails, the primary file is used and `sources.remote_error` is set.

**`unresolved`:** ids with no local row and (when consulted) no remote entry are reported as `{job_id, reason: not_found|rate_limited|upstream_unavailable|not_logged_in|credentials_not_synced}`.

**`jobs.list`**
- Sorted by `created_at` descending in the bridge, because the query has no `ORDER BY`.
- `origin` defaults to `cli`.
- `truncated` is true when more rows exist than `limit`.
- A row that fails to parse makes `list_tasks_for_frontend` fail entirely; this surfaces as `local_store_error`.

**Known limits**
- The remote list holds only the newest 100 jobs. An older job still pending locally cannot resolve, so `wait` times out with `job_wait_timeout`.
- The task DB is recreated on ArtCraft schema bumps. `job_id`s are server tokens and survive, and lookups fall back to remote.

### 7.7 `jobs.dismiss`

1. Resolve the local row via `get_task_by_provider_and_provider_job_id(provider: Artcraft)`; no row → `job_not_found`.
2. Compute the status. Local terminal is enough; otherwise consult remote. Not terminal → `job_not_terminal`.
3. Run the `sqlite_tasks` `mark_task_as_dismissed` query directly. It returns a `bool`, which the command would discard; `false` → `job_not_found`.

The `TaskId` never crosses the wire as an input.

## 8. Section 5 — media and settings

### 8.1 `media.upload` (images only)

1. Decode the base64 (workspace `base64 0.22`). If decoding fails → `invalid_args`.
2. Check the decoded size is ≤ 20,971,520 bytes.
3. Sniff the magic bytes: PNG, JPEG or GIF. Otherwise `upload_type_unsupported`.
4. `require_session`.
5. Await an upload `Semaphore(1)`, so only one decoded copy, temp file and multipart body exists at a time.
6. Write to `root.temp_dir().new_named_temp_file_with_extension(ext)` (`temporary_dir.rs:39`), i.e. `~/Artcraft/temp`. The extension is the sniffed one, because the binding sends no MIME type.
7. Call AC `upload_image_media_file_from_file_with_idempotency_token` (`upload_image_media_file_from_file.rs:56`) with `is_intermediate_system_file: false`, so uploads are **visible** in the user's library. All other optional fields are `None`, and the token is the caller's.
8. Drop the temp file.

**Error mapping:** as in 5.7. `StorytellerError::Client(_)` → `local_store_error`; `ApiError::DeserializationError` → `upstream_error`.

**No paths:** the bridge never reads a caller-supplied path, so the token cannot be used to read files off the disk.

**CLI side**
- The standalone upload key is `uuid5(NAMESPACE_URL, "artcraft-cli:upload:" + sha256)`.
- Re-uploading the same bytes should therefore return the same `media_token`. That depends on server-side deduplication, which M3 verifies.

### 8.2 `media.list`

1. `require_session`.
2. Get the username from `storyteller_get_login_session_command`. `Ok(None)` → `not_logged_in`.
3. Call the **new** AC binding:
   ```rust
   list_user_media_files(api_host, maybe_creds, username,
                         &ListUserMediaFilesQuery{page_index, page_size, sort_ascending, maybe_filter_media_classes})
     -> Result<serde_json::Value, StorytellerError>
   ```
   - It is `GET /v1/media_files/list/user/{username, path-segment encoded}?include_user_uploads=true&page_size=&page_index=&sort_ascending=[&filter_media_classes=a,b]`, mirroring the frontend's `MediaFilesApi.ts:157–191`.
   - It lives in `artcraft_client`, because `basic_json_get_request` is `pub(crate)`.
4. Project the response tolerantly. Every item field is optional; the server's `media_class` is nullable and items have no `media_links`.

### 8.3 Settings

- `settings.get` returns everything, read-only.
- `settings.set` accepts only `play_sounds` and `auto_download` as booleans. Everything else, including `preferred_download_directory`, gives `setting_not_writable`. A `Custom(PathBuf)` there would let the bridge write anywhere.
- **Known quirk:** the update emits no event, so a UI that cached preferences may show the old value until it re-reads them.

## 9. Exclusions (never reachable as ops in sub-project 1)

- **Unregistered:** `enqueue_text_to_image_command`, `enqueue_edit_image_command`, `enqueue_image_inpaint_command`, `reset_artcraft_command`.
- **Open windows:** `grok_open_login_command`, `midjourney_open_login_command`, `open_sora_login_command`, `worldlabs_open_login_command`, and the six `storyteller_open_*` billing, credits, subscription and customer-portal commands.
- **Credential mutation and login flows:** `provider_set_api_key_command`, `provider_clear_command`, `*_clear_credentials_command`, `sora_logout_command`, `storyteller_purge_credentials_command`, `storyteller_password_login_command`, `storyteller_password_signup_command`, the `storyteller_*_login_challenge_command`s, `check_sora_session_command`, `worldlabs_receive_bearer_command`.
- **Secret egress:** raw `provider_list_command` (plaintext `maybe_full_key`).
- **Provider credential info:** `grok_`, `midjourney_`, `sora_`, `worldlabs_get_credential_info_command`. They are not needed for Omni-only generation.
- **Fake or destructive:** `tasks_nuke_all_command` (a local-only "cancel" that dismisses all of the user's tasks while the remote jobs keep charging).
- **OS UI or filesystem:** `download_directory_reveal_command`, `download_url_command` (any URL into any directory), `download_media_file_command`, `get_download_path_command`. The CLI downloads CDN URLs itself.
- **Unsafe or debug:** `load_without_cors_command` (an unrestricted fetcher, i.e. SSRF), `flip_image`, and `platform_info_command` (a subset of `app.info`).
- **Cosmetic:** `get_provider_order_command`, `set_provider_order_command`. No generation path reads the order.
- **No job handle or not idempotent:** `enqueue_image_bg_removal_command`, `enqueue_image_to_3d_object_command`, `enqueue_image_to_gaussian_command`.
- **Superseded:** `get_task_queue_command`, by `list_tasks_for_frontend`, which keeps the subscriber id.
- **Irreversible:** `media_file_delete_command` (decision D8).
- **Native and legacy routes** inside the allowed generate and estimate commands (decision D6).

## 10. Section 6 — testing, milestones and collaboration

### 10.1 Who does what

- **`artcraft` session:** the Rust patch on `feature/cli-bridge` in `/Volumes/Containers/artcraft`. It runs `SQLX_OFFLINE=true cargo test -p artcraft` and `cargo test -p artcraft_client`.
- **`cli=api` session:** the pivot and the Python CLI on `pivot/artcraft-cli` here.
- **The contract:** this spec. Any contract change needs both sessions and the user.
- **User:**
  - launches the app and logs in for each live checklist
  - approves the outward steps: tag push, GitHub rename, `pipx` cleanup
  - decides on an upstream PR

### 10.2 Tests (named after outcomes; mock only boundaries — user Rule 10)

**Rust loopback tests** use a tokio `TcpListener` on `127.0.0.1:0` and a reqwest client, following `storyteller_login_bridge_tests.rs` and `core/utils/auto_download.rs`. No `AppHandle` is needed.

Gate and router:
- `dns_rebound_host_is_rejected_before_token_check`
- `lookalike_localhost_hosts_are_rejected`
- `all_three_loopback_host_spellings_are_accepted`
- `any_origin_or_fetch_metadata_header_is_rejected_even_with_valid_token`
- `wrong_token_is_401_and_never_echoed`
- `form_posts_from_web_pages_get_415`
- `options_preflight_never_succeeds_and_sends_no_cors_headers`
- `unknown_ops_never_reach_dispatch`
- `excess_in_flight_requests_get_503_bridge_busy`
- `op_errors_return_http_200_with_ok_false`
- `every_gate_rejection_is_a_json_envelope`
- `largest_allowed_upload_fits_under_the_body_cap`
- `non_upload_ops_over_1mib_get_args_too_large`

Token and discovery file:
- `each_launch_gets_a_fresh_256_bit_token`
- `debug_output_never_contains_token`
- `discovery_file_is_owner_only_and_written_after_bind`
- `exit_cleanup_only_removes_this_processes_file`

Mapping and request builder:
- `native_results_map_to_stable_codes`
- `legacy_image_models_are_refused_before_spend`
- `reserved_request_keys_are_refused`
- `inpainting_masks_are_unsupported_route`

Replay pre-check and dismiss (temp `TaskDatabase` via `TaskDatabase::connect(&AppDataRoot)`):
- `resubmitting_a_tagged_token_replays_every_batch_row_without_posting`
- `untagged_tasks_are_never_replayed`
- `dismiss_refuses_unfinished_jobs`

Media-list binding:
- `media_list_builds_the_user_list_url_with_filters`
- This is a unit test of a pure URL/query-builder fn. `artcraft_client` has no loopback-server tests today, and its dev-deps lack tokio `net`, so no new pattern is introduced and `artcraft_client/Cargo.toml` is untouched.

**Python unit tests** (`pytest -m "not e2e"`)
- They patch `artcraft_cli.utils.bridge._session` with a scripted fake that returns real status codes and envelope bodies.
- `DISCOVERY_PATH` points at a `tmp_path` file (mode `0600`, `pid = os.getpid()`).
- Core logic is never mocked.

`test_bridge.py`:
- `missing_discovery_file_reports_bridge_not_running`
- `dead_pid_reports_bridge_not_running_instead_of_hanging`
- `world_readable_or_foreign_discovery_file_is_refused`
- `refused_connection_rereads_discovery_then_reports_not_running`
- `restarted_app_on_new_port_is_found_on_retry`
- `bridge_error_body_survives_non_2xx_status`
- `op_error_with_http_200_raises_its_code`
- `read_timeout_after_send_is_never_reported_as_not_running`
- `protocol_version_mismatch_is_refused`
- `proxy_env_vars_never_route_bridge_traffic`
- `token_never_appears_in_stdout_stderr_or_exceptions`
- `credentials_not_synced_is_retried_briefly_then_surfaced`

`test_core.py`:
- `json_success_is_one_compact_object_without_error_key`
- `json_errors_are_objects_on_stdout_with_exit_1`
- `human_errors_go_to_stderr`
- `spend_without_max_credits_is_refused_before_any_rpc`
- `dry_run_never_uploads_or_submits`
- `submit_is_never_auto_retried_after_send`
- `rerun_with_same_token_and_local_input_gets_same_upload_key`
- `fields_ending_in_tokens_accumulate_lists`
- `wait_returns_all_files_when_every_job_succeeds`
- `wait_fails_with_job_failed_and_full_details`
- `wait_times_out_with_last_seen_state`
- `wait_never_polls_faster_than_five_seconds`
- `wait_checks_remote_at_most_once_a_minute`
- `download_refuses_to_clobber_and_rejects_non_https`
- `oversized_or_unsupported_upload_is_rejected_before_rpc`
- `repl_dispatches_lines_to_commands_and_survives_errors` (M5)

**Python E2E tests** (`test_full_e2e.py`)
- A session fixture runs `read_discovery()` and `health()` once. It skips, with a printed reason, **only** on `bridge_not_running`.

Free tests:
- `ping_reports_protocol_1_and_readiness`
- `whoami_matches_app_login`
- `estimate_changes_no_credits_and_creates_no_job`
- `models_list_includes_ids_estimate_accepts`
- `browser_origin_is_refused`
- `installed_console_script_emits_parseable_json`

Spend tests also require `ARTCRAFT_E2E_SPEND=1` and use `--max-credits ${ARTCRAFT_E2E_MAX_CREDITS:-10}`:
- `cheapest_image_completes_and_downloads_every_file`
- `retry_with_returned_token_replays_without_second_charge`
- `uploaded_image_is_usable_as_generation_reference`

**CI** runs on this repo only. ArtCraft's Rust tests run locally; the fork's CI is untouched.

### 10.3 Milestones

Each milestone ends with a live checklist, run by the user with `ARTCRAFT_CLI_BRIDGE=1 ./script/artcraft/unix_dev.sh`.

**M0 — Baseline**
- Here: the git sequence (3.1), deleting the harnesses, rebranding, workspace tooling, `.claude/CLAUDE.md` with its symlinks, the rewritten hook and skill. Done when CI is green on the empty `artcraft_cli` package.
- There: build and run **unmodified** ArtCraft on `feature/cli-bridge`; the user logs in once. This records the baseline build time and any toolchain installs needed.

**M1 — Thin live slice, zero spend**
- Rust: deps, spawn, server, token and discovery file with the exit plugin, gate/router/envelope, dispatch, result mapping, and the ops `app.info`, `account.session`, `jobs.list` (local only) and `generate.estimate`.
- Python: `utils/bridge.py`, `errors.py`, the root CLI, and `ping`, `app info`, `account whoami`, `jobs list`, `generate --dry-run`, with their unit tests.
- Live checklist:
  - (a) With the variable unset: no file, no listener (`lsof`), and the log says "cli bridge disabled".
  - (b) With it set: the file exists with `-rw-------` and the 6 keys.
  - (c) `ping` reports protocol 1, and `credentials_synced` turns true about 1–2 s after the main window appears.
  - (d) `app info` shows the version.
  - (e) `account whoami` matches the UI, both logged in and logged out.
  - (f) `jobs list --all` matches the task panel.
  - (g) `generate image --model <id> --prompt x --dry-run` returns a price, while `--model recraft_3` gives `unsupported_route`. Credits and the task count are unchanged.
  - (h) curl negatives: `Host: evil.test`, `Origin`, `Sec-Fetch-Site` → 403; no token → 401; `OPTIONS` → 405; `text/plain` POST → 415; an unknown op → 200 `unknown_op`.
  - (i) Cmd-Q removes the file. This confirms the runtime plugin receives `RunEvent::Exit`, which has not been verified until now.

**M2 — Spending**
- Rust: `job_tokens` → `pub(crate)`, `generate.submit`, `jobs.get` with the remote merge and batch expansion, `account.credits`, `account.subscription`, `models.list`.
- Python: `generate` submit, `--wait` and `--download`; `jobs get` and `jobs wait`; `account credits` and `subscription`; `models list`.
- Live checklist:
  - The cheapest image completes, and its files download.
  - A rerun with the same token replays, and the credits balance is unchanged.
  - Dismiss the job, then resubmit the same token to capture the real duplicate-rejection status and body. Record it in project memory and update 7.4 if the shape is distinguishable.
  - `--max-credits` below the estimate gives `cost_exceeds_limit` with no spend.

**M3 — Media**
- Rust: the AC `list_user_media_files` binding and its loopback test; `media.upload`, `media.get`, `media.list`.
- Python: `media upload`, `get`, `list`, `download`; `generate --media FIELD=PATH`.
- Live checklist:
  - An uploaded PNG appears in the library.
  - Re-uploading the same bytes returns the same token (server dedupe).
  - The uploaded token works in `image_media_tokens`.
  - `media list` paging matches the app.

**M4 — Settings, dismiss, hardening**
- `settings.get`/`set` and `jobs.dismiss`.
- Every excluded command name sent as an op returns `unknown_op`.
- Grepping the app log for the token, prompts or base64 finds nothing.
- `play_sounds false` silences a bridge generation.
- `preferred_download_directory` is refused.

**M5 — REPL and docs**
- The fresh REPL.
- `README.md`, `CONTRIBUTING.md` and `.claude/CLAUDE.md` finalized with the bridge SOP.
- Then the post-merge steps (3.7), each confirmed with the user.

## 11. Sub-project 2 hooks (reserved, not implemented)

- **Reserved op domains:** `scene.*`, `canvas2d.*`, `canvas3d.*`. They return `unknown_op` until registered. New ops join the same allowlist and `health.ops`, with no protocol bump.
- **Round trip:**
  1. Rust stores a `tokio::sync::oneshot::Sender` under a fresh id in a managed map.
  2. Rust `app.emit("cli_bridge_request", {id, op, args})`.
  3. A frontend module-level handler registry runs the op against the stores or editor.
  4. The frontend replies through a new `#[tauri::command] cli_bridge_respond_command({id, ok, data|error})`, in its own file per ArtCraft convention.
  5. Rust resolves the oneshot, with a timeout.
- The reply goes through invoke rather than an event: typed args, deserialize errors surface, and there is no dependency on event-capability details.
- **Reserved codes** (HTTP 200): `webview_unavailable` (no handler registered, or the emit failed), `webview_timeout`, and `webview_error` (frontend code in `details.frontend_code`).
- **Precondition:** webview ops work only while the relevant page or editor is mounted.

## 12. Risks, known limits, and pre-existing debt

**Unverified until live**
- Credential sync timing (M1)
- Exit-plugin cleanup (M1)
- The duplicate-rejection shape (M2)
- Upload dedupe and the media-list response shape (M3)

**Spend**
- `outcome_unknown` can mean credits were spent with no local row. The mitigations are: the CLI never auto-resubmits, `jobs list --remote` reconciles, and every submit is logged with its token.
- There is no per-launch spend cap (D7). Revisit before letting agents run unattended loops.

**UI and cache behaviour**
- Bridge jobs are visible in, and noisy in, the app UI (7.5).
- Preference changes made through the bridge are not pushed to the UI (8.3).

**Memory bounds**
- Worst case, request bodies use about 8 × 29 MB.
- Detached ops outlive their HTTP permit, but uploads are serialized by `Semaphore(1)`. This is acceptable for an opt-in loopback bridge.

**Upstream churn**
- Rebasing the fork is the user's ongoing cost.
- The patch is additive apart from one visibility change, which keeps conflicts small.

**Pre-existing ArtCraft debt** (noted, not fixed here)
- Sora, Grok and WorldLabs credential files are written with plain `std::fs::write` and no explicit mode.
- `provider_list_command` returns plaintext keys.
- `get_task_queue_command` and `list_tasks_for_frontend` fail entirely on one unparseable row.
- The storyteller poller's `handle_failed_job(..).await?` aborts a whole poll pass.
- `ResponseOrErrorMessage`'s `From<String>` defaults to `bad_request`.
- `provider_list_command.rs:103` byte-slices `&key[..6]`, which panics on non-ASCII keys.

**Pre-existing debt in this repo** (moot after the pivot)
- The Premiere REPL is broken under Click 8.3 (`mix_stderr`).
- The old `cep_backend` called `raise_for_status()` before parsing error bodies.
- The Adobe test baseline: Premiere unit tests passed 33/33; Illustrator and Acrobat were not re-run.
