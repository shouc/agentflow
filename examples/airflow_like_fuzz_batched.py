from agentflow import DAG, codex, fanout, merge


with DAG(
    "airflow-like-fuzz-batched-128",
    description="Python-authored 128-shard Codex fuzz swarm with batched reducers.",
    working_dir="./codex_fuzz_python_128",
    concurrency=32,
    fail_fast=True,
    node_defaults={
        "tools": "read_only",
        "capture": "final",
    },
    agent_defaults={
        "codex": {
            "model": "gpt-5-codex",
            "retries": 1,
            "retry_backoff_seconds": 2,
            "extra_args": [
                "--search",
                "-c",
                'model_reasoning_effort="high"',
            ],
        }
    },
) as dag:
    init = codex(
        task_id="init",
        tools="read_write",
        timeout_seconds=60,
        success_criteria=[
            {
                "kind": "output_contains",
                "value": "INIT_OK",
            }
        ],
        prompt=(
            "Create the following directory structure silently if it does not already exist:\n"
            "  mkdir -p docs crashes locks\n"
            "If crashes/README.md is missing or empty, create it with:\n"
            "  # Crash Registry\n"
            "  | Timestamp | Shard | Evidence | Artifact |\n"
            "  |---|---|---|---|\n"
            "If docs/global_lessons.md is missing or empty, create it with:\n"
            "  # Shared Lessons\n"
            "  Use this file only for reusable campaign-wide notes.\n"
            "Then respond with exactly: INIT_OK"
        ),
    )

    fuzzer = fanout(
        codex(
            task_id="fuzzer",
            tools="read_write",
            target={"cwd": "{{ item.workspace }}"},
            timeout_seconds=3600,
            retries=2,
            prompt=(
                "You are Codex fuzz shard {{ item.number }} of {{ item.count }} in an authorized campaign.\n\n"
                "Shared workspace:\n"
                "- Root: {{ pipeline.working_dir }}\n"
                "- Shard dir: {{ item.workspace }}\n"
                "- Crash registry: crashes/README.md\n"
                "- Shared notes: docs/global_lessons.md\n\n"
                "Shard contract:\n"
                "- Own only files under {{ item.workspace }} unless you are appending to the shared docs or crash registry with locking.\n"
                "- Keep your inputs and notes deterministic so another engineer can replay them.\n"
                "- Use shard id `{{ item.suffix }}` to vary corpus slices, seeds, flags, or target areas.\n"
                "- Focus on deep, high-signal failure modes rather than shallow lint or unit-test noise.\n"
                "- When you confirm a real issue, copy the minimal reproducer into `crashes/` and append a one-line entry to the registry.\n"
                "- When a target area looks exhausted, write concise lessons to `docs/`.\n"
                "- Continue searching until timeout."
            ),
        ),
        128,
        derive={"workspace": "agents/agent_{{ item.suffix }}"},
    )

    batch_merge = merge(
        codex(
            task_id="batch_merge",
            timeout_seconds=300,
            prompt=(
                "Prepare the maintainer handoff for shard batch {{ item.number }} of {{ item.count }}.\n\n"
                "Batch coverage:\n"
                "- Source group: {{ item.source_group }}\n"
                "- Total source shards: {{ item.source_count }}\n"
                "- Batch size: {{ item.size }}\n"
                "- Shard range: {{ item.start_number }} through {{ item.end_number }}\n"
                "- Shard ids: {{ item.member_ids | join(', ') }}\n\n"
                "Focus on confirmed crashers first, then recurring lessons, then quiet shards that need retargeting.\n\n"
                "{% for shard in item.scope.with_output.nodes %}\n"
                "### {{ shard.node_id }} (status: {{ shard.status }})\n"
                "Workspace: {{ shard.workspace }}\n"
                "{{ shard.output or '(no output)' }}\n\n"
                "{% endfor %}"
            ),
        ),
        fuzzer,
        size=16,
    )

    monitor = codex(
        task_id="monitor",
        tools="read_write",
        timeout_seconds=300,
        schedule={
            "every_seconds": 600,
            "until_fanout_settles_from": "fuzzer",
            "actuation": "output_json",
        },
        prompt=(
            "You are the periodic campaign monitor for this 128-shard run.\n\n"
            "Current tick: {{ item.tick_number }}\n"
            "Tick started at: {{ item.tick_started_at }}\n"
            "Total shards: {{ fanouts.fuzzer.size }}\n"
            "Completed shards: {{ fanouts.fuzzer.summary.completed }}\n"
            "Running shards: {{ fanouts.fuzzer.summary.running }}\n"
            "Failed shards: {{ fanouts.fuzzer.summary.failed }}\n"
            "Silent shards: {{ fanouts.fuzzer.summary.without_output }}\n\n"
            "Each shard exposes full artifact logs you can inspect with grep.\n"
            "{% for shard in fanouts.fuzzer.nodes %}\n"
            "- {{ shard.id }} stdout={{ shard.artifacts.stdout_log }} stderr={{ shard.artifacts.stderr_log }}\n"
            "{% endfor %}\n"
            "Analyze underperformance and respond with strict JSON:\n"
            "{\n"
            '  "analysis": "short maintainer summary",\n'
            '  "actions": [\n'
            '    {"kind": "cancel", "node_ids": ["fuzzer_000"]},\n'
            '    {"kind": "rerun", "node_ids": ["fuzzer_000"]}\n'
            "  ]\n"
            "}\n"
            "Use an empty `actions` list when no live intervention is needed."
        ),
    )

    final = codex(
        task_id="merge",
        timeout_seconds=300,
        prompt=(
            "Consolidate this 128-shard fuzzing campaign into a maintainer handoff.\n"
            "Start with campaign-wide status, then the strongest batch-level findings, and end with quiet or failed shards that need retargeting.\n\n"
            "Campaign status:\n"
            "- Total shards: {{ fanouts.fuzzer.size }}\n"
            "- Completed shards: {{ fanouts.fuzzer.summary.completed }}\n"
            "- Failed shards: {{ fanouts.fuzzer.summary.failed }}\n"
            "- Silent shards: {{ fanouts.fuzzer.summary.without_output }}\n"
            "- Batch reducers completed: {{ fanouts.batch_merge.summary.completed }} / {{ fanouts.batch_merge.size }}\n\n"
            "{% for batch in fanouts.batch_merge.with_output.nodes %}\n"
            "## Batch {{ batch.number }} :: {{ batch.start_number }}-{{ batch.end_number }} (status: {{ batch.status }})\n"
            "{{ batch.output }}\n\n"
            "{% endfor %}"
            "{% if fanouts.batch_merge.without_output.size %}\n"
            "Batch reducers needing attention:\n"
            "{% for batch in fanouts.batch_merge.without_output.nodes %}\n"
            "- {{ batch.id }} :: shards {{ batch.start_number }}-{{ batch.end_number }} (status: {{ batch.status }})\n"
            "{% endfor %}"
            "{% endif %}"
        ),
    )

    init >> [fuzzer, monitor]
    fuzzer >> batch_merge
    [batch_merge, monitor] >> final

print(dag.to_json())
