from __future__ import annotations

from agentflow.loader import load_pipeline_from_path


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
