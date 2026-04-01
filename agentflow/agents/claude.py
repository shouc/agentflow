from __future__ import annotations

import json
import os
from pathlib import Path

from agentflow.agents.base import AgentAdapter
from agentflow.env import merge_env_layers
from agentflow.prepared import ExecutionPaths, PreparedExecution
from agentflow.specs import NodeSpec, RepoInstructionsMode, ToolAccess


_CLAUDE_READ_ONLY_TOOLS = [
    "Read",
    "Glob",
    "Grep",
    "LS",
    "NotebookRead",
    "Task",
    "TaskOutput",
    "TodoRead",
    "WebFetch",
    "WebSearch",
]

_CLAUDE_READ_WRITE_TOOLS = _CLAUDE_READ_ONLY_TOOLS + [
    "Write",
    "Edit",
    "MultiEdit",
    "NotebookEdit",
    "TodoWrite",
    "Bash",
]


class ClaudeAdapter(AgentAdapter):
    def prepare(self, node: NodeSpec, prompt: str, paths: ExecutionPaths) -> PreparedExecution:
        provider = self.provider_config(node.provider, node.agent)
        executable = node.executable or "claude"
        repo_instructions_ignored = node.repo_instructions_mode == RepoInstructionsMode.IGNORE
        command = [
            executable,
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
            "--permission-mode",
            "bypassPermissions",
        ]
        if repo_instructions_ignored:
            command.extend(["--bare", "--add-dir", paths.target_workdir])
        if node.model:
            command.extend(["--model", node.model])
        allowed_tools = _CLAUDE_READ_ONLY_TOOLS if node.tools == ToolAccess.READ_ONLY else _CLAUDE_READ_WRITE_TOOLS
        command.extend(["--tools", ",".join(allowed_tools)])
        runtime_files: dict[str, str] = {}
        if node.mcps:
            mcp_payload: dict[str, object] = {"mcpServers": {}}
            for mcp in node.mcps:
                inner: dict[str, object] = {}
                if mcp.transport == "stdio":
                    if mcp.command:
                        inner["command"] = mcp.command
                    if mcp.args:
                        inner["args"] = mcp.args
                    if mcp.env:
                        inner["env"] = mcp.env
                else:
                    if mcp.url:
                        inner["url"] = mcp.url
                    if mcp.headers:
                        inner["headers"] = mcp.headers
                    inner["transport"] = "streamable_http"
                mcp_payload["mcpServers"][mcp.name] = inner
            relative_path = self.relative_runtime_file("claude-mcp.json")
            runtime_files[relative_path] = json.dumps(mcp_payload, ensure_ascii=False, indent=2)
            command.extend(["--mcp-config", str(Path(paths.target_runtime_dir) / relative_path)])
        env = merge_env_layers(getattr(provider, "env", None), node.env)
        if provider:
            if provider.base_url:
                env.setdefault("ANTHROPIC_BASE_URL", provider.base_url)
            if provider.headers:
                env.setdefault("ANTHROPIC_CUSTOM_HEADERS", json.dumps(provider.headers, ensure_ascii=False))
            if provider.api_key_env:
                if provider.api_key_env in env:
                    api_key = env[provider.api_key_env]
                else:
                    api_key = os.getenv(provider.api_key_env)
                if api_key is not None:
                    env.setdefault("ANTHROPIC_API_KEY", api_key)
        command.extend(node.extra_args)
        cwd = paths.target_workdir
        if repo_instructions_ignored:
            cwd = str(Path(paths.target_runtime_dir))
        return PreparedExecution(
            command=command,
            env=env,
            cwd=cwd,
            trace_kind="claude",
            runtime_files=runtime_files,
        )
