from __future__ import annotations

from pathlib import Path
from typing import Any

from agentflow.skills import compile_skill_prelude
from agentflow.specs import NodeResult, NodeSpec, PipelineSpec
from agentflow.utils import render_template


def _node_result_context(result: NodeResult) -> dict[str, Any]:
    return {
        "status": result.status.value,
        "output": result.output,
        "final_response": result.final_response,
        "stdout": "\n".join(result.stdout_lines),
        "stderr": "\n".join(result.stderr_lines),
        "trace": [event.model_dump(mode="json") for event in result.trace_events],
    }


def build_render_context(pipeline: PipelineSpec, results: dict[str, NodeResult]) -> dict[str, Any]:
    nodes: dict[str, Any] = {}
    for node_id, result in results.items():
        nodes[node_id] = _node_result_context(result)

    fanouts: dict[str, Any] = {}
    for group_id, member_ids in pipeline.fanouts.items():
        member_nodes: list[dict[str, Any]] = []
        for member_id in member_ids:
            result = results.get(member_id, NodeResult(node_id=member_id))
            member_context = {"id": member_id, **_node_result_context(result)}
            member_nodes.append(member_context)
        fanouts[group_id] = {
            "ids": list(member_ids),
            "size": len(member_ids),
            "nodes": member_nodes,
            "outputs": [member["output"] for member in member_nodes],
            "final_responses": [member["final_response"] for member in member_nodes],
            "statuses": [member["status"] for member in member_nodes],
        }
    return {"pipeline": pipeline.model_dump(mode="json"), "nodes": nodes, "fanouts": fanouts}


def render_node_prompt(
    pipeline: PipelineSpec,
    node: NodeSpec,
    results: dict[str, NodeResult],
) -> str:
    context = build_render_context(pipeline, results)
    prompt = render_template(node.prompt, context)
    skill_prelude = compile_skill_prelude(node.skills, pipeline.working_path)
    if skill_prelude:
        return f"Selected skills:\n{skill_prelude}\n\nTask:\n{prompt}"
    return prompt
