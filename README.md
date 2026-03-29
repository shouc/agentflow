# AgentFlow

AgentFlow is a general agent orchestration package for dependency-aware DAGs. It runs `codex`, `claude`, and `kimi` nodes locally, in containers, or on AWS Lambda.

## Quickstart

Requirements:

- Python 3.11+
- The agent CLIs your pipeline uses

Install:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
```

Scaffold and run a pipeline:

```bash
agentflow templates
agentflow init > pipeline.py
agentflow run pipeline.py
```

Useful next commands:

```bash
agentflow init repo-sweep-batched.py --template codex-repo-sweep-batched
agentflow inspect pipeline.py
agentflow serve --host 127.0.0.1 --port 8000
agentflow smoke
```

## Bundled Templates

- `pipeline`: generic Codex/Claude/Kimi starter DAG
- `codex-repo-sweep-batched`: large repo sweep with staged batch reducers
- `local-kimi-smoke`: shortest real-agent local smoke DAG
- `local-kimi-shell-init-smoke`: explicit `shell_init: kimi` smoke DAG
- `local-kimi-shell-wrapper-smoke`: explicit `target.shell` wrapper smoke DAG

## Fanout

AgentFlow keeps the framework generic. The core fanout surface is:

- `count`
- `values`
- `matrix`
- `group_by`
- `batches`
- optional `derive`, plus matrix-only `include` and `exclude`

Pipelines can also include a periodic local node with `schedule.every_seconds` and `schedule.until_fanout_settles_from`. That lets one collector run inside the same pipeline, inspect shard artifact logs on disk, and optionally issue cancel/rerun actions against a watched fanout group.

Use these primitives via the Python DSL helpers.

## Examples

- `examples/airflow_like.py` -- basic DAG with static dependencies
- `examples/airflow_like_fuzz_batched.py` -- 128-shard batched fuzz with periodic monitor
- `examples/airflow_like_fuzz_grouped.py` -- 128-shard matrix fuzz with grouped reducers
