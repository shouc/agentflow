# AgentFlow

AgentFlow orchestrates `codex`, `claude`, and `kimi` as dependency-aware DAGs that can run locally, in containers, or on AWS Lambda.

## Quickstart

Requirements:

- Python 3.11+
- The agent CLIs your pipeline uses (`codex`, `claude`, and/or `kimi`)

Install:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
```

Scaffold and run a starter pipeline:

```bash
agentflow templates
agentflow init > pipeline.yaml
agentflow init repo-sweep.yaml --template codex-fanout-repo-sweep
agentflow validate pipeline.yaml
agentflow run pipeline.yaml
```

Useful next commands:

```bash
agentflow inspect pipeline.yaml
agentflow serve --host 127.0.0.1 --port 8000
agentflow smoke
```

## Example

`examples/pipeline.yaml`

```yaml
name: parallel-code-orchestration
description: Codex plans, Claude implements, and Kimi reviews in parallel before a final Codex merge.
working_dir: .
concurrency: 3
nodes:
  - id: plan
    agent: codex
    model: gpt-5-codex
    tools: read_only
    capture: final
    prompt: |
      Inspect the repository and create a short implementation plan.

  - id: implement
    agent: claude
    model: claude-sonnet-4-5
    tools: read_write
    capture: final
    depends_on: [plan]
    prompt: |
      Use the plan below and implement the requested change.

      Plan:
      {{ nodes.plan.output }}

  - id: review
    agent: kimi
    model: kimi-k2-turbo-preview
    tools: read_only
    capture: trace
    depends_on: [plan]
    prompt: |
      Review the proposed implementation plan.

      Plan:
      {{ nodes.plan.output }}

  - id: merge
    agent: codex
    model: gpt-5-codex
    tools: read_only
    depends_on: [implement, review]
    success_criteria:
      - kind: output_contains
        value: success
    prompt: |
      Combine these two perspectives into a final release summary and include the word success.

      Implementation output:
      {{ nodes.implement.output }}

      Review trace:
      {{ nodes.review.output }}
```

For larger swarms, use node-level `fanout` to keep the YAML compact while still running a concrete DAG:

```yaml
nodes:
  - id: fuzzer
    fanout:
      count: 128
      as: shard
    agent: codex
    prompt: |
      You are shard {{ shard.number }} of {{ shard.count }}.

  - id: merge
    agent: codex
    depends_on: [fuzzer]
    prompt: |
      {% for shard in fanouts.fuzzer.nodes %}
      ## {{ shard.id }}
      {{ shard.output or "(no output)" }}

      {% endfor %}
```

See `examples/codex-fanout-repo-sweep.yaml` for a bundled maintainer-friendly review template and `examples/fuzz/fuzz_codex_128.yaml` for a compact 128-shard Codex fuzzing swarm.

## Docs

- [Docs index](docs/README.md)
- [CLI and operations](docs/cli.md)
- [Pipeline reference](docs/pipelines.md)
- [Testing and maintainer workflows](docs/testing.md)
- [Background and sources](docs/background.md)
