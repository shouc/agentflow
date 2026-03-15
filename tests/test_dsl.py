from pathlib import Path
import subprocess
import sys

from agentflow import DAG, claude, codex, fanout_batches, fanout_count, fanout_group_by, fanout_matrix, kimi
from agentflow.loader import load_pipeline_from_text


def test_airflow_like_dag_builds_dependencies():
    with DAG("demo", working_dir="/tmp/work", concurrency=2) as dag:
        plan = codex(task_id="plan", prompt="plan")
        implement = claude(task_id="implement", prompt="implement")
        review = kimi(task_id="review", prompt="review")
        merge = codex(task_id="merge", prompt="merge")
        plan >> [implement, review]
        [implement, review] >> merge

    spec = dag.to_spec()
    nodes = spec.node_map
    assert spec.name == "demo"
    assert spec.working_dir == "/tmp/work"
    assert nodes["implement"].depends_on == ["plan"]
    assert nodes["review"].depends_on == ["plan"]
    assert set(nodes["merge"].depends_on) == {"implement", "review"}


def test_airflow_like_dag_applies_local_target_defaults():
    with DAG(
        "local-defaults",
        local_target_defaults={
            "shell": "bash",
            "shell_login": True,
            "shell_interactive": True,
            "shell_init": ["command -v kimi >/dev/null 2>&1", "kimi"],
        },
    ) as dag:
        codex(task_id="plan", prompt="plan")
        claude(task_id="review", prompt="review", target={"cwd": "review-work"})

    spec = dag.to_spec()

    assert spec.local_target_defaults is not None
    assert spec.nodes[0].target.shell == "bash"
    assert spec.nodes[0].target.shell_init == ["command -v kimi >/dev/null 2>&1", "kimi"]
    assert spec.nodes[1].target.shell == "bash"
    assert spec.nodes[1].target.cwd == "review-work"


def test_airflow_like_dag_supports_pipeline_defaults_and_fanout():
    with DAG(
        "fanout-defaults",
        working_dir="/tmp/fanout-work",
        concurrency=16,
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
                "extra_args": ["--search"],
            }
        },
    ) as dag:
        prepare = codex(task_id="prepare", prompt="prepare")
        fuzzer = codex(
            task_id="fuzzer",
            prompt="fuzz shard {{ shard.number }}",
            fanout=fanout_count(4, as_="shard"),
        )
        merge = codex(task_id="merge", prompt="merge")
        prepare >> fuzzer
        fuzzer >> merge

    payload = dag.to_payload()
    spec = dag.to_spec()
    nodes = spec.node_map

    assert payload["fail_fast"] is True
    assert payload["node_defaults"] == {"tools": "read_only", "capture": "final"}
    assert payload["agent_defaults"]["codex"]["model"] == "gpt-5-codex"
    assert payload["nodes"][1]["fanout"] == {"count": 4, "as": "shard"}
    assert spec.working_dir == "/tmp/fanout-work"
    assert spec.concurrency == 16
    assert spec.fail_fast is True
    assert spec.node_defaults == {"tools": "read_only", "capture": "final"}
    assert spec.agent_defaults["codex"] == {
        "model": "gpt-5-codex",
        "retries": 1,
        "retry_backoff_seconds": 2,
        "extra_args": ["--search"],
    }
    assert spec.fanouts == {"fuzzer": ["fuzzer_0", "fuzzer_1", "fuzzer_2", "fuzzer_3"]}
    assert nodes["prepare"].model == "gpt-5-codex"
    assert nodes["prepare"].tools == "read_only"
    assert nodes["prepare"].capture == "final"
    assert nodes["prepare"].extra_args == ["--search"]
    assert nodes["fuzzer_0"].model == "gpt-5-codex"
    assert nodes["fuzzer_0"].depends_on == ["prepare"]
    assert nodes["fuzzer_3"].fanout_group == "fuzzer"
    assert nodes["fuzzer_3"].fanout_member["number"] == 4
    assert nodes["merge"].depends_on == ["fuzzer_0", "fuzzer_1", "fuzzer_2", "fuzzer_3"]
    assert nodes["merge"].retries == 1


def test_airflow_like_dag_supports_matrix_and_batch_fanout_helpers():
    with DAG(
        "batched-fuzz",
        working_dir="/tmp/batched-fuzz",
        concurrency=8,
        node_defaults={
            "agent": "codex",
            "tools": "read_only",
        },
        agent_defaults={
            "codex": {
                "model": "gpt-5-codex",
                "extra_args": ["--search"],
            }
        },
    ) as dag:
        init = codex(task_id="init", prompt="init", tools="read_write")
        fuzzer = codex(
            task_id="fuzzer",
            prompt="fuzz {{ shard.target }} {{ shard.sanitizer }} inside {{ shard.workspace }}",
            fanout=fanout_matrix(
                {
                    "family": [
                        {"target": "libpng"},
                        {"target": "sqlite"},
                    ],
                    "variant": [
                        {"sanitizer": "asan"},
                        {"sanitizer": "ubsan"},
                    ],
                },
                as_="shard",
                derive={"workspace": "agents/{{ shard.target }}_{{ shard.sanitizer }}_{{ shard.suffix }}"},
            ),
            target={"cwd": "{{ shard.workspace }}"},
        )
        batch_merge = codex(
            task_id="batch_merge",
            prompt="reduce batch {{ current.number }} covering {{ current.member_ids | join(', ') }}",
            fanout=fanout_batches("fuzzer", 2, as_="batch"),
        )
        merge = codex(task_id="merge", prompt="merge")
        init >> fuzzer
        fuzzer >> batch_merge
        batch_merge >> merge

    spec = dag.to_spec()
    nodes = spec.node_map

    assert spec.fanouts == {
        "fuzzer": ["fuzzer_0", "fuzzer_1", "fuzzer_2", "fuzzer_3"],
        "batch_merge": ["batch_merge_0", "batch_merge_1"],
    }
    assert nodes["init"].tools == "read_write"
    assert nodes["init"].model == "gpt-5-codex"
    assert nodes["fuzzer_0"].prompt == "fuzz libpng asan inside agents/libpng_asan_0"
    assert nodes["fuzzer_0"].target.cwd == "agents/libpng_asan_0"
    assert nodes["fuzzer_3"].prompt == "fuzz sqlite ubsan inside agents/sqlite_ubsan_3"
    assert nodes["fuzzer_3"].extra_args == ["--search"]
    assert nodes["batch_merge_0"].depends_on == ["fuzzer_0", "fuzzer_1"]
    assert nodes["batch_merge_0"].fanout_member["member_ids"] == ["fuzzer_0", "fuzzer_1"]
    assert nodes["batch_merge_1"].depends_on == ["fuzzer_2", "fuzzer_3"]
    assert nodes["merge"].depends_on == ["batch_merge_0", "batch_merge_1"]


