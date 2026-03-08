from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

import pytest

from agentflow.agents.base import AgentAdapter
from agentflow.agents.registry import AdapterRegistry
from agentflow.orchestrator import Orchestrator
from agentflow.prepared import ExecutionPaths, PreparedExecution
from agentflow.runners.registry import RunnerRegistry
from agentflow.specs import AgentKind, PipelineSpec
from agentflow.store import RunStore


class MockAdapter(AgentAdapter):
    def prepare(self, node, prompt: str, paths: ExecutionPaths) -> PreparedExecution:
        script = r'''
import json
import sys
import sys
import time
from pathlib import Path

node_id = sys.argv[1]
prompt = sys.argv[2]
agent = sys.argv[3]
workdir = Path.cwd()
if node_id in {"alpha", "beta"}:
    time.sleep(0.25)
if node_id == "slow":
    for _ in range(200):
        time.sleep(0.05)
if node_id == "flaky":
    marker = workdir / ".flaky"
    if not marker.exists():
        marker.write_text("first failure", encoding="utf-8")
        print("transient failure", file=sys.stderr)
        raise SystemExit(3)
if node_id == "flaky_silent":
    marker = workdir / ".flaky_silent"
    if not marker.exists():
        marker.write_text("first failure", encoding="utf-8")
        print("stale stdout from failed attempt")
        raise SystemExit(3)
    raise SystemExit(0)
if node_id == "writer":
    (workdir / "artifact.txt").write_text("file data", encoding="utf-8")
if agent == "codex":
    print(json.dumps({"type": "response.output_item.done", "item": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": prompt}]}}))
elif agent == "claude":
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": prompt}]}}))
    print(json.dumps({"type": "result", "result": prompt}))
else:
    print(json.dumps({"jsonrpc": "2.0", "method": "event", "params": {"type": "ContentPart", "payload": {"type": "text", "text": prompt}}}))
'''
        return PreparedExecution(
            command=["python3", "-c", script, node.id, prompt, node.agent.value],
            env={},
            cwd=paths.target_workdir,
            trace_kind=node.agent.value,
        )


class LaunchPlanAdapter(AgentAdapter):
    def prepare(self, node, prompt: str, paths: ExecutionPaths) -> PreparedExecution:
        return PreparedExecution(
            command=["python3", "-c", 'print("launch plan ok")'],
            env={
                "OPENAI_API_KEY": "super-secret",
                "UPSTREAM_AUTH_HEADER": "Bearer top-secret",
                "ANTHROPIC_CUSTOM_HEADERS": '{"x-api-key": "super-secret"}',
                "VISIBLE_FLAG": "visible",
            },
            cwd=paths.target_workdir,
            trace_kind=node.agent.value,
            runtime_files={"config/runtime.env": "OPENAI_API_KEY=super-secret\n"},
        )


def make_orchestrator(tmp_path: Path) -> Orchestrator:
    adapters = AdapterRegistry()
    adapters.register(AgentKind.CODEX, MockAdapter())
    adapters.register(AgentKind.CLAUDE, MockAdapter())
    adapters.register(AgentKind.KIMI, MockAdapter())
    return Orchestrator(store=RunStore(tmp_path / "runs"), adapters=adapters, runners=RunnerRegistry())


@pytest.mark.asyncio
async def test_orchestrator_runs_parallel_and_templates_outputs(tmp_path: Path):
    orchestrator = make_orchestrator(tmp_path)
    pipeline = PipelineSpec.model_validate(
        {
            "name": "parallel",
            "working_dir": str(tmp_path),
            "concurrency": 2,
            "nodes": [
                {"id": "alpha", "agent": "codex", "prompt": "alpha"},
                {"id": "beta", "agent": "claude", "prompt": "beta"},
                {
                    "id": "gamma",
                    "agent": "kimi",
                    "depends_on": ["alpha", "beta"],
                    "prompt": "merge {{ nodes.alpha.output }} + {{ nodes.beta.output }}",
                },
            ],
        }
    )
    started = asyncio.get_running_loop().time()
    run = await orchestrator.submit(pipeline)
    completed = await orchestrator.wait(run.id, timeout=5)
    elapsed = asyncio.get_running_loop().time() - started

    alpha = completed.nodes["alpha"]
    beta = completed.nodes["beta"]
    gamma = completed.nodes["gamma"]
    assert completed.status.value == "completed"
    assert alpha.output == "alpha"
    assert beta.output == "beta"
    assert "alpha" in gamma.output
    assert "beta" in gamma.output
    alpha_start = datetime.fromisoformat(alpha.started_at)
    beta_start = datetime.fromisoformat(beta.started_at)
    assert abs((alpha_start - beta_start).total_seconds()) < 0.15
    assert elapsed < 1.0


