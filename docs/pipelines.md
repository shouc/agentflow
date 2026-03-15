# Pipeline Reference

Pipeline authoring details, execution targets, and per-agent launch behavior.

## Airflow-like Python DAG

```python
from agentflow import DAG, claude, codex, kimi

with DAG("demo", working_dir=".", concurrency=3) as dag:
    plan = codex(task_id="plan", prompt="Inspect the repo and plan the work.")
    implement = claude(
        task_id="implement",
        prompt="Implement the plan:\n\n{{ nodes.plan.output }}",
        tools="read_write",
    )
    review = kimi(
        task_id="review",
        prompt="Review the plan:\n\n{{ nodes.plan.output }}",
        capture="trace",
    )
    merge = codex(
        task_id="merge",
        prompt="Merge the implementation and review outputs.",
    )

    plan >> [implement, review]
    [implement, review] >> merge

spec = dag.to_spec()
```

See `examples/airflow_like.py` for a complete runnable example.

## Pipeline schema

Each node supports:

- `agent`: `codex`, `claude`, or `kimi`
- `fanout`: expand one node definition into `count` concrete nodes before validation; accepts `count` and optional `as`
- `model`: any model string understood by the backend
- `provider`: a string or a structured provider config with `base_url`, `api_key_env`, headers, and env
- `tools`: `read_only` or `read_write`
- `mcps`: a list of MCP server definitions
- `skills`: a list of local skill paths or names
- `target`: `local`, `container`, or `aws_lambda`
- local working-dir and shell bootstrap fields: `cwd`, `bootstrap`, `shell`, `shell_login`, `shell_interactive`, and `shell_init`
- `capture`: `final` or `trace`
- `retries` and `retry_backoff_seconds`
- `success_criteria`: output or filesystem checks evaluated after execution

Skill entries are resolved from the pipeline `working_dir`. You can point `skills:` at a plain file, a `.md` file, a home-relative path such as `~/.codex/skills/release-skill`, or a directory that contains `SKILL.md`, which keeps reusable local skill bundles easy to share across Codex, Claude, and Kimi nodes.

Top-level pipeline controls include:

- `concurrency`: max parallel nodes within a run
- `fail_fast`: skip downstream work after the first failed node

## Fan-out nodes

Use `fanout` when a DAG needs many nearly identical nodes, such as repository sweeps, fuzzing swarms, or shardable audits.
AgentFlow expands those nodes into an ordinary concrete DAG before validation and execution, so the orchestrator, runners, and persisted runs still operate on normal node ids.

```yaml
nodes:
  - id: fuzz
    fanout:
      count: 8
      as: shard
    agent: codex
    prompt: |
      You are shard {{ shard.number }} of {{ shard.count }}.
      Use suffix {{ shard.suffix }} for any per-shard paths or seeds.

  - id: merge
    agent: codex
    depends_on: [fuzz]
    prompt: |
      {% for shard in fanouts.fuzz.nodes %}
      ## {{ shard.id }}
      {{ shard.output or "(no output)" }}

      {% endfor %}
```

Expansion rules:

- A fan-out node with `id: fuzz` and `count: 8` expands to `fuzz_0` through `fuzz_7`. The suffix is zero-padded when the fan-out size needs it, so `count: 128` becomes `fuzz_000` through `fuzz_127`.
- `fanout.as` picks the template variable name for pre-validation substitution. AgentFlow currently expands dotted placeholders rooted at that alias or `fanout`, such as `{{ shard.number }}`, `{{ shard.suffix }}`, `{{ fanout.count }}`, `target.cwd: agents/agent_{{ shard.suffix }}`, or `depends_on: ["prepare_{{ shard.suffix }}"]`.
- Ordinary runtime prompt templates such as `{{ nodes.prepare.output }}` are left intact and still render at execution time.
- A downstream `depends_on: [fuzz]` expands to all members of the `fuzz` group.
- During prompt rendering, `fanouts.<group>.nodes` exposes the grouped member outputs with `id`, `status`, `output`, `final_response`, `stdout`, `stderr`, and `trace`, plus convenience lists such as `fanouts.<group>.outputs`.

Runtime numeric settings are validated up front: `concurrency` must be at least `1`, `timeout_seconds` must be greater than `0`, and both `retries` and `retry_backoff_seconds` must be non-negative.

MCP definitions are also validated before launch: `stdio` servers require `command` and reject HTTP-only fields such as `url`, `streamable_http` servers require `url` and reject stdio-only fields such as `command`, and MCP server names must be unique within a node.

