# ArtCraft CLI Bridge (Rust) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in, loopback-only HTTP bridge to the ArtCraft desktop app. It exposes 15 allowlisted ops (account, models, Omni generation, jobs, media, settings) to the `artcraft-cli` Python CLI.

**Architecture:** One axum 0.8 router on `127.0.0.1:0` has two routes, `GET /v1/health` and `POST /v1/rpc`, behind a single header-only gate: Host, browser headers, route, bearer token, content type, then an in-flight limit. The RPC handler checks the op allowlist and calls an injected `DispatchFn`. Production dispatch spawns each op on the Tauri async runtime under a per-op deadline. Ops call the app's existing Tauri command functions, `artcraft_client` endpoints and `sqlite_tasks` queries directly. The bridge adds no `#[tauri::command]` and leaves `lib.rs` untouched.

**Tech Stack:** Rust (2-space indent), Tauri 2, axum 0.8 (`http1`, `json`, `tokio`), tokio 1.42 (`net`, `time`, `sync`, `macros` added), `subtle` 2.5, workspace `rand` 0.9 (`OsRng`), `tempfile`, `serde_json`, SQLx/SQLite via `sqlite_tasks`, `artcraft_client`.

**Spec:** `/Volumes/Containers/adobe-cli/docs/superpowers/specs/2026-10-09-artcraft-cli-bridge-design.md`, the user-approved version at commit `bc7b57d`. Read spec §4 (transport and security), §5 (wire contract), §7 (generate and jobs), §8 (media and settings) and §10 (tests and milestones) before starting any task.

**Repository:** every path below is relative to `/Volumes/Containers/artcraft`, on branch `feature/cli-bridge`. `S` means `crates/desktop/artcraft/src`, and `AC` means `crates/api_clients/artcraft/artcraft_client/src`.

## Global Constraints

- Opt-in only. `ARTCRAFT_CLI_BRIDGE` must equal exactly `"1"`. Any other value logs `info!("cli bridge disabled")`, binds nothing and writes no file. `spawn_cli_bridge_server` always returns `Ok(())`, and a bridge failure is logged while the app keeps running.
- **Bind:** `127.0.0.1:0` (IPv4 loopback, ephemeral port, no host option).
- **Routes:** exactly `GET /v1/health` and `POST /v1/rpc`.
- **Token:** 32 bytes from `rand::rngs::OsRng`, encoded as 64 lowercase hex characters and regenerated each launch.
  - Accepted only as `Authorization: Bearer <token>`, compared with `subtle::ConstantTimeEq`.
  - Never logged, never echoed. `Debug` is redacted and there is no `Display`.
- **Discovery file:** `~/Artcraft/state/cli_bridge.json`, built as `root.state_dir()` + `cli_bridge.json`.
  - Mode `0600`. Written only after bind, via `NamedTempFile::new_in(state_dir)` then `persist()`.
  - Exactly 6 keys: `bridge_protocol_version`, `port`, `pid`, `token`, `app_version`, `started_at`.
  - Removed on `RunEvent::Exit`, and only while it still holds this process's pid and token.
- **Gate order:** (1) `Host` byte-equals `127.0.0.1:PORT`, `localhost:PORT` or `[::1]:PORT`, else 403 `forbidden_host`. (2) Any `Origin`, `Sec-Fetch-Site` or `Sec-Fetch-Mode` header gives 403 `forbidden_origin`. (3) The route must be known, else 404 `not_found`; a wrong method gives 405 `method_not_allowed`. (4) The bearer token must match, else 401 `unauthorized`. (5) A POST must be `application/json`, else 415 `unsupported_media_type`. (6) `Semaphore(8).try_acquire_owned()`, else 503 `bridge_busy`.
- **Limits:**
  - Body: `29_010_604` bytes (20 MiB × 4/3 + 1 MiB), giving 413 `payload_too_large`.
  - Non-upload args: `1_048_576` bytes, giving HTTP 200 `args_too_large`.
  - Decoded upload: `20_971_520` bytes, giving `invalid_args` with `details{max_bytes: 20971520}`.
  - Uploads run one at a time, under `Semaphore(1)`.
- **Timeouts:**
  - Op deadlines: 30 s for read and local ops; 120 s for `generate.submit` and `media.upload`.
  - Per-call timeouts: 20 s inside 30 s ops, 10 s for the remote jobs list, 100 s for the upload call.
  - Submit POST hard cap: 300 s.
  - An expired deadline gives `upstream_unavailable{reason: "deadline"}`, except on submit, where it gives `outcome_unknown{idempotency_token, reason: "deadline"}`.
- **HTTP status:** non-2xx only for 400, 401, 403, 404, 405, 413, 415, 500 and 503. Every op-level error is HTTP 200 with `ok: false`. Every response, gate rejections included, is a JSON envelope.
- **Protocol:** `bridge_protocol_version` is `1`. No CORS headers are ever sent.
- **No panics:** no `unwrap`/`expect` in bridge code. Tests are exempt.
- **Logging:**
  - One `info!` per RPC: op, result code and `duration_ms`.
  - `generate.submit` also logs modality, model, idempotency token and job ids, **never the prompt**.
  - Never log headers, bodies or args. Use log macros with the default target.
- **Wire messages** never carry tokens, cookies, prompts or `{:?}` dumps. Upstream `bad_input` text is truncated to 500 characters.
- **Edits to existing files are exactly these, all additive:**
  - `crates/desktop/artcraft/Cargo.toml` (deps)
  - `S/core/mod.rs` (`pub mod cli_bridge;`)
  - `S/core/lifecycle/startup/tasks/mod.rs` (`pub (super) mod spawn_cli_bridge_server;`)
  - `S/core/lifecycle/startup/handle_tauri_startup.rs` (1 `use`, 1 call)
  - `S/core/commands/generate/omni/dispatch.rs:161` (`fn job_tokens` becomes `pub(crate) fn job_tokens`)
  - `AC/endpoints/media_files/mod.rs` (`pub mod list_user_media_files;`)
  - `Cargo.lock` changes as a consequence of the dependency edit.
- **Unchanged:** `lib.rs`, `generate_handler!`, `tauri*.conf.json`, capabilities, CSP, `sqlite_tasks`, `.sqlx`, `artcraft_api_defs`, the frontend, `external/` and `secrets/`.
- **ArtCraft conventions:**
  - 2-space indent, log macros, `mod.rs` holds declarations only.
  - Each file reads top to bottom: constants, primary type, supporting types, impls, with callers above callees.
  - `maybe_` prefix for optionals. `use serde_derive::{Deserialize, Serialize};` and `errors::AnyhowResult`.
  - Enums get `to_str()` and a hand-written `Display`.
  - Tests go in a bottom `#[cfg(test)] mod tests`: test cases first, helpers last.
- **Commands:**
  - Test: `SQLX_OFFLINE=true cargo test -p artcraft --lib <filter>` from the repo root.
  - Compile check: `SQLX_OFFLINE=true cargo check -p artcraft`.
  - Client tests: `cargo test -p artcraft_client --lib <filter>`.
- **Commits:**
  - `git add <explicit paths>`, never `-A` or `.`.
  - **Never stage `.gitignore`**: it has a pre-existing uncommitted `+.remember/` line that is not part of this work.
  - No `Co-Authored-By` or other agent trailer in any commit message.
- **Contract changes need the user.** If code and spec disagree, stop and report; do not change the wire contract.

## Decisions This Plan Makes Within the Spec (report, don't re-litigate)

