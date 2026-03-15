from __future__ import annotations

from pathlib import Path

from agentflow.agents.base import AgentAdapter
from agentflow.env import merge_env_layers
from agentflow.prepared import ExecutionPaths, PreparedExecution
from agentflow.specs import NodeSpec, ProviderConfig, ToolAccess


class CodexAdapter(AgentAdapter):
    def _format_toml_value(self, value: object) -> str:
        import json

        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, list):
            return "[" + ", ".join(self._format_toml_value(item) for item in value) + "]"
        if isinstance(value, dict):
            items = ", ".join(f"{key} = {self._format_toml_value(inner)}" for key, inner in value.items())
            return "{" + items + "}"
        return json.dumps(str(value), ensure_ascii=False)

    def _render_config(self, node: NodeSpec, provider: ProviderConfig | None) -> str:
        lines: list[str] = []
        if node.model:
            lines.append(f"model = {self._format_toml_value(node.model)}")
        lines.append(f"approval_policy = {self._format_toml_value('never')}")
        sandbox_mode = "read-only" if node.tools == ToolAccess.READ_ONLY else "workspace-write"
        lines.append(f"sandbox_mode = {self._format_toml_value(sandbox_mode)}")
        if provider and (provider.base_url or provider.api_key_env or provider.wire_api):
            lines.append("")
            lines.append(f"[model_providers.{provider.name}]")
            lines.append(f"name = {self._format_toml_value(provider.name)}")
            if provider.base_url:
                lines.append(f"base_url = {self._format_toml_value(provider.base_url)}")
            if provider.api_key_env:
                lines.append(f"env_key = {self._format_toml_value(provider.api_key_env)}")
            if provider.wire_api:
                lines.append(f"wire_api = {self._format_toml_value(provider.wire_api)}")
        if provider:
            lines.append("")
            lines.append("[profiles.agentflow]")
            if node.model:
                lines.append(f"model = {self._format_toml_value(node.model)}")
            lines.append(f"model_provider = {self._format_toml_value(provider.name)}")
        if node.mcps:
            for mcp in node.mcps:
                lines.append("")
                lines.append(f"[mcp_servers.{mcp.name}]")
                if mcp.transport == "stdio":
                    if mcp.command:
                        lines.append(f"command = {self._format_toml_value(mcp.command)}")
                    if mcp.args:
                        lines.append(f"args = {self._format_toml_value(mcp.args)}")
                    if mcp.env:
                        lines.append(f"env = {self._format_toml_value(mcp.env)}")
                else:
                    if mcp.url:
                        lines.append(f"url = {self._format_toml_value(mcp.url)}")
                    if mcp.headers:
                        lines.append(f"http_headers = {self._format_toml_value(mcp.headers)}")
        return "\n".join(lines) + "\n"

    def prepare(self, node: NodeSpec, prompt: str, paths: ExecutionPaths) -> PreparedExecution:
        provider = self.provider_config(node.provider, node.agent)
        executable = node.executable or "codex"
        sandbox = "read-only" if node.tools == ToolAccess.READ_ONLY else "workspace-write"
        command = [
            executable,
            "exec",
            "--json",
            "--skip-git-repo-check",
            "-c",
            'approval_policy="never"',
            "-c",
            "suppress_unstable_features_warning=true",
            "--sandbox",
            sandbox,
        ]
        if node.model and not provider:
            command.extend(["--model", node.model])
        if provider:
            command.extend(["--profile", "agentflow"])
        command.extend(node.extra_args)
        command.append(prompt)

        env = merge_env_layers(getattr(provider, "env", None), node.env)
        runtime_files: dict[str, str] = {}
        if provider or node.mcps:
            runtime_files[self.relative_runtime_file("codex_home", "config.toml")] = self._render_config(node, provider)
            env["CODEX_HOME"] = str(Path(paths.target_runtime_dir) / "codex_home")
        return PreparedExecution(
            command=command,
            env=env,
            cwd=paths.target_workdir,
            trace_kind="codex",
            runtime_files=runtime_files,
        )
