from pathlib import Path
import subprocess
import sys

import pytest

from agentflow import (
    DAG,
    claude,
    codex,
    codex_fuzz_campaign,
    codex_fuzz_campaign_matrix,
    codex_fuzz_campaign_preset_names,
    fanout_batches,
    fanout_count,
    fanout_group_by,
    fanout_matrix,
    fanout_values_path,
    kimi,
)
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


def test_codex_fuzz_campaign_helpers_build_preset_backed_matrix_payload():
    payload = codex_fuzz_campaign_matrix(
        preset="browser-surface",
        bucket_count=2,
        as_="shard",
        label_template="{{ shard.target }} :: {{ shard.bucket }}",
        derive={"campaign": "browser"},
        extra_axes={"lane": [{"lane": "dom"}]},
    )

    assert codex_fuzz_campaign_preset_names() == ("oss-fuzz-core", "browser-surface", "protocol-stack")
    assert payload["as"] == "shard"
    assert payload["matrix"]["family"][0] == {"target": "blink", "corpus": "html"}
    assert payload["matrix"]["strategy"][0] == {"sanitizer": "asan", "focus": "parser"}
    assert payload["matrix"]["seed_bucket"] == [
        {"bucket": "seed_001", "seed": 4101},
        {"bucket": "seed_002", "seed": 4102},
    ]
    assert payload["matrix"]["lane"] == [{"lane": "dom"}]
    assert payload["derive"]["label"] == "{{ shard.target }} :: {{ shard.bucket }}"
    assert payload["derive"]["workspace"] == "agents/{{ shard.target }}_{{ shard.sanitizer }}_{{ shard.bucket }}_{{ shard.suffix }}"
    assert payload["derive"]["campaign"] == "browser"


def test_codex_fuzz_campaign_helper_rejects_unknown_preset():
    with pytest.raises(ValueError, match=r"`preset` must be one of"):
        codex_fuzz_campaign_matrix(preset="missing-preset")


def test_airflow_like_dag_supports_codex_fuzz_campaign_matrix_helper():
    with DAG(
        "preset-fuzz",
        working_dir="/tmp/preset-fuzz",
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
            prompt="fuzz {{ shard.label }} in {{ shard.workspace }}",
            fanout=codex_fuzz_campaign_matrix(
                preset="browser-surface",
                bucket_count=2,
                as_="shard",
            ),
            target={"cwd": "{{ shard.workspace }}"},
        )
        batch_merge = codex(
            task_id="batch_merge",
            prompt="reduce {{ current.member_ids | join(', ') }}",
            fanout=fanout_batches("fuzzer", 4, as_="batch"),
        )
        merge = codex(task_id="merge", prompt="merge")
        init >> fuzzer
        fuzzer >> batch_merge
        batch_merge >> merge

    spec = dag.to_spec()
    nodes = spec.node_map

    assert len(spec.fanouts["fuzzer"]) == 32
    assert spec.fanouts["fuzzer"][:3] == ["fuzzer_00", "fuzzer_01", "fuzzer_02"]
    assert spec.fanouts["fuzzer"][-1] == "fuzzer_31"
    assert len(spec.fanouts["batch_merge"]) == 8
    assert nodes["fuzzer_00"].fanout_member["target"] == "blink"
    assert nodes["fuzzer_00"].fanout_member["label"] == "blink / asan / parser / seed_001"
    assert nodes["fuzzer_00"].target.cwd == "agents/blink_asan_seed_001_00"
    assert nodes["fuzzer_15"].fanout_member["target"] == "v8"
    assert nodes["fuzzer_15"].fanout_member["bucket"] == "seed_002"
    assert nodes["batch_merge_0"].depends_on == spec.fanouts["fuzzer"][:4]
    assert nodes["merge"].depends_on == spec.fanouts["batch_merge"]


