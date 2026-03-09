from __future__ import annotations

from agentflow.inspection import build_launch_inspection, build_launch_inspection_summary
from agentflow.loader import load_pipeline_from_path


def test_build_launch_inspection_summary_keeps_ambient_base_url_inheritance_when_startup_does_not_export_it(
    tmp_path,
    monkeypatch,
):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".bashrc").write_text("export PATH=\"$PATH\"\n", encoding="utf-8")

    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(
        """name: inspect-ambient-base-url
working_dir: .
nodes:
  - id: plan
    agent: codex
    prompt: hi
    target:
      kind: local
      shell: bash
      shell_interactive: true
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("OPENAI_BASE_URL", "https://relay.example/v1")

    pipeline = load_pipeline_from_path(pipeline_path)
    report = build_launch_inspection(pipeline, runs_dir=str(tmp_path / ".agentflow"))
    summary = build_launch_inspection_summary(report)

    assert summary["nodes"][0]["launch_env_inheritances"] == [
        {
            "key": "OPENAI_BASE_URL",
            "current_value": "https://relay.example/v1",
            "source": "current environment",
        }
    ]
    assert summary["nodes"][0]["warnings"] == [
        "Launch inherits current `OPENAI_BASE_URL` value `https://relay.example/v1`; configure `provider` or "
        "`node.env` explicitly if you want Codex routing pinned for this node."
    ]


def test_build_launch_inspection_summary_reports_effective_bootstrap_home_when_target_overrides_home(
    tmp_path,
    monkeypatch,
):
    process_home = tmp_path / "process-home"
    process_home.mkdir()
    custom_home = tmp_path / "custom-home"
    custom_home.mkdir()
    (custom_home / ".profile").write_text('if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n', encoding="utf-8")
    (custom_home / ".bashrc").write_text("export PATH=\"$PATH\"\n", encoding="utf-8")

    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(
        f"""name: inspect-custom-home
working_dir: .
nodes:
  - id: plan
    agent: codex
    prompt: hi
    target:
      kind: local
      shell: env HOME={custom_home} bash
      shell_login: true
      shell_interactive: true
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("HOME", str(process_home))

    pipeline = load_pipeline_from_path(pipeline_path)
    report = build_launch_inspection(pipeline, runs_dir=str(tmp_path / ".agentflow"))
    summary = build_launch_inspection_summary(report)

    assert summary["nodes"][0]["bootstrap"] == (
        f"shell=env HOME={custom_home} bash, login=true, startup=~/.profile -> ~/.bashrc, interactive=true"
    )
    assert summary["nodes"][0]["bootstrap_home"] == str(custom_home.resolve())
