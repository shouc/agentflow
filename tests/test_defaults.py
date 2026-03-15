from agentflow.defaults import (
    bundled_template_names,
    bundled_template_path,
    bundled_templates,
    default_smoke_pipeline_path,
    load_bundled_template_yaml,
)
from agentflow.loader import load_pipeline_from_path


def test_bundled_templates_expose_descriptions_and_example_files():
    templates = bundled_templates()

    assert tuple(template.name for template in templates) == bundled_template_names()

    by_name = {template.name: template for template in templates}
    assert by_name["pipeline"].example_name == "pipeline.yaml"
    assert by_name["pipeline"].description == "Generic Codex/Claude/Kimi starter DAG."
    assert by_name["codex-fanout-repo-sweep"].example_name == "codex-fanout-repo-sweep.yaml"
    assert "8 review shards" in by_name["codex-fanout-repo-sweep"].description
    assert by_name["local-kimi-smoke"].example_name == "local-real-agents-kimi-smoke.yaml"
    assert "bootstrap: kimi" in by_name["local-kimi-smoke"].description
    assert by_name["local-kimi-shell-init-smoke"].example_name == "local-real-agents-kimi-shell-init-smoke.yaml"
    assert "shell_init: kimi" in by_name["local-kimi-shell-init-smoke"].description
    assert by_name["local-kimi-shell-wrapper-smoke"].example_name == "local-real-agents-kimi-shell-wrapper-smoke.yaml"
    assert "target.shell" in by_name["local-kimi-shell-wrapper-smoke"].description


def test_bundled_smoke_pipeline_runs_both_agents_in_shared_kimi_bootstrap():
    pipeline = load_pipeline_from_path(default_smoke_pipeline_path())
    codex_node = next(node for node in pipeline.nodes if node.id == "codex_plan")
    claude_node = next(node for node in pipeline.nodes if node.id == "claude_review")

    assert pipeline.concurrency == 2
    assert codex_node.target.kind == "local"
    assert codex_node.target.bootstrap == "kimi"
    assert codex_node.target.shell == "bash"
    assert codex_node.target.shell_login is True
    assert codex_node.target.shell_interactive is True
    assert codex_node.target.shell_init == ["command -v kimi >/dev/null 2>&1", "kimi"]
    assert codex_node.depends_on == []
    assert claude_node.target.bootstrap == "kimi"
    assert claude_node.target.shell_init == ["command -v kimi >/dev/null 2>&1", "kimi"]
    assert claude_node.depends_on == []


def test_bundled_shell_init_smoke_template_is_available():
    assert "local-kimi-shell-init-smoke" in bundled_template_names()
    assert load_bundled_template_yaml("local-kimi-shell-init-smoke").startswith(
        "name: local-real-agents-kimi-shell-init-smoke\n"
    )


def test_bundled_shell_init_smoke_pipeline_runs_both_agents_in_explicit_shell_init_mode():
    pipeline = load_pipeline_from_path(str(bundled_template_path("local-kimi-shell-init-smoke")))
    codex_node = next(node for node in pipeline.nodes if node.id == "codex_plan")
    claude_node = next(node for node in pipeline.nodes if node.id == "claude_review")

    assert pipeline.concurrency == 2
    assert codex_node.target.kind == "local"
    assert codex_node.target.bootstrap is None
    assert codex_node.target.shell == "bash"
    assert codex_node.target.shell_login is True
    assert codex_node.target.shell_interactive is True
    assert codex_node.target.shell_init == "kimi"
    assert codex_node.depends_on == []
    assert claude_node.target.bootstrap is None
    assert claude_node.target.shell_init == "kimi"
    assert claude_node.depends_on == []


def test_bundled_shell_wrapper_smoke_template_is_available():
    assert "local-kimi-shell-wrapper-smoke" in bundled_template_names()
    assert load_bundled_template_yaml("local-kimi-shell-wrapper-smoke").startswith(
        "name: local-real-agents-kimi-shell-wrapper-smoke\n"
    )


def test_bundled_codex_fanout_repo_sweep_template_is_available():
    assert "codex-fanout-repo-sweep" in bundled_template_names()
    assert load_bundled_template_yaml("codex-fanout-repo-sweep").startswith(
        "name: codex-fanout-repo-sweep\n"
    )


def test_bundled_codex_fanout_repo_sweep_pipeline_expands_into_concrete_nodes():
    pipeline = load_pipeline_from_path(str(bundled_template_path("codex-fanout-repo-sweep")))

    assert pipeline.concurrency == 8
    assert pipeline.fanouts == {
        "sweep": ["sweep_0", "sweep_1", "sweep_2", "sweep_3", "sweep_4", "sweep_5", "sweep_6", "sweep_7"]
    }
    assert [node.id for node in pipeline.nodes[:3]] == ["prepare", "sweep_0", "sweep_1"]
    assert pipeline.node_map["merge"].depends_on == [
        "sweep_0",
        "sweep_1",
        "sweep_2",
        "sweep_3",
        "sweep_4",
        "sweep_5",
        "sweep_6",
        "sweep_7",
    ]


def test_bundled_shell_wrapper_smoke_pipeline_runs_both_agents_in_explicit_shell_wrapper_mode():
    pipeline = load_pipeline_from_path(str(bundled_template_path("local-kimi-shell-wrapper-smoke")))
    codex_node = next(node for node in pipeline.nodes if node.id == "codex_plan")
    claude_node = next(node for node in pipeline.nodes if node.id == "claude_review")

    assert pipeline.concurrency == 2
    assert codex_node.target.kind == "local"
    assert codex_node.target.bootstrap is None
    assert codex_node.target.shell == "bash -lic 'command -v kimi >/dev/null 2>&1 && kimi && {command}'"
    assert codex_node.target.shell_login is False
    assert codex_node.target.shell_interactive is False
    assert codex_node.target.shell_init is None
    assert codex_node.depends_on == []
    assert claude_node.target.bootstrap is None
    assert claude_node.target.shell == "bash -lic 'command -v kimi >/dev/null 2>&1 && kimi && {command}'"
    assert claude_node.target.shell_init is None
    assert claude_node.depends_on == []
