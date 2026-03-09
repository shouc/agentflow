from __future__ import annotations

from pathlib import Path
from typing import Any

from agentflow.skills import compile_skill_prelude
from agentflow.specs import NodeResult, NodeSpec, PipelineSpec
from agentflow.utils import render_template


def build_render_context(pipeline: PipelineSpec, results: dict[str, NodeResult]) -> dict[str, Any]:
    nodes: dict[str, Any] = {}
    for node_id, result in results.items():
        nodes[node_id] = {
            "status": result.status.value,
            "output": result.output,
            "final_response": result.final_response,
            "stdout": "\n".join(result.stdout_lines),
            "stderr": "\n".join(result.stderr_lines),
            "trace": [event.model_dump(mode="json") for event in result.trace_events],
        }
    return {"pipeline": pipeline.model_dump(mode="json"), "nodes": nodes}


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
