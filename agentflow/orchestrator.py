from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentflow.agents.registry import AdapterRegistry, default_adapter_registry
from agentflow.context import render_node_prompt
from agentflow.prepared import ExecutionPaths, build_execution_paths
from agentflow.runners.registry import RunnerRegistry, default_runner_registry
from agentflow.specs import NodeAttempt, NodeResult, NodeStatus, PipelineSpec, RunEvent, RunRecord, RunStatus
from agentflow.store import RunStore
from agentflow.success import evaluate_success
from agentflow.traces import create_trace_parser
from agentflow.utils import utcnow_iso


@dataclass(slots=True)
class Orchestrator:
    store: RunStore
    adapters: AdapterRegistry = default_adapter_registry
    runners: RunnerRegistry = default_runner_registry
    max_concurrent_runs: int = 2
    _run_slots: threading.Semaphore = field(init=False, repr=False)
    _cancel_flags: dict[str, threading.Event] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self._run_slots = threading.Semaphore(self.max_concurrent_runs)

    async def submit(self, pipeline: PipelineSpec) -> RunRecord:
        run_id = self.store.new_run_id()
        run = RunRecord(
            id=run_id,
            status=RunStatus.QUEUED,
            pipeline=pipeline,
            nodes={node.id: NodeResult(node_id=node.id, status=NodeStatus.PENDING) for node in pipeline.nodes},
        )
        self._cancel_flags[run_id] = threading.Event()
        await self.store.create_run(run)
        await self._publish(run_id, "run_queued", pipeline=pipeline.model_dump(mode="json"))

        def _background() -> None:
            acquired = False
            while not acquired:
                if self._should_cancel(run_id):
                    asyncio.run(self._finalize_cancelled_queue_run(run_id))
                    return
                acquired = self._run_slots.acquire(timeout=0.1)
            try:
                asyncio.run(self.run(run_id))
            finally:
                self._run_slots.release()

        threading.Thread(target=_background, name=f"agentflow-{run_id}", daemon=True).start()
        return run

    async def wait(self, run_id: str, timeout: float | None = None) -> RunRecord:
        terminal = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}

        async def _poll() -> RunRecord:
            while True:
                record = self.store.get_run(run_id)
                if record.status in terminal:
                    return record
                await asyncio.sleep(0.05)

        if timeout is None:
            return await _poll()
        return await asyncio.wait_for(_poll(), timeout=timeout)

    async def cancel(self, run_id: str) -> RunRecord:
        record = self.store.get_run(run_id)
        flag = self._cancel_flags.setdefault(run_id, threading.Event())
        flag.set()
        if record.status == RunStatus.QUEUED:
            await self._finalize_cancelled_queue_run(run_id)
            return self.store.get_run(run_id)
        if record.status in {RunStatus.RUNNING, RunStatus.PENDING}:
            record.status = RunStatus.CANCELLING
            await self._publish(run_id, "run_cancelling")
            await self.store.persist_run(run_id)
        return record

    async def rerun(self, run_id: str) -> RunRecord:
        record = self.store.get_run(run_id)
        return await self.submit(record.pipeline)

    def _should_cancel(self, run_id: str) -> bool:
        return self._cancel_flags.get(run_id, threading.Event()).is_set()

    async def _finalize_cancelled_queue_run(self, run_id: str) -> None:
        record = self.store.get_run(run_id)
        record.status = RunStatus.CANCELLED
        record.finished_at = utcnow_iso()
        for node in record.nodes.values():
            if node.status in {NodeStatus.PENDING, NodeStatus.QUEUED, NodeStatus.READY}:
                node.status = NodeStatus.CANCELLED
                node.finished_at = record.finished_at
        await self._publish(run_id, "run_completed", status=record.status.value)
        await self.store.persist_run(run_id)

    def _build_paths(self, pipeline: PipelineSpec, run_id: str, node_id: str, node_target: Any) -> ExecutionPaths:
        return build_execution_paths(
            base_dir=self.store.base_dir,
            pipeline_workdir=pipeline.working_path,
            run_id=run_id,
            node_id=node_id,
            node_target=node_target,
        )

    async def _publish(self, run_id: str, event_type: str, *, node_id: str | None = None, **data: Any) -> None:
        await self.store.append_event(run_id, RunEvent(run_id=run_id, type=event_type, node_id=node_id, data=data))

    async def _publish_trace(self, run_id: str, node_id: str, event) -> None:
        await self.store.append_artifact_text(run_id, node_id, "trace.jsonl", event.model_dump_json() + "\n")
        await self._publish(run_id, "node_trace", node_id=node_id, trace=event.model_dump(mode="json"))

    async def _mark_node_cancelled(self, run_id: str, node_id: str, reason: str) -> None:
        record = self.store.get_run(run_id)
        result = record.nodes[node_id]
        result.status = NodeStatus.CANCELLED
        result.finished_at = utcnow_iso()
        await self._publish(run_id, "node_cancelled", node_id=node_id, reason=reason)

    async def _execute_node(self, run_id: str, node_id: str) -> None:
        record = self.store.get_run(run_id)
        pipeline = record.pipeline
        node = pipeline.node_map[node_id]
        result = record.nodes[node_id]
        result.started_at = result.started_at or utcnow_iso()
        result.status = NodeStatus.RUNNING
        await self._publish(run_id, "node_started", node_id=node_id)

        prompt = render_node_prompt(pipeline, node, record.nodes)
        paths = self._build_paths(pipeline, run_id, node_id, node.target)
        adapter = self.adapters.get(node.agent)
        runner = self.runners.get(node.target.kind)
        parser = create_trace_parser(node.agent, node.id)

        for attempt_number in range(1, node.retries + 2):
            if self._should_cancel(run_id):
                await self._mark_node_cancelled(run_id, node_id, "run_cancelled")
                return

            attempt = NodeAttempt(number=attempt_number, status=NodeStatus.RUNNING, started_at=utcnow_iso())
            result.current_attempt = attempt_number
            result.attempts.append(attempt)
            parser.start_attempt(attempt_number)
            prepared = adapter.prepare(node, prompt, paths)
            await self.store.append_artifact_text(
                run_id,
                node_id,
                "stdout.log",
                f"\n=== attempt {attempt_number} started {attempt.started_at} ===\n",
            )
            await self.store.append_artifact_text(
                run_id,
                node_id,
                "stderr.log",
                f"\n=== attempt {attempt_number} started {attempt.started_at} ===\n",
            )
            if attempt_number > 1:
                result.status = NodeStatus.RETRYING
                await self._publish(
                    run_id,
                    "node_retrying",
                    node_id=node_id,
                    attempt=attempt_number,
                    max_attempts=node.retries + 1,
                )
                result.status = NodeStatus.RUNNING

            async def on_output(stream_name: str, line: str) -> None:
                if stream_name == "stdout":
                    result.stdout_lines.append(line)
                    await self.store.append_artifact_text(run_id, node_id, "stdout.log", line + "\n")
                    for event in parser.feed(line):
                        result.trace_events.append(event)
                        await self._publish_trace(run_id, node_id, event)
                else:
                    result.stderr_lines.append(line)
                    await self.store.append_artifact_text(run_id, node_id, "stderr.log", line + "\n")
                    event = parser.emit("stderr", "stderr", line, line, source="stderr")
                    result.trace_events.append(event)
                    await self._publish_trace(run_id, node_id, event)

            raw = await runner.execute(node, prepared, paths, on_output, lambda: self._should_cancel(run_id))
            result.exit_code = raw.exit_code
            result.final_response = parser.finalize() or "\n".join(result.stdout_lines).strip()
            result.output = result.final_response if node.capture.value == "final" else "\n".join(result.stdout_lines)
            success_ok, success_details = evaluate_success(node, result, paths.host_workdir)
            result.success = success_ok
            result.success_details = success_details
            attempt.finished_at = utcnow_iso()
            attempt.exit_code = raw.exit_code
            attempt.final_response = result.final_response
            attempt.output = result.output
            attempt.success = success_ok
            attempt.success_details = success_details

            if raw.cancelled or self._should_cancel(run_id):
                attempt.status = NodeStatus.CANCELLED
                result.status = NodeStatus.CANCELLED
                result.finished_at = attempt.finished_at
                await self._publish(
                    run_id,
                    "node_cancelled",
                    node_id=node_id,
                    attempt=attempt_number,
                    exit_code=raw.exit_code,
                )
                break

            if raw.exit_code == 0 and success_ok:
                attempt.status = NodeStatus.COMPLETED
                result.status = NodeStatus.COMPLETED
                result.finished_at = attempt.finished_at
                await self._publish(
                    run_id,
                    "node_completed",
                    node_id=node_id,
                    attempt=attempt_number,
                    exit_code=result.exit_code,
                    success=result.success,
                    output=result.output,
                    final_response=result.final_response,
                    success_details=result.success_details,
                )
                break

            attempt.status = NodeStatus.FAILED
            result.status = NodeStatus.FAILED
            result.finished_at = attempt.finished_at
            await self._publish(
                run_id,
                "node_failed",
                node_id=node_id,
                attempt=attempt_number,
                exit_code=result.exit_code,
                success=result.success,
                output=result.output,
                final_response=result.final_response,
                success_details=result.success_details,
            )
            if attempt_number <= node.retries:
                await asyncio.sleep(max(node.retry_backoff_seconds, 0.0) * attempt_number)
                continue
            break

        await self.store.write_artifact_text(run_id, node_id, "output.txt", result.output or "")
        await self.store.write_artifact_json(run_id, node_id, "result.json", result.model_dump(mode="json"))
        await self.store.persist_run(run_id)

    async def run(self, run_id: str) -> RunRecord:
        record = self.store.get_run(run_id)
        pipeline = record.pipeline
        record.status = RunStatus.RUNNING
        record.started_at = utcnow_iso()
        await self._publish(run_id, "run_started", pipeline=pipeline.model_dump(mode="json"))
        await self.store.persist_run(run_id)

        node_map = pipeline.node_map
        remaining = set(node_map)
        in_progress: dict[str, asyncio.Task[None]] = {}
        semaphore = asyncio.Semaphore(pipeline.concurrency)

        async def launch(node_id: str) -> None:
            async with semaphore:
                await self._execute_node(run_id, node_id)

        while remaining or in_progress:
            if self._should_cancel(run_id):
                for node_id in list(remaining):
                    await self._mark_node_cancelled(run_id, node_id, "run_cancelled")
                    remaining.remove(node_id)
                if not in_progress:
                    break

            failed_nodes = {node_id for node_id, node in record.nodes.items() if node.status == NodeStatus.FAILED}
            if pipeline.fail_fast and failed_nodes:
                for node_id in list(remaining):
                    record.nodes[node_id].status = NodeStatus.SKIPPED
                    record.nodes[node_id].finished_at = utcnow_iso()
                    remaining.remove(node_id)
                    await self._publish(run_id, "node_skipped", node_id=node_id, reason="fail_fast")

            ready = [
                node_id
                for node_id in list(remaining)
                if all(record.nodes[dependency].status == NodeStatus.COMPLETED for dependency in node_map[node_id].depends_on)
            ]
            blocked = [
                node_id
                for node_id in list(remaining)
                if any(record.nodes[dependency].status in {NodeStatus.FAILED, NodeStatus.SKIPPED, NodeStatus.CANCELLED} for dependency in node_map[node_id].depends_on)
            ]
            for node_id in blocked:
                record.nodes[node_id].status = NodeStatus.SKIPPED
                record.nodes[node_id].finished_at = utcnow_iso()
                remaining.remove(node_id)
                await self._publish(run_id, "node_skipped", node_id=node_id, reason="upstream_failure")
            for node_id in ready:
                if node_id not in in_progress:
                    remaining.remove(node_id)
                    record.nodes[node_id].status = NodeStatus.QUEUED
                    in_progress[node_id] = asyncio.create_task(launch(node_id))
            if in_progress:
                done, _ = await asyncio.wait(in_progress.values(), timeout=0.1, return_when=asyncio.FIRST_COMPLETED)
                finished_ids = [node_id for node_id, task in in_progress.items() if task in done]
                for node_id in finished_ids:
                    task = in_progress.pop(node_id)
                    await task
            elif remaining:
                await asyncio.sleep(0.05)
            else:
                break

        if record.status == RunStatus.CANCELLING or self._should_cancel(run_id):
            record.status = RunStatus.CANCELLED
        elif any(node.status == NodeStatus.FAILED for node in record.nodes.values()):
            record.status = RunStatus.FAILED
        else:
            record.status = RunStatus.COMPLETED
        record.finished_at = utcnow_iso()
        await self._publish(run_id, "run_completed", status=record.status.value)
        await self.store.persist_run(run_id)
        return record
