from __future__ import annotations

import json
from pathlib import Path

from agentflow.agents.claude import ClaudeAdapter
from agentflow.agents.codex import CodexAdapter
from agentflow.agents.kimi import KimiAdapter
from agentflow.prepared import ExecutionPaths
from agentflow.specs import NodeSpec


def _paths(tmp_path: Path) -> ExecutionPaths:
    return ExecutionPaths(
        host_workdir=tmp_path,
        host_runtime_dir=tmp_path / ".runtime",
        target_workdir=str(tmp_path),
        target_runtime_dir=str(tmp_path / ".runtime"),
        app_root=tmp_path,
    )


def test_claude_adapter_uses_provider_api_key_env_value(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_CLAUDE_API_KEY", "test-secret")
    node = NodeSpec.model_validate(
        {
            "id": "review",
            "agent": "claude",
            "prompt": "Review",
            "provider": {
                "name": "kimi-proxy",
                "base_url": "https://example.test/anthropic",
                "api_key_env": "TEST_CLAUDE_API_KEY",
                "headers": {"x-provider": "kimi"},
            },
        }
    )

    prepared = ClaudeAdapter().prepare(node, "Review", _paths(tmp_path))

    assert prepared.env["ANTHROPIC_BASE_URL"] == "https://example.test/anthropic"
    assert prepared.env["ANTHROPIC_API_KEY"] == "test-secret"
    assert json.loads(prepared.env["ANTHROPIC_CUSTOM_HEADERS"]) == {"x-provider": "kimi"}
    assert "ANTHROPIC_API_KEY_ENV" not in prepared.env


def test_codex_adapter_uses_current_exec_flags(tmp_path):
    node = NodeSpec.model_validate(
        {
            "id": "plan",
            "agent": "codex",
            "prompt": "Plan",
        }
    )

    prepared = CodexAdapter().prepare(node, "Plan", _paths(tmp_path))

    assert prepared.command[:4] == ["codex", "exec", "--json", "--skip-git-repo-check"]
    assert "--ask-for-approval" not in prepared.command
    assert prepared.command[4:8] == ["-c", 'approval_policy="never"', "--sandbox", "read-only"]


def test_codex_adapter_suppresses_unstable_feature_warning(tmp_path):
    node = NodeSpec.model_validate(
        {
            "id": "plan",
            "agent": "codex",
            "prompt": "Plan",
        }
    )

    prepared = CodexAdapter().prepare(node, "Plan", _paths(tmp_path))

    assert prepared.command.count("-c") == 2
    assert 'suppress_unstable_features_warning=true' in prepared.command


def test_claude_adapter_uses_tools_flag_for_read_only_access(tmp_path):
    node = NodeSpec.model_validate(
        {
            "id": "review",
            "agent": "claude",
            "prompt": "Review",
        }
    )

    prepared = ClaudeAdapter().prepare(node, "Review", _paths(tmp_path))

    assert "--allowedTools" not in prepared.command
    index = prepared.command.index("--tools")
    assert prepared.command[index + 1] == "Read,Glob,Grep,LS,NotebookRead,Task,TaskOutput,TodoRead,WebFetch,WebSearch"


def test_claude_adapter_uses_tools_flag_for_read_write_access(tmp_path):
    node = NodeSpec.model_validate(
        {
            "id": "implement",
            "agent": "claude",
            "prompt": "Implement",
            "tools": "read_write",
        }
    )

    prepared = ClaudeAdapter().prepare(node, "Implement", _paths(tmp_path))

    index = prepared.command.index("--tools")
    assert "Bash" in prepared.command[index + 1].split(",")
    assert "Write" in prepared.command[index + 1].split(",")


def test_claude_adapter_supports_kimi_provider_alias(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-kimi-secret")
    node = NodeSpec.model_validate(
        {
            "id": "review",
            "agent": "claude",
            "prompt": "Review",
            "provider": "kimi",
        }
    )

    prepared = ClaudeAdapter().prepare(node, "Review", _paths(tmp_path))

    assert prepared.env["ANTHROPIC_BASE_URL"] == "https://api.kimi.com/coding/"
    assert prepared.env["ANTHROPIC_API_KEY"] == "test-kimi-secret"


def test_kimi_adapter_supports_provider_alias(tmp_path):
    node = NodeSpec.model_validate(
        {
            "id": "review",
            "agent": "kimi",
            "prompt": "Review",
            "provider": "kimi",
        }
    )

    prepared = KimiAdapter().prepare(node, "Review", _paths(tmp_path))
    request = json.loads(prepared.runtime_files["kimi-request.json"])

    assert request["provider"]["name"] == "moonshot"
    assert request["provider"]["base_url"] == "https://api.moonshot.ai/v1"
    assert request["provider"]["api_key_env"] == "KIMI_API_KEY"
