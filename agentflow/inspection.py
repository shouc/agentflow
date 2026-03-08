from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from agentflow.agents.registry import AdapterRegistry, default_adapter_registry
from agentflow.context import render_node_prompt
from agentflow.prepared import build_execution_paths
from agentflow.runners.registry import RunnerRegistry, default_runner_registry
from agentflow.specs import NodeResult, NodeSpec, NodeStatus, PipelineSpec, resolve_provider
from agentflow.utils import looks_sensitive_key

_REDACTED = "<redacted>"
_GENERATED = "<generated>"


def _auto_preflight_summary(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    enabled = value.get("enabled")
    reason = value.get("reason")
    if not isinstance(reason, str) or not reason:
        return None
    status = "enabled" if enabled else "disabled"
    return f"{status} - {reason}"


def _auto_preflight_match_summary(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    matches = value.get("match_summary")
    if not isinstance(matches, list):
        return []
    return [match for match in matches if isinstance(match, str) and match]

def _preview_text(text: str | None, *, limit: int = 100) -> str | None:
    if text is None:
        return None
    collapsed = " ".join(text.split())
    if not collapsed:
        return None
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def _command_text(command: list[str] | None) -> str | None:
    if not command:
        return None
    return shlex.join(command)


def _placeholder_text(node_id: str, field: str) -> str:
    return f"<inspect placeholder for nodes.{node_id}.{field}>"


def _build_placeholder_results(pipeline: PipelineSpec) -> dict[str, NodeResult]:
    results: dict[str, NodeResult] = {}
    for node in pipeline.nodes:
        output = _placeholder_text(node.id, "output")
        result = NodeResult(
            node_id=node.id,
            status=NodeStatus.PENDING,
            output=output,
            final_response=_placeholder_text(node.id, "final_response"),
            stdout_lines=[_placeholder_text(node.id, "stdout")],
            stderr_lines=[_placeholder_text(node.id, "stderr")],
        )
        results[node.id] = result
    return results


# Keep non-secret debugging values readable while redacting likely credentials.
def _sanitize_env(env: dict[str, str]) -> dict[str, str]:
    return {
        key: (_REDACTED if looks_sensitive_key(key) else value)
        for key, value in sorted(env.items())
    }


def _sanitize_payload(value: Any, *, key: str | None = None) -> Any:
    if isinstance(value, dict):
        if key == "env":
            string_env = {env_key: str(env_value) for env_key, env_value in value.items()}
            return _sanitize_env(string_env)
        if key == "runtime_files":
            return {runtime_key: _GENERATED for runtime_key in sorted(value)}
        return {inner_key: _sanitize_payload(inner_value, key=inner_key) for inner_key, inner_value in value.items()}
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    if key and looks_sensitive_key(key):
        return _REDACTED
    return value


def _render_prompt_for_inspection(
    pipeline: PipelineSpec,
    node: NodeSpec,
    placeholder_results: dict[str, NodeResult],
) -> tuple[str, str | None]:
    try:
        return render_node_prompt(pipeline, node, placeholder_results), None
    except Exception as exc:
        return node.prompt, str(exc)


def _payload_summary(node_plan: dict[str, Any]) -> str | None:
    launch = node_plan["launch"]
    payload = launch.get("payload")
    if not isinstance(payload, dict):
        return None
    if launch["kind"] == "container":
        image = payload.get("image")
        engine = payload.get("engine")
        if image and engine:
            return f"{engine} image={image}"
    if launch["kind"] == "aws_lambda":
        function_name = payload.get("function_name")
        invocation_type = payload.get("invocation_type")
        if function_name and invocation_type:
            return f"function={function_name}, invocation={invocation_type}"
    return None


def _provider_summary(node_plan: dict[str, Any]) -> str | None:
    provider = node_plan.get("resolved_provider")
    if not isinstance(provider, dict):
        return None

    parts: list[str] = []
    name = provider.get("name")
    if name:
        parts.append(str(name))

    api_key_env = provider.get("api_key_env")
    if api_key_env:
        parts.append(f"key={api_key_env}")

    base_url = provider.get("base_url")
    if base_url:
        parts.append(f"url={base_url}")

    if not parts:
        return None
    return ", ".join(parts)


def _bootstrap_summary(target: dict[str, Any]) -> str | None:
    if target.get("kind") != "local":
        return None

    parts: list[str] = []
    shell = target.get("shell")
    if shell:
        parts.append(f"shell={shell}")

    if target.get("shell_login"):
        parts.append("login=true")

    if target.get("shell_interactive"):
        parts.append("interactive=true")

    shell_init = target.get("shell_init")
    if shell_init:
        parts.append(f"init={shell_init}")

    if not parts:
        return None
    return ", ".join(parts)


def _execution_mode_summary(node_plan: dict[str, Any]) -> str | None:
    parts: list[str] = []

    tools = node_plan.get("tools")
    if tools:
        parts.append(f"tools={tools}")

    capture = node_plan.get("capture")
    if capture:
        parts.append(f"capture={capture}")

    if not parts:
        return None
    return ", ".join(parts)


def build_launch_inspection(
    pipeline: PipelineSpec,
    *,
    runs_dir: str,
    node_ids: list[str] | None = None,
    adapters: AdapterRegistry = default_adapter_registry,
    runners: RunnerRegistry = default_runner_registry,
) -> dict[str, Any]:
    requested_nodes = set(node_ids or [])
    available_nodes = {node.id for node in pipeline.nodes}
    missing_nodes = sorted(requested_nodes - available_nodes)
    if missing_nodes:
        raise ValueError(f"unknown node ids: {missing_nodes}")

    placeholder_results = _build_placeholder_results(pipeline)
    base_dir = Path(runs_dir).expanduser().resolve()
    inspected_nodes: list[dict[str, Any]] = []

    for node in pipeline.nodes:
        if requested_nodes and node.id not in requested_nodes:
            continue

        prompt, render_error = _render_prompt_for_inspection(pipeline, node, placeholder_results)
        resolved_provider = resolve_provider(node.provider, node.agent)
        paths = build_execution_paths(
            base_dir=base_dir,
            pipeline_workdir=pipeline.working_path,
            run_id="inspect",
            node_id=node.id,
            node_target=node.target,
            create_runtime_dir=False,
        )
        prepared = adapters.get(node.agent).prepare(node, prompt, paths)
        launch = runners.get(node.target.kind).plan_execution(node, prepared, paths)

        node_plan = {
            "id": node.id,
            "agent": node.agent.value,
            "model": node.model,
            "tools": node.tools.value,
            "capture": node.capture.value,
            "depends_on": list(node.depends_on),
            "provider": node.provider.model_dump(mode="json") if hasattr(node.provider, "model_dump") else node.provider,
            "resolved_provider": resolved_provider.model_dump(mode="json") if resolved_provider is not None else None,
            "target": node.target.model_dump(mode="json"),
            "rendered_prompt": prompt,
            "rendered_prompt_preview": _preview_text(prompt, limit=120),
            "render_error": render_error,
            "prepared": {
                "command": list(prepared.command),
                "command_text": _command_text(prepared.command),
                "cwd": prepared.cwd,
                "trace_kind": prepared.trace_kind,
                "env": _sanitize_env(prepared.env),
                "env_keys": sorted(prepared.env),
                "stdin": _preview_text(prepared.stdin, limit=120),
                "runtime_files": sorted(prepared.runtime_files),
            },
            "launch": {
                "kind": launch.kind,
                "command": list(launch.command or []),
                "command_text": _command_text(launch.command),
                "cwd": launch.cwd,
                "env": _sanitize_env(launch.env),
                "env_keys": sorted(launch.env),
                "stdin": _preview_text(launch.stdin, limit=120),
                "runtime_files": list(launch.runtime_files),
                "payload": _sanitize_payload(launch.payload),
            },
        }
        node_plan["launch"]["payload_summary"] = _payload_summary(node_plan)
        inspected_nodes.append(node_plan)

    notes: list[str] = []
    if any("nodes." in node.prompt for node in pipeline.nodes):
        notes.append("Dependency references use placeholder node outputs because `inspect` does not execute the DAG.")

    return {
        "pipeline": {
            "name": pipeline.name,
            "description": pipeline.description,
            "working_dir": str(pipeline.working_path),
            "node_count": len(inspected_nodes),
        },
        "notes": notes,
        "nodes": inspected_nodes,
    }


def build_launch_inspection_summary(report: dict[str, Any]) -> dict[str, Any]:
    pipeline = {
        key: value
        for key, value in (report.get("pipeline") or {}).items()
        if value is not None
    }
    summary: dict[str, Any] = {
        "pipeline": pipeline,
        "nodes": [],
    }

    raw_auto_preflight = pipeline.get("auto_preflight")
    auto_preflight = _auto_preflight_summary(raw_auto_preflight)
    if auto_preflight:
        summary["pipeline"]["auto_preflight"] = auto_preflight
    auto_preflight_matches = _auto_preflight_match_summary(raw_auto_preflight)
    if auto_preflight_matches:
        summary["pipeline"]["auto_preflight_matches"] = auto_preflight_matches

    notes = report.get("notes")
    if notes:
        summary["notes"] = list(notes)

    for node in report.get("nodes", []):
        node_summary: dict[str, Any] = {
            "id": node["id"],
            "agent": node["agent"],
            "target": node["target"]["kind"],
        }
        depends_on = node.get("depends_on")
        if depends_on:
            node_summary["depends_on"] = list(depends_on)
        render_error = node.get("render_error")
        if render_error:
            node_summary["render_error"] = render_error
        model = node.get("model")
        if model:
            node_summary["model"] = model
        tools = node.get("tools")
        if tools:
            node_summary["tools"] = tools
        capture = node.get("capture")
        if capture:
            node_summary["capture"] = capture
        provider_summary = _provider_summary(node)
        if provider_summary:
            node_summary["provider"] = provider_summary
        bootstrap_summary = _bootstrap_summary(node["target"])
        if bootstrap_summary:
            node_summary["bootstrap"] = bootstrap_summary
        prompt_preview = node.get("rendered_prompt_preview")
        if prompt_preview:
            node_summary["prompt_preview"] = prompt_preview
        prepared_command = node.get("prepared", {}).get("command_text")
        if prepared_command:
            node_summary["prepared_command"] = prepared_command
        launch_command = node.get("launch", {}).get("command_text")
        node_summary["launch"] = launch_command or node["launch"]["kind"]
        cwd = node.get("launch", {}).get("cwd") or node.get("prepared", {}).get("cwd")
        if cwd:
            node_summary["cwd"] = cwd
        env_keys = node.get("launch", {}).get("env_keys") or node.get("prepared", {}).get("env_keys")
        if env_keys:
            node_summary["env_keys"] = list(env_keys)
        runtime_files = node.get("launch", {}).get("runtime_files") or node.get("prepared", {}).get("runtime_files")
        if runtime_files:
            node_summary["runtime_files"] = list(runtime_files)
        payload_summary = node.get("launch", {}).get("payload_summary")
        if payload_summary:
            node_summary["payload"] = payload_summary
        summary["nodes"].append(node_summary)

    return summary


def render_launch_inspection_summary(report: dict[str, Any]) -> str:
    pipeline = report["pipeline"]
    lines = [f"Pipeline: {pipeline['name']}", f"Working dir: {pipeline['working_dir']}"]
    raw_auto_preflight = pipeline.get("auto_preflight")
    auto_preflight = _auto_preflight_summary(raw_auto_preflight)
    if auto_preflight:
        lines.append(f"Auto preflight: {auto_preflight}")
    auto_preflight_matches = _auto_preflight_match_summary(raw_auto_preflight)
    if auto_preflight_matches:
        lines.append(f"Auto preflight matches: {', '.join(auto_preflight_matches)}")
    for note in report.get("notes", []):
        lines.append(f"Note: {note}")
    lines.append("Nodes:")

    for node in report.get("nodes", []):
        lines.append(f"- {node['id']} [{node['agent']}/{node['target']['kind']}]")
        if node["depends_on"]:
            lines.append(f"  Depends on: {', '.join(node['depends_on'])}")
        if node["render_error"]:
            lines.append(f"  Render error: {node['render_error']}")
        if node.get("model"):
            lines.append(f"  Model: {node['model']}")
        execution_mode_summary = _execution_mode_summary(node)
        if execution_mode_summary:
            lines.append(f"  Mode: {execution_mode_summary}")
        provider_summary = _provider_summary(node)
        if provider_summary:
            lines.append(f"  Provider: {provider_summary}")
        bootstrap_summary = _bootstrap_summary(node["target"])
        if bootstrap_summary:
            lines.append(f"  Bootstrap: {bootstrap_summary}")
        prompt_preview = node.get("rendered_prompt_preview")
        if prompt_preview:
            lines.append(f"  Prompt: {prompt_preview}")
        prepared_command = node["prepared"].get("command_text")
        if prepared_command:
            lines.append(f"  Prepared: {prepared_command}")
        launch_command = node["launch"].get("command_text")
        lines.append(f"  Launch: {launch_command or node['launch']['kind']}")
        cwd = node["launch"].get("cwd") or node["prepared"].get("cwd")
        if cwd:
            lines.append(f"  Cwd: {cwd}")
        env_keys = node["launch"].get("env_keys") or node["prepared"].get("env_keys")
        if env_keys:
            lines.append(f"  Env keys: {', '.join(env_keys)}")
        runtime_files = node["launch"].get("runtime_files") or node["prepared"].get("runtime_files")
        if runtime_files:
            lines.append(f"  Runtime files: {', '.join(runtime_files)}")
        payload_summary = node["launch"].get("payload_summary")
        if payload_summary:
            lines.append(f"  Payload: {payload_summary}")
    return "\n".join(lines)
