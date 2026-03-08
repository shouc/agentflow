from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentflow.utils import ensure_dir


@dataclass(slots=True)
class ExecutionPaths:
    host_workdir: Path
    host_runtime_dir: Path
    target_workdir: str
    target_runtime_dir: str
    app_root: Path


@dataclass(slots=True)
class PreparedExecution:
    command: list[str]
    env: dict[str, str]
    cwd: str
    trace_kind: str
    runtime_files: dict[str, str] = field(default_factory=dict)
    stdin: str | None = None


def resolve_local_workdir(pipeline_workdir: Path, cwd: str | None) -> Path:
    if not cwd:
        return pipeline_workdir

    candidate = Path(cwd).expanduser()
    if candidate.is_absolute():
        return candidate
    return (pipeline_workdir / candidate).resolve()


def build_execution_paths(
    *,
    base_dir: Path,
    pipeline_workdir: Path,
    run_id: str,
    node_id: str,
    node_target: Any,
    create_runtime_dir: bool = True,
) -> ExecutionPaths:
    host_runtime_dir = base_dir / run_id / "runtime" / node_id
    if create_runtime_dir:
        host_runtime_dir = ensure_dir(host_runtime_dir)

    app_root = Path(__file__).resolve().parents[1]
    if node_target.kind == "container":
        host_workdir = pipeline_workdir
        target_workdir = node_target.workdir_mount
        target_runtime_dir = node_target.runtime_mount
    elif node_target.kind == "aws_lambda":
        host_workdir = pipeline_workdir
        target_workdir = node_target.remote_workdir
        target_runtime_dir = f"{node_target.remote_workdir.rstrip('/')}/.agentflow-runtime/{node_id}"
    else:
        host_workdir = resolve_local_workdir(pipeline_workdir, node_target.cwd)
        target_workdir = str(host_workdir)
        target_runtime_dir = str(host_runtime_dir)

    return ExecutionPaths(
        host_workdir=host_workdir,
        host_runtime_dir=host_runtime_dir,
        target_workdir=target_workdir,
        target_runtime_dir=target_runtime_dir,
        app_root=app_root,
    )