def test_codex_fuzz_campaign_registers_batched_pipeline_with_defaults():
    with DAG("campaign-helper", working_dir="/tmp/campaign-helper", concurrency=16, fail_fast=True) as dag:
        campaign = codex_fuzz_campaign(
            preset="browser-surface",
            bucket_count=2,
            layout="batched",
            batch_size=4,
        )

    spec = dag.to_spec()
    nodes = spec.node_map

    assert campaign.reducer is not None
    assert campaign.init.id == "init"
    assert campaign.fuzzer.id == "fuzzer"
    assert campaign.reducer.id == "batch_merge"
    assert campaign.merge.id == "merge"
    assert spec.fail_fast is True
    assert len(spec.fanouts["fuzzer"]) == 32
    assert len(spec.fanouts["batch_merge"]) == 8
    assert nodes["init"].tools == "read_write"
    assert nodes["init"].success_criteria[0].value == "INIT_OK"
    assert nodes["fuzzer_00"].fanout_member["target"] == "blink"
    assert nodes["fuzzer_00"].fanout_member["label"] == "blink / asan / parser / seed_001"
    assert nodes["fuzzer_00"].target.cwd == "agents/blink_asan_seed_001_00"
    assert nodes["fuzzer_00"].extra_args == ["--search", "-c", 'model_reasoning_effort="high"']
    assert nodes["batch_merge_0"].depends_on == spec.fanouts["fuzzer"][:4]
    assert nodes["merge"].depends_on == spec.fanouts["batch_merge"]


def test_codex_fuzz_campaign_supports_grouped_layout_and_prefix_overrides():
    with DAG("campaign-helper-grouped", working_dir="/tmp/campaign-helper-grouped", concurrency=8) as dag:
        campaign = codex_fuzz_campaign(
            preset="protocol-stack",
            bucket_count=1,
            layout="grouped",
            task_prefix="protocol",
            campaign_label="protocol-stack",
            fuzzer_kwargs={"timeout_seconds": 7200, "env": {"FUZZ_MODE": "strict"}},
            merge_kwargs={"description": "grouped merge"},
        )

    spec = dag.to_spec()
    nodes = spec.node_map

    assert campaign.reducer is not None
    assert campaign.init.id == "protocol_init"
    assert campaign.fuzzer.id == "protocol_fuzzer"
    assert campaign.reducer.id == "protocol_family_merge"
    assert campaign.merge.id == "protocol_merge"
    assert len(spec.fanouts["protocol_fuzzer"]) == 16
    assert len(spec.fanouts["protocol_family_merge"]) == 4
    assert nodes["protocol_fuzzer_00"].fanout_member["target"] == "c-ares"
    assert nodes["protocol_fuzzer_00"].target.cwd == "agents/c-ares_asan_seed_001_00"
    assert nodes["protocol_fuzzer_00"].timeout_seconds == 7200
    assert nodes["protocol_fuzzer_00"].env == {"FUZZ_MODE": "strict"}
    assert nodes["protocol_family_merge_0"].depends_on == spec.fanouts["protocol_fuzzer"][:4]
    assert nodes["protocol_merge"].depends_on == spec.fanouts["protocol_family_merge"]
    assert nodes["protocol_merge"].description == "grouped merge"


def test_codex_fuzz_campaign_uses_custom_shared_paths_in_init_and_fuzzer_prompts():
    with DAG("campaign-helper-paths", working_dir="/tmp/campaign-helper-paths") as dag:
        campaign = codex_fuzz_campaign(
            preset="browser-surface",
            bucket_count=1,
            layout="flat",
            crash_registry_path="reports/crashes.md",
            notes_path="notes/campaign.md",
        )

    spec = dag.to_spec()
    nodes = spec.node_map

    assert "mkdir -p crashes reports notes" in nodes["init"].prompt
    assert "If reports/crashes.md is missing or empty" in nodes["init"].prompt
    assert "If notes/campaign.md is missing or empty" in nodes["init"].prompt
    assert "`reports/crashes.md`" in nodes["fuzzer_00"].prompt
    assert "`notes/campaign.md`" in nodes["fuzzer_00"].prompt
    assert campaign.reducer is None
    assert nodes["merge"].depends_on == spec.fanouts["fuzzer"]