1. **Gate `Content-Length` check.** A declared `Content-Length` over `29_010_604` is rejected in the gate with 413, before any body is read; spec §4.4 says this "may" be done.
2. **Omni error types.** An unknown or missing Omni `error_type` maps like `server_error`: `upstream_unavailable` from an estimate, `outcome_unknown{reason: "server_error"}` from the submit POST.
3. **Files beyond spec §4.8 (placement within the spec's allowance):**
   - `cli_bridge_token.rs`, `cli_bridge_discovery_file.rs`
   - `cli_bridge_envelope.rs`: `BridgeErrorCode`/`BridgeError`, split out of the gate
   - `ops/op_support.rs`
   - `ops/generate_rules.rs`: the pure validation and pricing rules
   - `ops/generate_submit.rs`: the in-flight set, replay and the hard cap
   - `ops/job_view.rs`: the pure JobView mapping and merge
   - `ops/test_tasks.rs`: `#[cfg(test)]` task-database fixtures
4. **`ALLOWED_OPS` grows per milestone:** 5 ops in M1, 9 in M2, 12 in M3, 15 in M4. `health.ops` always equals the allowlist. The cli=api peer accepted this.
5. **`jobs.list` remote merge ships in M1.** `jobs.list {include_remote: true}` lands in M1 rather than M2, because the pure merge and its tests land in M1. The merge is a free read.
6. **`JobView.created_at` is nullable**, only for a dismissed row whose job the remote list did not return. `get_task_by_provider_and_provider_job_id` returns no timestamps.
7. **Test rename.** Spec §10.2's `video_batches_are_priced_per_video_until_verified` becomes `video_batches_are_priced_per_video_like_the_app`.
   - The app's own video estimate omits the count and multiplies the unit price locally (`frontend/libs/components/pricing-modal/src/lib/useVideoCostEstimate.ts:89-91`).
   - So the bridge strips `video_batch_count` from the estimate call and multiplies. Image sends `image_batch_count` and uses the server's total.
   - A `video_batch_count` that is not a positive integer is refused with `invalid_args`; the bridge refuses rather than risk undercounting.
   - For video, the count keys `batch_size` and `image_batch_count` are also refused with `invalid_args`. Omni's `api_fields(Video)` renames neither, so the server would see them while the bridge priced a single video. This is a fail-closed addition to spec §7.2 for the user to confirm; `video_batch_count` is the key the app sends (`GenerateVideo.ts`, `generate_video/request.rs:109`).
8. **Loopback test client.** Loopback tests send raw HTTP/1.1 over `std::net::TcpStream` (in `spawn_blocking`), not reqwest, so they control `Host` byte-for-byte and can send a headers-only oversized POST. Spec §10.2 names reqwest.
9. **Tests added beyond §10.2**, for pure logic with no other coverage:
   - `idempotency_tokens_must_be_canonical_lowercase_uuids`
   - `job_lists_are_newest_first_and_report_truncation`
   - `unresolved_job_ids_carry_the_remote_failure_reason`
   - `uploads_are_limited_to_20mib_png_jpeg_or_gif`
   - `media_list_items_with_missing_fields_project_as_nulls`
   - `only_play_sounds_and_auto_download_are_writable`
10. **Arg enums are closed.** `modality`, `kind` and `origin` reject unknown values with `invalid_args` and carry no `Unknown(String)`. Catch-alls are for upstream enums the app reads; refusing unknown CLI input is the safe direction.
11. **The detached submit task.** Spec §7.4 step 7's "detached task" is the op task that `dispatch_op` spawns. It keeps running past the 120 s op deadline, and `run_submit` applies the 300 s hard cap inline.
12. **`media.list` items have `cdn_url: null`** unless the server includes `media_links`. The list endpoint's items carry `public_bucket_path` (`frontend/libs/components/pagescene/src/lib/models/mediaInfo.ts:31`). `media.get` returns the CDN URL.
13. **Generic `parse_args` message.** Arg-decoding errors use a generic message, so serde never echoes a value (for example a prompt) back.
14. **Exit cleanup before bind.** The exit-cleanup plugin is registered before bind, so a file can never outlive a half-started bridge.
15. **Panics unwind in release builds too.** `crates/desktop/artcraft/Cargo.toml` declares `[profile.release] panic = "abort"`, but Cargo ignores profiles in workspace members (it warns "profiles for the non root package will be ignored"), and the root `Cargo.toml` has no `[profile]`. So spec §4.2's "a panic in an op becomes 500 `internal_error`" holds in release builds. That would change only if upstream moved `panic = "abort"` to the workspace root.

**Not implemented (proposed amendments awaiting the user):** B (submit op deadline → `operation_in_progress`), C (CLI hint), D (`InternalServerError`/Cloudflare/≥500 → `upstream_unavailable`), E (`RUST_LOG` docs). This plan implements spec `bc7b57d` plus internal correction A only.

**Verification format deviation.** Wiring-only tasks (T7, T8, T12) have no unit-testable seam beyond what earlier tasks test. They are verified with `SQLX_OFFLINE=true cargo check -p artcraft`, the full bridge test filter, and the milestone's live checklist.

**Compiled vs. uncompiled code.** The token, discovery file, envelope, gate and `bind_and_publish` code below was compiled in a standalone prototype, with 17 tests passing. Everything under `ops/`, `op_dispatch.rs`, the server bootstrap and the AC binding is written against signatures read from the source, but has not been through a compiler. If a signature differs, fix the call site, not the contract.

## File Map

| Path                                                       | Responsibility                                                                                           | Task          |
|------------------------------------------------------------|----------------------------------------------------------------------------------------------------------|---------------|
| `crates/desktop/artcraft/Cargo.toml`                       | add `axum`, `subtle`; tokio features                                                                     | T2            |
| `S/core/mod.rs`                                            | `pub mod cli_bridge;`                                                                                    | T2            |
| `S/core/cli_bridge/mod.rs`                                 | declarations only                                                                                        | T2, T3, T4    |
| `S/core/cli_bridge/cli_bridge_token.rs`                    | per-launch bearer token                                                                                  | T2            |
| `S/core/cli_bridge/cli_bridge_discovery_file.rs`           | write / owned-remove `cli_bridge.json`                                                                   | T2            |
| `S/core/cli_bridge/cli_bridge_server.rs`                   | `bind_and_publish` (T2); `run_cli_bridge_server`, exit plugin, readiness (T8)                            | T2, T8        |
| `S/core/cli_bridge/cli_bridge_envelope.rs`                 | `BridgeErrorCode`, `BridgeError`, success envelope                                                       | T3            |
| `S/core/cli_bridge/cli_bridge_gate.rs`                     | gate middleware, router, health and RPC handlers                                                         | T3            |
| `S/core/cli_bridge/op_dispatch.rs`                         | `ALLOWED_OPS` (T3), dispatch with deadlines (T7), grows per milestone                                    | T3, T7, T12+  |
| `S/core/cli_bridge/native_result_mapping.rs`               | Omni / `StorytellerError` / `DesktopLoginError` mapped to codes                                          | T4            |
| `S/core/cli_bridge/ops/mod.rs`                             | declarations only                                                                                        | T4+           |
| `S/core/cli_bridge/ops/op_support.rs`                      | `OpContext`, `OpLimits`, arg parsing, session, ids, timeouts                                             | T4, T12, T16  |
| `S/core/cli_bridge/ops/generate_rules.rs`                  | deny-list, route guard, estimate input, `effective_credits`, `decide_spend`                              | T5, T10       |
| `S/core/cli_bridge/ops/job_view.rs`                        | `JobView`, status maps, merge, `build_job_list`, `build_job_get`                                         | T6, T13       |
| `S/core/cli_bridge/ops/{app,account,models,generate,jobs}_ops.rs` | op bodies                                                                                         | T7+           |
| `S/core/cli_bridge/ops/generate_submit.rs`                 | `InFlightTokens`, `run_submit`, replay                                                                   | T11           |
| `S/core/cli_bridge/ops/test_tasks.rs`                      | `#[cfg(test)]` temp `TaskDatabase` fixtures                                                              | T11           |
| `S/core/cli_bridge/ops/media_ops.rs`                       | upload / get / list                                                                                      | T16           |
| `S/core/cli_bridge/ops/settings_ops.rs`                    | settings get / set                                                                                       | T19           |
| `S/core/lifecycle/startup/tasks/spawn_cli_bridge_server.rs`| env gate + spawn                                                                                         | T8            |
| `S/core/lifecycle/startup/tasks/mod.rs`                    | `pub (super) mod spawn_cli_bridge_server;`                                                               | T8            |
| `S/core/lifecycle/startup/handle_tauri_startup.rs`         | `use` + call after `:133`                                                                                | T8            |
| `S/core/commands/generate/omni/dispatch.rs`                | `job_tokens` → `pub(crate)`                                                                              | T11           |
| `AC/endpoints/media_files/list_user_media_files.rs`        | new binding + URL builder                                                                                | T15           |
| `AC/endpoints/media_files/mod.rs`                          | `pub mod list_user_media_files;`                                                                         | T15           |

---

# M0 — Baseline

### Task 1: Branch, baseline build, baseline tests

**Files:** none modified.

**Interfaces:**
- Consumes: nothing.
- Produces: branch `feature/cli-bridge` and a recorded baseline (test results, build time), which later tasks compare against.

- [ ] **Step 1: Confirm the working tree**

Run: `git -C /Volumes/Containers/artcraft status --short`
Expected: exactly ` M .gitignore`. That is a pre-existing change that is not ours; leave it unstaged for the whole plan. If anything else appears, stop and report.

- [ ] **Step 2: Create the branch**

Run: `git -C /Volumes/Containers/artcraft switch -c feature/cli-bridge main`
Expected: `Switched to a new branch 'feature/cli-bridge'`

- [ ] **Step 3: Record the baseline test run**

Run:
```bash
cd /Volumes/Containers/artcraft && time (SQLX_OFFLINE=true cargo test -p artcraft --lib 2>&1 | tail -n 40)
cd /Volumes/Containers/artcraft && cargo test -p artcraft_client --lib 2>&1 | tail -n 20
```
Expected: both finish. Write down the `test result:` lines, every `FAILED` test name, and the wall time.

Write them to the project memory file `/Users/controlroom/.claude/projects/-Volumes-Containers-artcraft/memory/artcraft-baseline-tests.md`, with a pointer line in that directory's `MEMORY.md`. Pre-existing failures are logged, not fixed (user Rule 13).

- [ ] **Step 4: User runs unmodified ArtCraft once**

Ask the user to run `time ./script/artcraft/unix_dev.sh` from `/Volumes/Containers/artcraft` with `ARTCRAFT_CLI_BRIDGE` unset, and to log in once inside the app.

Record the cold build time and any toolchain installs it needed in the same memory file. No commit; nothing changed.

---

# M1 — Thin live slice, zero spend

### Task 2: Dependencies, token, discovery file, bind-and-publish

**Files:**
- Modify: `crates/desktop/artcraft/Cargo.toml:54,71,78`
- Modify: `crates/desktop/artcraft/src/core/mod.rs:2` (insert after `pub mod artcraft_error;`)
- Create: `crates/desktop/artcraft/src/core/cli_bridge/mod.rs`
- Create: `crates/desktop/artcraft/src/core/cli_bridge/cli_bridge_token.rs`
- Create: `crates/desktop/artcraft/src/core/cli_bridge/cli_bridge_discovery_file.rs`
- Create: `crates/desktop/artcraft/src/core/cli_bridge/cli_bridge_server.rs`
- Test: the bottom `mod tests` of the three new `.rs` files

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `CliBridgeToken::generate() -> AnyhowResult<CliBridgeToken>`
  - `CliBridgeToken::as_hex(&self) -> &str`
  - `CliBridgeToken::matches_bearer_header(&self, Option<&HeaderValue>) -> bool`
  - `BRIDGE_PROTOCOL_VERSION: u32 = 1`, `DISCOVERY_FILE_NAME: &str = "cli_bridge.json"`
  - `struct CliBridgeDiscoveryFile { bridge_protocol_version: u32, port: u16, pid: u32, token: String, app_version: String, started_at: String }`
  - `write_discovery_file(&Path, &CliBridgeDiscoveryFile) -> AnyhowResult<PathBuf>`
  - `remove_discovery_file_if_owned(&Path, pid: u32, token_hex: &str) -> AnyhowResult<bool>`
  - `bind_and_publish(state_dir: &Path, token: &CliBridgeToken, app_version: &str) -> AnyhowResult<(TcpListener, CliBridgeDiscoveryFile)>`

- [ ] **Step 1: Add the dependencies**

In `crates/desktop/artcraft/Cargo.toml`, insert after line 54 (`anyhow.workspace = true`):
```toml
axum = { version = "0.8", default-features = false, features = ["http1", "json", "tokio"] }
```
Insert after `serde_json.workspace = true`:
```toml
subtle = "2.5"
```
Replace the tokio line (`tokio = { version = "1.42", features = ["rt", "rt-multi-thread", "fs"] }`) with:
```toml
tokio = { version = "1.42", features = ["rt", "rt-multi-thread", "fs", "net", "time", "sync", "macros"] }
```

- [ ] **Step 2: Declare the module**

In `crates/desktop/artcraft/src/core/mod.rs`, insert `pub mod cli_bridge;` after `pub mod artcraft_error;`.

Create `crates/desktop/artcraft/src/core/cli_bridge/mod.rs`:
```rust
pub mod cli_bridge_discovery_file;
pub mod cli_bridge_server;
pub mod cli_bridge_token;
```

- [ ] **Step 3: Write the failing tests**

Create `crates/desktop/artcraft/src/core/cli_bridge/cli_bridge_token.rs` containing only:
```rust
#[cfg(test)]
mod tests {
  use super::*;

  #[test]
  fn each_launch_gets_a_fresh_256_bit_token() {
    let first = CliBridgeToken::generate().unwrap();
    let second = CliBridgeToken::generate().unwrap();

    assert_eq!(first.as_hex().len(), 64);
    assert!(first.as_hex().chars().all(|c| c.is_ascii_digit() || ('a'..='f').contains(&c)));
    assert_ne!(first.as_hex(), second.as_hex());
  }

  #[test]
  fn debug_output_never_contains_token() {
    let token = CliBridgeToken::generate().unwrap();

    let debug = format!("{:?}", token);

    assert!(!debug.contains(token.as_hex()));
    assert_eq!(debug, "CliBridgeToken(<redacted>)");
  }
}
```

Create `crates/desktop/artcraft/src/core/cli_bridge/cli_bridge_discovery_file.rs` containing only:
```rust
#[cfg(test)]
mod tests {
  use super::*;

  const OUR_PID: u32 = 4242;
  const OUR_TOKEN: &str = "aaaa";

  #[test]
  fn exit_cleanup_only_removes_this_processes_file() {
    let dir = tempfile::tempdir().unwrap();
    write_discovery_file(dir.path(), &sample_file(OUR_PID, OUR_TOKEN)).unwrap();
    let path = dir.path().join(DISCOVERY_FILE_NAME);

    // A different launch (other pid or token) must leave our file alone.
    assert!(!remove_discovery_file_if_owned(dir.path(), 9999, OUR_TOKEN).unwrap());
    assert!(!remove_discovery_file_if_owned(dir.path(), OUR_PID, "bbbb").unwrap());
    assert!(path.exists());

    assert!(remove_discovery_file_if_owned(dir.path(), OUR_PID, OUR_TOKEN).unwrap());
    assert!(!path.exists());

    // Already gone: nothing to do, and no error.
    assert!(!remove_discovery_file_if_owned(dir.path(), OUR_PID, OUR_TOKEN).unwrap());
  }

  fn sample_file(pid: u32, token: &str) -> CliBridgeDiscoveryFile {
    CliBridgeDiscoveryFile {
      bridge_protocol_version: BRIDGE_PROTOCOL_VERSION,
      port: 53817,
      pid,
      token: token.to_string(),
      app_version: "0.41.0".to_string(),
      started_at: "2026-10-09T15:04:05Z".to_string(),
    }
  }
}
```

Create `crates/desktop/artcraft/src/core/cli_bridge/cli_bridge_server.rs` containing only:
```rust
#[cfg(test)]
mod tests {
  use super::*;
  use crate::core::cli_bridge::cli_bridge_discovery_file::DISCOVERY_FILE_NAME;
  use serde_json::Value;
  use std::fs;
  use std::net::TcpStream;

  #[cfg(unix)]
  #[tokio::test]
  async fn discovery_file_is_owner_only_and_written_after_bind() {
    use std::os::unix::fs::PermissionsExt;
    let dir = tempfile::tempdir().unwrap();
    let token = CliBridgeToken::generate().unwrap();

    let (listener, published) = bind_and_publish(dir.path(), &token, "0.41.0").await.unwrap();

    let path = dir.path().join(DISCOVERY_FILE_NAME);
    assert_eq!(fs::metadata(&path).unwrap().permissions().mode() & 0o777, 0o600);
    let on_disk: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
    let keys: Vec<&str> = on_disk.as_object().unwrap().keys().map(String::as_str).collect();
    assert_eq!(keys, vec!["app_version", "bridge_protocol_version", "pid", "port", "started_at", "token"]);
    assert_eq!(on_disk["token"], token.as_hex());
    assert_eq!(on_disk["port"], published.port);
    // The advertised port is already accepting connections when the file appears.
    assert_eq!(listener.local_addr().unwrap().port(), published.port);
    TcpStream::connect(("127.0.0.1", published.port)).unwrap();
  }
}
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `SQLX_OFFLINE=true cargo test -p artcraft --lib cli_bridge`
Expected: FAIL to compile with `cannot find type CliBridgeToken`, `cannot find function write_discovery_file` and `cannot find function bind_and_publish`.

- [ ] **Step 5: Implement the token**

Insert above `#[cfg(test)]` in `cli_bridge_token.rs`:
```rust
use anyhow::anyhow;
use axum::http::HeaderValue;
use errors::AnyhowResult;
use rand::rngs::OsRng;
use rand::TryRngCore;
use std::fmt;
use subtle::ConstantTimeEq;

const TOKEN_BYTES: usize = 32;
const BEARER_PREFIX: &str = "Bearer ";

/// Per-launch secret every bridge request presents as `Authorization: Bearer <hex>`.
/// Never logged: `Debug` is redacted and there is no `Display`.
#[derive(Clone)]
pub struct CliBridgeToken {
  hex: String,
}

impl CliBridgeToken {
  pub fn generate() -> AnyhowResult<Self> {
    let mut bytes = [0u8; TOKEN_BYTES];
    OsRng.try_fill_bytes(&mut bytes).map_err(|err| anyhow!("OS RNG failed: {}", err))?;
    Ok(Self { hex: to_lower_hex(&bytes) })
  }

  pub fn as_hex(&self) -> &str {
    &self.hex
  }

  /// Constant-time comparison of an `Authorization` header against this token.
  pub fn matches_bearer_header(&self, maybe_header: Option<&HeaderValue>) -> bool {
    let Some(value) = maybe_header.and_then(|header| header.to_str().ok()) else {
      return false;
    };
    let Some(provided) = value.strip_prefix(BEARER_PREFIX) else {
      return false;
    };
    provided.as_bytes().ct_eq(self.hex.as_bytes()).into()
  }
}

impl fmt::Debug for CliBridgeToken {
  fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
    write!(f, "CliBridgeToken(<redacted>)")
  }
}

fn to_lower_hex(bytes: &[u8]) -> String {
  bytes.iter().map(|byte| format!("{:02x}", byte)).collect()
}

```

- [ ] **Step 6: Implement the discovery file**

Insert above `#[cfg(test)]` in `cli_bridge_discovery_file.rs`:
```rust
use errors::AnyhowResult;
use serde_derive::{Deserialize, Serialize};
use std::fs;
use std::io::{ErrorKind, Write};
use std::path::{Path, PathBuf};
use tempfile::NamedTempFile;

pub const BRIDGE_PROTOCOL_VERSION: u32 = 1;
pub const DISCOVERY_FILE_NAME: &str = "cli_bridge.json";

/// How the CLI finds the bridge: `~/Artcraft/state/cli_bridge.json` (spec §4.3).
/// Deliberately not `Debug`: it holds the bearer token.
#[derive(Serialize, Deserialize)]
pub struct CliBridgeDiscoveryFile {
  pub bridge_protocol_version: u32,
  pub port: u16,
  pub pid: u32,
  pub token: String,
  pub app_version: String,
  pub started_at: String,
}

/// Atomically writes the discovery file with owner-only (0600) permissions.
pub fn write_discovery_file(state_dir: &Path, file: &CliBridgeDiscoveryFile) -> AnyhowResult<PathBuf> {
  let path = state_dir.join(DISCOVERY_FILE_NAME);
  let mut temp_file = NamedTempFile::new_in(state_dir)?;
  temp_file.write_all(&serde_json::to_vec(file)?)?;
  set_owner_only(temp_file.path())?;
  temp_file.persist(&path)?;
  Ok(path)
}

/// Removes the discovery file only while it still describes this process (same pid and token),
/// so an exiting app never deletes the file of a newer launch.
pub fn remove_discovery_file_if_owned(state_dir: &Path, pid: u32, token_hex: &str) -> AnyhowResult<bool> {
  let path = state_dir.join(DISCOVERY_FILE_NAME);
  let contents = match fs::read(&path) {
    Ok(contents) => contents,
    Err(err) if err.kind() == ErrorKind::NotFound => return Ok(false),
    Err(err) => return Err(err.into()),
  };
  let Ok(file) = serde_json::from_slice::<CliBridgeDiscoveryFile>(&contents) else {
    return Ok(false);
  };
  if file.pid != pid || file.token != token_hex {
    return Ok(false);
  }
  fs::remove_file(&path)?;
  Ok(true)
}

#[cfg(unix)]
fn set_owner_only(path: &Path) -> AnyhowResult<()> {
  use std::os::unix::fs::PermissionsExt;
  fs::set_permissions(path, fs::Permissions::from_mode(0o600))?;
  Ok(())
}

#[cfg(not(unix))]
fn set_owner_only(_path: &Path) -> AnyhowResult<()> {
  Ok(())
}

```

- [ ] **Step 7: Implement bind-and-publish**

Insert above `#[cfg(test)]` in `cli_bridge_server.rs`:
```rust
use crate::core::cli_bridge::cli_bridge_discovery_file::{write_discovery_file, CliBridgeDiscoveryFile, BRIDGE_PROTOCOL_VERSION};
use crate::core::cli_bridge::cli_bridge_token::CliBridgeToken;
use chrono::{SecondsFormat, Utc};
use errors::AnyhowResult;
use std::net::Ipv4Addr;
use std::path::Path;
use tokio::net::TcpListener;

/// Binds an ephemeral IPv4 loopback port, then publishes the discovery file.
/// The file is only written once the port is listening, so the CLI never sees a dead port.
pub async fn bind_and_publish(
  state_dir: &Path,
  token: &CliBridgeToken,
  app_version: &str,
) -> AnyhowResult<(TcpListener, CliBridgeDiscoveryFile)> {
  let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).await?;
  let file = CliBridgeDiscoveryFile {
    bridge_protocol_version: BRIDGE_PROTOCOL_VERSION,
    port: listener.local_addr()?.port(),
    pid: std::process::id(),
    token: token.as_hex().to_string(),
    app_version: app_version.to_string(),
    started_at: Utc::now().to_rfc3339_opts(SecondsFormat::Secs, true),
  };
  write_discovery_file(state_dir, &file)?;
  Ok((listener, file))
}

```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `SQLX_OFFLINE=true cargo test -p artcraft --lib cli_bridge`
Expected: PASS, `4 passed`. The tests are `each_launch_gets_a_fresh_256_bit_token`, `debug_output_never_contains_token`, `exit_cleanup_only_removes_this_processes_file` and `discovery_file_is_owner_only_and_written_after_bind`.

- [ ] **Step 9: Commit**

```bash
git add Cargo.lock crates/desktop/artcraft/Cargo.toml crates/desktop/artcraft/src/core/mod.rs crates/desktop/artcraft/src/core/cli_bridge/mod.rs crates/desktop/artcraft/src/core/cli_bridge/cli_bridge_token.rs crates/desktop/artcraft/src/core/cli_bridge/cli_bridge_discovery_file.rs crates/desktop/artcraft/src/core/cli_bridge/cli_bridge_server.rs
git commit -m "feat(cli-bridge): add bridge token, discovery file and loopback bind"
```

### Task 3: Envelope, gate and router

**Files:**
- Modify: `crates/desktop/artcraft/src/core/cli_bridge/mod.rs`
- Create: `crates/desktop/artcraft/src/core/cli_bridge/cli_bridge_envelope.rs`
- Create: `crates/desktop/artcraft/src/core/cli_bridge/cli_bridge_gate.rs`
- Create: `crates/desktop/artcraft/src/core/cli_bridge/op_dispatch.rs` (allowlist only; T7 adds dispatch)
- Test: bottom `mod tests` of `cli_bridge_gate.rs`

**Interfaces:**
- Consumes (T2): `CliBridgeToken`, `BRIDGE_PROTOCOL_VERSION`.
- Produces:
  - `enum BridgeErrorCode`, 31 variants:
    - `to_str(&self) -> &'static str`
    - `http_status(&self) -> u16`
    - `Display`, `Debug`, `PartialEq`, `Copy`
  - `struct BridgeError { code: BridgeErrorCode, message: String, maybe_details: Option<Value> }`
    - `BridgeError::new(code, impl Into<String>)`
    - `.with_details(Value)`
    - `.to_envelope() -> Value`
  - `success_envelope(Value) -> Value`
  - Constants: `MAX_IN_FLIGHT = 8`, `MAX_UPLOAD_DECODED_BYTES = 20_971_520`, `MAX_ARGS_BYTES = 1_048_576`, `MAX_BODY_BYTES = 29_010_604`
  - `type DispatchFn = Arc<dyn Fn(String, Value) -> BoxFuture<'static, Result<Value, BridgeError>> + Send + Sync>`
  - `type ReadinessFn = Arc<dyn Fn() -> Readiness + Send + Sync>`
  - `struct GateState { port: u16, token: CliBridgeToken, in_flight: Arc<Semaphore>, health: HealthInfo, readiness: ReadinessFn }`
  - `struct HealthInfo { app_version: String, pid: u32, started_at: String }`
  - `struct Readiness { credentials_synced: bool, session_cookie_present: bool }`
  - `build_router(GateState, DispatchFn) -> Router`
  - `ALLOWED_OPS: &[&str]`

- [ ] **Step 1: Declare the new modules**

Replace `crates/desktop/artcraft/src/core/cli_bridge/mod.rs` with:
```rust
pub mod cli_bridge_discovery_file;
pub mod cli_bridge_envelope;
pub mod cli_bridge_gate;
pub mod cli_bridge_server;
pub mod cli_bridge_token;
pub mod op_dispatch;
```

- [ ] **Step 2: Write the envelope and the M1 allowlist**

The envelope has no tests of its own; the gate tests below exercise every path through it.

Create `crates/desktop/artcraft/src/core/cli_bridge/cli_bridge_envelope.rs`:
```rust
use serde_json::{json, Map, Value};
use std::fmt;

/// Every stable error code the bridge can put on the wire (spec §5.6).
/// Codes never change meaning; new ones need no protocol bump (spec §5.3).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BridgeErrorCode {
  InvalidRequest,
  Unauthorized,
  ForbiddenHost,
  ForbiddenOrigin,
  NotFound,
  MethodNotAllowed,
  PayloadTooLarge,
  UnsupportedMediaType,
  InternalError,
  BridgeBusy,
  UnknownOp,
  InvalidArgs,
  ArgsTooLarge,
  UnsupportedRoute,
  OperationInProgress,
  CredentialsNotSynced,
  NotLoggedIn,
  CostExceedsLimit,
  EstimateUnavailable,
  InsufficientCredits,
  RateLimited,
  UpstreamBadInput,
  UpstreamUnavailable,
  UpstreamError,
  OutcomeUnknown,
  JobNotFound,
  JobNotTerminal,
  MediaNotFound,
  UploadTypeUnsupported,
  SettingNotWritable,
  LocalStoreError,
}

/// A failed request or op. Rendered as `{"ok": false, "error": {code, message, details?}}`.
#[derive(Clone, Debug)]
pub struct BridgeError {
  pub code: BridgeErrorCode,
  pub message: String,
  pub maybe_details: Option<Value>,
}

impl BridgeErrorCode {
  pub const fn to_str(&self) -> &'static str {
    match self {
      Self::InvalidRequest => "invalid_request",
      Self::Unauthorized => "unauthorized",
      Self::ForbiddenHost => "forbidden_host",
      Self::ForbiddenOrigin => "forbidden_origin",
      Self::NotFound => "not_found",
      Self::MethodNotAllowed => "method_not_allowed",
      Self::PayloadTooLarge => "payload_too_large",
      Self::UnsupportedMediaType => "unsupported_media_type",
      Self::InternalError => "internal_error",
      Self::BridgeBusy => "bridge_busy",
      Self::UnknownOp => "unknown_op",
      Self::InvalidArgs => "invalid_args",
      Self::ArgsTooLarge => "args_too_large",
      Self::UnsupportedRoute => "unsupported_route",
      Self::OperationInProgress => "operation_in_progress",
      Self::CredentialsNotSynced => "credentials_not_synced",
      Self::NotLoggedIn => "not_logged_in",
      Self::CostExceedsLimit => "cost_exceeds_limit",
      Self::EstimateUnavailable => "estimate_unavailable",
      Self::InsufficientCredits => "insufficient_credits",
      Self::RateLimited => "rate_limited",
      Self::UpstreamBadInput => "upstream_bad_input",
      Self::UpstreamUnavailable => "upstream_unavailable",
      Self::UpstreamError => "upstream_error",
      Self::OutcomeUnknown => "outcome_unknown",
      Self::JobNotFound => "job_not_found",
      Self::JobNotTerminal => "job_not_terminal",
      Self::MediaNotFound => "media_not_found",
      Self::UploadTypeUnsupported => "upload_type_unsupported",
      Self::SettingNotWritable => "setting_not_writable",
      Self::LocalStoreError => "local_store_error",
    }
  }

  /// Non-2xx only when the request never reached an op handler, or the bridge itself failed (spec §5.2).
  pub const fn http_status(&self) -> u16 {
    match self {
      Self::InvalidRequest => 400,
      Self::Unauthorized => 401,
      Self::ForbiddenHost | Self::ForbiddenOrigin => 403,
      Self::NotFound => 404,
      Self::MethodNotAllowed => 405,
      Self::PayloadTooLarge => 413,
      Self::UnsupportedMediaType => 415,
      Self::InternalError => 500,
      Self::BridgeBusy => 503,
      _ => 200,
    }
  }
}

impl fmt::Display for BridgeErrorCode {
  fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
    write!(f, "{}", self.to_str())
  }
}

impl BridgeError {
  pub fn new(code: BridgeErrorCode, message: impl Into<String>) -> Self {
    Self {
      code,
      message: message.into(),
      maybe_details: None,
    }
  }

  pub fn with_details(mut self, details: Value) -> Self {
    self.maybe_details = Some(details);
    self
  }

  pub fn to_envelope(&self) -> Value {
    let mut error = Map::new();
    error.insert("code".to_string(), json!(self.code.to_str()));
    error.insert("message".to_string(), json!(self.message));
    if let Some(details) = &self.maybe_details {
      error.insert("details".to_string(), details.clone());
    }
    json!({ "ok": false, "error": Value::Object(error) })
  }
}

impl fmt::Display for BridgeError {
  fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
    write!(f, "{:?}", self)
  }
}

impl std::error::Error for BridgeError {}

pub fn success_envelope(data: Value) -> Value {
  json!({ "ok": true, "data": data })
}
```

Create `crates/desktop/artcraft/src/core/cli_bridge/op_dispatch.rs`:
```rust
/// The op allowlist, in spec §5.4 order. `GET /v1/health` reports it; the RPC handler refuses anything else with `unknown_op`.
pub const ALLOWED_OPS: &[&str] = &[
  "app.info",
  "account.session",
  "models.list",
  "generate.estimate",
  "jobs.list",
];
```

- [ ] **Step 3: Write the failing gate tests**

Create `crates/desktop/artcraft/src/core/cli_bridge/cli_bridge_gate.rs` containing only:
```rust
#[cfg(test)]
mod tests {
  use super::*;
  use std::io::{Read, Write};
  use std::net::TcpStream;
  use std::sync::atomic::{AtomicUsize, Ordering};
  use tokio::net::TcpListener;
  use tokio::sync::Notify;

  const IDEMPOTENCY_TOKEN: &str = "00000000-0000-4000-8000-000000000000";

  #[tokio::test]
  async fn dns_rebound_host_is_rejected_before_token_check() {
    let bridge = start_bridge(MAX_IN_FLIGHT, echo_dispatch()).await;

    // No Authorization header at all: the Host check must answer first.
    let response = send(bridge.port, http_request("GET", HEALTH_PATH, &[("Host", format!("evil.test:{}", bridge.port))], "")).await;

    assert_error(&response, 403, "forbidden_host");
  }

  #[tokio::test]
  async fn lookalike_localhost_hosts_are_rejected() {
    let bridge = start_bridge(MAX_IN_FLIGHT, echo_dispatch()).await;
    let port = bridge.port;
    let lookalikes = [
      format!("localhost.evil.test:{port}"),
      format!("127.0.0.1.nip.io:{port}"),
      format!("localhost:{port}.evil.test"),
      "localhost".to_string(),
      format!("127.0.0.1:{}", port.wrapping_add(1)),
    ];

    for host in lookalikes {
      let response = send(bridge.port, http_request("GET", HEALTH_PATH, &[("Host", host.clone()), bridge.auth()], "")).await;
      assert_error(&response, 403, "forbidden_host");
    }
  }

  #[tokio::test]
  async fn all_three_loopback_host_spellings_are_accepted() {
    let bridge = start_bridge(MAX_IN_FLIGHT, echo_dispatch()).await;
    let port = bridge.port;

    for host in [format!("127.0.0.1:{port}"), format!("localhost:{port}"), format!("[::1]:{port}")] {
      let response = send(bridge.port, http_request("GET", HEALTH_PATH, &[("Host", host), bridge.auth()], "")).await;
      assert_eq!(response.status, 200);
      assert_eq!(response.body["data"]["bridge_protocol_version"], 1);
    }
  }

  #[tokio::test]
  async fn any_origin_or_fetch_metadata_header_is_rejected_even_with_valid_token() {
    let bridge = start_bridge(MAX_IN_FLIGHT, echo_dispatch()).await;
    let browser_headers = [
      ("Origin", format!("http://127.0.0.1:{}", bridge.port)),
      ("Sec-Fetch-Site", "same-origin".to_string()),
      ("Sec-Fetch-Mode", "cors".to_string()),
    ];

    for header in browser_headers {
      let mut headers = bridge.json_headers();
      headers.push(header);
      let response = send(bridge.port, http_request("POST", RPC_PATH, &headers, r#"{"op":"app.info","args":{}}"#)).await;
      assert_error(&response, 403, "forbidden_origin");
    }
    assert_eq!(bridge.calls(), 0);
  }

  #[tokio::test]
  async fn wrong_token_is_401_and_never_echoed() {
    let bridge = start_bridge(MAX_IN_FLIGHT, echo_dispatch()).await;
    let wrong_token = "f".repeat(64);
    let headers = [bridge.host(), ("Authorization", format!("Bearer {wrong_token}"))];

    let wrong = send(bridge.port, http_request("GET", HEALTH_PATH, &headers, "")).await;
    let missing = send(bridge.port, http_request("GET", HEALTH_PATH, &[bridge.host()], "")).await;

    assert_error(&wrong, 401, "unauthorized");
    assert_error(&missing, 401, "unauthorized");
    assert!(!wrong.raw.contains(&wrong_token));
    assert!(!wrong.raw.contains(&bridge.token));
    assert!(!missing.raw.contains(&bridge.token));
  }

  #[tokio::test]
  async fn form_posts_from_web_pages_get_415() {
    let bridge = start_bridge(MAX_IN_FLIGHT, echo_dispatch()).await;

    for content_type in ["application/x-www-form-urlencoded", "text/plain", "multipart/form-data; boundary=x"] {
      let headers = [bridge.host(), bridge.auth(), ("Content-Type", content_type.to_string())];
      let response = send(bridge.port, http_request("POST", RPC_PATH, &headers, "op=app.info")).await;
      assert_error(&response, 415, "unsupported_media_type");
    }
    assert_eq!(bridge.calls(), 0);
  }

  #[tokio::test]
  async fn options_preflight_never_succeeds_and_sends_no_cors_headers() {
    let bridge = start_bridge(MAX_IN_FLIGHT, echo_dispatch()).await;
    let preflight = [
      bridge.host(),
      ("Origin", "https://evil.test".to_string()),
      ("Access-Control-Request-Method", "POST".to_string()),
    ];

    let with_origin = send(bridge.port, http_request("OPTIONS", RPC_PATH, &preflight, "")).await;
    let without_origin = send(bridge.port, http_request("OPTIONS", RPC_PATH, &[bridge.host(), bridge.auth()], "")).await;

    assert_error(&with_origin, 403, "forbidden_origin");
    assert_error(&without_origin, 405, "method_not_allowed");
    assert!(!with_origin.head.contains("access-control-"));
    assert!(!without_origin.head.contains("access-control-"));
  }

  #[tokio::test]
  async fn unknown_ops_never_reach_dispatch() {
    let bridge = start_bridge(MAX_IN_FLIGHT, echo_dispatch()).await;
    let not_ops = ["tasks_nuke_all_command", "provider_list_command", "load_without_cors_command", "app.nope", ""];

    for op in not_ops {
      let body = json!({ "op": op, "args": {} }).to_string();
      let response = send(bridge.port, http_request("POST", RPC_PATH, &bridge.json_headers(), &body)).await;
      assert_error(&response, 200, "unknown_op");
    }
    assert_eq!(bridge.calls(), 0);
  }

  #[tokio::test]
  async fn excess_in_flight_requests_get_503_bridge_busy() {
    let entered = Arc::new(Notify::new());
    let release = Arc::new(Notify::new());
    let bridge = start_bridge(1, blocking_dispatch(entered.clone(), release.clone())).await;
    let request = http_request("POST", RPC_PATH, &bridge.json_headers(), r#"{"op":"app.info","args":{}}"#);

    let first = tokio::spawn(send(bridge.port, request.clone()));
    entered.notified().await;
    let second = send(bridge.port, request).await;
    release.notify_one();
    let first = first.await.unwrap();

    assert_error(&second, 503, "bridge_busy");
    assert_eq!(first.status, 200);
    assert_eq!(first.body["ok"], true);
  }

  #[tokio::test]
  async fn op_errors_return_http_200_with_ok_false() {
    let bridge = start_bridge(MAX_IN_FLIGHT, failing_dispatch(BridgeErrorCode::NotLoggedIn)).await;

    let response = send(bridge.port, http_request("POST", RPC_PATH, &bridge.json_headers(), r#"{"op":"app.info","args":{}}"#)).await;

    assert_error(&response, 200, "not_logged_in");
  }

  #[tokio::test]
  async fn every_gate_rejection_is_a_json_envelope() {
    let bridge = start_bridge(MAX_IN_FLIGHT, echo_dispatch()).await;
    let port = bridge.port;
    let envelope = r#"{"op":"app.info","args":{}}"#;
    let cases = [
      (http_request("GET", HEALTH_PATH, &[("Host", format!("evil.test:{port}")), bridge.auth()], ""), 403, "forbidden_host"),
      (http_request("POST", RPC_PATH, &[bridge.host(), bridge.auth(), ("Origin", "https://evil.test".to_string())], envelope), 403, "forbidden_origin"),
      (http_request("GET", "/v2/anything", &[bridge.host(), bridge.auth()], ""), 404, "not_found"),
      (http_request("GET", RPC_PATH, &[bridge.host(), bridge.auth()], ""), 405, "method_not_allowed"),
      (http_request("GET", HEALTH_PATH, &[bridge.host()], ""), 401, "unauthorized"),
      (http_request("POST", RPC_PATH, &[bridge.host(), bridge.auth(), ("Content-Type", "text/plain".to_string())], envelope), 415, "unsupported_media_type"),
      (http_request("POST", RPC_PATH, &bridge.json_headers(), "{not json"), 400, "invalid_request"),
      (http_request("POST", RPC_PATH, &bridge.json_headers(), r#"{"op":"app.info","args":[]}"#), 400, "invalid_request"),
      (headers_only_post(&bridge, MAX_BODY_BYTES + 1), 413, "payload_too_large"),
    ];

    for (request, status, code) in cases {
      let response = send(bridge.port, request).await;
      assert!(response.head.contains("content-type: application/json"), "{code} has no JSON content type");
      assert_error(&response, status, code);
    }
  }

  #[tokio::test]
  async fn largest_allowed_upload_fits_under_the_body_cap() {
    assert_eq!(4 * MAX_UPLOAD_DECODED_BYTES.div_ceil(3) + MAX_ARGS_BYTES, MAX_BODY_BYTES);
    let bridge = start_bridge(MAX_IN_FLIGHT, echo_dispatch()).await;

    let largest = send(bridge.port, http_request("POST", RPC_PATH, &bridge.json_headers(), &upload_body_of_len(MAX_BODY_BYTES))).await;
    let too_large = send(bridge.port, headers_only_post(&bridge, MAX_BODY_BYTES + 1)).await;

    assert_eq!(largest.status, 200);
    assert_ne!(largest.body["error"]["code"], "payload_too_large");
    assert_error(&too_large, 413, "payload_too_large");
  }

  #[tokio::test]
  async fn non_upload_ops_over_1mib_get_args_too_large() {
    let bridge = start_bridge(MAX_IN_FLIGHT, echo_dispatch()).await;
    let body = json!({ "op": "app.info", "args": { "pad": "x".repeat(MAX_ARGS_BYTES) } }).to_string();

    let response = send(bridge.port, http_request("POST", RPC_PATH, &bridge.json_headers(), &body)).await;

    assert_error(&response, 200, "args_too_large");
    assert_eq!(bridge.calls(), 0);
  }

  struct TestBridge {
    port: u16,
    token: String,
    calls: Arc<AtomicUsize>,
  }

  impl TestBridge {
    fn calls(&self) -> usize {
      self.calls.load(Ordering::SeqCst)
    }

    fn host(&self) -> (&'static str, String) {
      ("Host", format!("127.0.0.1:{}", self.port))
    }

    fn auth(&self) -> (&'static str, String) {
      ("Authorization", format!("Bearer {}", self.token))
    }

    fn json_headers(&self) -> Vec<(&'static str, String)> {
      vec![self.host(), self.auth(), ("Content-Type", "application/json".to_string())]
    }
  }

  struct RawResponse {
    status: u16,
    head: String,
    body: Value,
    raw: String,
  }

  type StubFactory = Box<dyn FnOnce(Arc<AtomicUsize>) -> DispatchFn>;

  async fn start_bridge(max_in_flight: usize, make_dispatch: StubFactory) -> TestBridge {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let port = listener.local_addr().unwrap().port();
    let token = CliBridgeToken::generate().unwrap();
    let calls = Arc::new(AtomicUsize::new(0));
    let gate = GateState {
      port,
      token: token.clone(),
      in_flight: Arc::new(Semaphore::new(max_in_flight)),
      health: HealthInfo {
        app_version: "0.41.0".to_string(),
        pid: 4242,
        started_at: "2026-10-09T15:04:05Z".to_string(),
      },
      readiness: Arc::new(|| Readiness { credentials_synced: true, session_cookie_present: true }),
    };
    let router = build_router(gate, make_dispatch(calls.clone()));
    tokio::spawn(async move { axum::serve(listener, router).await });
    TestBridge { port, token: token.as_hex().to_string(), calls }
  }

  fn echo_dispatch() -> StubFactory {
    Box::new(|calls| {
      Arc::new(move |op: String, _args: Value| {
        calls.fetch_add(1, Ordering::SeqCst);
        let reply: BoxFuture<'static, Result<Value, BridgeError>> = Box::pin(async move { Ok(json!({ "op": op })) });
        reply
      })
    })
  }

  fn failing_dispatch(code: BridgeErrorCode) -> StubFactory {
    Box::new(move |calls| {
      Arc::new(move |_op: String, _args: Value| {
        calls.fetch_add(1, Ordering::SeqCst);
        let reply: BoxFuture<'static, Result<Value, BridgeError>> = Box::pin(async move { Err(BridgeError::new(code, "stub failure")) });
        reply
      })
    })
  }

  fn blocking_dispatch(entered: Arc<Notify>, release: Arc<Notify>) -> StubFactory {
    Box::new(move |calls| {
      Arc::new(move |op: String, _args: Value| {
        calls.fetch_add(1, Ordering::SeqCst);
        let entered = entered.clone();
        let release = release.clone();
        let reply: BoxFuture<'static, Result<Value, BridgeError>> = Box::pin(async move {
          entered.notify_one();
          release.notified().await;
          Ok(json!({ "op": op }))
        });
        reply
      })
    })
  }

  fn http_request(method: &str, path: &str, headers: &[(&str, String)], body: &str) -> String {
    let mut request = format!("{method} {path} HTTP/1.1\r\n");
    for (name, value) in headers {
      request.push_str(&format!("{name}: {value}\r\n"));
    }
    request.push_str(&format!("Content-Length: {}\r\nConnection: close\r\n\r\n{body}", body.len()));
    request
  }

  /// Declares an oversized body but sends none, so the server can answer without draining it.
  fn headers_only_post(bridge: &TestBridge, content_length: usize) -> String {
    let mut request = format!("POST {RPC_PATH} HTTP/1.1\r\n");
    for (name, value) in bridge.json_headers() {
      request.push_str(&format!("{name}: {value}\r\n"));
    }
    request.push_str(&format!("Content-Length: {content_length}\r\nConnection: close\r\n\r\n"));
    request
  }

  fn upload_body_of_len(total_len: usize) -> String {
    let prefix = r#"{"op":"media.upload","args":{"content_base64":""#;
    let suffix = format!(r#"","idempotency_token":"{IDEMPOTENCY_TOKEN}"}}}}"#);
    let padding = "A".repeat(total_len - prefix.len() - suffix.len());
    format!("{prefix}{padding}{suffix}")
  }

  async fn send(port: u16, request: String) -> RawResponse {
    tokio::task::spawn_blocking(move || send_blocking(port, &request)).await.unwrap()
  }

  fn send_blocking(port: u16, request: &str) -> RawResponse {
    let mut stream = TcpStream::connect(("127.0.0.1", port)).unwrap();
    stream.write_all(request.as_bytes()).unwrap();
    let mut raw = Vec::new();
    stream.read_to_end(&mut raw).unwrap();
    let raw = String::from_utf8_lossy(&raw).to_string();
    let (head, body) = raw.split_once("\r\n\r\n").unwrap();
    RawResponse {
      status: head.split(' ').nth(1).unwrap().parse().unwrap(),
      head: head.to_ascii_lowercase(),
      body: serde_json::from_str(body).unwrap_or(Value::Null),
      raw: raw.clone(),
    }
  }

  fn assert_error(response: &RawResponse, status: u16, code: &str) {
    assert_eq!(response.status, status, "unexpected status for {code}: {}", response.raw);
    assert_eq!(response.body["ok"], false);
    assert_eq!(response.body["error"]["code"], code);
  }
}
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `SQLX_OFFLINE=true cargo test -p artcraft --lib cli_bridge_gate`
Expected: FAIL to compile with `cannot find function build_router`, `cannot find struct GateState`, and the same for `HEALTH_PATH`.

- [ ] **Step 5: Implement the gate**

Insert above `#[cfg(test)]` in `cli_bridge_gate.rs`:
```rust
use crate::core::cli_bridge::cli_bridge_discovery_file::BRIDGE_PROTOCOL_VERSION;
use crate::core::cli_bridge::cli_bridge_envelope::{success_envelope, BridgeError, BridgeErrorCode};
use crate::core::cli_bridge::cli_bridge_token::CliBridgeToken;
use crate::core::cli_bridge::op_dispatch::ALLOWED_OPS;
use axum::body::Bytes;
use axum::extract::rejection::BytesRejection;
use axum::extract::{DefaultBodyLimit, Request, State};
use axum::http::header::{AUTHORIZATION, CONTENT_LENGTH, CONTENT_TYPE, HOST, ORIGIN};
use axum::http::{HeaderMap, Method, StatusCode};
use axum::middleware::{self, Next};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use futures::future::BoxFuture;
use log::info;
use serde_derive::Deserialize;
use serde_json::{json, Value};
use std::sync::Arc;
use std::time::Instant;
use tokio::sync::Semaphore;

pub const MAX_IN_FLIGHT: usize = 8;
pub const MAX_UPLOAD_DECODED_BYTES: usize = 20_971_520;
pub const MAX_ARGS_BYTES: usize = 1_048_576;
/// 20 MiB decoded upload × 4/3 for base64, plus 1 MiB envelope headroom (spec §4.4).
pub const MAX_BODY_BYTES: usize = 29_010_604;

const HEALTH_PATH: &str = "/v1/health";
const RPC_PATH: &str = "/v1/rpc";
const UPLOAD_OP: &str = "media.upload";
const FETCH_METADATA_HEADERS: [&str; 2] = ["sec-fetch-site", "sec-fetch-mode"];

/// Runs one allowlisted op. Production captures the `AppHandle`; tests pass a stub.
pub type DispatchFn = Arc<dyn Fn(String, Value) -> BoxFuture<'static, Result<Value, BridgeError>> + Send + Sync>;

/// Reads login readiness for `GET /v1/health` without a network call.
pub type ReadinessFn = Arc<dyn Fn() -> Readiness + Send + Sync>;

/// Everything the gate and the health handler need. Holds no `AppHandle`.
#[derive(Clone)]
pub struct GateState {
  pub port: u16,
  pub token: CliBridgeToken,
  pub in_flight: Arc<Semaphore>,
  pub health: HealthInfo,
  pub readiness: ReadinessFn,
}

#[derive(Clone)]
pub struct HealthInfo {
  pub app_version: String,
  pub pid: u32,
  pub started_at: String,
}

#[derive(Clone, Copy)]
pub struct Readiness {
  pub credentials_synced: bool,
  pub session_cookie_present: bool,
}

#[derive(Clone)]
struct RouterState {
  gate: GateState,
  dispatch: DispatchFn,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RpcRequest {
  op: String,
  args: Value,
}

struct DecodedRpc {
  op: String,
  args: Value,
  body_len: usize,
}

/// The whole HTTP surface: two routes behind one gate (spec §4.4).
pub fn build_router(gate_state: GateState, dispatch: DispatchFn) -> Router {
  let router_state = RouterState { gate: gate_state.clone(), dispatch };
  Router::new()
    .route(HEALTH_PATH, get(get_health_handler))
    .route(RPC_PATH, post(post_rpc_handler))
    .fallback(fallback_handler)
    .layer(DefaultBodyLimit::max(MAX_BODY_BYTES))
    .layer(middleware::from_fn_with_state(gate_state, gate_request))
    .with_state(router_state)
}

async fn gate_request(State(gate): State<GateState>, request: Request, next: Next) -> Response {
  if let Err(error) = check_request(&gate, request.method(), request.uri().path(), request.headers()) {
    info!("cli bridge rejected request: {}", error.code);
    return error_response(&error);
  }
  // The permit is held until the response is produced.
  let Ok(_permit) = gate.in_flight.clone().try_acquire_owned() else {
    return error_response(&BridgeError::new(BridgeErrorCode::BridgeBusy, "too many bridge requests are in flight"));
  };
  next.run(request).await
}

async fn get_health_handler(State(state): State<RouterState>) -> Response {
  let readiness = (state.gate.readiness)();
  success_response(json!({
    "bridge_protocol_version": BRIDGE_PROTOCOL_VERSION,
    "app_version": state.gate.health.app_version,
    "pid": state.gate.health.pid,
    "started_at": state.gate.health.started_at,
    "ops": ALLOWED_OPS,
    "readiness": {
      "credentials_synced": readiness.credentials_synced,
      "session_cookie_present": readiness.session_cookie_present,
    },
  }))
}

async fn post_rpc_handler(State(state): State<RouterState>, body: Result<Bytes, BytesRejection>) -> Response {
  let started_at = Instant::now();
  let request = match decode_rpc_request(body) {
    Ok(request) => request,
    Err(error) => return error_response(&error),
  };
  let op = request.op.clone();
  let result = run_rpc(&state.dispatch, request).await;
  let outcome = match &result {
    Ok(_) => "ok",
    Err(error) => error.code.to_str(),
  };
  info!("cli bridge op={} result={} duration_ms={}", op, outcome, started_at.elapsed().as_millis());
  match result {
    Ok(data) => success_response(data),
    Err(error) => error_response(&error),
  }
}

async fn fallback_handler() -> Response {
  error_response(&BridgeError::new(BridgeErrorCode::NotFound, "unknown path"))
}

fn check_request(gate: &GateState, method: &Method, path: &str, headers: &HeaderMap) -> Result<(), BridgeError> {
  check_host(headers, gate.port)?;
  check_browser_headers(headers)?;
  check_route(method, path)?;
  check_bearer(&gate.token, headers)?;
  if *method == Method::POST {
    check_content_type(headers)?;
    check_content_length(headers)?;
  }
  Ok(())
}

fn decode_rpc_request(body: Result<Bytes, BytesRejection>) -> Result<DecodedRpc, BridgeError> {
  let body = match body {
    Ok(body) => body,
    Err(rejection) if rejection.status() == StatusCode::PAYLOAD_TOO_LARGE => {
      return Err(BridgeError::new(BridgeErrorCode::PayloadTooLarge, "the request body exceeds the bridge limit"));
    },
    Err(_) => return Err(BridgeError::new(BridgeErrorCode::InvalidRequest, "the request body could not be read")),
  };
  let request: RpcRequest = serde_json::from_slice(&body)
    .map_err(|_| BridgeError::new(BridgeErrorCode::InvalidRequest, "the body is not a bridge envelope"))?;
  if !request.args.is_object() {
    return Err(BridgeError::new(BridgeErrorCode::InvalidRequest, "args must be a JSON object"));
  }
  Ok(DecodedRpc { op: request.op, args: request.args, body_len: body.len() })
}

async fn run_rpc(dispatch: &DispatchFn, request: DecodedRpc) -> Result<Value, BridgeError> {
  if !ALLOWED_OPS.contains(&request.op.as_str()) {
    return Err(BridgeError::new(BridgeErrorCode::UnknownOp, "this op is not available on the bridge"));
  }
  if request.op != UPLOAD_OP && request.body_len > MAX_ARGS_BYTES {
    return Err(BridgeError::new(BridgeErrorCode::ArgsTooLarge, "args are larger than 1 MiB"));
  }
  dispatch(request.op, request.args).await
}

/// Byte-exact loopback `Host`, so a DNS-rebound name never passes (spec §4.4 step 1).
fn check_host(headers: &HeaderMap, port: u16) -> Result<(), BridgeError> {
  let allowed = [format!("127.0.0.1:{port}"), format!("localhost:{port}"), format!("[::1]:{port}")];
  let is_loopback = headers
    .get(HOST)
    .is_some_and(|host| allowed.iter().any(|candidate| host.as_bytes() == candidate.as_bytes()));
  if is_loopback {
    Ok(())
  } else {
    Err(BridgeError::new(BridgeErrorCode::ForbiddenHost, "address the bridge as 127.0.0.1 with its port"))
  }
}

/// Browsers always send one of these; the CLI never does (spec §4.4 step 2).
fn check_browser_headers(headers: &HeaderMap) -> Result<(), BridgeError> {
  let from_browser = headers.contains_key(ORIGIN)
    || FETCH_METADATA_HEADERS.iter().any(|name| headers.contains_key(*name));
  if from_browser {
    Err(BridgeError::new(BridgeErrorCode::ForbiddenOrigin, "browsers cannot use the bridge"))
  } else {
    Ok(())
  }
}

fn check_route(method: &Method, path: &str) -> Result<(), BridgeError> {
  match (method, path) {
    (&Method::GET, HEALTH_PATH) | (&Method::POST, RPC_PATH) => Ok(()),
    (_, HEALTH_PATH) | (_, RPC_PATH) => Err(BridgeError::new(BridgeErrorCode::MethodNotAllowed, "method not allowed")),
    _ => Err(BridgeError::new(BridgeErrorCode::NotFound, "unknown path")),
  }
}

fn check_bearer(token: &CliBridgeToken, headers: &HeaderMap) -> Result<(), BridgeError> {
  if token.matches_bearer_header(headers.get(AUTHORIZATION)) {
    Ok(())
  } else {
    Err(BridgeError::new(BridgeErrorCode::Unauthorized, "missing or invalid bridge token"))
  }
}

fn check_content_type(headers: &HeaderMap) -> Result<(), BridgeError> {
  let is_json = headers
    .get(CONTENT_TYPE)
    .and_then(|value| value.to_str().ok())
    .and_then(|value| value.split(';').next())
    .is_some_and(|mime| mime.trim().eq_ignore_ascii_case("application/json"));
  if is_json {
    Ok(())
  } else {
    Err(BridgeError::new(BridgeErrorCode::UnsupportedMediaType, "POST bodies must be application/json"))
  }
}

/// Rejects an oversized declared body before any of it is read.
fn check_content_length(headers: &HeaderMap) -> Result<(), BridgeError> {
  let too_large = headers
    .get(CONTENT_LENGTH)
    .and_then(|value| value.to_str().ok())
    .and_then(|value| value.parse::<u64>().ok())
    .is_some_and(|length| length > MAX_BODY_BYTES as u64);
  if too_large {
    Err(BridgeError::new(BridgeErrorCode::PayloadTooLarge, "the request body exceeds the bridge limit"))
  } else {
    Ok(())
  }
}

fn success_response(data: Value) -> Response {
  (StatusCode::OK, Json(success_envelope(data))).into_response()
}

fn error_response(error: &BridgeError) -> Response {
  let status = StatusCode::from_u16(error.code.http_status()).unwrap_or(StatusCode::INTERNAL_SERVER_ERROR);
  (status, Json(error.to_envelope())).into_response()
}

```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `SQLX_OFFLINE=true cargo test -p artcraft --lib cli_bridge`
Expected: PASS, `17 passed`: the 13 gate tests plus the 4 from Task 2. `largest_allowed_upload_fits_under_the_body_cap` passes in M1 even though `media.upload` is not yet allowlisted. It asserts HTTP 200 and "not 413", and the op answers `unknown_op` until M3.

- [ ] **Step 7: Commit**

```bash
git add crates/desktop/artcraft/src/core/cli_bridge/mod.rs crates/desktop/artcraft/src/core/cli_bridge/cli_bridge_envelope.rs crates/desktop/artcraft/src/core/cli_bridge/cli_bridge_gate.rs crates/desktop/artcraft/src/core/cli_bridge/op_dispatch.rs
git commit -m "feat(cli-bridge): add loopback gate, JSON envelope and op allowlist"
```

### Task 4: Native result mapping and op support

**Files:**
- Modify: `crates/desktop/artcraft/src/core/cli_bridge/mod.rs`
- Create: `crates/desktop/artcraft/src/core/cli_bridge/native_result_mapping.rs`
- Create: `crates/desktop/artcraft/src/core/cli_bridge/ops/mod.rs`
- Create: `crates/desktop/artcraft/src/core/cli_bridge/ops/op_support.rs`
- Test: bottom `mod tests` of both new `.rs` files

**Interfaces:**
- Consumes (T3): `BridgeError`, `BridgeErrorCode`.
- Produces:
  - `enum OmniCallSite<'a> { Estimate, SubmitPost { idempotency_token: &'a str } }`
  - `enum StorytellerCallSite { MediaGet, Other }`
  - `map_omni_error(&CommandErrorResponseWrapper<String, ()>, OmniCallSite<'_>) -> BridgeError`
  - `map_storyteller_error(&StorytellerError, StorytellerCallSite) -> BridgeError`
  - `map_login_result(Result<Option<SessionUserInfo>, DesktopLoginError>) -> Result<Option<SessionUserInfo>, BridgeError>`
  - `outcome_unknown(idempotency_token: &str, reason: &str) -> BridgeError`
  - `upstream_error() -> BridgeError`
  - `#[derive(Clone)] struct OpContext { app: AppHandle, root: AppDataRoot, limits: OpLimits }` with `OpContext::new(AppHandle, AppDataRoot)`. T12 and T16 add fields.
  - `#[derive(Clone, Copy)] struct OpLimits { read_op_deadline, write_op_deadline, read_call_timeout, remote_jobs_timeout, upload_call_timeout, submit_hard_cap: Duration }` with `OpLimits::production()`.
  - `struct EmptyRequest {}`
  - `parse_args<T: DeserializeOwned>(Value) -> Result<T, BridgeError>`
  - `to_data<T: Serialize>(&T) -> Result<Value, BridgeError>`
  - `require_session(&AppHandle) -> Result<StorytellerCredentialSet, BridgeError>`
  - `task_database(&AppHandle) -> Result<TaskDatabase, BridgeError>`
  - `with_call_timeout<T>(Duration, impl Future<Output = T>) -> Result<T, BridgeError>`
  - `deadline_error() -> BridgeError`
  - `validate_id(field: &str, value: &str) -> Result<(), BridgeError>`
  - `validate_idempotency_token(&str) -> Result<(), BridgeError>`
  - `invalid_args(&str) -> BridgeError`, `local_store_error(&str) -> BridgeError`

- [ ] **Step 1: Declare the modules**

Replace `crates/desktop/artcraft/src/core/cli_bridge/mod.rs` with:
```rust
pub mod cli_bridge_discovery_file;
pub mod cli_bridge_envelope;
pub mod cli_bridge_gate;
pub mod cli_bridge_server;
pub mod cli_bridge_token;
pub mod native_result_mapping;
pub mod op_dispatch;
pub mod ops;
```

Create `crates/desktop/artcraft/src/core/cli_bridge/ops/mod.rs`:
```rust
pub mod op_support;
```

- [ ] **Step 2: Write the failing tests**

Create `crates/desktop/artcraft/src/core/cli_bridge/native_result_mapping.rs` containing only:
```rust
#[cfg(test)]
mod tests {
  use super::*;
  use crate::core::commands::response::failure_response_wrapper::CommandErrorStatus;
  use std::io;

  const TOKEN: &str = "00000000-0000-4000-8000-000000000001";

  #[test]
  fn native_results_map_to_stable_codes() {
    let omni_cases = [
      ("needs_storyteller_credentials", BridgeErrorCode::NotLoggedIn),
      ("unauthorized", BridgeErrorCode::NotLoggedIn),
      ("billing_issue", BridgeErrorCode::InsufficientCredits),
      ("too_many_requests", BridgeErrorCode::RateLimited),
      ("bad_input", BridgeErrorCode::UpstreamBadInput),
    ];
    for (error_type, code) in omni_cases {
      assert_eq!(map_omni_error(&omni_error(Some(error_type)), OmniCallSite::Estimate).code, code, "{error_type}");
      assert_eq!(map_omni_error(&omni_error(Some(error_type)), OmniCallSite::SubmitPost { idempotency_token: TOKEN }).code, code, "{error_type}");
    }

    // A server error is a free retry on an estimate, but the submit POST may already have been charged.
    for error_type in [Some("server_error"), Some("a_type_added_later"), None] {
      assert_eq!(map_omni_error(&omni_error(error_type), OmniCallSite::Estimate).code, BridgeErrorCode::UpstreamUnavailable);
      let submit = map_omni_error(&omni_error(error_type), OmniCallSite::SubmitPost { idempotency_token: TOKEN });
      assert_eq!(submit.code, BridgeErrorCode::OutcomeUnknown);
      assert_eq!(submit.maybe_details, Some(json!({ "idempotency_token": TOKEN, "reason": "server_error" })));
    }

    let storyteller_cases = [
      (StorytellerError::Api(ApiError::Unauthorized(String::new())), BridgeErrorCode::NotLoggedIn),
      (StorytellerError::Api(ApiError::Forbidden(String::new())), BridgeErrorCode::NotLoggedIn),
      (StorytellerError::Api(ApiError::NotFound(String::new())), BridgeErrorCode::UpstreamError),
      (StorytellerError::Api(ApiError::InvalidRequest("bad field".to_string())), BridgeErrorCode::UpstreamBadInput),
      (StorytellerError::Api(ApiError::PaymentRequired(String::new())), BridgeErrorCode::InsufficientCredits),
      (StorytellerError::Api(ApiError::TooManyRequests(String::new())), BridgeErrorCode::RateLimited),
      (StorytellerError::Api(ApiError::Timeout(String::new())), BridgeErrorCode::UpstreamUnavailable),
      (StorytellerError::Api(ApiError::NetworkError(String::new())), BridgeErrorCode::UpstreamUnavailable),
      (StorytellerError::Api(ApiError::IoError(io::Error::other("disk"))), BridgeErrorCode::LocalStoreError),
      (StorytellerError::Api(ApiError::InternalServerError { body: String::new(), backend_hostname: None }), BridgeErrorCode::UpstreamError),
    ];
    for (error, code) in storyteller_cases {
      assert_eq!(map_storyteller_error(&error, StorytellerCallSite::Other).code, code);
    }
    let missing_media = StorytellerError::Api(ApiError::NotFound(String::new()));
    assert_eq!(map_storyteller_error(&missing_media, StorytellerCallSite::MediaGet).code, BridgeErrorCode::MediaNotFound);

    // 401/403 from the session check mean "logged out", not a failure.
    assert!(matches!(map_login_result(Err(login_error(Some(401), false))), Ok(None)));
    assert!(matches!(map_login_result(Err(login_error(Some(403), false))), Ok(None)));
    assert_eq!(login_code(Some(429), false), Some(BridgeErrorCode::RateLimited));
    assert_eq!(login_code(None, true), Some(BridgeErrorCode::UpstreamUnavailable));
    assert_eq!(login_code(None, false), Some(BridgeErrorCode::UpstreamError));
    assert_eq!(login_code(Some(500), true), Some(BridgeErrorCode::UpstreamError));

    // Relayed upstream text is capped at 500 characters.
    let mut long = omni_error(Some("bad_input"));
    long.error_message = Some("x".repeat(2_000));
    assert_eq!(map_omni_error(&long, OmniCallSite::Estimate).message.chars().count(), 500);
  }

  fn omni_error(error_type: Option<&str>) -> CommandErrorResponseWrapper<String, ()> {
    CommandErrorResponseWrapper {
      status: CommandErrorStatus::ServerError,
      error_message: Some("upstream said no".to_string()),
      error_type: error_type.map(str::to_string),
      error_details: None,
    }
  }

  fn login_error(status: Option<u16>, retryable: bool) -> DesktopLoginError {
    DesktopLoginError { status, message: "login check failed".to_string(), retryable }
  }

  fn login_code(status: Option<u16>, retryable: bool) -> Option<BridgeErrorCode> {
    map_login_result(Err(login_error(status, retryable))).err().map(|error| error.code)
  }
}
```

Create `crates/desktop/artcraft/src/core/cli_bridge/ops/op_support.rs` containing only:
```rust
#[cfg(test)]
mod tests {
  use super::*;

  #[test]
  fn idempotency_tokens_must_be_canonical_lowercase_uuids() {
    assert!(validate_idempotency_token("0f8c2a1e-3b4d-4e5f-8a9b-0c1d2e3f4a5b").is_ok());

    // Uppercase, braces, missing hyphens, a subscriber-tag lookalike and the empty string all fail.
    let rejected = [
      "0F8C2A1E-3B4D-4E5F-8A9B-0C1D2E3F4A5B",
      "{0f8c2a1e-3b4d-4e5f-8a9b-0c1d2e3f4a5b}",
      "0f8c2a1e3b4d4e5f8a9b0c1d2e3f4a5b",
      "cli_bridge:0f8c2a1e-3b4d-4e5f-8a9b-0c1d2e3f4a5",
      "",
    ];
    for token in rejected {
      assert_eq!(validate_idempotency_token(token).unwrap_err().code, BridgeErrorCode::InvalidArgs, "{token}");
    }
  }
}
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `SQLX_OFFLINE=true cargo test -p artcraft --lib cli_bridge`
Expected: FAIL to compile with `cannot find function map_omni_error`, `cannot find function validate_idempotency_token`, and so on.

- [ ] **Step 4: Implement the mapping**

Insert above `#[cfg(test)]` in `native_result_mapping.rs`:
```rust
use crate::core::cli_bridge::cli_bridge_envelope::{BridgeError, BridgeErrorCode};
use crate::core::commands::response::failure_response_wrapper::CommandErrorResponseWrapper;
use crate::services::storyteller::commands::login_bridge::DesktopLoginError;
use artcraft_api_defs::users::session_info::SessionUserInfo;
use artcraft_client::error::api_error::ApiError;
use artcraft_client::error::storyteller_error::StorytellerError;
use serde_json::json;

const MAX_RELAYED_MESSAGE_CHARS: usize = 500;

/// Which Omni call failed. Only the submit POST may answer `outcome_unknown` (spec §5.7).
pub enum OmniCallSite<'a> {
  Estimate,
  SubmitPost { idempotency_token: &'a str },
}

/// Which direct `artcraft_client` call failed; `NotFound` means "no such media" only in `media.get`.
pub enum StorytellerCallSite {
  MediaGet,
  Other,
}

/// Spec §5.7 "OmniResult errors". Unknown or missing error types are treated as `server_error`.
pub fn map_omni_error(error: &CommandErrorResponseWrapper<String, ()>, site: OmniCallSite<'_>) -> BridgeError {
  match error.error_type.as_deref() {
    Some("needs_storyteller_credentials" | "unauthorized") => not_logged_in(),
    Some("billing_issue") => BridgeError::new(BridgeErrorCode::InsufficientCredits, "the account does not have enough credits"),
    Some("too_many_requests") => rate_limited(),
    Some("bad_input") => BridgeError::new(BridgeErrorCode::UpstreamBadInput, relayed_message(error.error_message.as_deref())),
    _ => match site {
      OmniCallSite::Estimate => BridgeError::new(BridgeErrorCode::UpstreamUnavailable, "the cost estimate failed; retrying is free"),
      OmniCallSite::SubmitPost { idempotency_token } => outcome_unknown(idempotency_token, "server_error"),
    },
  }
}

/// Spec §5.7 "StorytellerError", for calls made directly through `artcraft_client`.
pub fn map_storyteller_error(error: &StorytellerError, site: StorytellerCallSite) -> BridgeError {
  match error {
    StorytellerError::Api(ApiError::Unauthorized(_) | ApiError::Forbidden(_)) => not_logged_in(),
    StorytellerError::Api(ApiError::NotFound(_)) => match site {
      StorytellerCallSite::MediaGet => BridgeError::new(BridgeErrorCode::MediaNotFound, "no media file has this token"),
      StorytellerCallSite::Other => upstream_error(),
    },
    StorytellerError::Api(ApiError::InvalidRequest(body)) => {
      BridgeError::new(BridgeErrorCode::UpstreamBadInput, relayed_message(Some(body)))
    },
    StorytellerError::Api(ApiError::PaymentRequired(_)) => {
      BridgeError::new(BridgeErrorCode::InsufficientCredits, "the account does not have enough credits")
    },
    StorytellerError::Api(ApiError::TooManyRequests(_)) => rate_limited(),
    StorytellerError::Api(ApiError::Timeout(_) | ApiError::NetworkError(_) | ApiError::OtherReqwestError(_)) => {
      BridgeError::new(BridgeErrorCode::UpstreamUnavailable, "the ArtCraft API could not be reached")
    },
    StorytellerError::Api(ApiError::IoError(_)) | StorytellerError::Client(_) => {
      BridgeError::new(BridgeErrorCode::LocalStoreError, "a local file or client setup step failed")
    },
    StorytellerError::Api(_) => upstream_error(),
  }
}

/// Spec §5.5 `account.session`: 401/403 mean logged out, so they are `Ok(None)`, not errors.
pub fn map_login_result(
  result: Result<Option<SessionUserInfo>, DesktopLoginError>,
) -> Result<Option<SessionUserInfo>, BridgeError> {
  let error = match result {
    Ok(maybe_user) => return Ok(maybe_user),
    Err(error) => error,
  };
  match (error.status, error.retryable) {
    (Some(401 | 403), _) => Ok(None),
    (Some(429), _) => Err(rate_limited()),
    (None, true) => Err(BridgeError::new(BridgeErrorCode::UpstreamUnavailable, "the session check could not reach the ArtCraft API")),
    (None, false) | (Some(_), _) => Err(upstream_error()),
  }
}

pub fn outcome_unknown(idempotency_token: &str, reason: &str) -> BridgeError {
  BridgeError::new(
    BridgeErrorCode::OutcomeUnknown,
    "the generation may have been accepted; check `jobs list --remote --all` before resubmitting",
  )
  .with_details(json!({ "idempotency_token": idempotency_token, "reason": reason }))
}

pub fn upstream_error() -> BridgeError {
  BridgeError::new(BridgeErrorCode::UpstreamError, "the ArtCraft API returned an error")
}

fn not_logged_in() -> BridgeError {
  BridgeError::new(BridgeErrorCode::NotLoggedIn, "log in inside the ArtCraft app")
}

fn rate_limited() -> BridgeError {
  BridgeError::new(BridgeErrorCode::RateLimited, "the ArtCraft API is rate limiting requests")
}

fn relayed_message(maybe_message: Option<&str>) -> String {
  let message = maybe_message.unwrap_or("the ArtCraft API rejected the request");
  message.chars().take(MAX_RELAYED_MESSAGE_CHARS).collect()
}

```

- [ ] **Step 5: Implement op support**

Insert above `#[cfg(test)]` in `ops/op_support.rs`:
```rust
use crate::core::cli_bridge::cli_bridge_envelope::{BridgeError, BridgeErrorCode};
use crate::core::state::data_dir::app_data_root::AppDataRoot;
use crate::core::state::task_database::TaskDatabase;
use crate::services::storyteller::state::storyteller_credential_manager::StorytellerCredentialManager;
use artcraft_client::credentials::storyteller_credential_set::StorytellerCredentialSet;
use serde::de::DeserializeOwned;
use serde::Serialize;
use serde_derive::Deserialize;
use serde_json::{json, Value};
use std::future::Future;
use std::time::Duration;
use tauri::{AppHandle, Manager};

const MAX_ID_LEN: usize = 128;
const UUID_LEN: usize = 36;
const UUID_HYPHEN_POSITIONS: [usize; 4] = [8, 13, 18, 23];

/// What every op runs with. Cloned into each spawned op.
#[derive(Clone)]
pub struct OpContext {
  pub app: AppHandle,
  pub root: AppDataRoot,
  pub limits: OpLimits,
}

/// Op deadlines and per-call timeouts (spec §4.5). Parameters, so tests can use milliseconds.
#[derive(Clone, Copy)]
pub struct OpLimits {
  pub read_op_deadline: Duration,
  pub write_op_deadline: Duration,
  pub read_call_timeout: Duration,
  pub remote_jobs_timeout: Duration,
  pub upload_call_timeout: Duration,
  pub submit_hard_cap: Duration,
}

/// Args of the ops that take none: exactly `{}`.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct EmptyRequest {}

impl OpContext {
  pub fn new(app: AppHandle, root: AppDataRoot) -> Self {
    Self {
      app,
      root,
      limits: OpLimits::production(),
    }
  }
}

impl OpLimits {
  pub fn production() -> Self {
    Self {
      read_op_deadline: Duration::from_secs(30),
      write_op_deadline: Duration::from_secs(120),
      read_call_timeout: Duration::from_secs(20),
      remote_jobs_timeout: Duration::from_secs(10),
      upload_call_timeout: Duration::from_secs(100),
      submit_hard_cap: Duration::from_secs(300),
    }
  }
}

/// Decodes an op's `deny_unknown_fields` args. The message is generic so no arg value is echoed.
pub fn parse_args<T: DeserializeOwned>(args: Value) -> Result<T, BridgeError> {
  serde_json::from_value(args).map_err(|_| invalid_args("args do not match this op's schema"))
}

pub fn to_data<T: Serialize>(value: &T) -> Result<Value, BridgeError> {
  serde_json::to_value(value)
    .map_err(|_| BridgeError::new(BridgeErrorCode::InternalError, "the bridge could not encode the response"))
}

/// Spec §5.5 `require_session`.
pub fn require_session(app: &AppHandle) -> Result<StorytellerCredentialSet, BridgeError> {
  let manager = app.state::<StorytellerCredentialManager>();
  let Ok(Some(creds)) = manager.get_credentials() else {
    return Err(BridgeError::new(BridgeErrorCode::CredentialsNotSynced, "ArtCraft has not loaded its session yet"));
  };
  if creds.session.is_none() {
    return Err(BridgeError::new(BridgeErrorCode::NotLoggedIn, "log in inside the ArtCraft app"));
  }
  Ok(creds)
}

pub fn task_database(app: &AppHandle) -> Result<TaskDatabase, BridgeError> {
  app.try_state::<TaskDatabase>()
    .map(|database| database.inner().clone())
    .ok_or_else(|| local_store_error("the task database is not ready"))
}

/// `artcraft_client` has no timeouts of its own, so every outbound call goes through this (spec §4.5).
pub async fn with_call_timeout<T>(limit: Duration, call: impl Future<Output = T>) -> Result<T, BridgeError> {
  tokio::time::timeout(limit, call).await.map_err(|_| deadline_error())
}

pub fn deadline_error() -> BridgeError {
  BridgeError::new(BridgeErrorCode::UpstreamUnavailable, "the ArtCraft API did not answer in time")
    .with_details(json!({ "reason": "deadline" }))
}

/// Ids and tokens are 1–128 characters of `[A-Za-z0-9_-]` (spec §5.5).
pub fn validate_id(field: &str, value: &str) -> Result<(), BridgeError> {
  let valid = (1..=MAX_ID_LEN).contains(&value.len())
    && value.bytes().all(|byte| byte.is_ascii_alphanumeric() || byte == b'_' || byte == b'-');
  if valid {
    Ok(())
  } else {
    Err(invalid_args(&format!("{field} must be 1-128 characters of A-Z, a-z, 0-9, _ or -")))
  }
}

/// A canonical lowercase UUID, because it becomes part of the task row's subscriber tag.
pub fn validate_idempotency_token(value: &str) -> Result<(), BridgeError> {
  let valid = value.len() == UUID_LEN
    && value.bytes().enumerate().all(|(index, byte)| {
      if UUID_HYPHEN_POSITIONS.contains(&index) {
        byte == b'-'
      } else {
        byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)
      }
    });
  if valid {
    Ok(())
  } else {
    Err(invalid_args("idempotency_token must be a lowercase UUID"))
  }
}

pub fn invalid_args(message: &str) -> BridgeError {
  BridgeError::new(BridgeErrorCode::InvalidArgs, message)
}

pub fn local_store_error(message: &str) -> BridgeError {
  BridgeError::new(BridgeErrorCode::LocalStoreError, message)
}

```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `SQLX_OFFLINE=true cargo test -p artcraft --lib cli_bridge`
Expected: PASS, `19 passed`. If `ApiError::InternalServerError`'s fields differ from `{ body, backend_hostname }`, match `AC/error/api_error.rs` and re-run.

- [ ] **Step 7: Commit**

```bash
git add crates/desktop/artcraft/src/core/cli_bridge/mod.rs crates/desktop/artcraft/src/core/cli_bridge/native_result_mapping.rs crates/desktop/artcraft/src/core/cli_bridge/ops/mod.rs crates/desktop/artcraft/src/core/cli_bridge/ops/op_support.rs
git commit -m "feat(cli-bridge): map native results to stable bridge codes"
```

### Task 5: Generate rules (deny-list, route guard, effective credits)

**Files:**
- Modify: `crates/desktop/artcraft/src/core/cli_bridge/ops/mod.rs`
- Create: `crates/desktop/artcraft/src/core/cli_bridge/ops/generate_rules.rs`
- Test: bottom `mod tests` of `generate_rules.rs`

**Interfaces:**
- Consumes:
  - T3: `BridgeError`, `BridgeErrorCode`.
  - T4: `invalid_args`.
  - App: `OmniRequest` (`S/core/commands/generate/omni/request.rs:10`) with `uses_legacy_image_endpoint()`.
- Produces:
  - `SUBSCRIBER_ID_PREFIX: &str = "cli_bridge:"`
  - `#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)] enum GenerateModality { Image, Video, Audio, Mesh, Splat }`, with `to_str()` and `Display`.
  - `struct EstimateInput { fields: Map<String, Value>, video_count: u64 }`
  - `validate_generate_request(GenerateModality, &Map<String, Value>) -> Result<(), BridgeError>`
  - `build_omni_request(Map<String, Value>, Option<String>) -> OmniRequest`
  - `estimate_input(GenerateModality, &Map<String, Value>) -> Result<EstimateInput, BridgeError>`
  - `project_estimate(&Value) -> Value`
  - `effective_credits(&Value, video_count: u64) -> Option<u64>`

- [ ] **Step 1: Declare the module**

Replace `crates/desktop/artcraft/src/core/cli_bridge/ops/mod.rs` with:
```rust
pub mod generate_rules;
pub mod op_support;
```

- [ ] **Step 2: Write the failing tests**

Create `crates/desktop/artcraft/src/core/cli_bridge/ops/generate_rules.rs` containing only:
```rust
#[cfg(test)]
mod tests {
  use super::*;

  /// Any id that is not one of the four legacy image models; validation never checks existence.
  const OMNI_IMAGE_MODEL: &str = "gpt_image_1";
  const OMNI_VIDEO_MODEL: &str = "kling_2_1_pro";
  const LEGACY_IMAGE_MODELS: [&str; 4] = ["recraft_3", "flux_pro_kontext_max", "flux_dev_juggernaut", "flux_pro_1"];

  #[test]
  fn legacy_image_models_are_refused_before_estimate_or_spend() {
    for model in LEGACY_IMAGE_MODELS {
      let error = validate_generate_request(GenerateModality::Image, &request(json!({ "model": model, "prompt": "x" }))).unwrap_err();
      assert_eq!(error.code, BridgeErrorCode::UnsupportedRoute, "{model}");
    }

    assert!(validate_generate_request(GenerateModality::Image, &request(json!({ "model": OMNI_IMAGE_MODEL, "prompt": "x" }))).is_ok());
  }

  #[test]
  fn reserved_request_keys_are_refused() {
    let reserved = [
      "provider",
      "frontend_caller",
      "frontend_subscriber_id",
      "frontend_subscriber_payload",
      "idempotency_token",
      "image_raw_bytes",
      "canvas_image_media_token",
      "scene_image_media_token",
    ];
    for key in reserved {
      let mut fields = request(json!({ "model": OMNI_IMAGE_MODEL, "prompt": "x" }));
      fields.insert(key.to_string(), json!("value"));
      let error = validate_generate_request(GenerateModality::Image, &fields).unwrap_err();
      assert_eq!(error.code, BridgeErrorCode::InvalidArgs, "{key}");
    }

    let missing_model = validate_generate_request(GenerateModality::Video, &request(json!({ "prompt": "x" }))).unwrap_err();
    assert_eq!(missing_model.code, BridgeErrorCode::InvalidArgs);

    // `estimate_only` is the API's own cost-hint struct, so it passes.
    let with_hint = request(json!({ "model": OMNI_VIDEO_MODEL, "estimate_only": { "total_input_video_duration_millis": 4000 } }));
    assert!(validate_generate_request(GenerateModality::Video, &with_hint).is_ok());
  }

  #[test]
  fn inpainting_masks_are_unsupported_route() {
    // The mask check runs first, so `inpainting_mask_image_raw_bytes` is a route problem, not a reserved key.
    for key in ["inpainting_mask_image_media_token", "inpainting_mask_image_raw_bytes"] {
      let mut fields = request(json!({ "model": OMNI_IMAGE_MODEL, "prompt": "x" }));
      fields.insert(key.to_string(), json!("m_1"));
      let error = validate_generate_request(GenerateModality::Image, &fields).unwrap_err();
      assert_eq!(error.code, BridgeErrorCode::UnsupportedRoute, "{key}");
    }
  }

  #[test]
  fn video_batches_are_priced_per_video_like_the_app() {
    let input = estimate_input(GenerateModality::Video, &request(json!({ "model": OMNI_VIDEO_MODEL, "video_batch_count": 3 }))).unwrap();
    assert!(!input.fields.contains_key("video_batch_count"));
    assert_eq!(input.video_count, 3);
    let estimate = project_estimate(&json!({ "cost_in_credits": 40, "is_free": false, "is_unlimited": false }));
    assert_eq!(effective_credits(&estimate, input.video_count), Some(120));

    // Image keeps its count: the server prices the whole batch.
    let image = estimate_input(GenerateModality::Image, &request(json!({ "model": OMNI_IMAGE_MODEL, "image_batch_count": 4 }))).unwrap();
    assert_eq!(image.fields.get("image_batch_count"), Some(&json!(4)));
    assert_eq!(image.video_count, 1);

    // No count means one video. A count that is not a positive integer is refused, never undercounted.
    let single = estimate_input(GenerateModality::Video, &request(json!({ "model": OMNI_VIDEO_MODEL }))).unwrap();
    assert_eq!(single.video_count, 1);
    for bad_count in [json!(0), json!(2.5), json!("3")] {
      let fields = request(json!({ "model": OMNI_VIDEO_MODEL, "video_batch_count": bad_count }));
      let code = estimate_input(GenerateModality::Video, &fields).err().map(|error| error.code);
      assert_eq!(code, Some(BridgeErrorCode::InvalidArgs));
    }

    // Any other count key would reach the server unpriced, so video refuses it.
    for alias in ["batch_size", "image_batch_count"] {
      let mut fields = request(json!({ "model": OMNI_VIDEO_MODEL }));
      fields.insert(alias.to_string(), json!(4));
      let code = estimate_input(GenerateModality::Video, &fields).err().map(|error| error.code);
      assert_eq!(code, Some(BridgeErrorCode::InvalidArgs), "{alias}");
    }
  }

  fn request(value: Value) -> Map<String, Value> {
    value.as_object().cloned().unwrap()
  }
}
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `SQLX_OFFLINE=true cargo test -p artcraft --lib generate_rules`
Expected: FAIL to compile with `cannot find function validate_generate_request` and `cannot find type GenerateModality`.

- [ ] **Step 4: Implement the rules**

Insert above `#[cfg(test)]` in `generate_rules.rs`:
```rust
use crate::core::cli_bridge::cli_bridge_envelope::{BridgeError, BridgeErrorCode};
use crate::core::cli_bridge::ops::op_support::invalid_args;
use crate::core::commands::generate::omni::OmniRequest;
use serde_derive::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use std::fmt;

/// Tags every bridge task row (`frontend_subscriber_id`), so a retry can find it and no UI page claims it.
pub const SUBSCRIBER_ID_PREFIX: &str = "cli_bridge:";

const INPAINTING_MASK_PREFIX: &str = "inpainting_mask_image_";
const RESERVED_KEYS: [&str; 5] = [
  "provider",
  "frontend_caller",
  "frontend_subscriber_id",
  "frontend_subscriber_payload",
  "idempotency_token",
];
const RESERVED_PREFIXES: [&str; 2] = ["canvas_image_", "scene_image_"];
const RAW_BYTES_SUFFIX: &str = "_raw_bytes";
/// The key the app's video path sends (`frontend/libs/tauri-api/src/lib/generate/GenerateVideo.ts`,
/// `S/core/commands/generate/generate_video/request.rs:109`). Omni renames no count field for video.
const VIDEO_BATCH_COUNT_KEY: &str = "video_batch_count";
/// Count keys that video would pass through unpriced; refused so the `max_credits` cap cannot fail open.
const VIDEO_COUNT_ALIASES: [&str; 2] = ["batch_size", "image_batch_count"];

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum GenerateModality {
  Image,
  Video,
  Audio,
  Mesh,
  Splat,
}

/// What the estimate call sends, and how many videos one submit will produce.
pub struct EstimateInput {
  pub fields: Map<String, Value>,
  pub video_count: u64,
}

impl GenerateModality {
  pub const fn to_str(&self) -> &'static str {
    match self {
      Self::Image => "image",
      Self::Video => "video",
      Self::Audio => "audio",
      Self::Mesh => "mesh",
      Self::Splat => "splat",
    }
  }
}

impl fmt::Display for GenerateModality {
  fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
    write!(f, "{}", self.to_str())
  }
}

/// Spec §7.2 (in order), then §7.1. Runs before any estimate, session check or spend.
pub fn validate_generate_request(modality: GenerateModality, request: &Map<String, Value>) -> Result<(), BridgeError> {
  if request.keys().any(|key| key.starts_with(INPAINTING_MASK_PREFIX)) {
    return Err(unsupported_route("inpainting masks are not supported on the bridge"));
  }
  if let Some(key) = request.keys().find(|key| is_reserved_key(key)) {
    return Err(invalid_args(&format!("the bridge sets `{key}` itself; remove it from the request")));
  }
  let Some(model) = request.get("model").and_then(Value::as_str) else {
    return Err(invalid_args("request.model is required"));
  };
  // The bridge never sets `provider`, so `uses_artcraft()` always holds; only the legacy image check can fail.
  let probe = build_omni_request(Map::from_iter([("model".to_string(), json!(model))]), None);
  if modality == GenerateModality::Image && probe.uses_legacy_image_endpoint() {
    return Err(unsupported_route("this image model is not on ArtCraft's Omni route; pick one from `models list`"));
  }
  Ok(())
}

/// The bridge's only way into Omni: no provider, no frontend caller or payload.
pub fn build_omni_request(fields: Map<String, Value>, maybe_subscriber_id: Option<String>) -> OmniRequest {
  OmniRequest {
    provider: None,
    frontend_caller: None,
    frontend_subscriber_id: maybe_subscriber_id,
    frontend_subscriber_payload: None,
    fields,
  }
}

/// The app prices video per unit and multiplies by the count itself (`useVideoCostEstimate.ts:89-91`),
/// so the count is stripped from the estimate call. Image sends its count and gets the batch total.
pub fn estimate_input(modality: GenerateModality, request: &Map<String, Value>) -> Result<EstimateInput, BridgeError> {
  let mut fields = request.clone();
  if modality != GenerateModality::Video {
    return Ok(EstimateInput { fields, video_count: 1 });
  }
  if let Some(alias) = VIDEO_COUNT_ALIASES.iter().find(|alias| fields.contains_key(**alias)) {
    return Err(invalid_args(&format!("video counts go in `video_batch_count`, not `{alias}`")));
  }
  let video_count = match fields.remove(VIDEO_BATCH_COUNT_KEY) {
    None | Some(Value::Null) => 1,
    Some(count) => count
      .as_u64()
      .filter(|count| *count >= 1)
      .ok_or_else(|| invalid_args("video_batch_count must be a positive integer"))?,
  };
  Ok(EstimateInput { fields, video_count })
}

/// Keeps only the estimate fields the wire contract names (spec §5.5). Missing flags read as `false`.
pub fn project_estimate(raw: &Value) -> Value {
  json!({
    "cost_in_credits": raw.get("cost_in_credits"),
    "cost_in_usd_cents": raw.get("cost_in_usd_cents"),
    "is_free": flag(raw, "is_free"),
    "is_unlimited": flag(raw, "is_unlimited"),
    "is_rate_limited": flag(raw, "is_rate_limited"),
    "has_watermark": flag(raw, "has_watermark"),
    "failures_are_refunded": raw.get("failures_are_refunded"),
  })
}

/// Spec §7.3 step 3. `None` (an unknown or fractional cost) is refused before any spend.
pub fn effective_credits(estimate: &Value, video_count: u64) -> Option<u64> {
  if flag(estimate, "is_free") || flag(estimate, "is_unlimited") {
    return Some(0);
  }
  estimate.get("cost_in_credits")?.as_u64()?.checked_mul(video_count)
}

fn is_reserved_key(key: &str) -> bool {
  RESERVED_KEYS.contains(&key)
    || key.ends_with(RAW_BYTES_SUFFIX)
    || RESERVED_PREFIXES.iter().any(|prefix| key.starts_with(prefix))
}

fn flag(value: &Value, key: &str) -> bool {
  value.get(key).and_then(Value::as_bool).unwrap_or(false)
}

fn unsupported_route(message: &str) -> BridgeError {
  BridgeError::new(BridgeErrorCode::UnsupportedRoute, message)
}

```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `SQLX_OFFLINE=true cargo test -p artcraft --lib generate_rules`
Expected: PASS, `4 passed`.

- [ ] **Step 6: Commit**

```bash
git add crates/desktop/artcraft/src/core/cli_bridge/ops/mod.rs crates/desktop/artcraft/src/core/cli_bridge/ops/generate_rules.rs
git commit -m "feat(cli-bridge): add Omni route guard, request deny-list and credit pricing"
```

### Task 6: Job view (status maps, remote merge, job list)

**Files:**
- Modify: `crates/desktop/artcraft/src/core/cli_bridge/ops/mod.rs`
- Create: `crates/desktop/artcraft/src/core/cli_bridge/ops/job_view.rs`
- Test: bottom `mod tests` of `job_view.rs`

**Interfaces:**
- Consumes:
  - T3: `BridgeErrorCode`.
  - T5: `GenerateModality`, `SUBSCRIBER_ID_PREFIX`.
  - App: `sqlite_tasks::queries::list_tasks_for_frontend::TaskItem`, `artcraft_api_defs::jobs::list_session_jobs::ListSessionJobsItem`.
- Produces:
  - `struct JobView`. It serializes to spec §7.6, with every `maybe_*` field renamed on the wire.
  - `struct JobListView { jobs: Vec<JobView>, truncated: bool }`
  - `enum JobStatusView { Queued, Running, Succeeded, Failed, Cancelled, Unknown }`, with `to_str()` and `is_terminal()`.
  - `enum JobOrigin { Cli, App, Unknown }`
  - `#[derive(Default)] enum OriginFilter { Cli, All }`
  - `struct NativeStatusView`, `struct JobResultView { files, maybe_batch_token }`
  - `struct JobFileView { media_token, maybe_cdn_url, maybe_thumbnail_url_template, maybe_media_class }`
  - `struct JobFailureView`, `struct JobSourcesView { local, remote, maybe_remote_error: Option<&'static str> }`
  - `struct RemoteJob`, with `RemoteJob::from_item(&ListSessionJobsItem)`.
  - `map_local_status(&TaskStatus) -> JobStatusView`, `map_remote_status(&JobStatusPlus) -> JobStatusView`
  - `modality_of(&TaskType) -> Option<GenerateModality>`
  - `job_view_from_local(&TaskItem) -> Option<JobView>`, `job_view_from_remote(&RemoteJob) -> JobView`
  - `merge_remote(&mut JobView, &RemoteJob)`
  - `build_job_list(&[TaskItem], Option<Result<Vec<RemoteJob>, BridgeErrorCode>>, OriginFilter, limit: usize) -> JobListView`

- [ ] **Step 1: Declare the module**

Replace `crates/desktop/artcraft/src/core/cli_bridge/ops/mod.rs` with:
```rust
pub mod generate_rules;
pub mod job_view;
pub mod op_support;
```

- [ ] **Step 2: Write the failing tests**

Create `crates/desktop/artcraft/src/core/cli_bridge/ops/job_view.rs` containing only:
```rust
#[cfg(test)]
mod tests {
  use super::*;
  use chrono::TimeZone;
  use enums::tauri::tasks::task_model_type::TaskModelType;
  use tokens::tokens::sqlite::tasks::TaskId;

  const CLI_SUBSCRIBER: &str = "cli_bridge:00000000-0000-4000-8000-000000000001";
  const CLI_JOB: &str = "jinf_cli";
  const APP_JOB: &str = "jinf_app";
  const REMOTE_ONLY_JOB: &str = "jinf_remote";

  #[test]
  fn every_local_and_remote_status_maps_to_the_closed_vocabulary() {
    let local = [
      (TaskStatus::Pending, JobStatusView::Queued),
      (TaskStatus::Started, JobStatusView::Running),
      (TaskStatus::AttemptFailed, JobStatusView::Running),
      (TaskStatus::CompleteSuccess, JobStatusView::Succeeded),
      (TaskStatus::CompleteFailure, JobStatusView::Failed),
      (TaskStatus::Dead, JobStatusView::Failed),
      (TaskStatus::CancelledByProvider, JobStatusView::Cancelled),
      (TaskStatus::CancelledByUs, JobStatusView::Cancelled),
      (TaskStatus::CancelledByUser, JobStatusView::Unknown),
    ];
    for (status, expected) in local {
      assert_eq!(map_local_status(&status), expected, "{}", status.to_str());
    }

    let remote = [
      (JobStatusPlus::Pending, JobStatusView::Queued),
      (JobStatusPlus::Started, JobStatusView::Running),
      (JobStatusPlus::AttemptFailed, JobStatusView::Running),
      (JobStatusPlus::CompleteSuccess, JobStatusView::Succeeded),
      (JobStatusPlus::CompleteFailure, JobStatusView::Failed),
      (JobStatusPlus::Dead, JobStatusView::Failed),
      (JobStatusPlus::CancelledByUser, JobStatusView::Cancelled),
      (JobStatusPlus::CancelledBySystem, JobStatusView::Cancelled),
    ];
    for (status, expected) in remote {
      assert_eq!(map_remote_status(&status), expected, "{}", status.to_str());
    }

    // Only the three end states are terminal; `unknown` (the app's local-only cancel) is not.
    let all = [
      JobStatusView::Queued,
      JobStatusView::Running,
      JobStatusView::Succeeded,
      JobStatusView::Failed,
      JobStatusView::Cancelled,
      JobStatusView::Unknown,
    ];
    let terminal: Vec<JobStatusView> = all.into_iter().filter(JobStatusView::is_terminal).collect();
    assert_eq!(terminal, vec![JobStatusView::Succeeded, JobStatusView::Failed, JobStatusView::Cancelled]);
  }

  #[test]
  fn remote_terminal_status_wins_over_local() {
    let running = [task_item(Some(CLI_JOB), Some(CLI_SUBSCRIBER), TaskStatus::Started)];

    let list = build_job_list(&running, Some(Ok(vec![remote_job(CLI_JOB, JobStatusPlus::CompleteSuccess)])), OriginFilter::Cli, 50);

    let job = &list.jobs[0];
    assert_eq!(job.status, JobStatusView::Succeeded);
    assert!(job.terminal);
    assert_eq!(job.native_status.maybe_local, Some("started"));
    assert_eq!(job.native_status.maybe_remote, Some("complete_success"));
    assert!(job.sources.local && job.sources.remote);

    // A non-terminal remote status never overrides a finished local row.
    let finished = [task_item(Some(CLI_JOB), Some(CLI_SUBSCRIBER), TaskStatus::CompleteSuccess)];
    let list = build_job_list(&finished, Some(Ok(vec![remote_job(CLI_JOB, JobStatusPlus::Started)])), OriginFilter::Cli, 50);
    assert_eq!(list.jobs[0].status, JobStatusView::Succeeded);
  }

  #[test]
  fn remote_only_jobs_appear_only_under_origin_all() {
    let local = [
      task_item(Some(CLI_JOB), Some(CLI_SUBSCRIBER), TaskStatus::Pending),
      task_item(Some(APP_JOB), None, TaskStatus::Pending),
    ];
    let remote = || Some(Ok(vec![remote_job(CLI_JOB, JobStatusPlus::Started), remote_job(REMOTE_ONLY_JOB, JobStatusPlus::Started)]));

    let cli = build_job_list(&local, remote(), OriginFilter::Cli, 50);
    let all = build_job_list(&local, remote(), OriginFilter::All, 50);

    assert_eq!(sorted_ids(&cli), vec![CLI_JOB]);
    assert_eq!(sorted_ids(&all), vec![APP_JOB, CLI_JOB, REMOTE_ONLY_JOB]);
    let remote_only = all.jobs.iter().find(|job| job.job_id == REMOTE_ONLY_JOB).unwrap();
    assert_eq!(remote_only.origin, JobOrigin::Unknown);
    assert!(!remote_only.sources.local);
    let app = all.jobs.iter().find(|job| job.job_id == APP_JOB).unwrap();
    assert_eq!(app.origin, JobOrigin::App);
  }

  #[test]
  fn rows_without_a_provider_job_id_are_omitted() {
    let local = [
      task_item(None, Some(CLI_SUBSCRIBER), TaskStatus::Pending),
      task_item(Some(CLI_JOB), Some(CLI_SUBSCRIBER), TaskStatus::Pending),
    ];

    let list = build_job_list(&local, None, OriginFilter::All, 50);

    assert_eq!(sorted_ids(&list), vec![CLI_JOB]);
  }

  #[test]
  fn job_lists_are_newest_first_and_report_truncation() {
    let mut local = Vec::new();
    for (hour, job_id) in [(9, "jinf_a"), (11, "jinf_c"), (10, "jinf_b")] {
      let mut item = task_item(Some(job_id), Some(CLI_SUBSCRIBER), TaskStatus::Pending);
      item.created_at = at(hour);
      local.push(item);
    }

    let page = build_job_list(&local, None, OriginFilter::Cli, 2);
    let everything = build_job_list(&local, None, OriginFilter::Cli, 3);

    let page_ids: Vec<&str> = page.jobs.iter().map(|job| job.job_id.as_str()).collect();
    assert_eq!(page_ids, vec!["jinf_c", "jinf_b"]);
    assert!(page.truncated);
    assert!(!everything.truncated);
  }

  fn task_item(maybe_job_id: Option<&str>, maybe_subscriber_id: Option<&str>, status: TaskStatus) -> TaskItem {
    TaskItem {
      id: TaskId::new_from_str(&format!("task_{}", maybe_job_id.unwrap_or("none"))),
      status,
      task_type: TaskType::ImageGeneration,
      model_type: Some(TaskModelType::Unknown("gpt_image_1".to_string())),
      provider: Some(GenerationProvider::Artcraft),
      provider_job_id: maybe_job_id.map(str::to_string),
      frontend_caller: None,
      frontend_subscriber_id: maybe_subscriber_id.map(str::to_string),
      frontend_subscriber_payload: None,
      on_complete_primary_media_file_token: None,
      on_complete_primary_media_file_class: None,
      on_complete_batch_token: None,
      on_complete_primary_media_file_cdn_url: None,
      on_complete_primary_media_file_thumbnail_url_template: None,
      on_failure_type: None,
      on_failure_message: None,
      created_at: at(12),
      updated_at: at(12),
      completed_at: None,
    }
  }

  fn remote_job(job_id: &str, native: JobStatusPlus) -> RemoteJob {
    RemoteJob {
      job_id: job_id.to_string(),
      status: map_remote_status(&native),
      native_status: native.to_str(),
      progress_percent: 50,
      maybe_result: None,
      maybe_failure: None,
      created_at: at(8),
      updated_at: at(13),
    }
  }

  fn at(hour: u32) -> DateTime<Utc> {
    Utc.with_ymd_and_hms(2026, 10, 9, hour, 0, 0).unwrap()
  }

  fn sorted_ids(list: &JobListView) -> Vec<&str> {
    let mut ids: Vec<&str> = list.jobs.iter().map(|job| job.job_id.as_str()).collect();
    ids.sort();
    ids
  }
}
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `SQLX_OFFLINE=true cargo test -p artcraft --lib job_view`
Expected: FAIL to compile with `cannot find function build_job_list` and `cannot find type JobStatusView`.

- [ ] **Step 4: Implement the job view**

Insert above `#[cfg(test)]` in `job_view.rs`:
```rust
use crate::core::cli_bridge::cli_bridge_envelope::BridgeErrorCode;
use crate::core::cli_bridge::ops::generate_rules::{GenerateModality, SUBSCRIBER_ID_PREFIX};
use artcraft_api_defs::jobs::list_session_jobs::ListSessionJobsItem;
use chrono::{DateTime, Utc};
use enums::common::generation_provider::GenerationProvider;
use enums::common::job_status_plus::JobStatusPlus;
use enums::tauri::tasks::task_status::TaskStatus;
use enums::tauri::tasks::task_type::TaskType;
use serde_derive::{Deserialize, Serialize};
use sqlite_tasks::queries::list_tasks_for_frontend::TaskItem;
use std::collections::HashSet;
use std::fmt;

/// One job as `jobs.get` and `jobs.list` return it (spec §7.6).
#[derive(Clone, Debug, Serialize)]
pub struct JobView {
  pub job_id: String,
  #[serde(rename = "task_id")]
  pub maybe_task_id: Option<String>,
  pub origin: JobOrigin,
  #[serde(rename = "modality")]
  pub maybe_modality: Option<GenerateModality>,
  #[serde(rename = "model")]
  pub maybe_model: Option<String>,
  pub status: JobStatusView,
  pub terminal: bool,
  #[serde(rename = "progress_percent")]
  pub maybe_progress_percent: Option<u8>,
  pub native_status: NativeStatusView,
  #[serde(rename = "result")]
  pub maybe_result: Option<JobResultView>,
  #[serde(rename = "failure")]
  pub maybe_failure: Option<JobFailureView>,
  /// Null only for a dismissed row that the remote list did not cover.
  #[serde(rename = "created_at")]
  pub maybe_created_at: Option<DateTime<Utc>>,
  #[serde(rename = "remote_updated_at")]
  pub maybe_remote_updated_at: Option<DateTime<Utc>>,
  pub dismissed: bool,
  pub sources: JobSourcesView,
}

/// `jobs.list` data.
#[derive(Debug, Serialize)]
pub struct JobListView {
  pub jobs: Vec<JobView>,
  pub truncated: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum JobStatusView {
  Queued,
  Running,
  Succeeded,
  Failed,
  Cancelled,
  Unknown,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum JobOrigin {
  Cli,
  App,
  Unknown,
}

/// `jobs.list` `origin` arg. Defaults to the bridge's own jobs.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum OriginFilter {
  #[default]
  Cli,
  All,
}

#[derive(Clone, Debug, Serialize)]
pub struct NativeStatusView {
  #[serde(rename = "local")]
  pub maybe_local: Option<&'static str>,
  #[serde(rename = "remote")]
  pub maybe_remote: Option<&'static str>,
}

#[derive(Clone, Debug, Serialize)]
pub struct JobResultView {
  pub files: Vec<JobFileView>,
  #[serde(rename = "batch_token")]
  pub maybe_batch_token: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct JobFileView {
  pub media_token: String,
  #[serde(rename = "cdn_url")]
  pub maybe_cdn_url: Option<String>,
  #[serde(rename = "thumbnail_url_template")]
  pub maybe_thumbnail_url_template: Option<String>,
  #[serde(rename = "media_class")]
  pub maybe_media_class: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct JobFailureView {
  #[serde(rename = "category")]
  pub maybe_category: Option<String>,
  #[serde(rename = "message")]
  pub maybe_message: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct JobSourcesView {
  pub local: bool,
  pub remote: bool,
  #[serde(rename = "remote_error")]
  pub maybe_remote_error: Option<&'static str>,
}

/// The parts of a `GET /v1/jobs/session` entry the merge uses. Plain fields, so tests build it directly.
#[derive(Clone, Debug)]
pub struct RemoteJob {
  pub job_id: String,
  pub status: JobStatusView,
  pub native_status: &'static str,
  pub progress_percent: u8,
  pub maybe_result: Option<JobResultView>,
  pub maybe_failure: Option<JobFailureView>,
  pub created_at: DateTime<Utc>,
  pub updated_at: DateTime<Utc>,
}

impl JobStatusView {
  pub const fn to_str(&self) -> &'static str {
    match self {
      Self::Queued => "queued",
      Self::Running => "running",
      Self::Succeeded => "succeeded",
      Self::Failed => "failed",
      Self::Cancelled => "cancelled",
      Self::Unknown => "unknown",
    }
  }

  pub const fn is_terminal(&self) -> bool {
    matches!(self, Self::Succeeded | Self::Failed | Self::Cancelled)
  }
}

impl fmt::Display for JobStatusView {
  fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
    write!(f, "{}", self.to_str())
  }
}

impl JobOrigin {
  pub const fn to_str(&self) -> &'static str {
    match self {
      Self::Cli => "cli",
      Self::App => "app",
      Self::Unknown => "unknown",
    }
  }
}

impl fmt::Display for JobOrigin {
  fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
    write!(f, "{}", self.to_str())
  }
}

impl RemoteJob {
  pub fn from_item(item: &ListSessionJobsItem) -> Self {
    Self {
      job_id: item.job_token.as_str().to_string(),
      status: map_remote_status(&item.status.status),
      native_status: item.status.status.to_str(),
      progress_percent: item.status.progress_percentage,
      maybe_result: item.maybe_result.as_ref().map(|result| JobResultView {
        files: vec![JobFileView {
          media_token: result.entity_token.clone(),
          maybe_cdn_url: Some(result.media_links.cdn_url.to_string()),
          maybe_thumbnail_url_template: result.media_links.maybe_thumbnail_template.clone(),
          maybe_media_class: None,
        }],
        maybe_batch_token: result.maybe_batch_token.as_ref().map(|token| token.as_str().to_string()),
      }),
      maybe_failure: remote_failure(item),
      created_at: item.created_at,
      updated_at: item.updated_at,
    }
  }
}

/// Builds `jobs.list` (spec §7.6). Pure, so the merge rules are tested without a network.
/// `maybe_remote` is `None` when the remote list was not asked for.
pub fn build_job_list(
  local: &[TaskItem],
  maybe_remote: Option<Result<Vec<RemoteJob>, BridgeErrorCode>>,
  origin: OriginFilter,
  limit: usize,
) -> JobListView {
  let artcraft_ids = artcraft_job_ids(local);
  let mut jobs: Vec<JobView> = local
    .iter()
    .filter_map(job_view_from_local)
    .filter(|job| origin == OriginFilter::All || job.origin == JobOrigin::Cli)
    .collect();
  match maybe_remote {
    None => {},
    Some(Err(code)) => mark_remote_error(&mut jobs, &artcraft_ids, code),
    Some(Ok(remote_jobs)) => {
      let local_ids: HashSet<&str> = local.iter().filter_map(|item| item.provider_job_id.as_deref()).collect();
      for remote in &remote_jobs {
        if artcraft_ids.contains(remote.job_id.as_str()) {
          if let Some(job) = jobs.iter_mut().find(|job| job.job_id == remote.job_id) {
            merge_remote(job, remote);
          }
        } else if origin == OriginFilter::All && !local_ids.contains(remote.job_id.as_str()) {
          jobs.push(job_view_from_remote(remote));
        }
      }
    },
  }
  jobs.sort_by(|a, b| b.maybe_created_at.cmp(&a.maybe_created_at));
  let truncated = jobs.len() > limit;
  jobs.truncate(limit);
  JobListView { jobs, truncated }
}

/// `None` for a row without a `provider_job_id`: a job view needs an id (spec §7.6).
pub fn job_view_from_local(item: &TaskItem) -> Option<JobView> {
  let job_id = item.provider_job_id.clone()?;
  let status = map_local_status(&item.status);
  Some(JobView {
    job_id,
    maybe_task_id: Some(item.id.as_str().to_string()),
    origin: origin_of(item.frontend_subscriber_id.as_deref()),
    maybe_modality: modality_of(&item.task_type),
    maybe_model: item.model_type.as_ref().map(|model| model.to_str().to_string()),
    status,
    terminal: status.is_terminal(),
    maybe_progress_percent: None,
    native_status: NativeStatusView { maybe_local: Some(item.status.to_str()), maybe_remote: None },
    maybe_result: local_result(item),
    maybe_failure: local_failure(item),
    maybe_created_at: Some(item.created_at),
    maybe_remote_updated_at: None,
    dismissed: false,
    sources: JobSourcesView { local: true, remote: false, maybe_remote_error: None },
  })
}

pub fn job_view_from_remote(remote: &RemoteJob) -> JobView {
  JobView {
    job_id: remote.job_id.clone(),
    maybe_task_id: None,
    origin: JobOrigin::Unknown,
    maybe_modality: None,
    maybe_model: None,
    status: remote.status,
    terminal: remote.status.is_terminal(),
    maybe_progress_percent: Some(remote.progress_percent),
    native_status: NativeStatusView { maybe_local: None, maybe_remote: Some(remote.native_status) },
    maybe_result: remote.maybe_result.clone(),
    maybe_failure: remote.maybe_failure.clone(),
    maybe_created_at: Some(remote.created_at),
    maybe_remote_updated_at: Some(remote.updated_at),
    dismissed: false,
    sources: JobSourcesView { local: false, remote: true, maybe_remote_error: None },
  }
}

/// A remote terminal status wins over local; otherwise local keeps its status (spec §7.6).
pub fn merge_remote(view: &mut JobView, remote: &RemoteJob) {
  view.sources.remote = true;
  view.native_status.maybe_remote = Some(remote.native_status);
  view.maybe_remote_updated_at = Some(remote.updated_at);
  view.maybe_progress_percent = Some(remote.progress_percent);
  if view.maybe_created_at.is_none() {
    view.maybe_created_at = Some(remote.created_at);
  }
  if remote.status.is_terminal() {
    view.status = remote.status;
    view.terminal = true;
  }
  if view.maybe_result.is_none() {
    view.maybe_result = remote.maybe_result.clone();
  }
  if view.maybe_failure.is_none() {
    view.maybe_failure = remote.maybe_failure.clone();
  }
}

/// Exhaustive over all 9 variants, so a new upstream status fails compilation here first.
pub fn map_local_status(status: &TaskStatus) -> JobStatusView {
  match status {
    TaskStatus::Pending => JobStatusView::Queued,
    TaskStatus::Started | TaskStatus::AttemptFailed => JobStatusView::Running,
    TaskStatus::CompleteSuccess => JobStatusView::Succeeded,
    TaskStatus::CompleteFailure | TaskStatus::Dead => JobStatusView::Failed,
    TaskStatus::CancelledByProvider | TaskStatus::CancelledByUs => JobStatusView::Cancelled,
    // The app's cancel is local only: the remote job may still be running.
    TaskStatus::CancelledByUser => JobStatusView::Unknown,
  }
}

pub fn map_remote_status(status: &JobStatusPlus) -> JobStatusView {
  match status {
    JobStatusPlus::Pending => JobStatusView::Queued,
    JobStatusPlus::Started | JobStatusPlus::AttemptFailed => JobStatusView::Running,
    JobStatusPlus::CompleteSuccess => JobStatusView::Succeeded,
    JobStatusPlus::CompleteFailure | JobStatusPlus::Dead => JobStatusView::Failed,
    JobStatusPlus::CancelledByUser | JobStatusPlus::CancelledBySystem => JobStatusView::Cancelled,
  }
}

/// The generate modality that produces a task type, or `None` for types no generate op creates.
pub fn modality_of(task_type: &TaskType) -> Option<GenerateModality> {
  match task_type {
    TaskType::ImageGeneration => Some(GenerateModality::Image),
    TaskType::VideoGeneration => Some(GenerateModality::Video),
    TaskType::AudioGeneration => Some(GenerateModality::Audio),
    TaskType::ObjectGeneration => Some(GenerateModality::Mesh),
    TaskType::GaussianGeneration => Some(GenerateModality::Splat),
    _ => None,
  }
}

/// Only Artcraft-provider rows are merged with the remote list; other providers stay local-only.
fn artcraft_job_ids(local: &[TaskItem]) -> HashSet<&str> {
  local
    .iter()
    .filter(|item| matches!(item.provider, Some(GenerationProvider::Artcraft)))
    .filter_map(|item| item.provider_job_id.as_deref())
    .collect()
}

fn mark_remote_error(jobs: &mut [JobView], artcraft_ids: &HashSet<&str>, code: BridgeErrorCode) {
  for job in jobs.iter_mut().filter(|job| artcraft_ids.contains(job.job_id.as_str())) {
    job.sources.maybe_remote_error = Some(code.to_str());
  }
}

fn origin_of(maybe_subscriber_id: Option<&str>) -> JobOrigin {
  if maybe_subscriber_id.is_some_and(|id| id.starts_with(SUBSCRIBER_ID_PREFIX)) {
    JobOrigin::Cli
  } else {
    JobOrigin::App
  }
}

fn local_result(item: &TaskItem) -> Option<JobResultView> {
  let maybe_batch_token = item.on_complete_batch_token.as_ref().map(|token| token.as_str().to_string());
  let files: Vec<JobFileView> = item
    .on_complete_primary_media_file_token
    .iter()
    .map(|token| JobFileView {
      media_token: token.as_str().to_string(),
      maybe_cdn_url: item.on_complete_primary_media_file_cdn_url.clone(),
      maybe_thumbnail_url_template: item.on_complete_primary_media_file_thumbnail_url_template.clone(),
      maybe_media_class: item.on_complete_primary_media_file_class.as_ref().map(|class| class.to_str().to_string()),
    })
    .collect();
  if files.is_empty() && maybe_batch_token.is_none() {
    return None;
  }
  Some(JobResultView { files, maybe_batch_token })
}

fn local_failure(item: &TaskItem) -> Option<JobFailureView> {
  if item.on_failure_type.is_none() && item.on_failure_message.is_none() {
    return None;
  }
  Some(JobFailureView {
    maybe_category: item.on_failure_type.as_ref().map(|failure| failure.to_str().to_string()),
    maybe_message: item.on_failure_message.clone(),
  })
}

fn remote_failure(item: &ListSessionJobsItem) -> Option<JobFailureView> {
  let maybe_category = item
    .status
    .maybe_failure_category_updated
    .as_ref()
    .and_then(|category| serde_json::to_value(category).ok())
    .and_then(|value| value.as_str().map(str::to_string));
  let maybe_message = item.status.maybe_failure_message.clone();
  if maybe_category.is_none() && maybe_message.is_none() {
    return None;
  }
  Some(JobFailureView { maybe_category, maybe_message })
}

```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `SQLX_OFFLINE=true cargo test -p artcraft --lib job_view`
Expected: PASS, `5 passed`.

- [ ] **Step 6: Commit**

```bash
git add crates/desktop/artcraft/src/core/cli_bridge/ops/mod.rs crates/desktop/artcraft/src/core/cli_bridge/ops/job_view.rs
git commit -m "feat(cli-bridge): add job view with closed status vocabulary and remote merge"
```

### Task 7: M1 ops and op dispatch

**Files:**
- Modify: `crates/desktop/artcraft/src/core/cli_bridge/ops/mod.rs`
- Modify: `crates/desktop/artcraft/src/core/cli_bridge/op_dispatch.rs`
- Create: `crates/desktop/artcraft/src/core/cli_bridge/ops/app_ops.rs`
- Create: `crates/desktop/artcraft/src/core/cli_bridge/ops/account_ops.rs`
- Create: `crates/desktop/artcraft/src/core/cli_bridge/ops/models_ops.rs`
- Create: `crates/desktop/artcraft/src/core/cli_bridge/ops/generate_ops.rs`
- Create: `crates/desktop/artcraft/src/core/cli_bridge/ops/jobs_ops.rs`

**Interfaces:**
- Consumes:
  - T4: everything in `op_support`, plus `map_omni_error`, `map_storyteller_error`, `map_login_result`, `upstream_error`.
  - T5: `validate_generate_request`, `build_omni_request`, `estimate_input`, `project_estimate`, `effective_credits`, `GenerateModality`.
  - T6: `build_job_list`, `RemoteJob`, `OriginFilter`.
- Produces:
  - `make_dispatch(OpContext) -> DispatchFn` (used by T8).
  - `app_info(&OpContext, Value) -> Result<Value, BridgeError>`
  - `account_session(&OpContext, Value)`, `models_list(&OpContext, Value)`
  - `generate_estimate(&OpContext, Value)`
  - `estimate_cost(&OpContext, GenerateModality, &Map<String, Value>) -> Result<PricedRequest, BridgeError>` (used by T12)
  - `struct PricedRequest { estimate: Value, maybe_effective_credits: Option<u64> }`
  - `jobs_list(&OpContext, Value)`
  - `list_local_tasks(&TaskDatabase) -> Result<Vec<TaskItem>, BridgeError>` (used by T13)
  - `fetch_remote_jobs(&OpContext) -> Result<Vec<RemoteJob>, BridgeErrorCode>` (used by T13, T18)

This task is wiring only: each op calls an existing command or client function, and the logic it composes was unit-tested in T4–T6. Verification is `cargo check` plus the T9 live checklist.

- [ ] **Step 1: Declare the op modules**

Replace `crates/desktop/artcraft/src/core/cli_bridge/ops/mod.rs` with:
```rust
pub mod account_ops;
pub mod app_ops;
pub mod generate_ops;
pub mod generate_rules;
pub mod job_view;
pub mod jobs_ops;
pub mod models_ops;
pub mod op_support;
```

- [ ] **Step 2: Write `app_ops.rs`**

```rust
use crate::core::cli_bridge::cli_bridge_envelope::{BridgeError, BridgeErrorCode};
use crate::core::cli_bridge::ops::op_support::{parse_args, to_data, EmptyRequest, OpContext};
use crate::core::commands::get_app_info_command::get_app_info_command;
use serde_json::Value;
use tauri::Manager;

/// `app.info`: the app's own info payload, passed through (spec §5.5).
pub fn app_info(ctx: &OpContext, args: Value) -> Result<Value, BridgeError> {
  let _: EmptyRequest = parse_args(args)?;
  let response = get_app_info_command(ctx.app.state(), ctx.app.state(), ctx.app.state(), ctx.app.state());
  let Some(payload) = response.payload else {
    return Err(BridgeError::new(BridgeErrorCode::InternalError, "the app returned no info payload"));
  };
  to_data(&payload)
}
```

- [ ] **Step 3: Write `account_ops.rs` (session only; T12 adds credits and subscription)**

```rust
use crate::core::cli_bridge::cli_bridge_envelope::BridgeError;
use crate::core::cli_bridge::native_result_mapping::map_login_result;
use crate::core::cli_bridge::ops::op_support::{parse_args, with_call_timeout, EmptyRequest, OpContext};
use crate::services::storyteller::commands::storyteller_get_login_session_command::storyteller_get_login_session_command;
use serde_json::{json, Value};
use tauri::Manager;

/// `account.session` (spec §5.5). A 401/403 from the session check is a logged-out answer.
pub async fn account_session(ctx: &OpContext, args: Value) -> Result<Value, BridgeError> {
  let _: EmptyRequest = parse_args(args)?;
  let login = with_call_timeout(
    ctx.limits.read_call_timeout,
    storyteller_get_login_session_command(ctx.app.clone(), ctx.app.state()),
  ).await?;
  Ok(match map_login_result(login)? {
    Some(user) => json!({
      "logged_in": true,
      "username": user.username,
      "display_name": user.display_name,
      "user_token": user.user_token.as_str(),
    }),
    None => json!({ "logged_in": false }),
  })
}
```

- [ ] **Step 4: Write `models_ops.rs`**

```rust
use crate::core::cli_bridge::cli_bridge_envelope::BridgeError;
use crate::core::cli_bridge::native_result_mapping::upstream_error;
use crate::core::cli_bridge::ops::op_support::{parse_args, to_data, with_call_timeout, OpContext};
use crate::core::commands::generate::models::image::list_image_models_command::list_image_models_command;
use crate::core::commands::generate::models::video::list_video_models_command::list_video_models_command;
use serde_derive::Deserialize;
use serde_json::{json, Value};
use tauri::Manager;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ModelsListRequest {
  kind: ModelKind,
}

/// Image and video only: no command lists audio, mesh or splat models (spec §5.5).
#[derive(Clone, Copy, Deserialize)]
#[serde(rename_all = "snake_case")]
enum ModelKind {
  Image,
  Video,
}

/// `models.list`: the command's model objects, passed through unchanged. The commands flatten
/// every failure into a message, so any error is `upstream_error`.
pub async fn models_list(ctx: &OpContext, args: Value) -> Result<Value, BridgeError> {
  let request: ModelsListRequest = parse_args(args)?;
  let (kind, models) = match request.kind {
    ModelKind::Image => {
      let response = with_call_timeout(ctx.limits.read_call_timeout, list_image_models_command(ctx.app.state())).await?;
      let payload = response.map_err(|_| upstream_error())?.payload.ok_or_else(upstream_error)?;
      ("image", to_data(&payload.models)?)
    },
    ModelKind::Video => {
      let response = with_call_timeout(ctx.limits.read_call_timeout, list_video_models_command(ctx.app.state())).await?;
      let payload = response.map_err(|_| upstream_error())?.payload.ok_or_else(upstream_error)?;
      ("video", to_data(&payload.models)?)
    },
  };
  Ok(json!({ "kind": kind, "models": models }))
}
```

- [ ] **Step 5: Write `generate_ops.rs` (estimate only; T12 adds submit)**

```rust
use crate::core::cli_bridge::cli_bridge_envelope::BridgeError;
use crate::core::cli_bridge::native_result_mapping::{map_omni_error, OmniCallSite};
use crate::core::cli_bridge::ops::generate_rules::{
  build_omni_request, effective_credits, estimate_input, project_estimate, validate_generate_request, GenerateModality,
};
use crate::core::cli_bridge::ops::op_support::{parse_args, with_call_timeout, OpContext};
use crate::core::commands::cost_estimate::estimate_audio_cost_command::estimate_audio_cost_command;
use crate::core::commands::cost_estimate::estimate_image_cost_command::estimate_image_cost_command;
use crate::core::commands::cost_estimate::estimate_mesh_cost_command::estimate_mesh_cost_command;
use crate::core::commands::cost_estimate::estimate_splat_cost_command::estimate_splat_cost_command;
use crate::core::commands::cost_estimate::estimate_video_cost_command::estimate_video_cost_command;
use crate::core::commands::generate::omni::{OmniRequest, OmniResult};
use serde_derive::Deserialize;
use serde_json::{json, Map, Value};
use tauri::AppHandle;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct GenerateEstimateRequest {
  modality: GenerateModality,
  request: Map<String, Value>,
}

/// A validated request's projected estimate and the credits it would actually spend.
pub struct PricedRequest {
  pub estimate: Value,
  pub maybe_effective_credits: Option<u64>,
}

/// `generate.estimate` (spec §7.3): free, needs no login, creates no task.
pub async fn generate_estimate(ctx: &OpContext, args: Value) -> Result<Value, BridgeError> {
  let request: GenerateEstimateRequest = parse_args(args)?;
  let priced = estimate_cost(ctx, request.modality, &request.request).await?;
  Ok(json!({
    "modality": request.modality.to_str(),
    "model": model_of(&request.request),
    "estimate": priced.estimate,
    "effective_credits": priced.maybe_effective_credits,
  }))
}

/// Spec §7.3 steps 0–3. Shared with `generate.submit` step 5.
pub async fn estimate_cost(
  ctx: &OpContext,
  modality: GenerateModality,
  request: &Map<String, Value>,
) -> Result<PricedRequest, BridgeError> {
  validate_generate_request(modality, request)?;
  let input = estimate_input(modality, request)?;
  let omni_request = build_omni_request(input.fields, None);
  let result = with_call_timeout(ctx.limits.read_call_timeout, call_estimate_command(modality, omni_request, ctx.app.clone())).await?;
  let response = result.map_err(|error| map_omni_error(&error, OmniCallSite::Estimate))?;
  let raw = response.payload.map(|payload| payload.0).unwrap_or(Value::Null);
  let estimate = project_estimate(&raw);
  let maybe_effective_credits = effective_credits(&estimate, input.video_count);
  Ok(PricedRequest { estimate, maybe_effective_credits })
}

async fn call_estimate_command(modality: GenerateModality, request: OmniRequest, app: AppHandle) -> OmniResult {
  match modality {
    GenerateModality::Image => estimate_image_cost_command(request, app).await,
    GenerateModality::Video => estimate_video_cost_command(request, app).await,
    GenerateModality::Audio => estimate_audio_cost_command(request, app).await,
    GenerateModality::Mesh => estimate_mesh_cost_command(request, app).await,
    GenerateModality::Splat => estimate_splat_cost_command(request, app).await,
  }
}

/// `validate_generate_request` has already guaranteed a string `model`.
fn model_of(request: &Map<String, Value>) -> &str {
  request.get("model").and_then(Value::as_str).unwrap_or_default()
}
```

- [ ] **Step 6: Write `jobs_ops.rs` (list only; T13 adds get, T18 adds dismiss)**

```rust
use crate::core::cli_bridge::cli_bridge_envelope::{BridgeError, BridgeErrorCode};
use crate::core::cli_bridge::native_result_mapping::{map_storyteller_error, StorytellerCallSite};
use crate::core::cli_bridge::ops::job_view::{build_job_list, OriginFilter, RemoteJob};
use crate::core::cli_bridge::ops::op_support::{
  invalid_args, local_store_error, parse_args, require_session, task_database, to_data, with_call_timeout, OpContext,
};
use crate::core::state::app_env_configs::app_env_configs::AppEnvConfigs;
use crate::core::state::task_database::TaskDatabase;
use artcraft_client::endpoints::jobs::list_session_jobs::{list_session_jobs, States};
use serde_derive::Deserialize;
use serde_json::Value;
use sqlite_tasks::queries::list_tasks_for_frontend::{list_tasks_for_frontend, TaskItem};
use tauri::Manager;

const DEFAULT_LIST_LIMIT: usize = 50;
const MAX_LIST_LIMIT: usize = 200;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct JobsListRequest {
  #[serde(default)]
  origin: OriginFilter,
  #[serde(default = "default_list_limit")]
  limit: usize,
  #[serde(default)]
  include_remote: bool,
}

/// `jobs.list` (spec §7.6): newest first, local rows plus an optional remote merge.
pub async fn jobs_list(ctx: &OpContext, args: Value) -> Result<Value, BridgeError> {
  let request: JobsListRequest = parse_args(args)?;
  if !(1..=MAX_LIST_LIMIT).contains(&request.limit) {
    return Err(invalid_args("limit must be between 1 and 200"));
  }
  let db = task_database(&ctx.app)?;
  let local = list_local_tasks(&db).await?;
  let maybe_remote = if request.include_remote { Some(fetch_remote_jobs(ctx).await) } else { None };
  to_data(&build_job_list(&local, maybe_remote, request.origin, request.limit))
}

/// A row that fails to parse fails the whole query; that surfaces as `local_store_error` (spec §7.6).
pub async fn list_local_tasks(db: &TaskDatabase) -> Result<Vec<TaskItem>, BridgeError> {
  list_tasks_for_frontend(db.get_connection())
    .await
    .map(|task_list| task_list.tasks)
    .map_err(|_| local_store_error("the task database could not be read"))
}

/// The newest 100 remote jobs under a 10 s timeout. Failures become a code the merge reports.
pub async fn fetch_remote_jobs(ctx: &OpContext) -> Result<Vec<RemoteJob>, BridgeErrorCode> {
  let creds = require_session(&ctx.app).map_err(|error| error.code)?;
  let configs = ctx.app.state::<AppEnvConfigs>();
  let response = with_call_timeout(
    ctx.limits.remote_jobs_timeout,
    list_session_jobs(&configs.storyteller_host, Some(&creds), States::All),
  )
  .await
  .map_err(|error| error.code)?
  .map_err(|error| map_storyteller_error(&error, StorytellerCallSite::Other).code)?;
  Ok(response.jobs.iter().map(RemoteJob::from_item).collect())
}

fn default_list_limit() -> usize {
  DEFAULT_LIST_LIMIT
}
```

- [ ] **Step 7: Write op dispatch**

Replace `crates/desktop/artcraft/src/core/cli_bridge/op_dispatch.rs` with:
```rust
use crate::core::cli_bridge::cli_bridge_envelope::{BridgeError, BridgeErrorCode};
use crate::core::cli_bridge::cli_bridge_gate::DispatchFn;
use crate::core::cli_bridge::ops::account_ops::account_session;
use crate::core::cli_bridge::ops::app_ops::app_info;
use crate::core::cli_bridge::ops::generate_ops::generate_estimate;
use crate::core::cli_bridge::ops::jobs_ops::jobs_list;
use crate::core::cli_bridge::ops::models_ops::models_list;
use crate::core::cli_bridge::ops::op_support::{deadline_error, OpContext, OpLimits};
use futures::future::BoxFuture;
use serde_json::Value;
use std::sync::Arc;
use std::time::Duration;

/// The op allowlist, in spec §5.4 order. `GET /v1/health` reports it; the RPC handler refuses anything else with `unknown_op`.
pub const ALLOWED_OPS: &[&str] = &[
  "app.info",
  "account.session",
  "models.list",
  "generate.estimate",
  "jobs.list",
];

/// Production `DispatchFn`: every op runs as its own task on the Tauri runtime.
pub fn make_dispatch(ctx: OpContext) -> DispatchFn {
  Arc::new(move |op: String, args: Value| {
    let reply: BoxFuture<'static, Result<Value, BridgeError>> = Box::pin(dispatch_op(ctx.clone(), op, args));
    reply
  })
}

/// Spawned, so neither a client disconnect nor an expired deadline cancels an op halfway (spec §4.5).
async fn dispatch_op(ctx: OpContext, op: String, args: Value) -> Result<Value, BridgeError> {
  let deadline = op_deadline(&op, &ctx.limits);
  let handle = tauri::async_runtime::spawn(async move { run_op(&ctx, &op, args).await });
  match tokio::time::timeout(deadline, handle).await {
    Ok(Ok(result)) => result,
    Ok(Err(_)) => Err(BridgeError::new(BridgeErrorCode::InternalError, "the op failed inside the bridge; check the ArtCraft log")),
    Err(_) => Err(deadline_error()),
  }
}

async fn run_op(ctx: &OpContext, op: &str, args: Value) -> Result<Value, BridgeError> {
  match op {
    "app.info" => app_info(ctx, args),
    "account.session" => account_session(ctx, args).await,
    "models.list" => models_list(ctx, args).await,
    "generate.estimate" => generate_estimate(ctx, args).await,
    "jobs.list" => jobs_list(ctx, args).await,
    _ => Err(BridgeError::new(BridgeErrorCode::UnknownOp, "this op is not available on the bridge")),
  }
}

fn op_deadline(op: &str, limits: &OpLimits) -> Duration {
  match op {
    "generate.submit" | "media.upload" => limits.write_op_deadline,
    _ => limits.read_op_deadline,
  }
}
```

- [ ] **Step 8: Compile-check**

Run: `SQLX_OFFLINE=true cargo check -p artcraft`
Expected: `Finished` with no errors and no new warnings in `cli_bridge`. Fix any signature mismatch against the source, for example a `State` argument count or a renamed module, without changing behaviour.

- [ ] **Step 9: Run every bridge test**

Run: `SQLX_OFFLINE=true cargo test -p artcraft --lib cli_bridge`
Expected: PASS, `28 passed`: 4 (T2) + 13 (T3) + 2 (T4) + 4 (T5) + 5 (T6).

- [ ] **Step 10: Commit**

```bash
git add crates/desktop/artcraft/src/core/cli_bridge/op_dispatch.rs crates/desktop/artcraft/src/core/cli_bridge/ops/mod.rs crates/desktop/artcraft/src/core/cli_bridge/ops/app_ops.rs crates/desktop/artcraft/src/core/cli_bridge/ops/account_ops.rs crates/desktop/artcraft/src/core/cli_bridge/ops/models_ops.rs crates/desktop/artcraft/src/core/cli_bridge/ops/generate_ops.rs crates/desktop/artcraft/src/core/cli_bridge/ops/jobs_ops.rs
git commit -m "feat(cli-bridge): add M1 ops and deadline-bounded op dispatch"
```

### Task 8: Server bootstrap and startup wiring

**Files:**
- Modify: `crates/desktop/artcraft/src/core/cli_bridge/cli_bridge_server.rs` (the T2 file; replace its imports and add functions above `bind_and_publish`)
- Create: `crates/desktop/artcraft/src/core/lifecycle/startup/tasks/spawn_cli_bridge_server.rs`
- Modify: `crates/desktop/artcraft/src/core/lifecycle/startup/tasks/mod.rs` (append one line)
- Modify: `crates/desktop/artcraft/src/core/lifecycle/startup/handle_tauri_startup.rs` (1 `use`, 1 call after `:133`)

**Interfaces:**
- Consumes:
  - T2: `bind_and_publish`, `remove_discovery_file_if_owned`, `CliBridgeToken`.
  - T3: `build_router`, `GateState`, `HealthInfo`, `Readiness`, `ReadinessFn`, `MAX_IN_FLIGHT`.
  - T4: `OpContext::new`.
  - T7: `make_dispatch`.
- Produces:
  - `run_cli_bridge_server(AppHandle, AppDataRoot)` (async, infallible)
  - `spawn_cli_bridge_server(&AppHandle, &AppDataRoot) -> AnyhowResult<()>`

Wiring only. It is verified by `cargo check`, the bridge tests and the T9 live checklist: items (a), (b) and (i) exercise exactly this code.

- [ ] **Step 1: Extend `cli_bridge_server.rs`**

Replace the import block at the top of `cli_bridge_server.rs` (the 7 `use` lines from T2) with the block below. Then insert the functions between the imports and `bind_and_publish`. `bind_and_publish` and the test module stay unchanged.
```rust
use crate::core::cli_bridge::cli_bridge_discovery_file::{
  remove_discovery_file_if_owned, write_discovery_file, CliBridgeDiscoveryFile, BRIDGE_PROTOCOL_VERSION,
};
use crate::core::cli_bridge::cli_bridge_gate::{build_router, GateState, HealthInfo, Readiness, ReadinessFn, MAX_IN_FLIGHT};
use crate::core::cli_bridge::cli_bridge_token::CliBridgeToken;
use crate::core::cli_bridge::op_dispatch::make_dispatch;
use crate::core::cli_bridge::ops::op_support::OpContext;
use crate::core::state::data_dir::app_data_root::AppDataRoot;
use crate::core::state::data_dir::trait_data_subdir::DataSubdir;
use crate::services::storyteller::state::storyteller_credential_manager::StorytellerCredentialManager;
use crate::version::ARTCRAFT_VERSION;
use chrono::{SecondsFormat, Utc};
use errors::AnyhowResult;
use log::{error, info, warn};
use std::net::Ipv4Addr;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use tauri::plugin::{Builder as PluginBuilder, TauriPlugin};
use tauri::{AppHandle, Manager, RunEvent, Wry};
use tokio::net::TcpListener;
use tokio::sync::Semaphore;

const EXIT_PLUGIN_NAME: &str = "cli_bridge";

/// Runs the bridge for the life of the app. Every failure is logged and leaves the app running (spec §4.1).
pub async fn run_cli_bridge_server(app: AppHandle, root: AppDataRoot) {
  match serve(app, root).await {
    Ok(()) => warn!("cli bridge stopped"),
    Err(err) => error!("cli bridge failed: {}", err),
  }
}

async fn serve(app: AppHandle, root: AppDataRoot) -> AnyhowResult<()> {
  let token = CliBridgeToken::generate()?;
  let state_dir = root.state_dir().path().to_path_buf();
  // Registered before bind, so a discovery file can never outlive this process.
  app.plugin(exit_cleanup_plugin(state_dir.clone(), std::process::id(), token.as_hex().to_string()))?;
  let (listener, published) = bind_and_publish(&state_dir, &token, ARTCRAFT_VERSION).await?;
  let port = published.port;
  let gate_state = GateState {
    port,
    token,
    in_flight: Arc::new(Semaphore::new(MAX_IN_FLIGHT)),
    health: HealthInfo {
      app_version: published.app_version,
      pid: published.pid,
      started_at: published.started_at,
    },
    readiness: readiness_from(&app),
  };
  let dispatch = make_dispatch(OpContext::new(app, root));
  info!("cli bridge listening on 127.0.0.1:{}", port);
  axum::serve(listener, build_router(gate_state, dispatch)).await?;
  Ok(())
}

```
Then append these two functions below `bind_and_publish` and above `#[cfg(test)]`:
```rust
/// Removes the discovery file on `RunEvent::Exit`. Added at runtime, so `lib.rs` is untouched (spec §4.3).
fn exit_cleanup_plugin(state_dir: PathBuf, pid: u32, token_hex: String) -> TauriPlugin<Wry> {
  PluginBuilder::new(EXIT_PLUGIN_NAME)
    .on_event(move |_app, event| {
      if !matches!(event, RunEvent::Exit) {
        return;
      }
      if let Err(err) = remove_discovery_file_if_owned(&state_dir, pid, &token_hex) {
        warn!("cli bridge could not remove its discovery file: {}", err);
      }
    })
    .build()
}

/// `GET /v1/health` readiness from the in-memory credential set: no network call (spec §5.4).
fn readiness_from(app: &AppHandle) -> ReadinessFn {
  let app = app.clone();
  Arc::new(move || {
    let maybe_creds = app
      .try_state::<StorytellerCredentialManager>()
      .and_then(|manager| manager.get_credentials().ok().flatten());
    Readiness {
      credentials_synced: maybe_creds.is_some(),
      session_cookie_present: maybe_creds.is_some_and(|creds| creds.session.is_some()),
    }
  })
}

```

- [ ] **Step 2: Create the startup task**

Create `crates/desktop/artcraft/src/core/lifecycle/startup/tasks/spawn_cli_bridge_server.rs`:
```rust
use crate::core::cli_bridge::cli_bridge_server::run_cli_bridge_server;
use crate::core::state::data_dir::app_data_root::AppDataRoot;
use errors::AnyhowResult;
use log::info;
use tauri::AppHandle;

const CLI_BRIDGE_ENV_VAR: &str = "ARTCRAFT_CLI_BRIDGE";

/// Starts the CLI bridge only when `ARTCRAFT_CLI_BRIDGE=1`. Never blocks launch and always returns `Ok`.
pub fn spawn_cli_bridge_server(app: &AppHandle, root: &AppDataRoot) -> AnyhowResult<()> {
  if std::env::var(CLI_BRIDGE_ENV_VAR).as_deref() != Ok("1") {
    info!("cli bridge disabled");
    return Ok(());
  }
  tauri::async_runtime::spawn(run_cli_bridge_server(app.clone(), root.clone()));
  Ok(())
}
```

Append to `crates/desktop/artcraft/src/core/lifecycle/startup/tasks/mod.rs`:
```rust
pub (super) mod spawn_cli_bridge_server;
```

- [ ] **Step 3: Call it at startup**

In `crates/desktop/artcraft/src/core/lifecycle/startup/handle_tauri_startup.rs`, insert after line 8 (`use crate::core::lifecycle::startup::tasks::spawn_storyteller_threads::spawn_storyteller_threads;`):
```rust
use crate::core::lifecycle::startup::tasks::spawn_cli_bridge_server::spawn_cli_bridge_server;
```
Then insert after `initially_size_and_position_windows(&app, &root);` (line 133 before the edit) and before `Ok(())`:
```rust

  spawn_cli_bridge_server(&app, &root)?;
```

- [ ] **Step 4: Compile-check**

Run: `SQLX_OFFLINE=true cargo check -p artcraft`
Expected: `Finished` with no errors. If `AppHandle::plugin` or `PluginBuilder::new` reject the closure's signature, check the tauri version in `Cargo.lock`. Use the `on_event` closure form that version documents, and keep the behaviour.

- [ ] **Step 5: Run every bridge test**

Run: `SQLX_OFFLINE=true cargo test -p artcraft --lib cli_bridge`
Expected: PASS, `28 passed`.

- [ ] **Step 6: Commit**

```bash
git add crates/desktop/artcraft/src/core/cli_bridge/cli_bridge_server.rs crates/desktop/artcraft/src/core/lifecycle/startup/tasks/spawn_cli_bridge_server.rs crates/desktop/artcraft/src/core/lifecycle/startup/tasks/mod.rs crates/desktop/artcraft/src/core/lifecycle/startup/handle_tauri_startup.rs
git commit -m "feat(cli-bridge): start the bridge at launch when ARTCRAFT_CLI_BRIDGE=1"
```

### Task 9: M1 live checklist (user-run)

**Files:** none modified. Results go to project memory, and to the cli=api peer for spec §7.3.

**Interfaces:**
- Consumes: the M1 build.
- Produces:
  - The recorded answer to "does the image `cost_in_credits` cover `image_batch_count`?"
  - Confirmation that the runtime plugin receives `RunEvent::Exit`.

The user runs the app; the executing agent prepares the commands and records the results. Shell helpers (paste once per launch):
```bash
F=~/Artcraft/state/cli_bridge.json
PORT=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["port"])' "$F")
TOKEN=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["token"])' "$F")
B="http://127.0.0.1:$PORT"
rpc() { curl -s -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d "$1" "$B/v1/rpc"; echo; }
neg() { curl -s -w ' HTTP %{http_code}\n' "$@"; }
```

- [ ] **(a) Disabled by default.** Run `./script/artcraft/unix_dev.sh` with `ARTCRAFT_CLI_BRIDGE` unset.
  - `ls ~/Artcraft/state/cli_bridge.json` gives "No such file".
  - `lsof -nP -iTCP -sTCP:LISTEN | grep -i artcraft` shows no bridge listener.
  - The dev log shows `cli bridge disabled`.
- [ ] **(b) Enabled.** Quit the app, then run `ARTCRAFT_CLI_BRIDGE=1 ./script/artcraft/unix_dev.sh`.
  - `ls -l "$F"` shows `-rw-------`.
  - `python3 -c 'import json,sys; print(sorted(json.load(open(sys.argv[1]))))' "$F"` prints `['app_version', 'bridge_protocol_version', 'pid', 'port', 'started_at', 'token']`.
- [ ] **(c) Health.** Run `curl -s -H "Authorization: Bearer $TOKEN" "$B/v1/health"`.
  - It reports `bridge_protocol_version: 1` and the 5 M1 ops.
  - `credentials_synced` turns true about 1–2 s after the main window appears.
- [ ] **(d) App info.** `rpc '{"op":"app.info","args":{}}'` shows `artcraft_version: "0.41.0"`.
- [ ] **(e) Session.** `rpc '{"op":"account.session","args":{}}'` matches the UI when logged in. Log out in the app, re-run, and get `{"logged_in": false}`. Log back in.
- [ ] **(f) Jobs.** `rpc '{"op":"jobs.list","args":{"origin":"all","limit":200}}'` matches the task panel. `rpc '{"op":"jobs.list","args":{"origin":"all","include_remote":true}}'` adds `sources.remote: true`.
- [ ] **(g) Dry runs.** Credits (in the UI) and the task count must stay unchanged throughout.
  - `rpc '{"op":"models.list","args":{"kind":"image"}}'`: pick a `models[].model` id.
  - `rpc '{"op":"generate.estimate","args":{"modality":"image","request":{"model":"<id>","prompt":"x"}}}'` returns a price.
  - The same call with `"model":"recraft_3"` gives `unsupported_route`.
  - Placeholder refs: the same call with `"image_media_tokens":["mf_estimate_0"]` added, using a model with `image_refs_supported: true`. Record whether the server prices it or rejects the placeholder. The CLI's `--dry-run` sends these placeholders, so tell the peer.
  - Image batch: compare `cost_in_credits` for `"image_batch_count":1` vs `2`. Record whether the server total covers the batch.
  - Video: with a video model from `models.list {kind: "video"}`, `effective_credits` for `"video_batch_count":2` must be twice that for `1`. Confirm the app's own price display for a 2-video batch shows the same doubled figure.
  - Record both answers in project memory and send them to the cli=api peer, so the spec §7.3 note can be updated. The spec is theirs to edit.
  - **If the image batch-2 `cost_in_credits` equals batch-1, stop before M2.** Images must then be priced like video: strip the count key in `estimate_input` and multiply. Update `video_batches_are_priced_per_video_like_the_app` to cover image, and tell the user and the peer, because spend safety depends on it.
- [ ] **(h) curl negatives:**
  - `neg -H "Host: evil.test:$PORT" -H "Authorization: Bearer $TOKEN" "$B/v1/health"` gives `forbidden_host`, HTTP 403.
  - `neg -H "Origin: https://evil.test" -H "Authorization: Bearer $TOKEN" "$B/v1/health"` gives 403.
  - `neg -H "Sec-Fetch-Site: cross-site" -H "Authorization: Bearer $TOKEN" "$B/v1/health"` gives 403.
  - `neg "$B/v1/health"` gives `unauthorized`, HTTP 401.
  - `neg -X OPTIONS -H "Authorization: Bearer $TOKEN" "$B/v1/rpc"` gives `method_not_allowed`, HTTP 405.
  - `neg -H "Authorization: Bearer $TOKEN" -H 'Content-Type: text/plain' -d '{"op":"app.info","args":{}}' "$B/v1/rpc"` gives `unsupported_media_type`, HTTP 415.
  - `rpc '{"op":"tasks_nuke_all_command","args":{}}'` gives `unknown_op` (HTTP 200).
- [ ] **(i) Exit cleanup.** Cmd-Q the app, then `ls "$F"` gives "No such file". This is the first proof that a runtime-registered plugin receives `RunEvent::Exit`. If the file remains, stop and report: registering it in `lib.rs` would need the user's approval, because it edits a file the spec keeps unchanged.

When every box is checked, update the ARTC Plane work item for T9 and tell the peer that M1 Rust is live.

---

# M2 — Spending

### Task 10: The spend decision

**Files:**
- Modify: `crates/desktop/artcraft/src/core/cli_bridge/ops/generate_rules.rs`
- Test: a new `mod spend_tests` inside the existing `mod tests` of `generate_rules.rs`

**Interfaces:**
- Consumes (T5): `effective_credits`, `project_estimate`.
- Produces:
  - `decide_spend(maybe_effective_credits: Option<u64>, max_credits: u64, maybe_balance: Option<u64>) -> Result<u64, BridgeError>`
  - `needs_balance_check(effective_credits: u64) -> bool`

- [ ] **Step 1: Write the failing tests**

In `generate_rules.rs`, insert this sub-module inside `mod tests`, after `video_batches_are_priced_per_video_like_the_app` and before the `fn request` helper:
```rust
  mod spend_tests {
    use super::*;

    #[test]
    fn unknown_or_fractional_cost_is_refused_before_spend() {
      for raw in [json!({ "cost_in_credits": 2.5 }), json!({ "cost_in_credits": null }), json!({}), json!({ "cost_in_credits": -3 })] {
        let maybe_effective_credits = effective_credits(&project_estimate(&raw), 1);
        assert_eq!(maybe_effective_credits, None, "{raw}");
        let error = decide_spend(maybe_effective_credits, 1_000, Some(1_000)).unwrap_err();
        assert_eq!(error.code, BridgeErrorCode::EstimateUnavailable);
      }
    }

    #[test]
    fn cost_over_max_credits_is_refused_before_spend() {
      let error = decide_spend(Some(11), 10, None).unwrap_err();

      assert_eq!(error.code, BridgeErrorCode::CostExceedsLimit);
      assert_eq!(error.maybe_details, Some(json!({ "effective_credits": 11, "max_credits": 10 })));
      assert_eq!(decide_spend(Some(10), 10, None).unwrap(), 10);
    }

    #[test]
    fn free_or_unlimited_generations_skip_the_balance_check() {
      for raw in [json!({ "cost_in_credits": 40, "is_free": true }), json!({ "cost_in_credits": 40, "is_unlimited": true })] {
        let effective = effective_credits(&project_estimate(&raw), 3).unwrap();
        assert_eq!(effective, 0);
        assert!(!needs_balance_check(effective));
        // A zero cap and a zero balance still allow a free generation.
        assert_eq!(decide_spend(Some(effective), 0, Some(0)).unwrap(), 0);
      }
      assert!(needs_balance_check(1));
    }

    #[test]
    fn balance_below_estimate_is_refused_before_spend() {
      assert_eq!(decide_spend(Some(8), 10, Some(5)).unwrap_err().code, BridgeErrorCode::InsufficientCredits);
      assert_eq!(decide_spend(Some(8), 10, Some(8)).unwrap(), 8);
    }
  }

```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `SQLX_OFFLINE=true cargo test -p artcraft --lib generate_rules`
Expected: FAIL to compile with `cannot find function decide_spend` and `cannot find function needs_balance_check`.

- [ ] **Step 3: Implement the decision**

In `generate_rules.rs`, insert after `effective_credits` and before `fn is_reserved_key`:
```rust
/// Spec §7.4 steps 5–6 as one pure decision. `maybe_balance` stays `None` until the balance is
/// fetched, which happens only when `needs_balance_check` says credits will be spent.
pub fn decide_spend(maybe_effective_credits: Option<u64>, max_credits: u64, maybe_balance: Option<u64>) -> Result<u64, BridgeError> {
  let Some(effective_credits) = maybe_effective_credits else {
    return Err(BridgeError::new(BridgeErrorCode::EstimateUnavailable, "the cost of this request is unknown, so it was not submitted"));
  };
  if effective_credits > max_credits {
    return Err(
      BridgeError::new(BridgeErrorCode::CostExceedsLimit, "the estimate is above max_credits")
        .with_details(json!({ "effective_credits": effective_credits, "max_credits": max_credits })),
    );
  }
  if maybe_balance.is_some_and(|balance| effective_credits > balance) {
    return Err(BridgeError::new(BridgeErrorCode::InsufficientCredits, "the account balance is below the estimate"));
  }
  Ok(effective_credits)
}

/// Free and unlimited generations never call the balance endpoint.
pub fn needs_balance_check(effective_credits: u64) -> bool {
  effective_credits > 0
}

```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `SQLX_OFFLINE=true cargo test -p artcraft --lib generate_rules`
Expected: PASS, `8 passed`.

- [ ] **Step 5: Commit**

```bash
git add crates/desktop/artcraft/src/core/cli_bridge/ops/generate_rules.rs
git commit -m "feat(cli-bridge): add pure spend decision for submit"
```

### Task 11: Submit core (in-flight set, replay, hard cap)

**Files:**
- Modify: `crates/desktop/artcraft/src/core/commands/generate/omni/dispatch.rs:161`. This is the only change to existing logic: visibility only.
- Modify: `crates/desktop/artcraft/src/core/cli_bridge/ops/mod.rs`
- Create: `crates/desktop/artcraft/src/core/cli_bridge/ops/generate_submit.rs`
- Create: `crates/desktop/artcraft/src/core/cli_bridge/ops/test_tasks.rs`
- Test: bottom `mod tests` of `generate_submit.rs`

**Interfaces:**
- Consumes:
  - T4: `map_omni_error`, `outcome_unknown`, `OmniCallSite`, `local_store_error`.
  - T5: `SUBSCRIBER_ID_PREFIX`.
  - T6: `modality_of`.
  - App: `job_tokens(&Value) -> Vec<String>`.
- Produces:
  - `#[derive(Clone, Default)] struct InFlightTokens`, with `try_claim(&self, &str) -> Option<InFlightGuard>`.
  - `struct InFlightGuard`, which frees its token on `Drop`.
  - `struct ApprovedSpend { estimate: Value, effective_credits: u64 }`
  - `run_submit<A, AF, P, PF>(db: &TaskDatabase, in_flight: &InFlightTokens, idempotency_token: &str, hard_cap: Duration, approve_spend: A, post: P) -> Result<Value, BridgeError>`, where `A: FnOnce() -> AF`, `AF: Future<Output = Result<ApprovedSpend, BridgeError>>`, `P: FnOnce() -> PF`, `PF: Future<Output = OmniResult>`.
  - Test-only: `temp_task_database() -> (TempDir, TaskDatabase)`, `insert_artcraft_task(&TaskDatabase, job_id: &str, Option<&str>) -> TaskId`, `TEST_MODEL`.

- [ ] **Step 1: Make `job_tokens` reachable from the bridge**

In `crates/desktop/artcraft/src/core/commands/generate/omni/dispatch.rs:161`, change `fn job_tokens(response: &Value) -> Vec<String> {` to:
```rust
pub(crate) fn job_tokens(response: &Value) -> Vec<String> {
```

- [ ] **Step 2: Declare the modules**

Replace `crates/desktop/artcraft/src/core/cli_bridge/ops/mod.rs` with:
```rust
pub mod account_ops;
pub mod app_ops;
pub mod generate_ops;
pub mod generate_rules;
pub mod generate_submit;
pub mod job_view;
pub mod jobs_ops;
pub mod models_ops;
pub mod op_support;
#[cfg(test)]
pub mod test_tasks;
```

- [ ] **Step 3: Write the task-database fixtures**

Create `crates/desktop/artcraft/src/core/cli_bridge/ops/test_tasks.rs`:
```rust
use crate::core::commands::enqueue::task_enqueue_success::TaskEnqueueSuccess;
use crate::core::events::generation_events::common::GenerationModel;
use crate::core::state::data_dir::app_data_root::AppDataRoot;
use crate::core::state::task_database::TaskDatabase;
use enums::common::generation_provider::GenerationProvider;
use enums::tauri::tasks::task_type::TaskType;
use tempfile::TempDir;
use tokens::tokens::sqlite::tasks::TaskId;

pub const TEST_MODEL: &str = "gpt_image_1";

/// A real, migrated SQLite task database under a temp dir. Keep the `TempDir` alive for the whole test.
pub async fn temp_task_database() -> (TempDir, TaskDatabase) {
  let dir = tempfile::tempdir().unwrap();
  let root = AppDataRoot::create_existing(dir.path()).unwrap();
  let database = TaskDatabase::connect(&root).await.unwrap();
  (dir, database)
}

/// Inserts a row exactly as the Omni dispatch does after an accepted POST (`dispatch.rs:76-82`).
pub async fn insert_artcraft_task(database: &TaskDatabase, job_id: &str, maybe_subscriber_id: Option<&str>) -> TaskId {
  TaskEnqueueSuccess {
    task_type: TaskType::ImageGeneration,
    model: Some(GenerationModel::Unknown(TEST_MODEL.to_string())),
    provider: GenerationProvider::Artcraft,
    provider_job_id: Some(job_id.to_string()),
    maybe_queue_status_url: None,
    maybe_queue_response_url: None,
    maybe_prompt_token: None,
  }
  .insert_into_task_database_with_frontend_payload(database, None, maybe_subscriber_id, None)
  .await
  .unwrap()
}
```

- [ ] **Step 4: Write the failing tests**

Create `crates/desktop/artcraft/src/core/cli_bridge/ops/generate_submit.rs` containing only:
```rust
#[cfg(test)]
mod tests {
  use super::*;
  use crate::core::cli_bridge::ops::test_tasks::{insert_artcraft_task, temp_task_database, TEST_MODEL};
  use crate::core::commands::generate::omni::OmniResponse;
  use crate::core::commands::response::failure_response_wrapper::{CommandErrorResponseWrapper, CommandErrorStatus};
  use futures::future::BoxFuture;
  use std::sync::atomic::{AtomicUsize, Ordering};
  use tokio::sync::Notify;

  const TOKEN: &str = "0f8c2a1e-3b4d-4e5f-8a9b-0c1d2e3f4a5b";
  const OTHER_TOKEN: &str = "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d";
  const HARD_CAP: Duration = Duration::from_secs(5);

  #[tokio::test]
  async fn pre_post_failures_in_submit_never_become_outcome_unknown() {
    let (_dir, db) = temp_task_database().await;
    let failures = [
      // A server error from the step-5 estimate is a free retry, never a possible charge.
      map_omni_error(&server_error(), OmniCallSite::Estimate),
      BridgeError::new(BridgeErrorCode::CredentialsNotSynced, "not yet"),
      BridgeError::new(BridgeErrorCode::NotLoggedIn, "logged out"),
      BridgeError::new(BridgeErrorCode::EstimateUnavailable, "unknown cost"),
      BridgeError::new(BridgeErrorCode::CostExceedsLimit, "too expensive"),
      BridgeError::new(BridgeErrorCode::InsufficientCredits, "balance too low"),
    ];
    for failure in failures {
      let expected = failure.code;
      let posts = Arc::new(AtomicUsize::new(0));

      let result = run_submit(
        &db,
        &InFlightTokens::default(),
        TOKEN,
        HARD_CAP,
        move || async move { Err::<ApprovedSpend, BridgeError>(failure) },
        counting_post(posts.clone(), &["jinf_new"]),
      ).await;

      let code = result.unwrap_err().code;
      assert_eq!(code, expected);
      assert_ne!(code, BridgeErrorCode::OutcomeUnknown);
      assert_eq!(posts.load(Ordering::SeqCst), 0);
    }
  }

  mod replay_tests {
    use super::*;

    #[tokio::test]
    async fn resubmitting_a_tagged_token_replays_every_batch_row_without_posting() {
      let (_dir, db) = temp_task_database().await;
      let subscriber_id = format!("{SUBSCRIBER_ID_PREFIX}{TOKEN}");
      insert_artcraft_task(&db, "jinf_batch_a", Some(&subscriber_id)).await;
      insert_artcraft_task(&db, "jinf_batch_b", Some(&subscriber_id)).await;
      let calls = Arc::new(AtomicUsize::new(0));

      let data = run_submit(
        &db,
        &InFlightTokens::default(),
        TOKEN,
        HARD_CAP,
        counting_approval(calls.clone()),
        counting_post(calls.clone(), &["jinf_new"]),
      ).await.unwrap();

      let mut job_ids: Vec<String> = serde_json::from_value(data["job_ids"].clone()).unwrap();
      job_ids.sort();
      assert_eq!(job_ids, vec!["jinf_batch_a", "jinf_batch_b"]);
      assert_eq!(data["replayed"], true);
      assert_eq!(data["replayed_from"], json!({ "modality": "image", "model": TEST_MODEL }));
      // A replay repeats no estimate, so it carries none.
      assert!(data.get("estimate").is_none());
      assert!(data.get("effective_credits").is_none());
      assert_eq!(calls.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn untagged_tasks_are_never_replayed() {
      let (_dir, db) = temp_task_database().await;
      insert_artcraft_task(&db, "jinf_ui", None).await;
      insert_artcraft_task(&db, "jinf_ui_page", Some("image-page-subscriber")).await;
      insert_artcraft_task(&db, "jinf_other_token", Some(&format!("{SUBSCRIBER_ID_PREFIX}{OTHER_TOKEN}"))).await;
      let approvals = Arc::new(AtomicUsize::new(0));
      let posts = Arc::new(AtomicUsize::new(0));

      let data = run_submit(
        &db,
        &InFlightTokens::default(),
        TOKEN,
        HARD_CAP,
        counting_approval(approvals.clone()),
        counting_post(posts.clone(), &["jinf_new"]),
      ).await.unwrap();

      assert_eq!(data["replayed"], false);
      assert_eq!(data["job_ids"], json!(["jinf_new"]));
      assert_eq!(data["effective_credits"], 4);
      assert_eq!(approvals.load(Ordering::SeqCst), 1);
      assert_eq!(posts.load(Ordering::SeqCst), 1);
    }
  }

  mod in_flight_tests {
    use super::*;

    #[tokio::test]
    async fn concurrent_submits_with_one_token_post_once() {
      let (_dir, db) = temp_task_database().await;
      let in_flight = InFlightTokens::default();
      let posts = Arc::new(AtomicUsize::new(0));
      let entered = Arc::new(Notify::new());
      let release = Arc::new(Notify::new());
      let first = {
        let (db, in_flight, posts, entered, release) = (db.clone(), in_flight.clone(), posts.clone(), entered.clone(), release.clone());
        tokio::spawn(async move {
          let blocking_post = move || -> BoxFuture<'static, OmniResult> {
            posts.fetch_add(1, Ordering::SeqCst);
            Box::pin(async move {
              entered.notify_one();
              release.notified().await;
              accepted(&["jinf_first"])
            })
          };
          run_submit(&db, &in_flight, TOKEN, HARD_CAP, counting_approval(Arc::new(AtomicUsize::new(0))), blocking_post).await
        })
      };
      entered.notified().await;

      let second = run_submit(
        &db,
        &in_flight,
        TOKEN,
        HARD_CAP,
        counting_approval(Arc::new(AtomicUsize::new(0))),
        counting_post(posts.clone(), &["jinf_second"]),
      ).await;
      release.notify_one();
      let first = first.await.unwrap();

      assert_eq!(second.unwrap_err().code, BridgeErrorCode::OperationInProgress);
      assert_eq!(first.unwrap()["job_ids"], json!(["jinf_first"]));
      assert_eq!(posts.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn stalled_submit_returns_outcome_unknown_and_frees_its_token_after_the_hard_cap() {
      let (_dir, db) = temp_task_database().await;
      let in_flight = InFlightTokens::default();

      let stalled = run_submit(
        &db,
        &in_flight,
        TOKEN,
        Duration::from_millis(50),
        counting_approval(Arc::new(AtomicUsize::new(0))),
        || std::future::pending::<OmniResult>(),
      ).await;

      let error = stalled.unwrap_err();
      assert_eq!(error.code, BridgeErrorCode::OutcomeUnknown);
      assert_eq!(error.maybe_details, Some(json!({ "idempotency_token": TOKEN, "reason": "deadline" })));
      // The token is free again, so a retry reaches the replay check instead of `operation_in_progress`.
      assert!(in_flight.try_claim(TOKEN).is_some());
    }
  }

  fn counting_approval(calls: Arc<AtomicUsize>) -> impl FnOnce() -> BoxFuture<'static, Result<ApprovedSpend, BridgeError>> {
    move || {
      calls.fetch_add(1, Ordering::SeqCst);
      Box::pin(async { Ok(ApprovedSpend { estimate: json!({ "cost_in_credits": 4 }), effective_credits: 4 }) })
    }
  }

  fn counting_post(posts: Arc<AtomicUsize>, job_ids: &[&str]) -> impl FnOnce() -> BoxFuture<'static, OmniResult> {
    let response = accepted(job_ids);
    move || {
      posts.fetch_add(1, Ordering::SeqCst);
      Box::pin(async move { response })
    }
  }

  fn accepted(job_ids: &[&str]) -> OmniResult {
    Ok(OmniResponse(json!({ "inference_job_token": job_ids[0], "all_job_tokens": job_ids })).into())
  }

  fn server_error() -> CommandErrorResponseWrapper<String, ()> {
    CommandErrorResponseWrapper {
      status: CommandErrorStatus::ServerError,
      error_message: Some("boom".to_string()),
      error_type: Some("server_error".to_string()),
      error_details: None,
    }
  }
}
```

- [ ] **Step 5: Run the tests to verify they fail**

Run: `SQLX_OFFLINE=true cargo test -p artcraft --lib generate_submit`
Expected: FAIL to compile with `cannot find function run_submit` and `cannot find struct InFlightTokens`.

- [ ] **Step 6: Implement the submit core**

Insert above `#[cfg(test)]` in `generate_submit.rs`:
```rust
use crate::core::cli_bridge::cli_bridge_envelope::{BridgeError, BridgeErrorCode};
use crate::core::cli_bridge::native_result_mapping::{map_omni_error, outcome_unknown, OmniCallSite};
use crate::core::cli_bridge::ops::generate_rules::SUBSCRIBER_ID_PREFIX;
use crate::core::cli_bridge::ops::job_view::modality_of;
use crate::core::cli_bridge::ops::op_support::local_store_error;
use crate::core::commands::generate::omni::dispatch::job_tokens;
use crate::core::commands::generate::omni::OmniResult;
use crate::core::state::task_database::TaskDatabase;
use serde_json::{json, Value};
use sqlite_tasks::queries::list_tasks_for_frontend::{list_tasks_for_frontend, TaskItem};
use std::collections::HashSet;
use std::future::Future;
use std::sync::{Arc, Mutex, PoisonError};
use std::time::Duration;

/// Idempotency tokens whose submit is running right now (spec §7.4 step 2).
#[derive(Clone, Default)]
pub struct InFlightTokens {
  tokens: Arc<Mutex<HashSet<String>>>,
}

/// Holds one token. Dropping it frees the token however the submit ends: success, error, panic or hard cap.
pub struct InFlightGuard {
  tokens: InFlightTokens,
  token: String,
}

/// What steps 4–6 approved: the estimate to echo back and the credits it will spend.
pub struct ApprovedSpend {
  pub estimate: Value,
  pub effective_credits: u64,
}

impl InFlightTokens {
  pub fn try_claim(&self, token: &str) -> Option<InFlightGuard> {
    let mut tokens = self.tokens.lock().unwrap_or_else(PoisonError::into_inner);
    if !tokens.insert(token.to_string()) {
      return None;
    }
    Some(InFlightGuard { tokens: self.clone(), token: token.to_string() })
  }
}

impl Drop for InFlightGuard {
  fn drop(&mut self) {
    let mut tokens = self.tokens.tokens.lock().unwrap_or_else(PoisonError::into_inner);
    tokens.remove(&self.token);
  }
}

/// Spec §7.4 steps 2–9. Step 1 (validation) runs before this. The op task that `dispatch_op`
/// spawns is the "detached task": it outlives the 120 s op deadline, and `hard_cap` bounds step 7.
pub async fn run_submit<A, AF, P, PF>(
  db: &TaskDatabase,
  in_flight: &InFlightTokens,
  idempotency_token: &str,
  hard_cap: Duration,
  approve_spend: A,
  post: P,
) -> Result<Value, BridgeError>
where
  A: FnOnce() -> AF,
  AF: Future<Output = Result<ApprovedSpend, BridgeError>>,
  P: FnOnce() -> PF,
  PF: Future<Output = OmniResult>,
{
  let Some(_guard) = in_flight.try_claim(idempotency_token) else {
    return Err(BridgeError::new(BridgeErrorCode::OperationInProgress, "a submit with this idempotency token is still running"));
  };
  let subscriber_id = format!("{SUBSCRIBER_ID_PREFIX}{idempotency_token}");
  if let Some(replayed) = find_replay(db, &subscriber_id, idempotency_token).await? {
    return Ok(replayed);
  }
  let spend = approve_spend().await?;
  // Only this call can produce `outcome_unknown`: everything above failed before any POST.
  let response = match tokio::time::timeout(hard_cap, post()).await {
    Ok(Ok(response)) => response,
    Ok(Err(error)) => return Err(map_omni_error(&error, OmniCallSite::SubmitPost { idempotency_token })),
    Err(_) => return Err(outcome_unknown(idempotency_token, "deadline")),
  };
  let job_ids = response.payload.map(|payload| job_tokens(&payload.0)).unwrap_or_default();
  if job_ids.is_empty() {
    return Err(outcome_unknown(idempotency_token, "server_error"));
  }
  Ok(json!({
    "job_ids": job_ids,
    "idempotency_token": idempotency_token,
    "estimate": spend.estimate,
    "effective_credits": spend.effective_credits,
    "replayed": false,
  }))
}

/// Spec §7.4 step 3: every row tagged with this token, so a batch replays in full. Dismissed rows
/// are filtered out of this query, so their tokens POST again (a documented edge case).
async fn find_replay(db: &TaskDatabase, subscriber_id: &str, idempotency_token: &str) -> Result<Option<Value>, BridgeError> {
  let task_list = list_tasks_for_frontend(db.get_connection())
    .await
    .map_err(|_| local_store_error("the task database could not be read"))?;
  let rows: Vec<&TaskItem> = task_list
    .tasks
    .iter()
    .filter(|task| task.frontend_subscriber_id.as_deref() == Some(subscriber_id))
    .collect();
  let job_ids: Vec<&str> = rows.iter().filter_map(|task| task.provider_job_id.as_deref()).collect();
  let Some(first) = rows.first() else {
    return Ok(None);
  };
  if job_ids.is_empty() {
    return Ok(None);
  }
  Ok(Some(json!({
    "job_ids": job_ids,
    "idempotency_token": idempotency_token,
    "replayed": true,
    "replayed_from": {
      "modality": modality_of(&first.task_type).map(|modality| modality.to_str()),
      "model": first.model_type.as_ref().map(|model| model.to_str()),
    },
  })))
}

```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `SQLX_OFFLINE=true cargo test -p artcraft --lib generate_submit`
Expected: PASS, `5 passed`. If `AppDataRoot::create_existing` does not create the state subdirectory that `TaskDatabase::connect` needs, create `dir.path().join("state")` in `temp_task_database` first. Check `S/core/state/data_dir/app_data_root.rs:42` for the subdirectory name, then re-run.

- [ ] **Step 8: Run every bridge test**

Run: `SQLX_OFFLINE=true cargo test -p artcraft --lib cli_bridge`
Expected: PASS, `37 passed`.

- [ ] **Step 9: Commit**

```bash
git add crates/desktop/artcraft/src/core/commands/generate/omni/dispatch.rs crates/desktop/artcraft/src/core/cli_bridge/ops/mod.rs crates/desktop/artcraft/src/core/cli_bridge/ops/generate_submit.rs crates/desktop/artcraft/src/core/cli_bridge/ops/test_tasks.rs
git commit -m "feat(cli-bridge): add idempotent submit core with replay and hard cap"
```

### Task 12: `generate.submit`, `account.credits`, `account.subscription`

**Files:**
- Modify: `crates/desktop/artcraft/src/core/cli_bridge/ops/op_support.rs` (`OpContext` gains `in_flight_tokens`)
- Modify: `crates/desktop/artcraft/src/core/cli_bridge/ops/generate_ops.rs` (full replacement below)
- Modify: `crates/desktop/artcraft/src/core/cli_bridge/ops/account_ops.rs` (full replacement below)
- Modify: `crates/desktop/artcraft/src/core/cli_bridge/op_dispatch.rs` (full replacement below)

**Interfaces:**
- Consumes:
  - T7: `estimate_cost`, `PricedRequest`.
  - T10: `decide_spend`, `needs_balance_check`.
  - T11: `run_submit`, `ApprovedSpend`, `InFlightTokens`.
- Produces:
  - `generate_submit(&OpContext, Value)`
  - `account_credits(&OpContext, Value)`, `account_subscription(&OpContext, Value)`
  - `fetch_credit_balance(&OpContext, &StorytellerCredentialSet) -> Result<u64, BridgeError>`
  - `ALLOWED_OPS`, now 8 ops.

Wiring only: the logic it composes was unit-tested in T10 and T11. It is verified by `cargo check`, the bridge tests and the T14 live checklist.

- [ ] **Step 1: Give `OpContext` the in-flight set**

In `op_support.rs`, add `use crate::core::cli_bridge::ops::generate_submit::InFlightTokens;` to the imports. Then replace the `OpContext` struct and its `impl` with:
```rust
/// What every op runs with. Cloned into each spawned op; clones share the in-flight set.
#[derive(Clone)]
pub struct OpContext {
  pub app: AppHandle,
  pub root: AppDataRoot,
  pub limits: OpLimits,
  pub in_flight_tokens: InFlightTokens,
}
```
```rust
impl OpContext {
  pub fn new(app: AppHandle, root: AppDataRoot) -> Self {
    Self {
      app,
      root,
      limits: OpLimits::production(),
      in_flight_tokens: InFlightTokens::default(),
    }
  }
}
```

- [ ] **Step 2: Replace `account_ops.rs`**

```rust
use crate::core::cli_bridge::cli_bridge_envelope::BridgeError;
use crate::core::cli_bridge::native_result_mapping::{map_login_result, map_storyteller_error, StorytellerCallSite};
use crate::core::cli_bridge::ops::op_support::{parse_args, require_session, with_call_timeout, EmptyRequest, OpContext};
use crate::core::state::app_env_configs::app_env_configs::AppEnvConfigs;
use crate::services::storyteller::commands::storyteller_get_login_session_command::storyteller_get_login_session_command;
use artcraft_api_defs::credits::get_session_credits::GetSessionCreditsResponse;
use artcraft_client::credentials::storyteller_credential_set::StorytellerCredentialSet;
use artcraft_client::endpoints::credits::get_session_credits::get_session_credits;
use artcraft_client::endpoints::subscriptions::get_session_subscription::get_session_subscription;
use enums::common::artcraft_subscription_slug::ArtcraftSubscriptionSlug;
use enums::common::payments_namespace::PaymentsNamespace;
use serde_json::{json, Value};
use tauri::Manager;

/// `account.session` (spec §5.5). A 401/403 from the session check is a logged-out answer.
pub async fn account_session(ctx: &OpContext, args: Value) -> Result<Value, BridgeError> {
  let _: EmptyRequest = parse_args(args)?;
  let login = with_call_timeout(
    ctx.limits.read_call_timeout,
    storyteller_get_login_session_command(ctx.app.clone(), ctx.app.state()),
  ).await?;
  Ok(match map_login_result(login)? {
    Some(user) => json!({
      "logged_in": true,
      "username": user.username,
      "display_name": user.display_name,
      "user_token": user.user_token.as_str(),
    }),
    None => json!({ "logged_in": false }),
  })
}

/// `account.credits`, called directly: the command flattens every error to `bad_request` (spec §5.5).
pub async fn account_credits(ctx: &OpContext, args: Value) -> Result<Value, BridgeError> {
  let _: EmptyRequest = parse_args(args)?;
  let creds = require_session(&ctx.app)?;
  let credits = get_credits(ctx, &creds).await?;
  Ok(json!({
    "free_credits": credits.free_credits,
    "monthly_credits": credits.monthly_credits,
    "banked_credits": credits.banked_credits,
    "sum_total_credits": credits.sum_total_credits,
  }))
}

/// `account.subscription`. Unknown product slugs read as no subscription, like the app's command.
pub async fn account_subscription(ctx: &OpContext, args: Value) -> Result<Value, BridgeError> {
  let _: EmptyRequest = parse_args(args)?;
  let creds = require_session(&ctx.app)?;
  let configs = ctx.app.state::<AppEnvConfigs>();
  let response = with_call_timeout(
    ctx.limits.read_call_timeout,
    get_session_subscription(&configs.storyteller_host, Some(&creds), PaymentsNamespace::Artcraft),
  )
  .await?
  .map_err(|error| map_storyteller_error(&error, StorytellerCallSite::Other))?;
  let maybe_active = response
    .active_subscription
    .filter(|subscription| ArtcraftSubscriptionSlug::from_str(&subscription.product_slug).is_ok())
    .map(|subscription| json!({
      "product_slug": subscription.product_slug,
      "namespace": subscription.namespace.to_str(),
      "next_bill_at": subscription.next_bill_at,
      "subscription_end_at": subscription.subscription_end_at,
    }));
  Ok(json!({ "active_subscription": maybe_active }))
}

/// Spec §7.4 step 6: the balance a paid submit is checked against.
pub async fn fetch_credit_balance(ctx: &OpContext, creds: &StorytellerCredentialSet) -> Result<u64, BridgeError> {
  Ok(get_credits(ctx, creds).await?.sum_total_credits)
}

async fn get_credits(ctx: &OpContext, creds: &StorytellerCredentialSet) -> Result<GetSessionCreditsResponse, BridgeError> {
  let configs = ctx.app.state::<AppEnvConfigs>();
  with_call_timeout(
    ctx.limits.read_call_timeout,
    get_session_credits(&configs.storyteller_host, Some(creds), PaymentsNamespace::Artcraft),
  )
  .await?
  .map_err(|error| map_storyteller_error(&error, StorytellerCallSite::Other))
}
```

- [ ] **Step 3: Replace `generate_ops.rs`**

```rust
use crate::core::cli_bridge::cli_bridge_envelope::BridgeError;
use crate::core::cli_bridge::native_result_mapping::{map_omni_error, OmniCallSite};
use crate::core::cli_bridge::ops::account_ops::fetch_credit_balance;
use crate::core::cli_bridge::ops::generate_rules::{
  build_omni_request, decide_spend, effective_credits, estimate_input, needs_balance_check, project_estimate,
  validate_generate_request, GenerateModality, SUBSCRIBER_ID_PREFIX,
};
use crate::core::cli_bridge::ops::generate_submit::{run_submit, ApprovedSpend};
use crate::core::cli_bridge::ops::op_support::{
  parse_args, require_session, task_database, validate_idempotency_token, with_call_timeout, OpContext,
};
use crate::core::commands::cost_estimate::estimate_audio_cost_command::estimate_audio_cost_command;
use crate::core::commands::cost_estimate::estimate_image_cost_command::estimate_image_cost_command;
use crate::core::commands::cost_estimate::estimate_mesh_cost_command::estimate_mesh_cost_command;
use crate::core::commands::cost_estimate::estimate_splat_cost_command::estimate_splat_cost_command;
use crate::core::commands::cost_estimate::estimate_video_cost_command::estimate_video_cost_command;
use crate::core::commands::generate::generate_audio_command::generate_audio_command;
use crate::core::commands::generate::generate_image::generate_image_command::generate_image_command;
use crate::core::commands::generate::generate_mesh_command::generate_mesh_command;
use crate::core::commands::generate::generate_splat_command::generate_splat_command;
use crate::core::commands::generate::generate_video::generate_video_command::generate_video_command;
use crate::core::commands::generate::omni::{OmniRequest, OmniResult};
use log::info;
use serde_derive::Deserialize;
use serde_json::{json, Map, Value};
use tauri::AppHandle;

const IDEMPOTENCY_TOKEN_KEY: &str = "idempotency_token";

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct GenerateEstimateRequest {
  modality: GenerateModality,
  request: Map<String, Value>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct GenerateSubmitRequest {
  modality: GenerateModality,
  idempotency_token: String,
  max_credits: u64,
  request: Map<String, Value>,
}

/// A validated request's projected estimate and the credits it would actually spend.
pub struct PricedRequest {
  pub estimate: Value,
  pub maybe_effective_credits: Option<u64>,
}

/// `generate.estimate` (spec §7.3): free, needs no login, creates no task.
pub async fn generate_estimate(ctx: &OpContext, args: Value) -> Result<Value, BridgeError> {
  let request: GenerateEstimateRequest = parse_args(args)?;
  let priced = estimate_cost(ctx, request.modality, &request.request).await?;
  Ok(json!({
    "modality": request.modality.to_str(),
    "model": model_of(&request.request),
    "estimate": priced.estimate,
    "effective_credits": priced.maybe_effective_credits,
  }))
}

/// `generate.submit` (spec §7.4). Logs modality, model, token and job ids, never the prompt.
pub async fn generate_submit(ctx: &OpContext, args: Value) -> Result<Value, BridgeError> {
  let submit: GenerateSubmitRequest = parse_args(args)?;
  validate_idempotency_token(&submit.idempotency_token)?;
  validate_generate_request(submit.modality, &submit.request)?;
  let db = task_database(&ctx.app)?;
  let modality = submit.modality;
  let token = submit.idempotency_token.as_str();
  info!("cli bridge submit modality={} model={} idempotency_token={}", modality, model_of(&submit.request), token);
  let mut post_fields = submit.request.clone();
  post_fields.insert(IDEMPOTENCY_TOKEN_KEY.to_string(), Value::String(token.to_string()));
  let post_request = build_omni_request(post_fields, Some(format!("{SUBSCRIBER_ID_PREFIX}{token}")));
  let app = ctx.app.clone();
  let data = run_submit(
    &db,
    &ctx.in_flight_tokens,
    token,
    ctx.limits.submit_hard_cap,
    || approve_spend(ctx, modality, &submit.request, submit.max_credits),
    move || call_generate_command(modality, post_request, app),
  ).await?;
  info!("cli bridge submit idempotency_token={} job_ids={} replayed={}", token, data["job_ids"], data["replayed"]);
  Ok(data)
}

/// Spec §7.3 steps 0–3. Shared with `generate.submit` step 5.
pub async fn estimate_cost(
  ctx: &OpContext,
  modality: GenerateModality,
  request: &Map<String, Value>,
) -> Result<PricedRequest, BridgeError> {
  validate_generate_request(modality, request)?;
  let input = estimate_input(modality, request)?;
  let omni_request = build_omni_request(input.fields, None);
  let result = with_call_timeout(ctx.limits.read_call_timeout, call_estimate_command(modality, omni_request, ctx.app.clone())).await?;
  let response = result.map_err(|error| map_omni_error(&error, OmniCallSite::Estimate))?;
  let raw = response.payload.map(|payload| payload.0).unwrap_or(Value::Null);
  let estimate = project_estimate(&raw);
  let maybe_effective_credits = effective_credits(&estimate, input.video_count);
  Ok(PricedRequest { estimate, maybe_effective_credits })
}

/// Spec §7.4 steps 4–6: session, estimate, then the balance only when credits will be spent.
async fn approve_spend(
  ctx: &OpContext,
  modality: GenerateModality,
  request: &Map<String, Value>,
  max_credits: u64,
) -> Result<ApprovedSpend, BridgeError> {
  let creds = require_session(&ctx.app)?;
  let priced = estimate_cost(ctx, modality, request).await?;
  let effective_credits = decide_spend(priced.maybe_effective_credits, max_credits, None)?;
  if needs_balance_check(effective_credits) {
    let balance = fetch_credit_balance(ctx, &creds).await?;
    decide_spend(Some(effective_credits), max_credits, Some(balance))?;
  }
  Ok(ApprovedSpend { estimate: priced.estimate, effective_credits })
}

async fn call_estimate_command(modality: GenerateModality, request: OmniRequest, app: AppHandle) -> OmniResult {
  match modality {
    GenerateModality::Image => estimate_image_cost_command(request, app).await,
    GenerateModality::Video => estimate_video_cost_command(request, app).await,
    GenerateModality::Audio => estimate_audio_cost_command(request, app).await,
    GenerateModality::Mesh => estimate_mesh_cost_command(request, app).await,
    GenerateModality::Splat => estimate_splat_cost_command(request, app).await,
  }
}

async fn call_generate_command(modality: GenerateModality, request: OmniRequest, app: AppHandle) -> OmniResult {
  match modality {
    GenerateModality::Image => generate_image_command(request, app).await,
    GenerateModality::Video => generate_video_command(request, app).await,
    GenerateModality::Audio => generate_audio_command(request, app).await,
    GenerateModality::Mesh => generate_mesh_command(request, app).await,
    GenerateModality::Splat => generate_splat_command(request, app).await,
  }
}

/// `validate_generate_request` has already guaranteed a string `model`.
fn model_of(request: &Map<String, Value>) -> &str {
  request.get("model").and_then(Value::as_str).unwrap_or_default()
}
```

- [ ] **Step 4: Replace `op_dispatch.rs`**

```rust
use crate::core::cli_bridge::cli_bridge_envelope::{BridgeError, BridgeErrorCode};
use crate::core::cli_bridge::cli_bridge_gate::DispatchFn;
use crate::core::cli_bridge::native_result_mapping::outcome_unknown;
use crate::core::cli_bridge::ops::account_ops::{account_credits, account_session, account_subscription};
use crate::core::cli_bridge::ops::app_ops::app_info;
use crate::core::cli_bridge::ops::generate_ops::{generate_estimate, generate_submit};
use crate::core::cli_bridge::ops::jobs_ops::jobs_list;
use crate::core::cli_bridge::ops::models_ops::models_list;
use crate::core::cli_bridge::ops::op_support::{deadline_error, OpContext, OpLimits};
use futures::future::BoxFuture;
use serde_json::Value;
use std::sync::Arc;
use std::time::Duration;

/// The op allowlist, in spec §5.4 order. `GET /v1/health` reports it; the RPC handler refuses anything else with `unknown_op`.
pub const ALLOWED_OPS: &[&str] = &[
  "app.info",
  "account.session",
  "account.credits",
  "account.subscription",
  "models.list",
  "generate.estimate",
  "generate.submit",
  "jobs.list",
];

const SUBMIT_OP: &str = "generate.submit";
const UPLOAD_OP: &str = "media.upload";

/// Production `DispatchFn`: every op runs as its own task on the Tauri runtime.
pub fn make_dispatch(ctx: OpContext) -> DispatchFn {
  Arc::new(move |op: String, args: Value| {
    let reply: BoxFuture<'static, Result<Value, BridgeError>> = Box::pin(dispatch_op(ctx.clone(), op, args));
    reply
  })
}

/// Spawned, so neither a client disconnect nor an expired deadline cancels an op halfway (spec §4.5).
async fn dispatch_op(ctx: OpContext, op: String, args: Value) -> Result<Value, BridgeError> {
  let deadline = op_deadline(&op, &ctx.limits);
  let expired = deadline_error_for(&op, &args);
  let handle = tauri::async_runtime::spawn(async move { run_op(&ctx, &op, args).await });
  match tokio::time::timeout(deadline, handle).await {
    Ok(Ok(result)) => result,
    Ok(Err(_)) => Err(BridgeError::new(BridgeErrorCode::InternalError, "the op failed inside the bridge; check the ArtCraft log")),
    Err(_) => Err(expired),
  }
}

async fn run_op(ctx: &OpContext, op: &str, args: Value) -> Result<Value, BridgeError> {
  match op {
    "app.info" => app_info(ctx, args),
    "account.session" => account_session(ctx, args).await,
    "account.credits" => account_credits(ctx, args).await,
    "account.subscription" => account_subscription(ctx, args).await,
    "models.list" => models_list(ctx, args).await,
    "generate.estimate" => generate_estimate(ctx, args).await,
    "generate.submit" => generate_submit(ctx, args).await,
    "jobs.list" => jobs_list(ctx, args).await,
    _ => Err(BridgeError::new(BridgeErrorCode::UnknownOp, "this op is not available on the bridge")),
  }
}

/// An expired deadline is a free retry for every op except submit, whose POST may already be accepted (spec §4.5).
fn deadline_error_for(op: &str, args: &Value) -> BridgeError {
  if op != SUBMIT_OP {
    return deadline_error();
  }
  let idempotency_token = args.get("idempotency_token").and_then(Value::as_str).unwrap_or_default();
  outcome_unknown(idempotency_token, "deadline")
}

fn op_deadline(op: &str, limits: &OpLimits) -> Duration {
  match op {
    SUBMIT_OP | UPLOAD_OP => limits.write_op_deadline,
    _ => limits.read_op_deadline,
  }
}
```

- [ ] **Step 5: Compile-check**

Run: `SQLX_OFFLINE=true cargo check -p artcraft`
Expected: `Finished` with no errors. If the borrow checker rejects the `approve_spend` closure borrowing `submit.request`, bind `let approval_request = submit.request.clone();` before `run_submit` and pass `&approval_request`.

- [ ] **Step 6: Run every bridge test**

Run: `SQLX_OFFLINE=true cargo test -p artcraft --lib cli_bridge`
Expected: PASS, `37 passed`.

- [ ] **Step 7: Commit**

```bash
git add crates/desktop/artcraft/src/core/cli_bridge/ops/op_support.rs crates/desktop/artcraft/src/core/cli_bridge/ops/generate_ops.rs crates/desktop/artcraft/src/core/cli_bridge/ops/account_ops.rs crates/desktop/artcraft/src/core/cli_bridge/op_dispatch.rs
git commit -m "feat(cli-bridge): add generate.submit and account credit and subscription ops"
```

### Task 13: `jobs.get` with dismissed rows and batch expansion

**Files:**
- Modify: `crates/desktop/artcraft/src/core/cli_bridge/ops/job_view.rs` (new types, `build_job_get`, `job_view_from_dismissed`, 1 test)
- Modify: `crates/desktop/artcraft/src/core/cli_bridge/ops/jobs_ops.rs` (full replacement below)
- Modify: `crates/desktop/artcraft/src/core/cli_bridge/op_dispatch.rs` (allowlist and one `run_op` arm)

**Interfaces:**
- Consumes:
  - T6: `job_view_from_local`, `job_view_from_remote`, `merge_remote`, `map_local_status`, `modality_of`.
  - T7: `list_local_tasks`, `fetch_remote_jobs`.
- Produces:
  - `struct JobGetView { jobs: Vec<JobView>, unresolved: Vec<UnresolvedJob> }`
  - `struct UnresolvedJob { job_id: String, reason: &'static str }`
  - `build_job_get(&[String], &[TaskItem], &HashMap<String, Task>, Option<Result<Vec<RemoteJob>, BridgeErrorCode>>) -> JobGetView`
  - `job_view_from_dismissed(&str, &Task) -> JobView`
  - `jobs_get(&OpContext, Value)`

- [ ] **Step 1: Write the failing test**

In `job_view.rs`, inside `mod tests`, insert after `job_lists_are_newest_first_and_report_truncation` and before `fn task_item`:
```rust
  #[test]
  fn unresolved_job_ids_carry_the_remote_failure_reason() {
    let local = [task_item(Some(CLI_JOB), Some(CLI_SUBSCRIBER), TaskStatus::Started)];
    let job_ids = vec![CLI_JOB.to_string(), REMOTE_ONLY_JOB.to_string()];

    let offline = build_job_get(&job_ids, &local, &HashMap::new(), Some(Err(BridgeErrorCode::RateLimited)));
    let local_only = build_job_get(&job_ids, &local, &HashMap::new(), None);

    // The local job still resolves, flagged with the remote failure; the unknown id carries the reason.
    assert_eq!(offline.jobs.len(), 1);
    assert_eq!(offline.jobs[0].sources.maybe_remote_error, Some("rate_limited"));
    assert_eq!(offline.unresolved[0].job_id, REMOTE_ONLY_JOB);
    assert_eq!(offline.unresolved[0].reason, "rate_limited");
    // Without a remote check, an unknown id is simply not found.
    assert_eq!(local_only.unresolved[0].reason, "job_not_found");
  }

```

- [ ] **Step 2: Run the test to verify it fails**

Run: `SQLX_OFFLINE=true cargo test -p artcraft --lib job_view`
Expected: FAIL to compile with `cannot find function build_job_get`.

- [ ] **Step 3: Implement `build_job_get`**

In `job_view.rs`:
- Replace `use std::collections::HashSet;` with `use std::collections::{HashMap, HashSet};`.
- Add `use sqlite_tasks::queries::task::Task;` after the `list_tasks_for_frontend::TaskItem` import.

Insert after the `JobListView` struct:
```rust
/// `jobs.get` data (spec §5.5).
#[derive(Debug, Serialize)]
pub struct JobGetView {
  pub jobs: Vec<JobView>,
  pub unresolved: Vec<UnresolvedJob>,
}

/// An id with no local row and no remote entry. `reason` reuses an error code (spec §7.6).
#[derive(Debug, Serialize)]
pub struct UnresolvedJob {
  pub job_id: String,
  pub reason: &'static str,
}

```
Insert after `build_job_list`:
```rust
/// Builds `jobs.get` in request order. Local rows win, then dismissed rows (status only), then remote-only entries.
pub fn build_job_get(
  job_ids: &[String],
  local: &[TaskItem],
  dismissed: &HashMap<String, Task>,
  maybe_remote: Option<Result<Vec<RemoteJob>, BridgeErrorCode>>,
) -> JobGetView {
  let artcraft_ids = artcraft_job_ids(local);
  let (remote_jobs, maybe_remote_error) = match maybe_remote {
    None => (Vec::new(), None),
    Some(Ok(remote_jobs)) => (remote_jobs, None),
    Some(Err(code)) => (Vec::new(), Some(code)),
  };
  let mut jobs = Vec::new();
  let mut unresolved = Vec::new();
  for job_id in job_ids {
    let maybe_remote_job = remote_jobs.iter().find(|remote| remote.job_id == *job_id);
    let maybe_local = local.iter().find(|item| item.provider_job_id.as_deref() == Some(job_id.as_str()));
    let maybe_view = if let Some(item) = maybe_local {
      job_view_from_local(item).map(|view| (view, artcraft_ids.contains(job_id.as_str())))
    } else if let Some(task) = dismissed.get(job_id) {
      Some((job_view_from_dismissed(job_id, task), true))
    } else {
      maybe_remote_job.map(|remote| (job_view_from_remote(remote), false))
    };
    let Some((mut view, mergeable)) = maybe_view else {
      let reason = maybe_remote_error.map_or("job_not_found", |code| code.to_str());
      unresolved.push(UnresolvedJob { job_id: job_id.clone(), reason });
      continue;
    };
    if mergeable {
      match (maybe_remote_job, maybe_remote_error) {
        (Some(remote), _) => merge_remote(&mut view, remote),
        (None, Some(code)) => view.sources.maybe_remote_error = Some(code.to_str()),
        (None, None) => {},
      }
    }
    jobs.push(view);
  }
  JobGetView { jobs, unresolved }
}

```
Insert after `job_view_from_remote`:
```rust
/// Dismissed rows are hidden from the frontend list; the provider lookup returns status but no timestamps.
pub fn job_view_from_dismissed(job_id: &str, task: &Task) -> JobView {
  let status = map_local_status(&task.status);
  JobView {
    job_id: job_id.to_string(),
    maybe_task_id: Some(task.id.as_str().to_string()),
    origin: origin_of(task.frontend_subscriber_id.as_deref()),
    maybe_modality: modality_of(&task.task_type),
    maybe_model: task.model_type.as_ref().map(|model| model.to_str().to_string()),
    status,
    terminal: status.is_terminal(),
    maybe_progress_percent: None,
    native_status: NativeStatusView { maybe_local: Some(task.status.to_str()), maybe_remote: None },
    maybe_result: None,
    maybe_failure: None,
    maybe_created_at: None,
    maybe_remote_updated_at: None,
    dismissed: true,
    sources: JobSourcesView { local: true, remote: false, maybe_remote_error: None },
  }
}

```

- [ ] **Step 4: Run the test to verify it passes**

Run: `SQLX_OFFLINE=true cargo test -p artcraft --lib job_view`
Expected: PASS, `6 passed`.

- [ ] **Step 5: Replace `jobs_ops.rs`**

```rust
use crate::core::cli_bridge::cli_bridge_envelope::{BridgeError, BridgeErrorCode};
use crate::core::cli_bridge::native_result_mapping::{map_storyteller_error, StorytellerCallSite};
use crate::core::cli_bridge::ops::job_view::{
  build_job_get, build_job_list, JobFileView, JobStatusView, JobView, OriginFilter, RemoteJob,
};
use crate::core::cli_bridge::ops::op_support::{
  invalid_args, local_store_error, parse_args, require_session, task_database, to_data, validate_id, with_call_timeout,
  OpContext,
};
use crate::core::state::app_env_configs::app_env_configs::AppEnvConfigs;
use crate::core::state::task_database::TaskDatabase;
use artcraft_client::endpoints::jobs::list_session_jobs::{list_session_jobs, States};
use artcraft_client::endpoints::media_files::list_batch_generated_redux_media_files::list_batch_generated_redux_media_files;
use enums::common::generation_provider::GenerationProvider;
use serde_derive::Deserialize;
use serde_json::Value;
use sqlite_tasks::queries::get_task_by_provider_and_provider_job_id::{
  get_task_by_provider_and_provider_job_id, GetTaskByProviderAndProviderJobIdArgs,
};
use sqlite_tasks::queries::list_tasks_for_frontend::{list_tasks_for_frontend, TaskItem};
use sqlite_tasks::queries::task::Task;
use std::collections::HashMap;
use tauri::Manager;
use tokens::tokens::batch_generations::BatchGenerationToken;

const DEFAULT_LIST_LIMIT: usize = 50;
const MAX_LIST_LIMIT: usize = 200;
const MAX_GET_IDS: usize = 50;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct JobsListRequest {
  #[serde(default)]
  origin: OriginFilter,
  #[serde(default = "default_list_limit")]
  limit: usize,
  #[serde(default)]
  include_remote: bool,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct JobsGetRequest {
  job_ids: Vec<String>,
  #[serde(default)]
  include_remote: bool,
}

/// `jobs.list` (spec §7.6): newest first, local rows plus an optional remote merge.
pub async fn jobs_list(ctx: &OpContext, args: Value) -> Result<Value, BridgeError> {
  let request: JobsListRequest = parse_args(args)?;
  if !(1..=MAX_LIST_LIMIT).contains(&request.limit) {
    return Err(invalid_args("limit must be between 1 and 200"));
  }
  let db = task_database(&ctx.app)?;
  let local = list_local_tasks(&db).await?;
  let maybe_remote = if request.include_remote { Some(fetch_remote_jobs(ctx).await) } else { None };
  to_data(&build_job_list(&local, maybe_remote, request.origin, request.limit))
}

/// `jobs.get` (spec §7.6). Batch expansion runs only with `include_remote`, and only for succeeded jobs.
pub async fn jobs_get(ctx: &OpContext, args: Value) -> Result<Value, BridgeError> {
  let request: JobsGetRequest = parse_args(args)?;
  if !(1..=MAX_GET_IDS).contains(&request.job_ids.len()) {
    return Err(invalid_args("job_ids must hold between 1 and 50 ids"));
  }
  for job_id in &request.job_ids {
    validate_id("job_ids", job_id)?;
  }
  let db = task_database(&ctx.app)?;
  let local = list_local_tasks(&db).await?;
  let dismissed = find_dismissed_tasks(&db, &request.job_ids, &local).await?;
  let maybe_remote = if request.include_remote { Some(fetch_remote_jobs(ctx).await) } else { None };
  let mut view = build_job_get(&request.job_ids, &local, &dismissed, maybe_remote);
  if request.include_remote {
    expand_batches(ctx, &mut view.jobs).await;
  }
  to_data(&view)
}

/// A row that fails to parse fails the whole query; that surfaces as `local_store_error` (spec §7.6).
pub async fn list_local_tasks(db: &TaskDatabase) -> Result<Vec<TaskItem>, BridgeError> {
  list_tasks_for_frontend(db.get_connection())
    .await
    .map(|task_list| task_list.tasks)
    .map_err(|_| local_store_error("the task database could not be read"))
}

/// The newest 100 remote jobs under a 10 s timeout. Failures become a code the merge reports.
pub async fn fetch_remote_jobs(ctx: &OpContext) -> Result<Vec<RemoteJob>, BridgeErrorCode> {
  let creds = require_session(&ctx.app).map_err(|error| error.code)?;
  let configs = ctx.app.state::<AppEnvConfigs>();
  let response = with_call_timeout(
    ctx.limits.remote_jobs_timeout,
    list_session_jobs(&configs.storyteller_host, Some(&creds), States::All),
  )
  .await
  .map_err(|error| error.code)?
  .map_err(|error| map_storyteller_error(&error, StorytellerCallSite::Other).code)?;
  Ok(response.jobs.iter().map(RemoteJob::from_item).collect())
}

/// Ids missing from the frontend list may be dismissed Artcraft rows; look each one up.
async fn find_dismissed_tasks(
  db: &TaskDatabase,
  job_ids: &[String],
  local: &[TaskItem],
) -> Result<HashMap<String, Task>, BridgeError> {
  let mut dismissed = HashMap::new();
  for job_id in job_ids {
    if local.iter().any(|item| item.provider_job_id.as_deref() == Some(job_id.as_str())) {
      continue;
    }
    let maybe_task = get_task_by_provider_and_provider_job_id(GetTaskByProviderAndProviderJobIdArgs {
      db: db.get_connection(),
      provider: GenerationProvider::Artcraft,
      provider_job_id: job_id,
    })
    .await
    .map_err(|_| local_store_error("the task database could not be read"))?;
    if let Some(task) = maybe_task {
      dismissed.insert(job_id.clone(), task);
    }
  }
  Ok(dismissed)
}

/// Replaces the primary file with the whole batch, as `auto_download.rs:42-54` does. A failure keeps
/// the primary file and records `sources.remote_error`.
async fn expand_batches(ctx: &OpContext, jobs: &mut [JobView]) {
  for job in jobs.iter_mut().filter(|job| job.status == JobStatusView::Succeeded) {
    let Some(batch_token) = job.maybe_result.as_ref().and_then(|result| result.maybe_batch_token.clone()) else {
      continue;
    };
    match fetch_batch_files(ctx, &batch_token).await {
      Ok(files) if !files.is_empty() => {
        if let Some(result) = job.maybe_result.as_mut() {
          result.files = files;
        }
      },
      Ok(_) => {},
      Err(code) => job.sources.maybe_remote_error = Some(code.to_str()),
    }
  }
}

async fn fetch_batch_files(ctx: &OpContext, batch_token: &str) -> Result<Vec<JobFileView>, BridgeErrorCode> {
  let creds = require_session(&ctx.app).map_err(|error| error.code)?;
  let configs = ctx.app.state::<AppEnvConfigs>();
  let token = BatchGenerationToken::new_from_str(batch_token);
  let response = with_call_timeout(
    ctx.limits.read_call_timeout,
    list_batch_generated_redux_media_files(&configs.storyteller_host, Some(&creds), &token),
  )
  .await
  .map_err(|error| error.code)?
  .map_err(|error| map_storyteller_error(&error, StorytellerCallSite::Other).code)?;
  Ok(response.media_files.iter().map(|file| JobFileView {
    media_token: file.token.as_str().to_string(),
    maybe_cdn_url: Some(file.media_links.cdn_url.to_string()),
    maybe_thumbnail_url_template: file.media_links.maybe_thumbnail_template.clone(),
    maybe_media_class: Some(file.media_class.to_str().to_string()),
  }).collect())
}

fn default_list_limit() -> usize {
  DEFAULT_LIST_LIMIT
}
```

- [ ] **Step 6: Allowlist `jobs.get`**

In `op_dispatch.rs`:
- Change `use crate::core::cli_bridge::ops::jobs_ops::jobs_list;` to `use crate::core::cli_bridge::ops::jobs_ops::{jobs_get, jobs_list};`.
- Replace `ALLOWED_OPS` with:
```rust
pub const ALLOWED_OPS: &[&str] = &[
  "app.info",
  "account.session",
  "account.credits",
  "account.subscription",
  "models.list",
  "generate.estimate",
  "generate.submit",
  "jobs.get",
  "jobs.list",
];
```
- In `run_op`, insert before the `"jobs.list"` arm:
```rust
    "jobs.get" => jobs_get(ctx, args).await,
```

- [ ] **Step 7: Compile-check and run every bridge test**

Run: `SQLX_OFFLINE=true cargo check -p artcraft && SQLX_OFFLINE=true cargo test -p artcraft --lib cli_bridge`
Expected: `Finished`, then PASS, `38 passed`.

- [ ] **Step 8: Commit**

```bash
git add crates/desktop/artcraft/src/core/cli_bridge/ops/job_view.rs crates/desktop/artcraft/src/core/cli_bridge/ops/jobs_ops.rs crates/desktop/artcraft/src/core/cli_bridge/op_dispatch.rs
git commit -m "feat(cli-bridge): add jobs.get with dismissed rows and batch expansion"
```

### Task 14: M2 live checklist (user-run)

**Files:** none modified. Results go to project memory, and to the cli=api peer for spec §5.6 and §7.4.

**Interfaces:**
- Consumes: the M2 build, the T9 shell helpers, and an image model id from T9 (g).
- Produces: the recorded duplicate-rejection status and body.

Use `--max-credits ${ARTCRAFT_E2E_MAX_CREDITS:-10}`-sized caps and the cheapest image model from T9.

- [ ] **(a) Credits and subscription.** `rpc '{"op":"account.credits","args":{}}'` matches the app's balance. `rpc '{"op":"account.subscription","args":{}}'` matches the account.
- [ ] **(b) The cheapest image completes.** Run `T=$(uuidgen | tr 'A-Z' 'a-z')`, then `rpc "{\"op\":\"generate.submit\",\"args\":{\"modality\":\"image\",\"idempotency_token\":\"$T\",\"max_credits\":10,\"request\":{\"model\":\"<id>\",\"prompt\":\"a red cube\"}}}"`.
  - The response has `job_ids`, `replayed: false`, `estimate` and `effective_credits`.
  - The job appears in the app's task panel and image feed.
  - Poll `rpc "{\"op\":\"jobs.get\",\"args\":{\"job_ids\":[\"<job id>\"],\"include_remote\":true}}"` until `terminal: true`. `result.files[].cdn_url` downloads with `curl -sO <cdn_url>`.
- [ ] **(c) Replay.** Re-run the same `generate.submit` with the same `$T`.
  - The response has `replayed: true` and the same `job_ids`.
  - `account.credits` is unchanged, and no new task appears.
- [ ] **(d) Duplicate rejection, after dismissing.** Dismiss the job **in the app's task panel** (`jobs.dismiss` arrives in M4). Resubmit with the same `$T` and `max_credits` equal to (b)'s `effective_credits`.
  - Record the exact `error.code`, the message, and the app log's HTTP status and body for the POST.
  - If the server accepts it, the cap bounds the second charge; record that too.
  - Write the result to project memory and send it to the peer, so spec §5.6/§7.4 can be updated if the shape is distinguishable.
  - Re-run `jobs.get` for the dismissed id: it resolves with `dismissed: true`.
- [ ] **(e) Cost guard.** Submit with `max_credits` set to 1 below (b)'s `effective_credits`. The result is `cost_exceeds_limit`, with `details.effective_credits` and `details.max_credits`. `account.credits` is unchanged.
- [ ] **(f) Remote merge.** `rpc '{"op":"jobs.list","args":{"origin":"all","limit":50,"include_remote":true}}'` lists the job with `sources.remote: true` and a non-null `remote_updated_at`.
- [ ] **(g) Log hygiene.** Grep the dev log for the prompt text ("a red cube"); with `RUST_LOG` unset it is absent. The `cli bridge submit` lines show modality, model, token and job ids.

When every box is checked, update the ARTC Plane work item for T14 and tell the peer M2 Rust is live, with the (d) result.

---

# M3 — Media

### Task 15: `artcraft_client` binding for the user media list

**Files:**
- Create: `crates/api_clients/artcraft/artcraft_client/src/endpoints/media_files/list_user_media_files.rs`
- Modify: `crates/api_clients/artcraft/artcraft_client/src/endpoints/media_files/mod.rs` (insert after `pub mod list_batch_generated_redux_media_files;`)
- Test: bottom `mod tests` of the new file (a pure URL-builder unit test; `artcraft_client/Cargo.toml` is untouched)

**Interfaces:**
- Consumes: `basic_json_get_request(api_host: &ApiHost, route_path: &str, maybe_creds: Option<&StorytellerCredentialSet>) -> Result<Res, StorytellerError>`. It is `pub(crate)`, which is why this binding lives in `artcraft_client`.
- Produces:
  - `struct ListUserMediaFilesQuery { page_index: u32, page_size: u32, sort_ascending: bool, maybe_filter_media_classes: Option<Vec<String>> }`
  - `list_user_media_files(&ApiHost, Option<&StorytellerCredentialSet>, username: &str, &ListUserMediaFilesQuery) -> Result<serde_json::Value, StorytellerError>`

- [ ] **Step 1: Declare the module**

In `crates/api_clients/artcraft/artcraft_client/src/endpoints/media_files/mod.rs`, insert after `pub mod list_batch_generated_redux_media_files;`:
```rust
pub mod list_user_media_files;
```

- [ ] **Step 2: Write the failing test**

Create `list_user_media_files.rs` containing only:
```rust
#[cfg(test)]
mod tests {
  use super::*;

  #[test]
  fn media_list_builds_the_user_list_url_with_filters() {
    let filtered = ListUserMediaFilesQuery {
      page_index: 2,
      page_size: 25,
      sort_ascending: false,
      maybe_filter_media_classes: Some(vec!["image".to_string(), "video".to_string()]),
    };
    let unfiltered = ListUserMediaFilesQuery {
      page_index: 0,
      page_size: 100,
      sort_ascending: true,
      maybe_filter_media_classes: None,
    };

    assert_eq!(
      list_user_media_files_path("echelon", &filtered),
      "/v1/media_files/list/user/echelon?include_user_uploads=true&page_size=25&page_index=2&sort_ascending=false&filter_media_classes=image,video",
    );
    // The username is a single path segment: a slash or a space can never change the route.
    assert_eq!(
      list_user_media_files_path("a b/../admin", &unfiltered),
      "/v1/media_files/list/user/a%20b%2F..%2Fadmin?include_user_uploads=true&page_size=100&page_index=0&sort_ascending=true",
    );
  }
}
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cargo test -p artcraft_client --lib list_user_media_files`
Expected: FAIL to compile with `cannot find function list_user_media_files_path` and `cannot find struct ListUserMediaFilesQuery`.

- [ ] **Step 4: Implement the binding**

Insert above `#[cfg(test)]`:
```rust
use crate::credentials::storyteller_credential_set::StorytellerCredentialSet;
use crate::error::storyteller_error::StorytellerError;
use crate::utils::api_host::ApiHost;
use crate::utils::basic_json_get_request::basic_json_get_request;
use serde_json::Value;

const LIST_USER_MEDIA_FILES_PATH_PREFIX: &str = "/v1/media_files/list/user/";

/// Query for `GET /v1/media_files/list/user/{username}`, mirroring the frontend's
/// `ListUserMediaFiles` (`frontend/apps/artcraft/app/src/Classes/ApiManager/MediaFilesApi.ts:157-191`).
pub struct ListUserMediaFilesQuery {
  pub page_index: u32,
  pub page_size: u32,
  pub sort_ascending: bool,
  pub maybe_filter_media_classes: Option<Vec<String>>,
}

/// Lists a user's media files, uploads included. The body stays JSON because list items are sparse.
pub async fn list_user_media_files(
  api_host: &ApiHost,
  maybe_creds: Option<&StorytellerCredentialSet>,
  username: &str,
  query: &ListUserMediaFilesQuery,
) -> Result<Value, StorytellerError> {
  basic_json_get_request(api_host, &list_user_media_files_path(username, query), maybe_creds).await
}

fn list_user_media_files_path(username: &str, query: &ListUserMediaFilesQuery) -> String {
  let mut path = format!(
    "{}{}?include_user_uploads=true&page_size={}&page_index={}&sort_ascending={}",
    LIST_USER_MEDIA_FILES_PATH_PREFIX,
    percent_encode(username),
    query.page_size,
    query.page_index,
    query.sort_ascending,
  );
  if let Some(media_classes) = query.maybe_filter_media_classes.as_ref().filter(|classes| !classes.is_empty()) {
    let encoded: Vec<String> = media_classes.iter().map(|media_class| percent_encode(media_class)).collect();
    path.push_str("&filter_media_classes=");
    path.push_str(&encoded.join(","));
  }
  path
}

/// Percent-encodes everything outside RFC 3986's unreserved set.
fn percent_encode(value: &str) -> String {
  value
    .bytes()
    .map(|byte| match byte {
      b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'.' | b'_' | b'~' => (byte as char).to_string(),
      _ => format!("%{:02X}", byte),
    })
    .collect()
}

```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cargo test -p artcraft_client --lib list_user_media_files`
Expected: PASS, `1 passed`.

- [ ] **Step 6: Commit**

```bash
git add crates/api_clients/artcraft/artcraft_client/src/endpoints/media_files/mod.rs crates/api_clients/artcraft/artcraft_client/src/endpoints/media_files/list_user_media_files.rs
git commit -m "feat(artcraft_client): add user media list binding"
```

### Task 16: `media.upload`, `media.get`, `media.list`

**Files:**
- Modify: `crates/desktop/artcraft/src/core/cli_bridge/ops/op_support.rs` (`OpContext` gains `upload_slot`)
- Modify: `crates/desktop/artcraft/src/core/cli_bridge/ops/mod.rs`
- Modify: `crates/desktop/artcraft/src/core/cli_bridge/op_dispatch.rs` (full replacement below)
- Create: `crates/desktop/artcraft/src/core/cli_bridge/ops/media_ops.rs`
- Test: bottom `mod tests` of `media_ops.rs`

**Interfaces:**
- Consumes:
  - T3: `MAX_UPLOAD_DECODED_BYTES`.
  - T4: `map_storyteller_error`, `map_login_result`, op support.
  - T15: `list_user_media_files`, `ListUserMediaFilesQuery`.
  - App: `upload_image_media_file_from_file_with_idempotency_token(UploadImageFromFileArgs, &str)`, `get_media_file(&ApiHost, &MediaFileToken)`, `TemporaryDir::new_named_temp_file_with_extension(&str)`. That last function adds the dot itself.
- Produces:
  - `media_upload`, `media_get`, `media_list`: each `(&OpContext, Value) -> Result<Value, BridgeError>`.
  - `check_upload_bytes(&[u8]) -> Result<UploadImageType, BridgeError>`
  - `enum UploadImageType { Png, Jpeg, Gif }`
  - `ALLOWED_OPS`, now 12 ops.

- [ ] **Step 1: Give `OpContext` the upload slot**

In `op_support.rs`, add `use std::sync::Arc;` and `use tokio::sync::Semaphore;` to the imports. Then replace the `OpContext` struct and its `impl` with:
```rust
/// What every op runs with. Cloned into each spawned op; clones share the in-flight set and the upload slot.
#[derive(Clone)]
pub struct OpContext {
  pub app: AppHandle,
  pub root: AppDataRoot,
  pub limits: OpLimits,
  pub in_flight_tokens: InFlightTokens,
  /// One upload at a time: one decoded copy, temp file and multipart body (spec §8.1 step 1).
  pub upload_slot: Arc<Semaphore>,
}
```
```rust
impl OpContext {
  pub fn new(app: AppHandle, root: AppDataRoot) -> Self {
    Self {
      app,
      root,
      limits: OpLimits::production(),
      in_flight_tokens: InFlightTokens::default(),
      upload_slot: Arc::new(Semaphore::new(1)),
    }
  }
}
```

- [ ] **Step 2: Declare the module**

Replace `crates/desktop/artcraft/src/core/cli_bridge/ops/mod.rs` with:
```rust
pub mod account_ops;
pub mod app_ops;
pub mod generate_ops;
pub mod generate_rules;
pub mod generate_submit;
pub mod job_view;
pub mod jobs_ops;
pub mod media_ops;
pub mod models_ops;
pub mod op_support;
#[cfg(test)]
pub mod test_tasks;
```

- [ ] **Step 3: Write the failing tests**

Create `crates/desktop/artcraft/src/core/cli_bridge/ops/media_ops.rs` containing only:
```rust
#[cfg(test)]
mod tests {
  use super::*;

  #[test]
  fn uploads_are_limited_to_20mib_png_jpeg_or_gif() {
    let mut png = PNG_MAGIC.to_vec();
    png.extend_from_slice(b"rest of the file");
    assert_eq!(check_upload_bytes(&png).unwrap(), UploadImageType::Png);
    assert_eq!(check_upload_bytes(&[0xFF, 0xD8, 0xFF, 0xE0]).unwrap(), UploadImageType::Jpeg);
    assert_eq!(check_upload_bytes(b"GIF89a....").unwrap(), UploadImageType::Gif);
    assert_eq!(check_upload_bytes(b"GIF87a....").unwrap(), UploadImageType::Gif);

    let unsupported: [&[u8]; 4] = [b"RIFF....WEBPVP8 ", b"<svg xmlns=", b"", b"\x89PN"];
    for bytes in unsupported {
      assert_eq!(check_upload_bytes(bytes).unwrap_err().code, BridgeErrorCode::UploadTypeUnsupported);
    }

    let mut largest = png.clone();
    largest.resize(MAX_UPLOAD_DECODED_BYTES, 0);
    assert!(check_upload_bytes(&largest).is_ok());
    let mut oversized = png;
    oversized.resize(MAX_UPLOAD_DECODED_BYTES + 1, 0);
    let error = check_upload_bytes(&oversized).unwrap_err();
    assert_eq!(error.code, BridgeErrorCode::InvalidArgs);
    assert_eq!(error.maybe_details, Some(json!({ "max_bytes": 20_971_520 })));
  }

  #[test]
  fn media_list_items_with_missing_fields_project_as_nulls() {
    let query = ListUserMediaFilesQuery { page_index: 1, page_size: 25, sort_ascending: false, maybe_filter_media_classes: None };
    let raw = json!({
      "success": true,
      "results": [
        {
          "token": "mf_full",
          "media_class": "image",
          "media_type": "image",
          "created_at": "2026-10-09T15:04:05Z",
          "maybe_title": "cube",
          "maybe_original_filename": "cube.png",
          "maybe_batch_token": "batch_1",
          "maybe_duration_millis": null,
          "public_bucket_path": "/media/x.png"
        },
        { "token": "mf_sparse", "media_class": null }
      ],
      "pagination": { "current": 1, "total_page_count": 4 }
    });

    let data = project_media_list("echelon", &query, &raw);

    assert_eq!(data["username"], "echelon");
    assert_eq!(data["page"], json!({ "index": 1, "size": 25, "total_pages": 4 }));
    assert_eq!(data["items"][0]["title"], "cube");
    assert_eq!(data["items"][0]["batch_token"], "batch_1");
    assert_eq!(data["items"][1], json!({
      "media_token": "mf_sparse",
      "media_class": null,
      "media_type": null,
      "created_at": null,
      "title": null,
      "original_filename": null,
      "batch_token": null,
      "duration_millis": null,
      "cdn_url": null,
    }));
    // A response without results is an empty page, not an error.
    assert_eq!(project_media_list("echelon", &query, &json!({}))["items"], json!([]));
  }
}
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `SQLX_OFFLINE=true cargo test -p artcraft --lib media_ops`
Expected: FAIL to compile with `cannot find function check_upload_bytes` and `cannot find value PNG_MAGIC`.

- [ ] **Step 5: Implement the media ops**

Insert above `#[cfg(test)]` in `media_ops.rs`:
```rust
use crate::core::cli_bridge::cli_bridge_envelope::{BridgeError, BridgeErrorCode};
use crate::core::cli_bridge::cli_bridge_gate::MAX_UPLOAD_DECODED_BYTES;
use crate::core::cli_bridge::native_result_mapping::{map_login_result, map_storyteller_error, StorytellerCallSite};
use crate::core::cli_bridge::ops::op_support::{
  invalid_args, local_store_error, parse_args, require_session, validate_id, validate_idempotency_token, with_call_timeout,
  OpContext,
};
use crate::core::state::app_env_configs::app_env_configs::AppEnvConfigs;
use crate::services::storyteller::commands::storyteller_get_login_session_command::storyteller_get_login_session_command;
use artcraft_client::endpoints::media_files::get_media_file::get_media_file;
use artcraft_client::endpoints::media_files::list_user_media_files::{list_user_media_files, ListUserMediaFilesQuery};
use artcraft_client::endpoints::media_files::upload_image_media_file_from_file::{
  upload_image_media_file_from_file_with_idempotency_token, UploadImageFromFileArgs,
};
use base64::prelude::BASE64_STANDARD;
use base64::Engine;
use serde_derive::Deserialize;
use serde_json::{json, Value};
use std::io::Write;
use tauri::Manager;
use tempfile::NamedTempFile;
use tokens::tokens::media_files::MediaFileToken;

const DEFAULT_PAGE_SIZE: u32 = 25;
const MAX_PAGE_SIZE: u32 = 100;
const PNG_MAGIC: &[u8] = &[0x89, b'P', b'N', b'G', 0x0D, 0x0A, 0x1A, 0x0A];
const JPEG_MAGIC: &[u8] = &[0xFF, 0xD8, 0xFF];
const GIF_MAGICS: [&[u8]; 2] = [b"GIF87a", b"GIF89a"];

/// The only upload kinds the bridge accepts, judged by magic bytes, never by a caller's claim.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum UploadImageType {
  Png,
  Jpeg,
  Gif,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct MediaUploadRequest {
  content_base64: String,
  idempotency_token: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct MediaGetRequest {
  media_token: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct MediaListRequest {
  #[serde(default)]
  media_classes: Vec<String>,
  #[serde(default)]
  page_index: u32,
  #[serde(default = "default_page_size")]
  page_size: u32,
  #[serde(default)]
  sort_ascending: bool,
}

impl UploadImageType {
  pub const fn to_str(&self) -> &'static str {
    match self {
      Self::Png => "png",
      Self::Jpeg => "jpeg",
      Self::Gif => "gif",
    }
  }

  /// The binding sends no MIME type, so the temp file's extension carries it (spec §8.1 step 6).
  const fn extension(&self) -> &'static str {
    match self {
      Self::Png => "png",
      Self::Jpeg => "jpg",
      Self::Gif => "gif",
    }
  }
}

/// `media.upload` (spec §8.1). Images only, and never a caller-supplied path.
pub async fn media_upload(ctx: &OpContext, args: Value) -> Result<Value, BridgeError> {
  let request: MediaUploadRequest = parse_args(args)?;
  validate_idempotency_token(&request.idempotency_token)?;
  let _upload_slot = ctx
    .upload_slot
    .acquire()
    .await
    .map_err(|_| BridgeError::new(BridgeErrorCode::InternalError, "the upload queue is closed"))?;
  let bytes = BASE64_STANDARD
    .decode(request.content_base64.as_bytes())
    .map_err(|_| invalid_args("content_base64 is not valid base64"))?;
  let image_type = check_upload_bytes(&bytes)?;
  let creds = require_session(&ctx.app)?;
  let temp_file = write_temp_image(ctx, image_type, &bytes)?;
  let configs = ctx.app.state::<AppEnvConfigs>();
  let upload = UploadImageFromFileArgs {
    api_host: &configs.storyteller_host,
    maybe_creds: Some(&creds),
    path: temp_file.path(),
    is_intermediate_system_file: false,
    maybe_prompt_token: None,
    maybe_generation_provider: None,
    maybe_batch_token: None,
  };
  let response = with_call_timeout(
    ctx.limits.upload_call_timeout,
    upload_image_media_file_from_file_with_idempotency_token(upload, &request.idempotency_token),
  )
  .await?
  .map_err(|error| map_storyteller_error(&error, StorytellerCallSite::Other))?;
  drop(temp_file);
  Ok(json!({
    "media_token": response.media_file_token.as_str(),
    "kind": "image",
    "image_type": image_type.to_str(),
    "byte_count": bytes.len(),
  }))
}

/// `media.get`: one media file's CDN link and class.
pub async fn media_get(ctx: &OpContext, args: Value) -> Result<Value, BridgeError> {
  let request: MediaGetRequest = parse_args(args)?;
  validate_id("media_token", &request.media_token)?;
  let configs = ctx.app.state::<AppEnvConfigs>();
  let token = MediaFileToken::new_from_str(&request.media_token);
  let response = with_call_timeout(ctx.limits.read_call_timeout, get_media_file(&configs.storyteller_host, &token))
    .await?
    .map_err(|error| map_storyteller_error(&error, StorytellerCallSite::MediaGet))?;
  let file = response.media_file;
  Ok(json!({
    "media_token": file.token.as_str(),
    "media_class": file.media_class.to_str(),
    "media_type": file.media_type.to_str(),
    "cdn_url": file.media_links.cdn_url.as_str(),
    "thumbnail_url_template": file.media_links.maybe_thumbnail_template,
    "batch_token": file.maybe_batch_token.as_ref().map(|token| token.as_str()),
  }))
}

/// `media.list` (spec §8.2): the logged-in user's library, uploads included.
pub async fn media_list(ctx: &OpContext, args: Value) -> Result<Value, BridgeError> {
  let request: MediaListRequest = parse_args(args)?;
  if !(1..=MAX_PAGE_SIZE).contains(&request.page_size) {
    return Err(invalid_args("page_size must be between 1 and 100"));
  }
  for media_class in &request.media_classes {
    validate_id("media_classes", media_class)?;
  }
  let creds = require_session(&ctx.app)?;
  let login = with_call_timeout(
    ctx.limits.read_call_timeout,
    storyteller_get_login_session_command(ctx.app.clone(), ctx.app.state()),
  ).await?;
  let Some(user) = map_login_result(login)? else {
    return Err(BridgeError::new(BridgeErrorCode::NotLoggedIn, "log in inside the ArtCraft app"));
  };
  let query = ListUserMediaFilesQuery {
    page_index: request.page_index,
    page_size: request.page_size,
    sort_ascending: request.sort_ascending,
    maybe_filter_media_classes: (!request.media_classes.is_empty()).then_some(request.media_classes),
  };
  let configs = ctx.app.state::<AppEnvConfigs>();
  let raw = with_call_timeout(
    ctx.limits.read_call_timeout,
    list_user_media_files(&configs.storyteller_host, Some(&creds), &user.username, &query),
  )
  .await?
  .map_err(|error| map_storyteller_error(&error, StorytellerCallSite::Other))?;
  Ok(project_media_list(&user.username, &query, &raw))
}

/// Spec §8.1 steps 3–4, before any session check or upload.
pub fn check_upload_bytes(bytes: &[u8]) -> Result<UploadImageType, BridgeError> {
  if bytes.len() > MAX_UPLOAD_DECODED_BYTES {
    return Err(invalid_args("the image is larger than 20 MiB").with_details(json!({ "max_bytes": MAX_UPLOAD_DECODED_BYTES })));
  }
  if bytes.starts_with(PNG_MAGIC) {
    return Ok(UploadImageType::Png);
  }
  if bytes.starts_with(JPEG_MAGIC) {
    return Ok(UploadImageType::Jpeg);
  }
  if GIF_MAGICS.iter().any(|magic| bytes.starts_with(magic)) {
    return Ok(UploadImageType::Gif);
  }
  Err(BridgeError::new(BridgeErrorCode::UploadTypeUnsupported, "only PNG, JPEG and GIF images can be uploaded"))
}

/// `~/Artcraft/temp`, deleted when the returned file drops (spec §8.1 steps 6 and 8).
fn write_temp_image(ctx: &OpContext, image_type: UploadImageType, bytes: &[u8]) -> Result<NamedTempFile, BridgeError> {
  let mut temp_file = ctx
    .root
    .temp_dir()
    .new_named_temp_file_with_extension(image_type.extension())
    .map_err(|_| local_store_error("the upload temp file could not be created"))?;
  temp_file.write_all(bytes).map_err(|_| local_store_error("the upload temp file could not be written"))?;
  temp_file.flush().map_err(|_| local_store_error("the upload temp file could not be written"))?;
  Ok(temp_file)
}

/// Spec §8.2 step 4: every item field is optional, so absent fields become nulls, never errors.
/// List items carry no `media_links`, so `cdn_url` is null unless the server adds them.
fn project_media_list(username: &str, query: &ListUserMediaFilesQuery, raw: &Value) -> Value {
  let items: Vec<Value> = raw
    .get("results")
    .and_then(Value::as_array)
    .map(|results| results.iter().map(project_media_item).collect())
    .unwrap_or_default();
  json!({
    "username": username,
    "items": items,
    "page": {
      "index": query.page_index,
      "size": query.page_size,
      "total_pages": raw.pointer("/pagination/total_page_count"),
    },
  })
}

fn project_media_item(item: &Value) -> Value {
  json!({
    "media_token": item.get("token"),
    "media_class": item.get("media_class"),
    "media_type": item.get("media_type"),
    "created_at": item.get("created_at"),
    "title": item.get("maybe_title"),
    "original_filename": item.get("maybe_original_filename"),
    "batch_token": item.get("maybe_batch_token"),
    "duration_millis": item.get("maybe_duration_millis"),
    "cdn_url": item.pointer("/media_links/cdn_url"),
  })
}

fn default_page_size() -> u32 {
  DEFAULT_PAGE_SIZE
}

```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `SQLX_OFFLINE=true cargo test -p artcraft --lib media_ops`
Expected: PASS, `2 passed`.

- [ ] **Step 7: Replace `op_dispatch.rs`**

```rust
use crate::core::cli_bridge::cli_bridge_envelope::{BridgeError, BridgeErrorCode};
use crate::core::cli_bridge::cli_bridge_gate::DispatchFn;
use crate::core::cli_bridge::native_result_mapping::outcome_unknown;
use crate::core::cli_bridge::ops::account_ops::{account_credits, account_session, account_subscription};
use crate::core::cli_bridge::ops::app_ops::app_info;
use crate::core::cli_bridge::ops::generate_ops::{generate_estimate, generate_submit};
use crate::core::cli_bridge::ops::jobs_ops::{jobs_get, jobs_list};
use crate::core::cli_bridge::ops::media_ops::{media_get, media_list, media_upload};
use crate::core::cli_bridge::ops::models_ops::models_list;
use crate::core::cli_bridge::ops::op_support::{deadline_error, OpContext, OpLimits};
use futures::future::BoxFuture;
use serde_json::Value;
use std::sync::Arc;
use std::time::Duration;

/// The op allowlist, in spec §5.4 order. `GET /v1/health` reports it; the RPC handler refuses anything else with `unknown_op`.
pub const ALLOWED_OPS: &[&str] = &[
  "app.info",
  "account.session",
  "account.credits",
  "account.subscription",
  "models.list",
  "generate.estimate",
  "generate.submit",
  "jobs.get",
  "jobs.list",
  "media.upload",
  "media.get",
  "media.list",
];

const SUBMIT_OP: &str = "generate.submit";
const UPLOAD_OP: &str = "media.upload";

/// Production `DispatchFn`: every op runs as its own task on the Tauri runtime.
pub fn make_dispatch(ctx: OpContext) -> DispatchFn {
  Arc::new(move |op: String, args: Value| {
    let reply: BoxFuture<'static, Result<Value, BridgeError>> = Box::pin(dispatch_op(ctx.clone(), op, args));
    reply
  })
}

/// Spawned, so neither a client disconnect nor an expired deadline cancels an op halfway (spec §4.5).
async fn dispatch_op(ctx: OpContext, op: String, args: Value) -> Result<Value, BridgeError> {
  let deadline = op_deadline(&op, &ctx.limits);
  let expired = deadline_error_for(&op, &args);
  let handle = tauri::async_runtime::spawn(async move { run_op(&ctx, &op, args).await });
  match tokio::time::timeout(deadline, handle).await {
    Ok(Ok(result)) => result,
    Ok(Err(_)) => Err(BridgeError::new(BridgeErrorCode::InternalError, "the op failed inside the bridge; check the ArtCraft log")),
    Err(_) => Err(expired),
  }
}

async fn run_op(ctx: &OpContext, op: &str, args: Value) -> Result<Value, BridgeError> {
  match op {
    "app.info" => app_info(ctx, args),
    "account.session" => account_session(ctx, args).await,
    "account.credits" => account_credits(ctx, args).await,
    "account.subscription" => account_subscription(ctx, args).await,
    "models.list" => models_list(ctx, args).await,
    "generate.estimate" => generate_estimate(ctx, args).await,
    "generate.submit" => generate_submit(ctx, args).await,
    "jobs.get" => jobs_get(ctx, args).await,
    "jobs.list" => jobs_list(ctx, args).await,
    "media.upload" => media_upload(ctx, args).await,
    "media.get" => media_get(ctx, args).await,
    "media.list" => media_list(ctx, args).await,
    _ => Err(BridgeError::new(BridgeErrorCode::UnknownOp, "this op is not available on the bridge")),
  }
}

/// An expired deadline is a free retry for every op except submit, whose POST may already be accepted (spec §4.5).
/// An upload is retried with the same idempotency token.
fn deadline_error_for(op: &str, args: &Value) -> BridgeError {
  if op != SUBMIT_OP {
    return deadline_error();
  }
  let idempotency_token = args.get("idempotency_token").and_then(Value::as_str).unwrap_or_default();
  outcome_unknown(idempotency_token, "deadline")
}

fn op_deadline(op: &str, limits: &OpLimits) -> Duration {
  match op {
    SUBMIT_OP | UPLOAD_OP => limits.write_op_deadline,
    _ => limits.read_op_deadline,
  }
}
```

- [ ] **Step 8: Compile-check and run every bridge test**

Run: `SQLX_OFFLINE=true cargo check -p artcraft && SQLX_OFFLINE=true cargo test -p artcraft --lib cli_bridge`
Expected: `Finished`, then PASS, `40 passed`. `largest_allowed_upload_fits_under_the_body_cap` now reaches the real upload op through the stub dispatch; it still asserts only "HTTP 200, not 413".

- [ ] **Step 9: Commit**

```bash
git add crates/desktop/artcraft/src/core/cli_bridge/ops/op_support.rs crates/desktop/artcraft/src/core/cli_bridge/ops/mod.rs crates/desktop/artcraft/src/core/cli_bridge/ops/media_ops.rs crates/desktop/artcraft/src/core/cli_bridge/op_dispatch.rs
git commit -m "feat(cli-bridge): add media upload, get and list ops"
```

### Task 17: M3 live checklist (user-run)

**Files:** none modified. Results go to project memory, and to the peer for spec §6.3 and §8.1.

**Interfaces:**
- Consumes: the M3 build and the T9 shell helpers.
- Produces: the recorded server behaviour for a re-sent upload idempotency key.

- [ ] **(a) Upload.** `U=$(uuidgen | tr 'A-Z' 'a-z'); B64=$(base64 -i some.png | tr -d '\n'); rpc "{\"op\":\"media.upload\",\"args\":{\"content_base64\":\"$B64\",\"idempotency_token\":\"$U\"}}"`
  - The response has `media_token`, `kind: "image"`, `image_type: "png"` and the right `byte_count`.
  - The image appears in the app's library.
  - `ls ~/Artcraft/temp` holds no leftover upload file.
- [ ] **(b) Re-sent key.** Re-send the identical upload with the same `$U`. Record whether the server returns the original `media_token`, returns an error, or creates a second file (check the library). Send the answer to the peer: it decides whether deterministic upload keys are ever adopted (spec §6.3).
- [ ] **(c) Upload refusals.** A `.webp` gives `upload_type_unsupported`. Non-base64 text gives `invalid_args`.
- [ ] **(d) Media get.** `rpc "{\"op\":\"media.get\",\"args\":{\"media_token\":\"<token>\"}}"` returns an https `cdn_url`. A made-up token gives `media_not_found`.
- [ ] **(e) The upload works as a reference.** Estimate a model with `image_refs_supported: true` using `"image_media_tokens":["<token>"]`; the server prices it (no spend).
- [ ] **(f) Paging.** `rpc '{"op":"media.list","args":{"page_index":0,"page_size":10,"sort_ascending":false}}'` matches the app's library order and paging (`page.total_pages`). With `"media_classes":["image"]` only images are returned.

When every box is checked, update the ARTC Plane work item for T17 and tell the peer that M3 Rust is live, with the (b) result.

---

# M4 — Settings, dismiss, hardening

### Task 18: `jobs.dismiss`

**Files:**
- Modify: `crates/desktop/artcraft/src/core/cli_bridge/ops/jobs_ops.rs` (new imports, request struct, three functions, test module)
- Modify: `crates/desktop/artcraft/src/core/cli_bridge/op_dispatch.rs` (allowlist and one `run_op` arm)
- Test: new bottom `mod tests` of `jobs_ops.rs`

**Interfaces:**
- Consumes:
  - T6: `map_local_status`, `JobStatusView`.
  - T7/T13: `fetch_remote_jobs`, `list_local_tasks`.
  - T11: `temp_task_database`, `insert_artcraft_task`.
  - App: `mark_task_as_dismissed(&TaskDbConnection, &TaskId) -> Result<bool, SqliteTasksError>`.
- Produces:
  - `jobs_dismiss(&OpContext, Value)`
  - `dismiss_job<F, Fut>(&TaskDatabase, job_id: &str, remote_status: F) -> Result<Value, BridgeError>`, where `F: FnOnce() -> Fut` and `Fut: Future<Output = Result<Option<JobStatusView>, BridgeError>>`.
  - `ALLOWED_OPS`, now 13 ops.

- [ ] **Step 1: Write the failing test**

Append to the end of `jobs_ops.rs`:
```rust
#[cfg(test)]
mod tests {
  use super::*;
  use crate::core::cli_bridge::ops::test_tasks::{insert_artcraft_task, temp_task_database};
  use enums::tauri::tasks::task_status::TaskStatus;
  use sqlite_tasks::queries::update_task_status::{update_task_status, UpdateTaskArgs};
  use std::sync::atomic::{AtomicUsize, Ordering};
  use tokens::tokens::sqlite::tasks::TaskId;

  const CLI_SUBSCRIBER: &str = "cli_bridge:0f8c2a1e-3b4d-4e5f-8a9b-0c1d2e3f4a5b";
  const RUNNING_JOB: &str = "jinf_running";
  const FINISHED_JOB: &str = "jinf_finished";

  #[tokio::test]
  async fn dismiss_refuses_unfinished_jobs() {
    let (_dir, db) = temp_task_database().await;
    let running = insert_artcraft_task(&db, RUNNING_JOB, Some(CLI_SUBSCRIBER)).await;
    set_status(&db, &running, TaskStatus::Started).await;
    let finished = insert_artcraft_task(&db, FINISHED_JOB, Some(CLI_SUBSCRIBER)).await;
    set_status(&db, &finished, TaskStatus::CompleteSuccess).await;

    // Unfinished locally and remotely: refused, and the row stays visible.
    let still_running = dismiss_job(&db, RUNNING_JOB, || async { Ok::<_, BridgeError>(Some(JobStatusView::Running)) }).await;
    assert_eq!(still_running.unwrap_err().code, BridgeErrorCode::JobNotTerminal);
    assert!(listed_job_ids(&db).await.contains(&RUNNING_JOB.to_string()));

    // A failed remote check is returned as-is, and nothing is dismissed.
    let offline = dismiss_job(&db, RUNNING_JOB, || async {
      Err::<Option<JobStatusView>, _>(BridgeError::new(BridgeErrorCode::RateLimited, "slow down"))
    }).await;
    assert_eq!(offline.unwrap_err().code, BridgeErrorCode::RateLimited);
    assert!(listed_job_ids(&db).await.contains(&RUNNING_JOB.to_string()));

    // A locally finished job is dismissed without consulting the remote list.
    let remote_checks = AtomicUsize::new(0);
    let checks = &remote_checks;
    let done = dismiss_job(&db, FINISHED_JOB, move || async move {
      checks.fetch_add(1, Ordering::SeqCst);
      Ok::<_, BridgeError>(None)
    }).await.unwrap();
    assert_eq!(done["dismissed"], true);
    assert_eq!(done["task_id"], finished.as_str());
    assert_eq!(remote_checks.load(Ordering::SeqCst), 0);
    assert!(!listed_job_ids(&db).await.contains(&FINISHED_JOB.to_string()));

    // A job the server finished can go even while the local row lags behind.
    let finished_remotely = dismiss_job(&db, RUNNING_JOB, || async { Ok::<_, BridgeError>(Some(JobStatusView::Succeeded)) }).await.unwrap();
    assert_eq!(finished_remotely["dismissed"], true);

    let unknown = dismiss_job(&db, "jinf_never_seen", || async { Ok::<_, BridgeError>(None) }).await;
    assert_eq!(unknown.unwrap_err().code, BridgeErrorCode::JobNotFound);
  }

  async fn set_status(db: &TaskDatabase, task_id: &TaskId, status: TaskStatus) {
    update_task_status(UpdateTaskArgs { db: db.get_connection(), task_id, status }).await.unwrap();
  }

  async fn listed_job_ids(db: &TaskDatabase) -> Vec<String> {
    list_local_tasks(db).await.unwrap().into_iter().filter_map(|task| task.provider_job_id).collect()
  }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `SQLX_OFFLINE=true cargo test -p artcraft --lib jobs_ops`
Expected: FAIL to compile with `cannot find function dismiss_job`.

- [ ] **Step 3: Implement dismiss**

In `jobs_ops.rs`, replace the import block with:
```rust
use crate::core::cli_bridge::cli_bridge_envelope::{BridgeError, BridgeErrorCode};
use crate::core::cli_bridge::native_result_mapping::{map_storyteller_error, StorytellerCallSite};
use crate::core::cli_bridge::ops::job_view::{
  build_job_get, build_job_list, map_local_status, JobFileView, JobStatusView, JobView, OriginFilter, RemoteJob,
};
use crate::core::cli_bridge::ops::op_support::{
  invalid_args, local_store_error, parse_args, require_session, task_database, to_data, validate_id, with_call_timeout,
  OpContext,
};
use crate::core::state::app_env_configs::app_env_configs::AppEnvConfigs;
use crate::core::state::task_database::TaskDatabase;
use artcraft_client::endpoints::jobs::list_session_jobs::{list_session_jobs, States};
use artcraft_client::endpoints::media_files::list_batch_generated_redux_media_files::list_batch_generated_redux_media_files;
use enums::common::generation_provider::GenerationProvider;
use serde_derive::Deserialize;
use serde_json::{json, Value};
use sqlite_tasks::queries::get_task_by_provider_and_provider_job_id::{
  get_task_by_provider_and_provider_job_id, GetTaskByProviderAndProviderJobIdArgs,
};
use sqlite_tasks::queries::list_tasks_for_frontend::{list_tasks_for_frontend, TaskItem};
use sqlite_tasks::queries::mark_task_as_dismissed::mark_task_as_dismissed;
use sqlite_tasks::queries::task::Task;
use std::collections::HashMap;
use std::future::Future;
use tauri::Manager;
use tokens::tokens::batch_generations::BatchGenerationToken;
```
Insert after the `JobsGetRequest` struct:
```rust
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct JobsDismissRequest {
  job_id: String,
}
```
Insert after `jobs_get` (above `list_local_tasks`):
```rust
/// `jobs.dismiss` (spec §7.7): Artcraft-provider rows only, and only once the job has finished.
pub async fn jobs_dismiss(ctx: &OpContext, args: Value) -> Result<Value, BridgeError> {
  let request: JobsDismissRequest = parse_args(args)?;
  validate_id("job_id", &request.job_id)?;
  let db = task_database(&ctx.app)?;
  dismiss_job(&db, &request.job_id, || remote_status_of(ctx, &request.job_id)).await
}

/// Spec §7.7. `remote_status` runs only when the local row is not terminal. Its failure is returned
/// as-is and nothing is dismissed. The `TaskId` never crosses the wire as an input.
pub async fn dismiss_job<F, Fut>(db: &TaskDatabase, job_id: &str, remote_status: F) -> Result<Value, BridgeError>
where
  F: FnOnce() -> Fut,
  Fut: Future<Output = Result<Option<JobStatusView>, BridgeError>>,
{
  let maybe_task = get_task_by_provider_and_provider_job_id(GetTaskByProviderAndProviderJobIdArgs {
    db: db.get_connection(),
    provider: GenerationProvider::Artcraft,
    provider_job_id: job_id,
  })
  .await
  .map_err(|_| local_store_error("the task database could not be read"))?;
  let Some(task) = maybe_task else {
    return Err(job_not_found());
  };
  let terminal = map_local_status(&task.status).is_terminal()
    || remote_status().await?.is_some_and(|status| status.is_terminal());
  if !terminal {
    return Err(BridgeError::new(BridgeErrorCode::JobNotTerminal, "the job has not finished; wait before dismissing it"));
  }
  let dismissed = mark_task_as_dismissed(db.get_connection(), &task.id)
    .await
    .map_err(|_| local_store_error("the task database could not be updated"))?;
  if !dismissed {
    return Err(job_not_found());
  }
  Ok(json!({ "job_id": job_id, "task_id": task.id.as_str(), "dismissed": true }))
}

/// The remote status of one job. A job older than the newest 100 reads as unknown, so it stays undismissed.
async fn remote_status_of(ctx: &OpContext, job_id: &str) -> Result<Option<JobStatusView>, BridgeError> {
  let remote_jobs = fetch_remote_jobs(ctx)
    .await
    .map_err(|code| BridgeError::new(code, "the remote job status could not be checked"))?;
  Ok(remote_jobs.iter().find(|remote| remote.job_id == job_id).map(|remote| remote.status))
}
```
Insert above `fn default_list_limit`:
```rust
fn job_not_found() -> BridgeError {
  BridgeError::new(BridgeErrorCode::JobNotFound, "no ArtCraft task has this job id")
}

```

- [ ] **Step 4: Run the test to verify it passes**

Run: `SQLX_OFFLINE=true cargo test -p artcraft --lib jobs_ops`
Expected: PASS, `1 passed`.

- [ ] **Step 5: Allowlist `jobs.dismiss`**

In `op_dispatch.rs`:
- Change the jobs import to `use crate::core::cli_bridge::ops::jobs_ops::{jobs_dismiss, jobs_get, jobs_list};`.
- Replace `ALLOWED_OPS` with:
```rust
pub const ALLOWED_OPS: &[&str] = &[
  "app.info",
  "account.session",
  "account.credits",
  "account.subscription",
  "models.list",
  "generate.estimate",
  "generate.submit",
  "jobs.get",
  "jobs.list",
  "jobs.dismiss",
  "media.upload",
  "media.get",
  "media.list",
];
```
- In `run_op`, insert after the `"jobs.list"` arm:
```rust
    "jobs.dismiss" => jobs_dismiss(ctx, args).await,
```

- [ ] **Step 6: Compile-check and run every bridge test**

Run: `SQLX_OFFLINE=true cargo check -p artcraft && SQLX_OFFLINE=true cargo test -p artcraft --lib cli_bridge`
Expected: `Finished`, then PASS, `41 passed`.

- [ ] **Step 7: Commit**

```bash
git add crates/desktop/artcraft/src/core/cli_bridge/ops/jobs_ops.rs crates/desktop/artcraft/src/core/cli_bridge/op_dispatch.rs
git commit -m "feat(cli-bridge): add jobs.dismiss for finished jobs only"
```

### Task 19: `settings.get` and `settings.set`; the final allowlist

**Files:**
- Modify: `crates/desktop/artcraft/src/core/cli_bridge/ops/mod.rs`
- Modify: `crates/desktop/artcraft/src/core/cli_bridge/op_dispatch.rs` (full replacement below)
- Create: `crates/desktop/artcraft/src/core/cli_bridge/ops/settings_ops.rs`
- Test: bottom `mod tests` of `settings_ops.rs`

**Interfaces:**
- Consumes:
  - App: `get_app_preferences_command(State<AppPreferencesManager>) -> Result<GetAppPreferencesResponse, String>`.
  - App: `update_app_preferences_command(UpdateAppPreferencesRequest, State<AppPreferencesManager>, State<AppDataRoot>) -> Result<_, String>`.
  - App: `PreferenceName`, `ValueType`.
- Produces:
  - `settings_get`, `settings_set`: each `(&OpContext, Value) -> Result<Value, BridgeError>`.
  - The final 15-op `ALLOWED_OPS`, in spec §5.4 order.

- [ ] **Step 1: Declare the module**

Replace `crates/desktop/artcraft/src/core/cli_bridge/ops/mod.rs` with:
```rust
pub mod account_ops;
pub mod app_ops;
pub mod generate_ops;
pub mod generate_rules;
pub mod generate_submit;
pub mod job_view;
pub mod jobs_ops;
pub mod media_ops;
pub mod models_ops;
pub mod op_support;
pub mod settings_ops;
#[cfg(test)]
pub mod test_tasks;
```

- [ ] **Step 2: Write the failing test**

Create `crates/desktop/artcraft/src/core/cli_bridge/ops/settings_ops.rs` containing only:
```rust
#[cfg(test)]
mod tests {
  use super::*;

  #[test]
  fn only_play_sounds_and_auto_download_are_writable() {
    assert!(matches!(writable_preference("play_sounds"), Some(PreferenceName::PlaySounds)));
    assert!(matches!(writable_preference("auto_download"), Some(PreferenceName::AutoDownload)));

    // A path preference would let the bridge write anywhere, so it is never writable.
    let refused = ["preferred_download_directory", "preferred_download_filename", "delete_file_sound", "PLAY_SOUNDS", ""];
    for name in refused {
      assert!(writable_preference(name).is_none(), "{name}");
    }
  }
}
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `SQLX_OFFLINE=true cargo test -p artcraft --lib settings_ops`
Expected: FAIL to compile with `cannot find function writable_preference`.

- [ ] **Step 4: Implement the settings ops**

Insert above `#[cfg(test)]` in `settings_ops.rs`:
```rust
use crate::core::cli_bridge::cli_bridge_envelope::{BridgeError, BridgeErrorCode};
use crate::core::cli_bridge::ops::op_support::{invalid_args, local_store_error, parse_args, to_data, EmptyRequest, OpContext};
use crate::core::commands::app_preferences::get_app_preferences_command::get_app_preferences_command;
use crate::core::commands::app_preferences::update_app_preference_command::{
  update_app_preferences_command, PreferenceName, UpdateAppPreferencesRequest, ValueType,
};
use serde_derive::Deserialize;
use serde_json::Value;
use tauri::Manager;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SettingsSetRequest {
  preference: String,
  value: Value,
}

/// `settings.get`: every preference, read-only (spec §8.3).
pub async fn settings_get(ctx: &OpContext, args: Value) -> Result<Value, BridgeError> {
  let _: EmptyRequest = parse_args(args)?;
  read_preferences(ctx).await
}

/// `settings.set`: `play_sounds` and `auto_download` only, as booleans. The update emits no event,
/// so a UI that cached preferences may show the old value until it re-reads them.
pub async fn settings_set(ctx: &OpContext, args: Value) -> Result<Value, BridgeError> {
  let request: SettingsSetRequest = parse_args(args)?;
  let Some(preference) = writable_preference(&request.preference) else {
    return Err(BridgeError::new(BridgeErrorCode::SettingNotWritable, "only play_sounds and auto_download can be set from the bridge"));
  };
  let Some(value) = request.value.as_bool() else {
    return Err(invalid_args("value must be true or false"));
  };
  let update = UpdateAppPreferencesRequest { preference, value: Some(ValueType::Bool(value)) };
  update_app_preferences_command(update, ctx.app.state(), ctx.app.state())
    .await
    .map_err(|_| local_store_error("the preferences file could not be written"))?;
  read_preferences(ctx).await
}

async fn read_preferences(ctx: &OpContext) -> Result<Value, BridgeError> {
  let response = get_app_preferences_command(ctx.app.state())
    .await
    .map_err(|_| local_store_error("the preferences file could not be read"))?;
  to_data(&response)
}

/// Checked by name, never by deserializing into `PreferenceName`, so a path preference such as
/// `preferred_download_directory` can never be written (spec §8.3).
fn writable_preference(name: &str) -> Option<PreferenceName> {
  match name {
    "play_sounds" => Some(PreferenceName::PlaySounds),
    "auto_download" => Some(PreferenceName::AutoDownload),
    _ => None,
  }
}

```

- [ ] **Step 5: Run the test to verify it passes**

Run: `SQLX_OFFLINE=true cargo test -p artcraft --lib settings_ops`
Expected: PASS, `1 passed`.

- [ ] **Step 6: Replace `op_dispatch.rs` with the final allowlist**

```rust
use crate::core::cli_bridge::cli_bridge_envelope::{BridgeError, BridgeErrorCode};
use crate::core::cli_bridge::cli_bridge_gate::DispatchFn;
use crate::core::cli_bridge::native_result_mapping::outcome_unknown;
use crate::core::cli_bridge::ops::account_ops::{account_credits, account_session, account_subscription};
use crate::core::cli_bridge::ops::app_ops::app_info;
use crate::core::cli_bridge::ops::generate_ops::{generate_estimate, generate_submit};
use crate::core::cli_bridge::ops::jobs_ops::{jobs_dismiss, jobs_get, jobs_list};
use crate::core::cli_bridge::ops::media_ops::{media_get, media_list, media_upload};
use crate::core::cli_bridge::ops::models_ops::models_list;
use crate::core::cli_bridge::ops::op_support::{deadline_error, OpContext, OpLimits};
use crate::core::cli_bridge::ops::settings_ops::{settings_get, settings_set};
use futures::future::BoxFuture;
use serde_json::Value;
use std::sync::Arc;
use std::time::Duration;

/// The op allowlist, in spec §5.4 order. `GET /v1/health` reports it; the RPC handler refuses anything else with `unknown_op`.
pub const ALLOWED_OPS: &[&str] = &[
  "app.info",
  "account.session",
  "account.credits",
  "account.subscription",
  "models.list",
  "generate.estimate",
  "generate.submit",
  "jobs.get",
  "jobs.list",
  "jobs.dismiss",
  "media.upload",
  "media.get",
  "media.list",
  "settings.get",
  "settings.set",
];

const SUBMIT_OP: &str = "generate.submit";
const UPLOAD_OP: &str = "media.upload";

/// Production `DispatchFn`: every op runs as its own task on the Tauri runtime.
pub fn make_dispatch(ctx: OpContext) -> DispatchFn {
  Arc::new(move |op: String, args: Value| {
    let reply: BoxFuture<'static, Result<Value, BridgeError>> = Box::pin(dispatch_op(ctx.clone(), op, args));
    reply
  })
}

/// Spawned, so neither a client disconnect nor an expired deadline cancels an op halfway (spec §4.5).
async fn dispatch_op(ctx: OpContext, op: String, args: Value) -> Result<Value, BridgeError> {
  let deadline = op_deadline(&op, &ctx.limits);
  let expired = deadline_error_for(&op, &args);
  let handle = tauri::async_runtime::spawn(async move { run_op(&ctx, &op, args).await });
  match tokio::time::timeout(deadline, handle).await {
    Ok(Ok(result)) => result,
    Ok(Err(_)) => Err(BridgeError::new(BridgeErrorCode::InternalError, "the op failed inside the bridge; check the ArtCraft log")),
    Err(_) => Err(expired),
  }
}

async fn run_op(ctx: &OpContext, op: &str, args: Value) -> Result<Value, BridgeError> {
  match op {
    "app.info" => app_info(ctx, args),
    "account.session" => account_session(ctx, args).await,
    "account.credits" => account_credits(ctx, args).await,
    "account.subscription" => account_subscription(ctx, args).await,
    "models.list" => models_list(ctx, args).await,
    "generate.estimate" => generate_estimate(ctx, args).await,
    "generate.submit" => generate_submit(ctx, args).await,
    "jobs.get" => jobs_get(ctx, args).await,
    "jobs.list" => jobs_list(ctx, args).await,
    "jobs.dismiss" => jobs_dismiss(ctx, args).await,
    "media.upload" => media_upload(ctx, args).await,
    "media.get" => media_get(ctx, args).await,
    "media.list" => media_list(ctx, args).await,
    "settings.get" => settings_get(ctx, args).await,
    "settings.set" => settings_set(ctx, args).await,
    _ => Err(BridgeError::new(BridgeErrorCode::UnknownOp, "this op is not available on the bridge")),
  }
}

/// An expired deadline is a free retry for every op except submit, whose POST may already be accepted (spec §4.5).
/// An upload is retried with the same idempotency token.
fn deadline_error_for(op: &str, args: &Value) -> BridgeError {
  if op != SUBMIT_OP {
    return deadline_error();
  }
  let idempotency_token = args.get("idempotency_token").and_then(Value::as_str).unwrap_or_default();
  outcome_unknown(idempotency_token, "deadline")
}

fn op_deadline(op: &str, limits: &OpLimits) -> Duration {
  match op {
    SUBMIT_OP | UPLOAD_OP => limits.write_op_deadline,
    _ => limits.read_op_deadline,
  }
}
```

- [ ] **Step 7: Full verification**

Run, from the repo root:
```bash
SQLX_OFFLINE=true cargo check -p artcraft
SQLX_OFFLINE=true cargo test -p artcraft --lib cli_bridge
cargo test -p artcraft_client --lib list_user_media_files
SQLX_OFFLINE=true cargo test -p artcraft --lib 2>&1 | tail -n 40
```
Expected:
- `Finished`, with no new warnings under `cli_bridge`.
- PASS, `42 passed`; then `1 passed`.
- The full `artcraft` run shows the T1 baseline results plus 42 new passes. Any failure not in the T1 baseline is a regression: stop and fix it before committing. Report pre-existing failures as they are; never skip or silence them.

Then confirm that every spec §10.2 Rust test name exists exactly once (the renamed video test is checked separately):
```bash
for t in dns_rebound_host_is_rejected_before_token_check lookalike_localhost_hosts_are_rejected all_three_loopback_host_spellings_are_accepted any_origin_or_fetch_metadata_header_is_rejected_even_with_valid_token wrong_token_is_401_and_never_echoed form_posts_from_web_pages_get_415 options_preflight_never_succeeds_and_sends_no_cors_headers unknown_ops_never_reach_dispatch excess_in_flight_requests_get_503_bridge_busy op_errors_return_http_200_with_ok_false every_gate_rejection_is_a_json_envelope largest_allowed_upload_fits_under_the_body_cap non_upload_ops_over_1mib_get_args_too_large each_launch_gets_a_fresh_256_bit_token debug_output_never_contains_token discovery_file_is_owner_only_and_written_after_bind exit_cleanup_only_removes_this_processes_file native_results_map_to_stable_codes pre_post_failures_in_submit_never_become_outcome_unknown legacy_image_models_are_refused_before_estimate_or_spend reserved_request_keys_are_refused inpainting_masks_are_unsupported_route unknown_or_fractional_cost_is_refused_before_spend cost_over_max_credits_is_refused_before_spend free_or_unlimited_generations_skip_the_balance_check balance_below_estimate_is_refused_before_spend video_batches_are_priced_per_video_like_the_app concurrent_submits_with_one_token_post_once stalled_submit_returns_outcome_unknown_and_frees_its_token_after_the_hard_cap every_local_and_remote_status_maps_to_the_closed_vocabulary remote_terminal_status_wins_over_local remote_only_jobs_appear_only_under_origin_all rows_without_a_provider_job_id_are_omitted resubmitting_a_tagged_token_replays_every_batch_row_without_posting untagged_tasks_are_never_replayed dismiss_refuses_unfinished_jobs media_list_builds_the_user_list_url_with_filters; do n=$(grep -rn "fn $t()" crates/desktop/artcraft/src/core/cli_bridge crates/api_clients/artcraft/artcraft_client/src/endpoints/media_files | wc -l | tr -d ' '); [ "$n" = 1 ] || echo "MISSING_OR_DUPLICATE $t $n"; done; echo checked
```
Expected: only `checked`.

- [ ] **Step 8: Commit**

```bash
git add crates/desktop/artcraft/src/core/cli_bridge/ops/mod.rs crates/desktop/artcraft/src/core/cli_bridge/ops/settings_ops.rs crates/desktop/artcraft/src/core/cli_bridge/op_dispatch.rs
git commit -m "feat(cli-bridge): add settings ops and complete the 15-op allowlist"
```

### Task 20: M4 live checklist (user-run)

**Files:** none modified. Results go to project memory.

**Interfaces:**
- Consumes: the M4 build and the T9 shell helpers. Run the app as `ARTCRAFT_CLI_BRIDGE=1 ./script/artcraft/unix_dev.sh 2>&1 | tee ~/artcraft-dev.log`, with `RUST_LOG` **unset** (the default Info level; see spec §4.6).
- Produces: sign-off that sub-project 1's Rust side is complete.

- [ ] **(a) The allowlist is final.** `curl -s -H "Authorization: Bearer $TOKEN" "$B/v1/health"` lists exactly the 15 spec §5.4 ops, in order.
- [ ] **(b) Nothing excluded is reachable.** Send every registered command name, plus `flip_image`, as an op. Every reply is `unknown_op`:
```bash
for op in $(grep -oE '\b[a-z0-9_]+_command\b' crates/desktop/artcraft/src/lib.rs | sort -u) flip_image; do rpc "{\"op\":\"$op\",\"args\":{}}"; done | grep -vc '"unknown_op"'
```
Expected: `0`.
- [ ] **(c) Dismiss.** On a finished bridge job, `rpc "{\"op\":\"jobs.dismiss\",\"args\":{\"job_id\":\"<job id>\"}}"` gives `dismissed: true`, and the job leaves the app's task panel. On a running job it gives `job_not_terminal`. On a made-up id it gives `job_not_found`.
- [ ] **(d) Settings.**
  - `rpc '{"op":"settings.get","args":{}}'` matches the app's settings.
  - `rpc '{"op":"settings.set","args":{"preference":"play_sounds","value":false}}'` returns the updated preferences. A bridge generation then plays no sound. Restore with `true`.
  - `rpc '{"op":"settings.set","args":{"preference":"preferred_download_directory","value":true}}'` gives `setting_not_writable`.
  - `rpc '{"op":"settings.set","args":{"preference":"play_sounds","value":"no"}}'` gives `invalid_args`.
- [ ] **(e) Log hygiene.** Run `grep -c "$TOKEN" ~/artcraft-dev.log` (expect `0`). Grep for a prompt used in this session (expect `0`). Grep for the first 40 characters of an uploaded file's base64 (expect `0`).

When every box is checked, update the ARTC Plane work item for T20 and tell the peer that the Rust side of sub-project 1 is complete. A PR to `storytold/artcraft` is the user's decision (spec §10.1), so do not open one.

---

## Spec Coverage Map

| Spec section                                       | Task(s)                    |
|----------------------------------------------------|----------------------------|
| §4.1 opt-in and startup                            | T8, T9 (a)                 |
| §4.2 server, routes, panics                        | T3, T7, T8                 |
| §4.3 token and discovery file                      | T2, T8, T9 (b)(i)          |
| §4.4 gate and limits                               | T3, T9 (h)                 |
| §4.5 deadlines and timeouts                        | T4, T7, T11, T12           |
| §4.6 logging                                       | T3, T12, T14 (g), T20 (e)  |
| §4.8 code changes and conventions                  | all                        |
| §5.1–5.4 envelope, status, version, health         | T3                         |
| §5.5 ops table                                     | T7, T12, T13, T16, T18, T19|
| §5.6 error codes                                   | T3                         |
| §5.7 native result mapping                         | T4                         |
| §7.1–7.3 route guard, deny-list, estimate          | T5, T7                     |
| §7.4 submit                                        | T10, T11, T12, T14         |
| §7.6 jobs.get / jobs.list                          | T6, T7, T13                |
| §7.7 jobs.dismiss                                  | T18                        |
| §8.1 media.upload                                  | T16, T17                   |
| §8.2 media.list                                    | T15, T16, T17              |
| §8.3 settings                                      | T19, T20 (d)               |
| §9 exclusions                                      | T3 (allowlist), T20 (b)    |
| §10.2 Rust tests                                   | T2–T6, T10, T11, T15, T18  |
| §10.3 live checklists                              | T1, T9, T14, T17, T20      |