@pytest.mark.asyncio
async def test_orchestrator_applies_success_criteria(tmp_path: Path):
    orchestrator = make_orchestrator(tmp_path)
    pipeline = PipelineSpec.model_validate(
        {
            "name": "writer",
            "working_dir": str(tmp_path),
            "nodes": [
                {
                    "id": "writer",
                    "agent": "codex",
                    "prompt": "success",
                    "success_criteria": [
                        {"kind": "file_exists", "path": "artifact.txt"},
                        {"kind": "file_contains", "path": "artifact.txt", "value": "file data"},
                    ],
                }
            ],
        }
    )
    run = await orchestrator.submit(pipeline)
    completed = await orchestrator.wait(run.id, timeout=5)
    assert completed.nodes["writer"].status.value == "completed"
    assert (tmp_path / "artifact.txt").read_text(encoding="utf-8") == "file data"


@pytest.mark.asyncio
async def test_orchestrator_applies_file_success_criteria_in_local_target_cwd(tmp_path: Path):
    orchestrator = make_orchestrator(tmp_path)
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    pipeline = PipelineSpec.model_validate(
        {
            "name": "writer-target-cwd",
            "working_dir": str(tmp_path),
            "nodes": [
                {
                    "id": "writer",
                    "agent": "codex",
                    "prompt": "success",
                    "target": {"kind": "local", "cwd": str(task_dir)},
                    "success_criteria": [
                        {"kind": "file_exists", "path": "artifact.txt"},
                        {"kind": "file_contains", "path": "artifact.txt", "value": "file data"},
                    ],
                }
            ],
        }
    )

    run = await orchestrator.submit(pipeline)
    completed = await orchestrator.wait(run.id, timeout=5)

    assert completed.nodes["writer"].status.value == "completed"
    assert (task_dir / "artifact.txt").read_text(encoding="utf-8") == "file data"


@pytest.mark.asyncio
async def test_orchestrator_resolves_relative_local_target_cwd_from_pipeline_workdir(tmp_path: Path):
    orchestrator = make_orchestrator(tmp_path)
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    pipeline = PipelineSpec.model_validate(
        {
            "name": "writer-relative-target-cwd",
            "working_dir": str(tmp_path),
            "nodes": [
                {
                    "id": "writer",
                    "agent": "codex",
                    "prompt": "success",
                    "target": {"kind": "local", "cwd": "task"},
                    "success_criteria": [
                        {"kind": "file_exists", "path": "artifact.txt"},
                    ],
                }
            ],
        }
    )

    run = await orchestrator.submit(pipeline)
    completed = await orchestrator.wait(run.id, timeout=5)

    assert completed.nodes["writer"].status.value == "completed"
    assert (task_dir / "artifact.txt").read_text(encoding="utf-8") == "file data"


@pytest.mark.asyncio
async def test_orchestrator_retries_failed_nodes(tmp_path: Path):
    orchestrator = make_orchestrator(tmp_path)
    pipeline = PipelineSpec.model_validate(
        {
            "name": "retry",
            "working_dir": str(tmp_path),
            "nodes": [
                {
                    "id": "flaky",
                    "agent": "codex",
                    "prompt": "recovered",
                    "retries": 1,
                    "retry_backoff_seconds": 0.01,
                }
            ],
        }
    )
    run = await orchestrator.submit(pipeline)
    completed = await orchestrator.wait(run.id, timeout=5)
    node = completed.nodes["flaky"]
    assert completed.status.value == "completed"
    assert node.status.value == "completed"
    assert node.current_attempt == 2
    assert len(node.attempts) == 2
    assert node.attempts[0].status.value == "failed"
    assert node.attempts[1].status.value == "completed"
    assert orchestrator.store.read_artifact_text(completed.id, "flaky", "output.txt") == "recovered"


@pytest.mark.asyncio
async def test_orchestrator_retry_isolates_final_capture_from_failed_attempt_stdout(tmp_path: Path):
    orchestrator = make_orchestrator(tmp_path)
    pipeline = PipelineSpec.model_validate(
        {
            "name": "retry-silent-success",
            "working_dir": str(tmp_path),
            "nodes": [
                {
                    "id": "flaky_silent",
                    "agent": "codex",
                    "prompt": "unused",
                    "retries": 1,
                    "retry_backoff_seconds": 0.01,
                }
            ],
        }
    )

    run = await orchestrator.submit(pipeline)
    completed = await orchestrator.wait(run.id, timeout=5)
    node = completed.nodes["flaky_silent"]

    assert completed.status.value == "completed"
    assert node.status.value == "completed"
    assert node.final_response == ""
    assert node.output == ""
    assert node.stdout_lines == []
    assert node.attempts[0].output == "stale stdout from failed attempt"
    assert node.attempts[1].output == ""
    assert orchestrator.store.read_artifact_text(completed.id, "flaky_silent", "output.txt") == ""


