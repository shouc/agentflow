from __future__ import annotations

from agentflow.context import render_node_prompt
from agentflow.specs import NodeResult, PipelineSpec


def test_pipeline_working_path_expands_home_relative_directory(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    pipeline = PipelineSpec.model_validate(
        {
            "name": "home-working-path",
            "working_dir": "~/workspace",
            "nodes": [
                {
                    "id": "plan",
                    "agent": "codex",
                    "prompt": "hi",
                }
            ],
        }
    )

    assert pipeline.working_path == (home / "workspace").resolve()


def test_render_node_prompt_uses_expanded_home_relative_pipeline_working_dir_for_skills(tmp_path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    skill_dir = workspace / "skills" / "release-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("Follow the shared release checklist.", encoding="utf-8")

    monkeypatch.setenv("HOME", str(home))

    pipeline = PipelineSpec.model_validate(
        {
            "name": "home-working-dir-skills",
            "working_dir": "~/workspace",
            "nodes": [
                {
                    "id": "plan",
                    "agent": "codex",
                    "prompt": "Ship it.",
                    "skills": ["release-skill"],
                }
            ],
        }
    )

    prompt = render_node_prompt(pipeline, pipeline.nodes[0], {"plan": NodeResult(node_id="plan")})

    assert "Selected skills:" in prompt
    assert "Follow the shared release checklist." in prompt
    assert prompt.endswith("Task:\nShip it.")
