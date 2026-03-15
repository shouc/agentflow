from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from agentflow.specs import PipelineSpec, expand_compact_nodes


def load_pipeline_from_path(path: str | Path) -> PipelineSpec:
    path = Path(path)
    data = path.read_text(encoding="utf-8")
    return load_pipeline_from_text(data, base_dir=path.parent.resolve())


def load_pipeline_from_text(data: str, *, base_dir: str | Path | None = None) -> PipelineSpec:
    parsed = _parse_pipeline_text(data)
    return load_pipeline_from_data(parsed, base_dir=base_dir)


def load_pipeline_from_data(data: Any, *, base_dir: str | Path | None = None) -> PipelineSpec:
    if isinstance(data, dict) and base_dir is not None:
        data = expand_compact_nodes(data)
        data = _resolve_file_relative_paths(data, _resolve_base_dir(base_dir))
    return PipelineSpec.model_validate(data)


def _parse_pipeline_text(data: str) -> Any:
    parsed: Any
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError:
        parsed = yaml.safe_load(data)
    return parsed


def _resolve_base_dir(base_dir: str | Path) -> Path:
    return Path(base_dir).expanduser().resolve()


def _resolve_file_relative_paths(parsed: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    resolved = dict(parsed)
    working_dir_value = resolved.get("working_dir", ".")
    working_dir = Path(working_dir_value).expanduser()
    if not working_dir.is_absolute():
        working_dir = (base_dir / working_dir).resolve()
        resolved["working_dir"] = str(working_dir)
    else:
        working_dir = working_dir.resolve()
        resolved["working_dir"] = str(working_dir)

    local_target_defaults = resolved.get("local_target_defaults")
    if isinstance(local_target_defaults, dict) and local_target_defaults.get("kind", "local") == "local":
        cwd = local_target_defaults.get("cwd")
        if isinstance(cwd, str) and cwd:
            expanded_cwd = Path(cwd).expanduser()
            updated_local_target_defaults = dict(local_target_defaults)
            if expanded_cwd.is_absolute():
                updated_local_target_defaults["cwd"] = str(expanded_cwd.resolve())
            else:
                updated_local_target_defaults["cwd"] = str((working_dir / expanded_cwd).resolve())
            resolved["local_target_defaults"] = updated_local_target_defaults

    nodes: list[Any] = []
    for node in resolved.get("nodes", []):
        if not isinstance(node, dict):
            nodes.append(node)
            continue
        updated = dict(node)
        target = updated.get("target")
        if isinstance(target, dict) and target.get("kind", "local") == "local":
            cwd = target.get("cwd")
            if isinstance(cwd, str) and cwd:
                expanded_cwd = Path(cwd).expanduser()
                updated_target = dict(target)
                if expanded_cwd.is_absolute():
                    updated_target["cwd"] = str(expanded_cwd.resolve())
                else:
                    updated_target["cwd"] = str((working_dir / expanded_cwd).resolve())
                updated["target"] = updated_target
        nodes.append(updated)
    resolved["nodes"] = nodes
    return resolved