def test_codex_fuzz_campaign_rejects_invalid_layout_and_reducer_overrides():
    with pytest.raises(ValueError, match=r"`layout` must be one of"):
        with DAG("invalid-layout") as dag:
            codex_fuzz_campaign(layout="missing")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match=r"`reducer_prompt` and `reducer_kwargs` are only valid"):
        with DAG("invalid-flat") as dag:
            codex_fuzz_campaign(layout="flat", reducer_kwargs={"timeout_seconds": 42})


def test_airflow_like_dag_can_render_json_and_yaml():
    with DAG(
        "render-demo",
        description="render helpers",
        working_dir="/tmp/render-demo",
        node_defaults={"tools": "read_only"},
    ) as dag:
        codex(task_id="plan", prompt="line one\nline two")

    rendered_json = dag.to_json()
    rendered_yaml = dag.to_yaml()
    spec_from_json = load_pipeline_from_text(rendered_json)
    spec_from_yaml = load_pipeline_from_text(rendered_yaml)

    assert '"description": "render helpers"' in rendered_json
    assert '"working_dir": "/tmp/render-demo"' in rendered_json
    assert "description: render helpers\n" in rendered_yaml
    assert "working_dir: /tmp/render-demo\n" in rendered_yaml
    assert "node_defaults:\n  tools: read_only\n" in rendered_yaml
    assert "prompt: |-" in rendered_yaml
    assert "line one" in rendered_yaml
    assert "line two" in rendered_yaml
    assert spec_from_json.name == "render-demo"
    assert spec_from_json.node_map["plan"].prompt == "line one\nline two"
    assert spec_from_yaml.name == "render-demo"
    assert spec_from_yaml.node_map["plan"].prompt == "line one\nline two"


def test_airflow_like_dag_supports_values_path_and_batch_fanout_helpers(tmp_path):
    workspace = tmp_path / "workspace"
    catalog_path = workspace / "catalog.csv"
    catalog_path.parent.mkdir(parents=True)
    catalog_path.write_text(
        (
            "label,target,corpus,sanitizer,focus,bucket,seed,workspace\n"
            "libpng/asan/parser/seed_001,libpng,png,asan,parser,seed_001,4101,agents/libpng_asan_seed_001_0\n"
            "sqlite/ubsan/stateful/seed_001,sqlite,sql,ubsan,stateful,seed_001,4101,agents/sqlite_ubsan_seed_001_1\n"
        ),
        encoding="utf-8",
    )

    with DAG(
        "catalog-batched",
        working_dir=str(workspace),
        concurrency=4,
        node_defaults={
            "agent": "codex",
            "tools": "read_only",
        },
        agent_defaults={
            "codex": {
                "model": "gpt-5-codex",
            }
        },
    ) as dag:
        init = codex(task_id="init", prompt="init", tools="read_write")
        fuzzer = codex(
            task_id="fuzzer",
            prompt="fuzz {{ shard.label }} inside {{ shard.workspace }}",
            fanout=fanout_values_path(catalog_path, as_="shard"),
            tools="read_write",
            target={"cwd": "{{ shard.workspace }}"},
        )
        batch_merge = codex(
            task_id="batch_merge",
            prompt="reduce {{ current.scope.ids | join(', ') }}",
            fanout=fanout_batches("fuzzer", 1, as_="batch"),
        )
        merge = codex(task_id="merge", prompt="merge")
        init >> fuzzer
        fuzzer >> batch_merge
        batch_merge >> merge

    spec = dag.to_spec()
    nodes = spec.node_map

    assert spec.fanouts == {
        "fuzzer": ["fuzzer_0", "fuzzer_1"],
        "batch_merge": ["batch_merge_0", "batch_merge_1"],
    }
    assert nodes["fuzzer_0"].prompt == "fuzz libpng/asan/parser/seed_001 inside agents/libpng_asan_seed_001_0"
    assert nodes["fuzzer_0"].target.cwd == "agents/libpng_asan_seed_001_0"
    assert nodes["fuzzer_1"].fanout_member["target"] == "sqlite"
    assert nodes["batch_merge_0"].depends_on == ["fuzzer_0"]
    assert nodes["batch_merge_0"].fanout_member["member_ids"] == ["fuzzer_0"]
    assert nodes["merge"].depends_on == ["batch_merge_0", "batch_merge_1"]


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


