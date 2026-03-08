# AgentFlow

AgentFlow is a Python orchestrator for `codex`, `claude`, and `kimi` agents with Airflow-style DAGs, parallel scheduling, multiple execution targets, and a live web console for traces and artifacts.

## Features

- Airflow-like pipeline definitions in Python and YAML
- Parallel DAG execution with dependency-aware scheduling
- Per-node selection of model, provider, tools policy, MCP servers, and skills
- Execution targets for local processes, containers, and AWS Lambda
- Per-node output capture as either final response or full trace
- Post-run success criteria including output contains text, file exists, file contains text, and file non-empty
- Run queueing, retries, retry backoff, cancellation, rerun, and persisted run recovery
- Web UI for DAG state, attempt history, JSONL trace parsing, stdout/stderr, and node artifacts
- API endpoints for validation, launch, events, artifacts, cancel, rerun, and health checks

## Why this shape

This project was built in this repo, and the integrations were informed by:

- OpenAI Codex CLI patterns in `reference/codex`
- Claude Code web and stream patterns in `reference/claude-code-telegram`
- Moonshot Kimi CLI protocol and UI patterns in `reference/kimi-cli`

Those references shaped the trace parsers, adapter contracts, and frontend event model.

## Install

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
```

## Quick start

Validate a pipeline:

```bash
agentflow validate examples/pipeline.yaml
```

Run a pipeline once:

```bash
agentflow run examples/pipeline.yaml
```

Run the bundled real-agent smoke check:

```bash
agentflow smoke
```

Check the local Codex/Claude/Kimi smoke prerequisites without launching a run:

```bash
agentflow doctor
```

Run the web console:

```bash
agentflow serve --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`.

## Runtime configuration

You can configure the runtime via CLI flags or environment variables.

- `AGENTFLOW_RUNS_DIR`: base directory for run state and artifacts
- `AGENTFLOW_MAX_CONCURRENT_RUNS`: maximum number of concurrently executing DAG runs

CLI equivalents:

```bash
agentflow serve --runs-dir .agentflow/runs --max-concurrent-runs 2
agentflow run examples/pipeline.yaml --runs-dir .agentflow/runs --max-concurrent-runs 2
```

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
- `model`: any model string understood by the backend
- `provider`: a string or a structured provider config with `base_url`, `api_key_env`, headers, and env
- `tools`: `read_only` or `read_write`
- `mcps`: a list of MCP server definitions
- `skills`: a list of local skill paths or names
- `target`: `local`, `container`, or `aws_lambda`
- local shell bootstrap fields: `shell`, `shell_login`, `shell_interactive`, and `shell_init`
- `capture`: `final` or `trace`
- `retries` and `retry_backoff_seconds`
- `success_criteria`: output or filesystem checks evaluated after execution

Top-level pipeline controls include:

- `concurrency`: max parallel nodes within a run
- `fail_fast`: skip downstream work after the first failed node

Built-in provider shorthands:

- `codex`: `openai`
- `claude`: `anthropic`, `kimi`
- `kimi`: `kimi`, `moonshot`, `moonshot-ai`

`provider: kimi` is intentionally rejected on `codex` nodes. Codex requires an OpenAI Responses API backend, and Kimi's public endpoints do not expose `/responses`.

## Execution targets

### Local

Runs the prepared agent command directly on the host. Set `target.shell` to wrap the command in a specific shell, such as `bash -lc`. If you provide a shell name without an explicit command flag, AgentFlow uses `-c` by default; opt into startup file loading with `shell_login: true` and `shell_interactive: true`. You can also use a `{command}` placeholder in the shell string to run shell bootstrap steps before the prepared agent command.

The local-shell bootstrap fields `shell_login`, `shell_interactive`, and `shell_init` require `target.shell`. AgentFlow now rejects configs that set those fields without an explicit shell, because they would otherwise be silently ignored.

For common shell helper workflows, you can keep the config declarative instead of hand-writing a quoted shell template:

```yaml
target:
  kind: local
  shell: bash
  shell_login: true
  shell_interactive: true
  shell_init: kimi
