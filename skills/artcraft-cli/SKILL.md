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