def test_airflow_like_fuzz_catalog_batched_example_emits_valid_pipeline():
    repo_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, str(repo_root / "examples" / "airflow_like_fuzz_catalog_batched.py")],
        check=True,
        capture_output=True,
        text=True,
        cwd=repo_root,
    )

    spec = load_pipeline_from_text(completed.stdout, base_dir=repo_root)

    assert spec.name == "airflow-like-fuzz-catalog-batched-128"
    assert spec.fail_fast is True
    assert spec.concurrency == 32
    assert len(spec.fanouts["fuzzer"]) == 128
    assert len(spec.fanouts["batch_merge"]) == 8
    assert spec.node_map["fuzzer_000"].target.cwd.endswith(
        "/codex_fuzz_python_catalog_batched_128/agents/libpng_asan_seed_001_000"
    )
    assert spec.node_map["batch_merge_0"].depends_on == spec.fanouts["fuzzer"][:16]
    assert spec.node_map["merge"].depends_on == spec.fanouts["batch_merge"]


def test_airflow_like_fuzz_preset_batched_example_emits_valid_pipeline():
    repo_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, str(repo_root / "examples" / "airflow_like_fuzz_preset_batched.py")],
        check=True,
        capture_output=True,
        text=True,
        cwd=repo_root,
    )

    spec = load_pipeline_from_text(completed.stdout, base_dir=repo_root)

    assert spec.name == "airflow-like-fuzz-preset-batched-128"
    assert spec.fail_fast is True
    assert spec.concurrency == 32
    assert len(spec.fanouts["fuzzer"]) == 128
    assert len(spec.fanouts["batch_merge"]) == 8
    assert spec.node_map["fuzzer_000"].fanout_member["target"] == "blink"
    assert spec.node_map["fuzzer_000"].fanout_member["label"] == "blink / asan / parser / seed_001"
    assert spec.node_map["fuzzer_000"].target.cwd.endswith(
        "/codex_fuzz_python_preset_batched_128/agents/blink_asan_seed_001_000"
    )
    assert spec.node_map["batch_merge_0"].depends_on == spec.fanouts["fuzzer"][:16]
    assert spec.node_map["merge"].depends_on == spec.fanouts["batch_merge"]


def test_airflow_like_fuzz_campaign_helper_example_emits_valid_pipeline():
    repo_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, str(repo_root / "examples" / "airflow_like_fuzz_campaign.py")],
        check=True,
        capture_output=True,
        text=True,
        cwd=repo_root,
    )

    spec = load_pipeline_from_text(completed.stdout, base_dir=repo_root)

    assert spec.name == "airflow-like-fuzz-campaign-helper-128"
    assert spec.fail_fast is True
    assert spec.concurrency == 32
    assert len(spec.fanouts["fuzzer"]) == 128
    assert len(spec.fanouts["family_merge"]) == 4
    assert spec.node_map["fuzzer_000"].fanout_member["target"] == "c-ares"
    assert spec.node_map["fuzzer_000"].target.cwd.endswith(
        "/codex_fuzz_python_campaign_helper_128/agents/c-ares_asan_seed_001_000"
    )
    assert spec.node_map["family_merge_0"].depends_on == spec.fanouts["fuzzer"][:32]
    assert spec.node_map["merge"].depends_on == spec.fanouts["family_merge"]
