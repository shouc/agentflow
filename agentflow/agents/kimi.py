from __future__ import annotations

import json
import os
from pathlib import Path

from agentflow.agents.base import AgentAdapter
from agentflow.env import merge_env_layers
from agentflow.prepared import ExecutionPaths, PreparedExecution
from agentflow.specs import NodeSpec


class KimiAdapter(AgentAdapter):
    def prepare(self, node: NodeSpec, prompt: str, paths: ExecutionPaths) -> PreparedExecution:
        provider = self.provider_config(node.provider, node.agent)
        executable = node.executable or "kimi"
        command = [
            executable,
            "--print",
            "--output-format",
            "stream-json",
            "--yolo",
            "-p",
            prompt,
        ]
        if node.model:
            command.extend(["--model", node.model])
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
            relative_path = self.relative_runtime_file("kimi-mcp.json")
            runtime_files[relative_path] = json.dumps(mcp_payload, ensure_ascii=False, indent=2)
            command.extend(["--mcp-config-file", str(Path(paths.target_runtime_dir) / relative_path)])
        command.extend(node.extra_args)
        env = merge_env_layers(getattr(provider, "env", None), node.env)
        if provider:
            if provider.api_key_env:
                if provider.api_key_env in env:
                    api_key = env[provider.api_key_env]
                else:
                    api_key = os.getenv(provider.api_key_env)
                if api_key is not None:
                    env.setdefault("KIMI_API_KEY", api_key)
        return PreparedExecution(
            command=command,
            env=env,
            cwd=paths.target_workdir,
            trace_kind="kimi",
            runtime_files=runtime_files,
        )