@pytest.mark.asyncio
async def test_orchestrator_cancels_running_nodes(tmp_path: Path):
    orchestrator = make_orchestrator(tmp_path)
    pipeline = PipelineSpec.model_validate(
        {
            "name": "cancel",
            "working_dir": str(tmp_path),
            "nodes": [
                {
                    "id": "slow",
                    "agent": "codex",
                    "prompt": "eventually cancelled",
                    "timeout_seconds": 30,
                }
            ],
        }
    )
    run = await orchestrator.submit(pipeline)
    for _ in range(50):
        snapshot = orchestrator.store.get_run(run.id)
        if snapshot.status.value == "running":
            break
        await asyncio.sleep(0.05)
    await orchestrator.cancel(run.id)
    completed = await orchestrator.wait(run.id, timeout=5)
    assert completed.status.value == "cancelled"
    assert completed.nodes["slow"].status.value == "cancelled"
    assert "Cancelled by user" in orchestrator.store.read_artifact_text(completed.id, "slow", "stderr.log")


@pytest.mark.asyncio
async def test_orchestrator_persists_cancel_stderr_before_first_attempt(tmp_path: Path, monkeypatch):
    original_publish = Orchestrator._publish
    node_started = asyncio.Event()
    release_node = asyncio.Event()

    async def gated_publish(self, run_id: str, event_type: str, *, node_id: str | None = None, **data):
        await original_publish(self, run_id, event_type, node_id=node_id, **data)
        if event_type == "node_started" and node_id == "slow":
            node_started.set()
            await release_node.wait()

    monkeypatch.setattr(Orchestrator, "_publish", gated_publish)

    orchestrator = make_orchestrator(tmp_path)
    pipeline = PipelineSpec.model_validate(
        {
            "name": "cancel-before-attempt",
            "working_dir": str(tmp_path),
            "nodes": [
                {
                    "id": "slow",
                    "agent": "codex",
                    "prompt": "cancel before attempt",
                    "timeout_seconds": 30,
                }
            ],
        }
    )

    run = await orchestrator.submit(pipeline)
    await asyncio.wait_for(node_started.wait(), timeout=5)
    await orchestrator.cancel(run.id)
    release_node.set()

    completed = await orchestrator.wait(run.id, timeout=5)

    assert completed.status.value == "cancelled"
    assert completed.nodes["slow"].status.value == "cancelled"
    assert "Cancelled by user" in orchestrator.store.read_artifact_text(completed.id, "slow", "stderr.log")


@pytest.mark.asyncio
async def test_orchestrator_writes_redacted_launch_artifact(tmp_path: Path):
    adapters = AdapterRegistry()
    adapters.register(AgentKind.CODEX, LaunchPlanAdapter())
    orchestrator = Orchestrator(store=RunStore(tmp_path / "runs"), adapters=adapters, runners=RunnerRegistry())
    pipeline = PipelineSpec.model_validate(
        {
            "name": "launch-artifact",
            "working_dir": str(tmp_path),
            "nodes": [
                {
                    "id": "alpha",
                    "agent": "codex",
                    "prompt": "launch",
                    "target": {"kind": "local", "shell": "bash"},
                }
            ],
        }
    )

    run = await orchestrator.submit(pipeline)
    completed = await orchestrator.wait(run.id, timeout=5)

    assert completed.status.value == "completed"
    launch_artifact = json.loads(orchestrator.store.read_artifact_text(completed.id, "alpha", "launch.json"))
    assert launch_artifact == {
        "attempt": 1,
        "kind": "process",
        "command": ["bash", "-c", "python3 -c 'print(\"launch plan ok\")'"],
        "env": {
            "ANTHROPIC_CUSTOM_HEADERS": "<redacted>",
            "OPENAI_API_KEY": "<redacted>",
            "UPSTREAM_AUTH_HEADER": "<redacted>",
            "VISIBLE_FLAG": "visible",
        },
        "cwd": str(tmp_path),
        "stdin": None,
        "runtime_files": ["config/runtime.env"],
        "payload": None,
    }


@pytest.mark.asyncio
async def test_orchestrator_redacts_inline_shell_bootstrap_secrets_in_launch_artifact(tmp_path: Path):
    adapters = AdapterRegistry()
    adapters.register(AgentKind.CODEX, LaunchPlanAdapter())
    orchestrator = Orchestrator(store=RunStore(tmp_path / "runs"), adapters=adapters, runners=RunnerRegistry())
    pipeline = PipelineSpec.model_validate(
        {
            "name": "launch-artifact-shell-secret",
            "working_dir": str(tmp_path),
            "nodes": [
                {
                    "id": "alpha",
                    "agent": "codex",
                    "prompt": "launch",
                    "target": {
                        "kind": "local",
                        "shell": "bash",
                        "shell_init": ["export ANTHROPIC_API_KEY=super-secret-inline"],
                    },
                }
            ],
        }
    )

    run = await orchestrator.submit(pipeline)
    completed = await orchestrator.wait(run.id, timeout=5)

    assert completed.status.value == "completed"
    launch_artifact = json.loads(orchestrator.store.read_artifact_text(completed.id, "alpha", "launch.json"))
    assert launch_artifact["command"] == [
        "bash",
        "-c",
        'export ANTHROPIC_API_KEY=<redacted> && eval "$AGENTFLOW_TARGET_COMMAND"',
    ]