Built-in provider shorthands:

- `codex`: `openai`
- `claude`: `anthropic`, `kimi`
- `kimi`: `kimi`, `moonshot`, `moonshot-ai`

`provider: kimi` is intentionally rejected on `codex` nodes. Codex requires an OpenAI Responses API backend, and Kimi's public endpoints do not expose `/responses`.

When both `provider.env` and `node.env` define the same variable, `node.env` wins. That keeps per-node overrides aligned with the values `agentflow doctor`, `inspect`, and the actual launch environment use.
For Claude-compatible Kimi setups, that same effective-env rule also means `doctor` and `inspect` recognize custom providers that set `ANTHROPIC_BASE_URL=https://api.kimi.com/coding/` in `provider.env`, even when `provider.base_url` is omitted.

## Execution targets

### Local

Runs the prepared agent command directly on the host. Set `target.shell` to wrap the command in a specific shell, such as `bash -lc`. If you provide a shell name without an explicit command flag, AgentFlow uses `-c` by default; opt into startup file loading with `shell_login: true` and `shell_interactive: true`. You can also use a `{command}` placeholder in the shell string to run shell bootstrap steps before the prepared agent command.

That default `-c` behavior applies to `{command}` templates too, so wrappers such as `env FOO=bar bash {command}` work without needing to spell `-c` manually.
When the wrapper starts with `env -i`, AgentFlow now preserves the prepared launch env by inlining those variables into the `env` command itself, and it still applies `shell_login` / `shell_interactive` to the real shell executable rather than mistaking wrapper flags such as `env -i` for shell flags.
For Bash specifically, use `-c` and either `-i` or `shell_interactive: true`; Bash accepts `--login`, but not `--command` or `--interactive`, and AgentFlow now rejects those invalid wrappers during validation instead of failing later at launch time.

`target.cwd` controls the local node working directory. Absolute paths are used as-is; relative paths are resolved from the pipeline `working_dir`. File-based success criteria such as `file_exists`, `file_contains`, and `file_nonempty` are evaluated from that resolved local node working directory.

The local-shell bootstrap fields `shell_login`, `shell_interactive`, and `shell_init` require `target.shell`. For the common Kimi helper case, `target.bootstrap: kimi` expands to the same `bash` + login + interactive + `shell_init` setup automatically.

For common shell helper workflows, you can keep the config declarative instead of hand-writing a quoted shell template:

```yaml
target:
  kind: local
  bootstrap: kimi
```

This expands to `shell: bash`, `shell_login: true`, `shell_interactive: true`, and `shell_init: ["command -v kimi >/dev/null 2>&1", "kimi"]`, then launches the prepared agent command. `shell_init` still accepts either a single command or a list of commands when you need the lower-level form; list entries are joined with `&&` so bootstrap failures still stop the wrapped agent launch. When you combine `bootstrap: kimi` with extra `shell_init` commands, AgentFlow now keeps those extra commands first and still appends the Kimi helper automatically, so node-specific bootstrap tweaks do not silently drop the shared Kimi setup.
`agentflow validate` also treats `bootstrap: kimi` as a contract: if later overrides switch the node away from bash or disable interactive bash startup, validation now fails early instead of deferring that contradiction to inspect or preflight. If you need a different shell shape, drop `target.bootstrap` and configure the wrapper explicitly.

When most local nodes share the same shell bootstrap, move that block to top-level `local_target_defaults` and only override the nodes that differ:

```yaml
local_target_defaults:
  bootstrap: kimi

nodes:
  - id: codex_plan
    agent: codex
    prompt: Reply with exactly: codex ok

  - id: claude_review
    agent: claude
    provider: kimi
    prompt: Reply with exactly: claude ok
    target:
      cwd: review
```

AgentFlow applies `local_target_defaults` to local nodes that omit `target`, merges it into local nodes that only override part of `target`, and leaves container or Lambda targets unchanged. If you prefer to spell the wrapper directly, explicit shells such as `bash -lic` behave the same way, and AgentFlow suppresses Bash's harmless no-job-control stderr noise for those interactive wrappers too. If your login shell uses `~/.bash_profile`, make sure it eventually reaches `~/.bashrc`, either directly or via another startup file such as `~/.profile`; otherwise Bash only reads `~/.profile` when no `~/.bash_profile` or `~/.bash_login` file is present. A minimal bridge looks like:

If one local node should not inherit the shared Kimi preset, set `target.bootstrap: null` on that node. AgentFlow now treats that as an explicit opt-out from the inherited bootstrap while still preserving unrelated local defaults such as `cwd`. That opt-out also drops inherited shell bootstrap fields such as `shell`, `shell_login`, `shell_interactive`, and any shared `shell_init` commands, including extra commands that were prepended to the shared Kimi bootstrap.

```yaml
local_target_defaults:
  bootstrap: kimi
  cwd: workspace

nodes:
  - id: codex_plan
    agent: codex
    prompt: Reply with exactly: codex ok

  - id: codex_direct
    agent: codex
    prompt: Reply with exactly: direct ok
    target:
      bootstrap: null
```

```bash
# ~/.bash_profile or ~/.profile
if [ -f "$HOME"/.bashrc ]; then
  . "$HOME"/.bashrc
fi
```

When you bootstrap `kimi` through Bash, keep Bash interactive too. `agentflow inspect` and the `run`/`smoke` auto-preflight now warn when either `shell_init: kimi` or an explicit `target.shell` wrapper such as `bash -lc 'kimi && {command}'`, `bash -lc 'eval "$(kimi)" && {command}'`, `bash -lc 'export $(kimi) && {command}'`, or `bash -lc 'source <(kimi) && {command}'` is paired with non-interactive Bash, because helpers defined in `~/.bashrc` are commonly skipped in `bash -lc`-style setups. That warning also calls out the easy-to-miss case where the wrapper explicitly runs `source ~/.bashrc` first, but `~/.bashrc` still returns early for non-interactive shells on the current host. If you intentionally preload `kimi` through `BASH_ENV=/path/to/shell.env bash -c ...` and that file defines the `kimi` helper or sources another file that does, AgentFlow treats that wrapper as ready and does not emit the `~/.bashrc` warning. The same readiness shortcut now applies when a non-interactive Bash wrapper explicitly sources a login file such as `~/.profile` or `~/.bash_profile` before `kimi`, as long as that sourced file really defines `kimi` or reaches another file that does. Use an explicit home path such as `~/.profile` or `$HOME/.bashrc` for those bridges; bare relative paths like `.bashrc` resolve from the shell's current working directory, not your home directory.

`agentflow doctor` now also calls out the easy-to-miss case where `~/.bash_profile` exists, does not source `~/.bashrc`, and silently prevents a working `~/.profile` -> `~/.bashrc` bridge from ever running. When Bash falls back to `~/.profile` because `~/.bash_profile` and `~/.bash_login` are absent, the doctor output now says so directly. It also recognizes bridges written as absolute home paths such as `source /home/alice/.bashrc`, treats `~/.bashrc` symlinks into an external dotfiles repo as valid login-shell bridges, follows custom sourced files inside `HOME` such as `~/.bash_profile` -> `~/.bash_agentflow` -> `~/.bashrc`, verifies that both `claude --version` and `codex --version` still work after the shared `kimi` bootstrap, and reports unreadable startup files as warnings instead of crashing. When bash startup checks fail in less predictable ways, the doctor output now strips Bash's harmless interactive-shell noise and redacts likely secret values before echoing shell diagnostics back to you. If you want the exact bridge to paste into the active login file, run `agentflow doctor --output summary --shell-bridge`.

`shell_init` is treated as a bootstrap prerequisite: if it exits non-zero, AgentFlow does not launch the wrapped agent command. This helps smoke runs fail fast when helper functions such as `kimi` are missing.

### Container

Wraps the command in `docker run`, mounts the working directory, runtime directory, and the AgentFlow app, then streams stdout and stderr back into the run trace.

### AWS Lambda

Invokes `agentflow.remote.lambda_handler.handler`. The payload contains the prepared command, environment, runtime files, and execution metadata so the Lambda package can execute the node remotely.

## Agent notes

### Codex

- Uses `codex exec --json`
- Maps tools mode to Codex sandboxing
- Keeps model-only Codex nodes on the ambient CLI login path instead of forcing an isolated `CODEX_HOME`
- Writes `CODEX_HOME/config.toml` only when provider or MCP selection requires an isolated home

### Claude

- Uses `claude -p ... --output-format stream-json --verbose`
- Passes `--tools` according to the read-only vs read-write policy
- Writes a per-node MCP JSON config and passes it with `--mcp-config`

### Kimi

- Uses the active Python interpreter via `sys.executable -m agentflow.remote.kimi_bridge`
- Emits a Kimi-style JSON-RPC event stream
- Calls Moonshot's OpenAI-compatible chat completions API
- Provides a small built-in tool layer for read, search, write, and shell actions
