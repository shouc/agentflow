from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BundledTemplate:
    name: str
    example_name: str
    description: str


_BUNDLED_TEMPLATES = (
    BundledTemplate(
        name="pipeline",
        example_name="pipeline.yaml",
        description="Generic Codex/Claude/Kimi starter DAG.",
    ),
    BundledTemplate(
        name="codex-fanout-repo-sweep",
        example_name="codex-fanout-repo-sweep.yaml",
        description="Codex repo sweep that fans out one plan into 8 review shards and a final merge.",
    ),
    BundledTemplate(
        name="local-kimi-smoke",
        example_name="local-real-agents-kimi-smoke.yaml",
        description="Local Codex plus Claude-on-Kimi smoke DAG using `bootstrap: kimi`.",
    ),
    BundledTemplate(
        name="local-kimi-shell-init-smoke",
        example_name="local-real-agents-kimi-shell-init-smoke.yaml",
        description="Local Codex plus Claude-on-Kimi smoke DAG using explicit `shell_init: kimi`.",
    ),
    BundledTemplate(
        name="local-kimi-shell-wrapper-smoke",
        example_name="local-real-agents-kimi-shell-wrapper-smoke.yaml",
        description="Local Codex plus Claude-on-Kimi smoke DAG using an explicit `target.shell` Kimi wrapper.",
    ),
)

_BUNDLED_TEMPLATE_FILES = {template.name: template.example_name for template in _BUNDLED_TEMPLATES}

DEFAULT_PIPELINE_YAML = """name: parallel-code-orchestration
description: Codex plans, Claude implements, and Kimi reviews in parallel before a final Codex merge.
working_dir: .
concurrency: 3
nodes:
  - id: plan
    agent: codex
    model: gpt-5-codex
    tools: read_only
    capture: final
    retries: 1
    retry_backoff_seconds: 1
    prompt: |
      Inspect the repository and create a short implementation plan.

  - id: implement
    agent: claude
    model: claude-sonnet-4-5
    tools: read_write
    capture: final
    depends_on: [plan]
    prompt: |
      Use the plan below and implement the requested change.

      Plan:
      {{ nodes.plan.output }}

  - id: review
    agent: kimi
    model: kimi-k2-turbo-preview
    tools: read_only
    capture: trace
    depends_on: [plan]
    prompt: |
      Review the proposed implementation plan.

      Plan:
      {{ nodes.plan.output }}

  - id: merge
    agent: codex
    model: gpt-5-codex
    tools: read_only
    depends_on: [implement, review]
    success_criteria:
      - kind: output_contains
        value: success
    prompt: |
      Combine these two perspectives into a final release summary and include the word success.

      Implementation output:
      {{ nodes.implement.output }}

      Review trace:
      {{ nodes.review.output }}
"""


def load_default_pipeline_yaml() -> str:
    example_path = bundled_example_path("pipeline.yaml")
    if example_path.exists():
        return example_path.read_text(encoding="utf-8")
    return DEFAULT_PIPELINE_YAML


def bundled_example_path(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "examples" / name


def bundled_templates() -> tuple[BundledTemplate, ...]:
    return _BUNDLED_TEMPLATES


def bundled_template_names() -> tuple[str, ...]:
    return tuple(template.name for template in bundled_templates())


def bundled_template_path(name: str) -> Path:
    try:
        example_name = _BUNDLED_TEMPLATE_FILES[name]
    except KeyError as exc:
        available = ", ".join(f"`{template}`" for template in bundled_template_names())
        raise ValueError(
            f"unknown bundled template `{name}` (available: {available}; see `agentflow templates`)"
        ) from exc
    return bundled_example_path(example_name)


def load_bundled_template_yaml(name: str) -> str:
    if name == "pipeline":
        return load_default_pipeline_yaml()

    template_path = bundled_template_path(name)
    return template_path.read_text(encoding="utf-8")


def default_smoke_pipeline_path() -> str:
    return str(bundled_example_path("local-real-agents-kimi-smoke.yaml"))