```

This runs the node inside `bash`, explicitly enables login and interactive startup files, executes `kimi`, and then launches the prepared agent command. It is useful for helper functions defined in `~/.bashrc`. Validation rejects `shell_login`, `shell_interactive`, or `shell_init` unless `target.shell` is also set, so these bootstrap fields cannot silently no-op. If your login shell uses `~/.bash_profile`, make sure it eventually reaches `~/.bashrc`, either directly or via another startup file such as `~/.profile`; otherwise Bash only reads `~/.profile` when no `~/.bash_profile` or `~/.bash_login` file is present.

`shell_init` is treated as a bootstrap prerequisite: if it exits non-zero, AgentFlow does not launch the wrapped agent command. This helps smoke runs fail fast when helper functions such as `kimi` are missing.

### Container

Wraps the command in `docker run`, mounts the working directory, runtime directory, and the AgentFlow app, then streams stdout and stderr back into the run trace.

### AWS Lambda

Invokes `agentflow.remote.lambda_handler.handler`. The payload contains the prepared command, environment, runtime files, and execution metadata so the Lambda package can execute the node remotely.

## Agent notes

### Codex

- Uses `codex exec --json`
- Maps tools mode to Codex sandboxing
- Writes `CODEX_HOME/config.toml` per node for provider and MCP selection

### Claude

- Uses `claude -p ... --output-format stream-json --verbose`
- Passes `--tools` according to the read-only vs read-write policy
- Writes a per-node MCP JSON config and passes it with `--mcp-config`

### Kimi

- Uses `python3 -m agentflow.remote.kimi_bridge`
- Emits a Kimi-style JSON-RPC event stream
- Calls Moonshot's OpenAI-compatible chat completions API
- Provides a small built-in tool layer for read, search, write, and shell actions

## Web console

The frontend shows:

- current DAG state and node statuses
- live run timeline and parsed JSONL trace events
- per-node attempts and retry history
- final outputs plus stdout, stderr, trace, and result artifacts
- controls to validate, launch, cancel, and rerun pipelines

Artifact files are persisted under `AGENTFLOW_RUNS_DIR/<run_id>/artifacts/<node_id>/`.

## API surface

The FastAPI app exposes:

- `POST /api/runs/validate`
- `POST /api/runs`
- `GET /api/runs`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/events`
- `GET /api/runs/{run_id}/stream`
- `GET /api/runs/{run_id}/artifacts/{node_id}/{name}`
- `POST /api/runs/{run_id}/cancel`
- `POST /api/runs/{run_id}/rerun`
- `GET /api/health`

## Testing

Run the Python suite:

```bash
. .venv/bin/activate
pytest -q
```

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

This keeps the check small while exercising both local `codex` and local `claude` end-to-end. Before the bundled smoke pipeline starts, AgentFlow runs a local preflight that verifies `codex`, confirms that `bash -lic` can find the `kimi` shell helper and still launch `claude` afterwards, checks that `kimi` exports `ANTHROPIC_API_KEY` for Claude-on-Kimi, and reports which bash login startup file is active, including transitive bridges such as `~/.bash_profile` -> `~/.profile` -> `~/.bashrc`.

You can run the same preflight directly:

```bash
. .venv/bin/activate
agentflow doctor
```

The bundled smoke pipeline bootstraps the `kimi` shell helper inside the Claude node, so you do not need to wrap the entire `agentflow smoke` command in `bash -lic`. If you want to run a custom smoke pipeline instead, pass its path explicitly with `agentflow smoke path/to/pipeline.yaml`.

## Reference sources

- `https://developers.openai.com/codex/security`
- `https://docs.anthropic.com/en/docs/claude-code/sdk`
- `https://github.com/openai/codex`
- `https://github.com/RichardAtCT/claude-code-telegram`
- `https://github.com/MoonshotAI/kimi-cli`
