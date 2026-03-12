# Testing and Maintainer Workflows

Repo test commands, smoke checks, and local verification helpers.

## Testing

Run the Python suite:

```bash
make test
```

That shortcut uses the same interpreter resolution as the other repo-local helpers: `.venv/bin/python` when the repo virtualenv exists, otherwise `python3`. Run `make python` when you want to confirm which interpreter those shortcuts will use on your machine.

Run the browser suite:

```bash
npm install
npx playwright install chromium
npx playwright test
```

The Playwright tests use lightweight mock `codex` and `claude` executables under `tests/e2e/bin/` and exercise validation, retries, rerun, cancellation, and artifact viewing through the web UI.

Run a real local smoke check with your installed CLIs:

```bash
. .venv/bin/activate
agentflow smoke
```

When you are iterating on local Kimi shell bootstrap behavior itself, run the lighter maintainer check first:

```bash
agentflow toolchain-local
```

That command intentionally uses `bash -lic` before running `kimi`, `codex --version`, and `claude --version`, so it exercises the same login + interactive shell path that the bundled local smoke depends on. This avoids the easy-to-misread non-interactive `source ~/.bashrc` path where Bash often returns before the `kimi` helper is defined.
It also now enforces the same Kimi-specific assumptions that the bundled smoke preflight depends on: `kimi` must export `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL` must resolve to `https://api.kimi.com/coding/`, and Codex auth must already work via `codex login status` or `OPENAI_API_KEY`.
Before those checks run, `agentflow toolchain-local` also prints the active bash login startup chain, for example `~/.bash_profile -> ~/.profile -> ~/.bashrc` or `~/.profile -> ~/.bashrc`, so it is easier to confirm which file actually supplied the shared Kimi bootstrap on your machine. The summary now also includes how `kimi` resolved inside that login shell, such as `function` from your startup files or `file (/path/to/kimi)` when it came from PATH, plus the resolved `codex` and `claude` executable paths alongside their versions. That helps when the local shell and the prepared smoke shell are not using the same install or when `kimi` only exists as a shell function.
When your current shell still exports ambient relay values such as `OPENAI_BASE_URL` or `ANTHROPIC_BASE_URL`, `toolchain-local` now prints them too. That keeps custom local Codex and Claude pipelines from inheriting hidden routing drift just because the bundled smoke happens to clear or pin those values for you.
Like the other maintainer-oriented CLI surfaces, `toolchain-local` also accepts `--output json-summary` when you want a compact machine-readable payload for wrappers without the full `shell_bridge.snippet` from `--output json`.
On hosts that rely on Bash falling back to `~/.profile`, a healthy setup can still print `~/.bash_profile: missing` and `~/.bash_login: missing`; the key line is the resolved `bash login startup: ...` chain. When that chain is broken or shadowed, the maintainer check follows it with either `bash login bridge: not needed` or the explicit target, source, reason, and snippet to paste into the active login file.
Those maintainer shell probes fail fast too: the default budget is 15 seconds per wrapped command, and `AGENTFLOW_DOCTOR_TIMEOUT_SECONDS` raises that budget when a slower local bootstrap genuinely needs more time.

From the repo root, `make toolchain-local` is now just a thin shortcut for `agentflow toolchain-local --output summary`.

From the repo root, `make inspect-local`, `make doctor-local`, `make smoke-local`, `make run-local`, and `make check-local` wrap the same bundled Kimi-backed workflow and now prefer `.venv/bin/python` automatically when that repo-local virtualenv exists, falling back to `python3` otherwise. `make run-local` delegates to `agentflow run examples/local-real-agents-kimi-smoke.yaml --output summary`, which makes it easy to exercise the bundled DAG through the main run surface without switching to JSON or a custom path. `make check-local` now delegates straight to `agentflow check-local --output summary`, which keeps the preflight and run in one pass instead of rerunning Doctor through `smoke-local`, while forcing compact maintainer-friendly output even when logs are captured without a TTY. `make probe-codex-local` and `make probe-claude-local` sit next to those shortcuts as the smallest possible live Codex and Claude requests, so CLI auth, relay, membership, or billing failures show up before the wider smoke stack, and raw API rejections now carry a diagnosis that distinguishes upstream provider failures from local shell/bootstrap drift. The CLI itself still keeps its normal auto-output behavior outside those shortcuts, and its stderr preflight report follows the requested run output style: summary for `--output summary`, full JSON for `--output json`, and compact JSON summary for `--output json-summary`. When you specifically want the external custom-pipeline versions of the doctor, inspect, check-local, and run contracts, the `make *-local-custom*` helpers now cover `bootstrap: kimi`, explicit `shell_init: kimi`, and explicit `target.shell` Kimi wrappers against the real local Codex and Claude CLIs.

This keeps the check small while exercising both local `codex` and local `claude` end-to-end. Before the bundled smoke pipeline starts, AgentFlow runs a local preflight that verifies `codex`, confirms that `bash -lic` can find the `kimi` shell helper and still launch both `claude` and `codex` afterwards, checks that `claude --version` still works inside that shared smoke shell, checks that `kimi` exports both `ANTHROPIC_API_KEY` and the Kimi Claude endpoint in `ANTHROPIC_BASE_URL`, confirms Codex authentication is ready inside that shared smoke shell via `codex login status` or `OPENAI_API_KEY`, and reports which bash login startup file is active, including transitive bridges such as `~/.bash_profile` -> `~/.profile` -> `~/.bashrc`. That startup check also accepts the common dotfiles pattern where `~/.bashrc` itself is a symlink into another repo. The preflight warns when a login startup file references `~/.bashrc` but that file is missing, or when no bash login startup file exists to bridge into `~/.bashrc` at all. If `codex` or `claude` only become available inside that shared login-shell bootstrap, the readiness report still stays green because the bundled smoke pipeline can already launch them there.

When `~/.bash_profile` or `~/.bash_login` shadows a working `~/.profile` bridge, the preflight now tells you that the alternate startup path will never run, points you at the file that needs the bridge, and includes the bridge snippet inline when one is available.

You can run the same preflight directly:

```bash
. .venv/bin/activate
agentflow doctor
```

When `codex` or `claude` are already on `PATH`, the doctor summary now includes the resolved executable path and `--version` output to make local CLI mismatches easier to spot. Use `agentflow doctor --output json-summary` when you want the compact machine-readable summary payload that matches the other orchestration commands, or `--output json` when you need each check's full `context`.

The bundled smoke pipeline bootstraps the `kimi` shell helper inside both local nodes, so you do not need to wrap the entire `agentflow smoke` command in `bash -lic`. If you want to run a custom smoke pipeline instead, pass its path explicitly with `agentflow smoke path/to/pipeline.yaml`, or run it directly with `agentflow run path/to/pipeline.yaml` and keep the same `auto` preflight behavior for bundled and Kimi-bootstrapped local smoke pipelines. `run` now mirrors `smoke` by defaulting to the compact summary on an interactive terminal while still falling back to full JSON when stdout is redirected. Use `--preflight always` for other custom pipelines that still need those checks; forced preflight still follows the agents and bootstrap that your pipeline actually uses. Use `--preflight never` to skip preflight even for the bundled example. Add `--output json-summary` when you want a concise machine-readable result, or `--output json` when you want the full persisted run record instead of the compact summary.

