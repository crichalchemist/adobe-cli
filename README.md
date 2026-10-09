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