def test_airflow_like_dag_supports_grouped_fanout_helpers():
    with DAG(
        "grouped-fuzz",
        working_dir="/tmp/grouped-fuzz",
        concurrency=8,
        node_defaults={
            "agent": "codex",
            "tools": "read_only",
        },
        agent_defaults={
            "codex": {
                "model": "gpt-5-codex",
                "extra_args": ["--search"],
            }
        },
    ) as dag:
        init = codex(task_id="init", prompt="init", tools="read_write")
        fuzzer = codex(
            task_id="fuzzer",
            prompt="fuzz {{ shard.target }} {{ shard.sanitizer }} inside {{ shard.workspace }}",
            fanout=fanout_matrix(
                {
                    "family": [
                        {"target": "libpng", "corpus": "png"},
                        {"target": "sqlite", "corpus": "sql"},
                    ],
                    "variant": [
                        {"sanitizer": "asan"},
                        {"sanitizer": "ubsan"},
                    ],
                },
                as_="shard",
                derive={"workspace": "agents/{{ shard.target }}_{{ shard.sanitizer }}_{{ shard.suffix }}"},
            ),
            target={"cwd": "{{ shard.workspace }}"},
        )
        family_merge = codex(
            task_id="family_merge",
            prompt="group {{ current.target }} has {{ current.scope.size }} shards",
            fanout=fanout_group_by("fuzzer", ["target", "corpus"], as_="family"),
        )
        merge = codex(task_id="merge", prompt="merge")
        init >> fuzzer
        fuzzer >> family_merge
        family_merge >> merge

    spec = dag.to_spec()
    nodes = spec.node_map

    assert spec.fanouts == {
        "fuzzer": ["fuzzer_0", "fuzzer_1", "fuzzer_2", "fuzzer_3"],
        "family_merge": ["family_merge_0", "family_merge_1"],
    }
    assert nodes["family_merge_0"].depends_on == ["fuzzer_0", "fuzzer_1"]
    assert nodes["family_merge_0"].fanout_member["member_ids"] == ["fuzzer_0", "fuzzer_1"]
    assert nodes["family_merge_0"].fanout_member["target"] == "libpng"
    assert nodes["family_merge_1"].depends_on == ["fuzzer_2", "fuzzer_3"]
    assert nodes["family_merge_1"].fanout_member["target"] == "sqlite"
    assert nodes["merge"].depends_on == ["family_merge_0", "family_merge_1"]


def test_airflow_like_fuzz_batched_example_emits_valid_pipeline():
    repo_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, str(repo_root / "examples" / "airflow_like_fuzz_batched.py")],
        check=True,
        capture_output=True,
        text=True,
        cwd=repo_root,
    )

    spec = load_pipeline_from_text(completed.stdout, base_dir=repo_root)

    assert spec.name == "airflow-like-fuzz-batched-128"
    assert spec.fail_fast is True
    assert spec.concurrency == 32
    assert len(spec.fanouts["fuzzer"]) == 128
    assert len(spec.fanouts["batch_merge"]) == 8
    assert spec.node_map["fuzzer_000"].target.cwd.endswith("/codex_fuzz_python_128/agents/agent_000")
    assert spec.node_map["batch_merge_0"].depends_on == spec.fanouts["fuzzer"][:16]
    assert spec.node_map["merge"].depends_on == spec.fanouts["batch_merge"]


def test_airflow_like_fuzz_grouped_example_emits_valid_pipeline():
    repo_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, str(repo_root / "examples" / "airflow_like_fuzz_grouped.py")],
        check=True,
        capture_output=True,
        text=True,
        cwd=repo_root,
    )

    spec = load_pipeline_from_text(completed.stdout, base_dir=repo_root)

    assert spec.name == "airflow-like-fuzz-grouped-128"
    assert spec.fail_fast is True
    assert spec.concurrency == 32
    assert len(spec.fanouts["fuzzer"]) == 128
    assert len(spec.fanouts["family_merge"]) == 4
    assert spec.node_map["fuzzer_000"].target.cwd.endswith("/codex_fuzz_python_grouped_128/agents/libpng_asan_seed_a_000")
    assert spec.node_map["family_merge_0"].depends_on == spec.fanouts["fuzzer"][:32]
    assert spec.node_map["family_merge_0"].fanout_member["member_ids"] == spec.fanouts["fuzzer"][:32]
    assert spec.node_map["merge"].depends_on == spec.fanouts["family_merge"]
