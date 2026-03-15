import json

from agentflow import DAG, codex, fanout_group_by, fanout_matrix


with DAG(
    "airflow-like-fuzz-grouped-128",
    description="Python-authored 128-shard Codex fuzz matrix with grouped reducers and scoped reducer context.",
    working_dir="./codex_fuzz_python_grouped_128",
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
            "  mkdir -p docs crashes\n"
            "If crashes/README.md is missing or empty, create it with:\n"
            "  # Crash Registry\n"
            "  | Timestamp | Target | Sanitizer | Bucket | Shard | Evidence |\n"
            "  |---|---|---|---|---|---|\n"
            "If docs/campaign_notes.md is missing or empty, create it with:\n"
            "  # Campaign Notes\n"
            "  Use this file only for cross-shard lessons and retargeting guidance.\n"
            "Then respond with exactly: INIT_OK"
        ),
    )

    fuzzer = codex(
        task_id="fuzzer",
        fanout=fanout_matrix(
            {
                "family": [
                    {"target": "libpng", "corpus": "png"},
                    {"target": "libjpeg", "corpus": "jpeg"},
                    {"target": "freetype", "corpus": "fonts"},
                    {"target": "sqlite", "corpus": "sql"},
                ],
                "strategy": [
                    {"sanitizer": "asan", "focus": "parser"},
                    {"sanitizer": "asan", "focus": "structure-aware"},
                    {"sanitizer": "ubsan", "focus": "differential"},
                    {"sanitizer": "ubsan", "focus": "stateful"},
                ],
                "seed_bucket": [
                    {"bucket": "seed_a", "seed": 4101},
                    {"bucket": "seed_b", "seed": 4102},
                    {"bucket": "seed_c", "seed": 4103},
                    {"bucket": "seed_d", "seed": 4104},
                    {"bucket": "seed_e", "seed": 4105},
                    {"bucket": "seed_f", "seed": 4106},
                    {"bucket": "seed_g", "seed": 4107},
                    {"bucket": "seed_h", "seed": 4108},
                ],
            },
            as_="shard",
            derive={
                "label": "{{ shard.target }} / {{ shard.sanitizer }} / {{ shard.focus }} / {{ shard.bucket }}",
                "workspace": "agents/{{ shard.target }}_{{ shard.sanitizer }}_{{ shard.bucket }}_{{ shard.suffix }}",
            },
        ),
        tools="read_write",
        target={"cwd": "{{ shard.workspace }}"},
        timeout_seconds=3600,
        retries=2,
        prompt=(
            "You are Codex fuzz shard {{ shard.number }} of {{ shard.count }} in an authorized campaign.\n\n"
            "Campaign inputs:\n"
            "- Target: {{ shard.target }}\n"
            "- Corpus family: {{ shard.corpus }}\n"
            "- Sanitizer: {{ shard.sanitizer }}\n"
            "- Strategy focus: {{ shard.focus }}\n"
            "- Seed bucket: {{ shard.bucket }}\n"
            "- Seed: {{ shard.seed }}\n"
            "- Label: {{ shard.label }}\n"
            "- Workspace: {{ shard.workspace }}\n\n"
            "Shard contract:\n"
            "- Stay within {{ shard.workspace }} unless you are appending to the shared crash registry or notes.\n"
            "- Use the label, target family, sanitizer, focus, and seed bucket to keep the campaign reproducible.\n"
            "- Prefer high-signal crashers, assertion failures, memory safety bugs, or logic corruptions.\n"
            "- Record confirmed findings in `crashes/README.md` and copy minimal repro artifacts into `crashes/`.\n"
            "- Add short cross-shard lessons to `docs/campaign_notes.md` when they help other shards avoid duplicate work."
        ),
    )

    family_merge = codex(
        task_id="family_merge",
        fanout=fanout_group_by("fuzzer", ["target", "corpus"], as_="family"),
        timeout_seconds=300,
        prompt=(
            "Prepare the maintainer handoff for target family {{ current.target }} (corpus {{ current.corpus }}).\n\n"
            "Campaign snapshot:\n"
            "- Total shards: {{ fanouts.fuzzer.size }}\n"
            "- Completed shards: {{ fanouts.fuzzer.summary.completed }}\n"
            "- Failed shards: {{ fanouts.fuzzer.summary.failed }}\n"
            "- Silent shards: {{ fanouts.fuzzer.summary.without_output }}\n"
            "- Scoped reducer shards: {{ current.scope.size }}\n"
            "- Scoped completed shards: {{ current.scope.summary.completed }}\n"
            "- Scoped failed shards: {{ current.scope.summary.failed }}\n"
            "- Scoped shard ids: {{ current.scope.ids | join(', ') }}\n\n"
            "Focus only on {{ current.target }}. Summarize strong or confirmed findings first, then recurring lessons, "
            "then quiet or failed shards that need retargeting.\n\n"
            "{% for shard in current.scope.with_output.nodes %}\n"
            "### {{ shard.label }} :: {{ shard.id }} (status: {{ shard.status }})\n"
            "{{ shard.output }}\n\n"
            "{% endfor %}"
            "{% if current.scope.failed.size %}\n"
            "Failed scoped shards:\n"
            "{% for shard in current.scope.failed.nodes %}\n"
            "- {{ shard.id }} :: {{ shard.label }}\n"
            "{% endfor %}"
            "{% endif %}"
            "{% if not current.scope.with_output.size %}\n"
            "No scoped shard produced reducer-ready output. Say that explicitly and use the failed shard list to suggest retargeting.\n"
            "{% endif %}"
        ),
    )

    merge = codex(
        task_id="merge",
        timeout_seconds=300,
        prompt=(
            "Consolidate this hierarchical 128-shard fuzz campaign into a maintainer handoff.\n"
            "Start with campaign-wide status, then group the strongest findings by target family, and end with failed or quiet shards that need retargeting.\n\n"
            "Campaign status:\n"
            "- Total shards: {{ fanouts.fuzzer.size }}\n"
            "- Completed shards: {{ fanouts.fuzzer.summary.completed }}\n"
            "- Failed shards: {{ fanouts.fuzzer.summary.failed }}\n"
            "- Silent shards: {{ fanouts.fuzzer.summary.without_output }}\n"
            "- Family reducers completed: {{ fanouts.family_merge.summary.completed }} / {{ fanouts.family_merge.size }}\n\n"
            "{% for review in fanouts.family_merge.with_output.nodes %}\n"
            "## {{ review.target }} :: {{ review.id }} (status: {{ review.status }})\n"
            "{{ review.output }}\n\n"
            "{% endfor %}"
            "{% if fanouts.fuzzer.failed.size %}\n"
            "Failed shard ids:\n"
            "{% for shard in fanouts.fuzzer.failed.nodes %}\n"
            "- {{ shard.id }} :: {{ shard.label }}\n"
            "{% endfor %}"
            "{% endif %}"
        ),
    )

    init >> fuzzer
    fuzzer >> family_merge
    family_merge >> merge

print(json.dumps(dag.to_payload(), indent=2))
