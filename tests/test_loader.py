from __future__ import annotations

from agentflow.loader import load_pipeline_from_data, load_pipeline_from_path, load_pipeline_from_text


def test_load_pipeline_from_path_expands_home_relative_working_dir(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()

    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(
        """name: home-working-dir
working_dir: ~/workspace
nodes:
  - id: plan
    agent: codex
    prompt: hi
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("HOME", str(home))

    pipeline = load_pipeline_from_path(pipeline_path)

    assert pipeline.working_dir == str((home / "workspace").resolve())


def test_load_pipeline_from_path_resolves_relative_cwd_from_expanded_home_working_dir(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()

    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(
        """name: home-working-dir-relative-cwd
working_dir: ~/workspace
nodes:
  - id: plan
    agent: codex
    prompt: hi
    target:
      kind: local
      cwd: task
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("HOME", str(home))

    pipeline = load_pipeline_from_path(pipeline_path)

    assert pipeline.nodes[0].target.cwd == str((home / "workspace" / "task").resolve())


def test_load_pipeline_from_path_expands_home_relative_local_cwds(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()

    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(
        """name: home-local-cwds
working_dir: .
local_target_defaults:
  cwd: ~/shared
nodes:
  - id: plan
    agent: codex
    prompt: hi
  - id: review
    agent: claude
    prompt: hi
    target:
      kind: local
      cwd: ~/task
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("HOME", str(home))

    pipeline = load_pipeline_from_path(pipeline_path)

    assert pipeline.local_target_defaults is not None
    assert pipeline.local_target_defaults.cwd == str((home / "shared").resolve())
    assert pipeline.nodes[1].target.cwd == str((home / "task").resolve())


def test_load_pipeline_from_text_resolves_relative_paths_from_explicit_base_dir(tmp_path):
    workspace = tmp_path / "workspace"
    pipeline = load_pipeline_from_text(
        """name: api-yaml
working_dir: .
local_target_defaults:
  cwd: shared
nodes:
  - id: plan
    agent: codex
    prompt: hi
    target:
      kind: local
      cwd: task
""",
        base_dir=workspace,
    )

    assert pipeline.working_dir == str(workspace.resolve())
    assert pipeline.local_target_defaults is not None
    assert pipeline.local_target_defaults.cwd == str((workspace / "shared").resolve())
    assert pipeline.nodes[0].target.cwd == str((workspace / "task").resolve())


def test_load_pipeline_from_data_resolves_relative_paths_from_explicit_base_dir(tmp_path):
    workspace = tmp_path / "workspace"
    pipeline = load_pipeline_from_data(
        {
            "name": "api-json",
            "working_dir": ".",
            "nodes": [
                {
                    "id": "plan",
                    "agent": "codex",
                    "prompt": "hi",
                    "target": {
                        "kind": "local",
                        "cwd": "task",
                    },
                }
            ],
        },
        base_dir=workspace,
    )

    assert pipeline.working_dir == str(workspace.resolve())
    assert pipeline.nodes[0].target.cwd == str((workspace / "task").resolve())


def test_load_pipeline_from_text_expands_fanout_nodes_before_resolving_relative_cwds(tmp_path):
    workspace = tmp_path / "workspace"
    pipeline = load_pipeline_from_text(
        """name: fanout-loader
working_dir: .
nodes:
  - id: fuzz
    fanout:
      count: 2
      as: shard
    agent: codex
    prompt: shard {{ shard.number }}
    target:
      kind: local
      cwd: agents/agent_{{ shard.suffix }}
""",
        base_dir=workspace,
    )

    assert pipeline.fanouts == {"fuzz": ["fuzz_0", "fuzz_1"]}
    assert [node.id for node in pipeline.nodes] == ["fuzz_0", "fuzz_1"]
    assert pipeline.nodes[0].target.cwd == str((workspace / "agents" / "agent_0").resolve())
    assert pipeline.nodes[1].target.cwd == str((workspace / "agents" / "agent_1").resolve())
