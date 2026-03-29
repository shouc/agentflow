from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Mapping


@dataclass(frozen=True)
class BundledTemplateParameter:
    name: str
    description: str
    default: str


@dataclass(frozen=True)
class BundledTemplate:
    name: str
    example_name: str
    description: str
    parameters: tuple[BundledTemplateParameter, ...] = ()
    support_files: tuple[str, ...] = ()


@dataclass(frozen=True)
class RenderedBundledTemplateFile:
    relative_path: str
    content: str


@dataclass(frozen=True)
class RenderedBundledTemplate:
    content: str
    support_files: tuple[RenderedBundledTemplateFile, ...] = ()


_DEFAULT_CODEX_REPO_SWEEP_BATCHED_SHARDS = 128
_DEFAULT_CODEX_REPO_SWEEP_BATCHED_BATCH_SIZE = 16
_DEFAULT_CODEX_REPO_SWEEP_BATCHED_CONCURRENCY = 32
_DEFAULT_CODEX_REPO_SWEEP_BATCHED_FOCUS = "bugs, risky code paths, and missing tests"


def _parse_positive_template_int(template_name: str, field_name: str, raw_value: str) -> int:
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"template `{template_name}` expects `{field_name}` to be an integer, got `{raw_value}`") from exc
    if value < 1:
        raise ValueError(f"template `{template_name}` expects `{field_name}` to be at least 1, got `{raw_value}`")
    return value


def _template_string_value(template_name: str, field_name: str, raw_value: str | None, *, default: str) -> str:
    value = (raw_value if raw_value is not None else default).strip()
    if not value:
        raise ValueError(f"template `{template_name}` expects `{field_name}` to be a non-empty string")
    return value


def _validate_template_settings(template_name: str, raw_values: Mapping[str, str], *, allowed: set[str]) -> None:
    unknown = sorted(set(raw_values) - allowed)
    if unknown:
        supported = ", ".join(f"`{name}`" for name in sorted(allowed))
        unknown_display = ", ".join(f"`{name}`" for name in unknown)
        raise ValueError(
            f"template `{template_name}` does not recognize {unknown_display}; supported settings: {supported}"
        )


def _render_codex_repo_sweep_batched_template(values: Mapping[str, str] | None = None) -> RenderedBundledTemplate:
    template_name = "codex-repo-sweep-batched"
    raw_values = dict(values or {})
    allowed = {"shards", "batch_size", "concurrency", "focus", "name", "working_dir"}
    _validate_template_settings(template_name, raw_values, allowed=allowed)

    shards = _parse_positive_template_int(
        template_name,
        "shards",
        raw_values.get("shards", str(_DEFAULT_CODEX_REPO_SWEEP_BATCHED_SHARDS)),
    )
    batch_size = _parse_positive_template_int(
        template_name,
        "batch_size",
        raw_values.get("batch_size", str(_DEFAULT_CODEX_REPO_SWEEP_BATCHED_BATCH_SIZE)),
    )
    concurrency = _parse_positive_template_int(
        template_name,
        "concurrency",
        raw_values.get("concurrency", str(_DEFAULT_CODEX_REPO_SWEEP_BATCHED_CONCURRENCY)),
    )
    focus = _template_string_value(
        template_name,
        "focus",
        raw_values.get("focus"),
        default=_DEFAULT_CODEX_REPO_SWEEP_BATCHED_FOCUS,
    )
    name = _template_string_value(
        template_name,
        "name",
        raw_values.get("name"),
        default=f"codex-repo-sweep-batched-{shards}",
    )
    working_dir = _template_string_value(
        template_name,
        "working_dir",
        raw_values.get("working_dir"),
        default=f"./codex_repo_sweep_batched_{shards}",
    )

    rendered = Template(
        '''# Configurable large-scale Codex repository sweep
#
# This scaffold fans out a large repo review into many Codex shards, then
# inserts batched reducers so a $shards-worker sweep still lands in a readable
# maintainer handoff.
#
# Usage:
#   agentflow init repo-sweep-batched.py --template codex-repo-sweep-batched
#   agentflow init repo-sweep-security.py --template codex-repo-sweep-batched --set shards=64 --set batch_size=8 --set concurrency=16 --set focus="security bugs, privilege boundaries, and missing coverage"
#   agentflow inspect repo-sweep-batched.py --output summary
#   agentflow run repo-sweep-batched.py

from agentflow import DAG, codex, fanout, merge

with DAG(
    "$name",
    description="Configurable $shards-shard Codex repository sweep with batched reducers for maintainer review.",
    working_dir="$working_dir",
    concurrency=$concurrency,
    node_defaults={
        "agent": "codex",
        "tools": "read_only",
        "capture": "final",
        "timeout_seconds": 900,
    },
    agent_defaults={
        "codex": {
            "model": "gpt-5-codex",
            "retries": 1,
            "retry_backoff_seconds": 1,
            "extra_args": ["--search", "-c", 'model_reasoning_effort="high"'],
        }
    },
) as dag:
    prepare = codex(
        task_id="prepare",
        prompt=(
            "Inspect the repository and write shared instructions for a $shards-shard Codex maintainer sweep.\\n"
            "\\n"
            "Review goal:\\n"
            "- Focus on $focus.\\n"
            "- Prefer concrete bugs, risky assumptions, or clearly missing tests over generic style feedback.\\n"
            "- Make the sweep reproducible by using a stable path-hash modulo strategy across $shards shards.\\n"
            "- Call out hot subsystems or directories that deserve extra attention.\\n"
            "- End with a compact rubric the reducers can use to rank findings by severity and confidence.\\n"
        ),
    )

    sweep = fanout(
        codex(
            task_id="sweep",
            prompt=(
                "You are Codex repository sweep shard {{ item.number }} of {{ item.count }}.\\n"
                "\\n"
                "Shared plan:\\n"
                "{{ nodes.prepare.output }}\\n"
                "\\n"
                "Your shard contract:\\n"
                "- Stable identity: {{ item.node_id }} (suffix {{ item.suffix }})\\n"
                "- Review files whose stable path hash modulo {{ item.count }} equals {{ item.index }}.\\n"
                "- Focus on $focus.\\n"
                "- Avoid duplicate work outside your modulo slice unless you need one small neighboring file for context.\\n"
                "- Report concrete findings first. Include file paths, the failure mode, and the missing validation or test if applicable.\\n"
                "- If your slice is quiet, report the most suspicious code paths worth a second pass.\\n"
            ),
        ),
        $shards,
        derive={"label": "slice {{ item.number }}/{{ item.count }}"},
    )

    batch_merge = merge(
        codex(
            task_id="batch_merge",
            prompt=(
                "Prepare the maintainer handoff for review batch {{ item.number }} of {{ item.count }}.\\n"
                "\\n"
                "Batch coverage:\\n"
                "- Source group: {{ item.source_group }}\\n"
                "- Total source shards: {{ item.source_count }}\\n"
                "- Batch size: {{ item.scope.size }}\\n"
                "- Shard range: {{ item.start_number }} through {{ item.end_number }}\\n"
                '- Shard ids: {{ item.scope.ids | join(", ") }}\\n'
                "- Completed shards: {{ item.scope.summary.completed }}\\n"
                "- Failed shards: {{ item.scope.summary.failed }}\\n"
                "- Silent shards: {{ item.scope.summary.without_output }}\\n"
            "\\n"
            "Rank the batch findings by severity, then confidence, then breadth of impact. "
            "If the batch is quiet, say so explicitly and point to the slices that should be rerun or retargeted.\\n"
            "\\n"
            "{% for shard in item.scope.with_output.nodes %}\\n"
            "## {{ shard.label }} :: {{ shard.node_id }} (status: {{ shard.status }})\\n"
            "{{ shard.output }}\\n"
            "\\n"
            "{% endfor %}"
            "{% if item.scope.failed.size %}\\n"
            "Failed slices:\\n"
            "{% for shard in item.scope.failed.nodes %}\\n"
            "- {{ shard.id }} :: {{ shard.label }}\\n"
            "{% endfor %}"
            "{% endif %}"
            "{% if not item.scope.with_output.size %}\\n"
            "No slice in this batch produced reducer-ready output. "
            "Say that explicitly and use the failed shard list to suggest retargeting.\\n"
            "{% endif %}"
            ),
        ),
        sweep,
        size=$batch_size,
    )

    final = codex(
        task_id="merge",
        prompt=(
            "Consolidate this $shards-shard repository sweep into a maintainer summary.\\n"
            "Start with the highest-risk findings, then repeated patterns across batches, "
            "and end with quiet or failed slices that need a follow-up pass.\\n"
            "\\n"
            "Campaign status:\\n"
            "- Total review shards: {{ fanouts.sweep.size }}\\n"
            "- Completed shards: {{ fanouts.sweep.summary.completed }}\\n"
            "- Failed shards: {{ fanouts.sweep.summary.failed }}\\n"
            "- Silent shards: {{ fanouts.sweep.summary.without_output }}\\n"
            "- Batch reducers completed: {{ fanouts.batch_merge.summary.completed }} / {{ fanouts.batch_merge.size }}\\n"
            "\\n"
            "{% for batch in fanouts.batch_merge.with_output.nodes %}\\n"
            "## Batch {{ batch.number }} :: shards {{ batch.start_number }}-{{ batch.end_number }} (status: {{ batch.status }})\\n"
            "{{ batch.output }}\\n"
            "\\n"
            "{% endfor %}"
            "{% if fanouts.batch_merge.without_output.size %}\\n"
            "Batch reducers needing attention:\\n"
            "{% for batch in fanouts.batch_merge.without_output.nodes %}\\n"
            "- {{ batch.id }} :: shards {{ batch.start_number }}-{{ batch.end_number }} (status: {{ batch.status }})\\n"
            "{% endfor %}"
            "{% endif %}"
        ),
    )

    prepare >> sweep
    sweep >> batch_merge
    batch_merge >> final

print(dag.to_json())
'''
    ).substitute(
        name=name,
        shards=shards,
        batch_size=batch_size,
        concurrency=concurrency,
        working_dir=working_dir,
        focus=focus,
    )
    return RenderedBundledTemplate(content=rendered)


_BUNDLED_TEMPLATES = (
    BundledTemplate(
        name="pipeline",
        example_name="airflow_like.py",
        description="Generic Codex/Claude/Kimi starter DAG.",
    ),
    BundledTemplate(
        name="codex-repo-sweep-batched",
        example_name="airflow_like_fuzz_batched.py",
        description="Configurable large-scale Codex repo sweep that uses `fanout` and `merge` to keep 128-shard maintainer reviews readable.",
        parameters=(
            BundledTemplateParameter(
                name="shards",
                description="Number of Codex review workers to fan out.",
                default=str(_DEFAULT_CODEX_REPO_SWEEP_BATCHED_SHARDS),
            ),
            BundledTemplateParameter(
                name="batch_size",
                description="Number of review shards each intermediate reducer should own.",
                default=str(_DEFAULT_CODEX_REPO_SWEEP_BATCHED_BATCH_SIZE),
            ),
            BundledTemplateParameter(
                name="concurrency",
                description="Maximum number of review shards to run in parallel.",
                default=str(_DEFAULT_CODEX_REPO_SWEEP_BATCHED_CONCURRENCY),
            ),
            BundledTemplateParameter(
                name="focus",
                description="Shared review focus for the batched maintainer sweep.",
                default=_DEFAULT_CODEX_REPO_SWEEP_BATCHED_FOCUS,
            ),
            BundledTemplateParameter(
                name="name",
                description="Pipeline name override.",
                default="codex-repo-sweep-batched-<shards>",
            ),
            BundledTemplateParameter(
                name="working_dir",
                description="Pipeline working directory override.",
                default="./codex_repo_sweep_batched_<shards>",
            ),
        ),
    ),
    BundledTemplate(
        name="local-kimi-smoke",
        example_name="local-real-agents-kimi-smoke.py",
        description="Local Codex plus Claude-on-Kimi smoke DAG using `bootstrap: kimi`.",
    ),
    BundledTemplate(
        name="local-kimi-shell-init-smoke",
        example_name="local-real-agents-kimi-shell-init-smoke.py",
        description="Local Codex plus Claude-on-Kimi smoke DAG using explicit `shell_init: kimi`.",
    ),
    BundledTemplate(
        name="local-kimi-shell-wrapper-smoke",
        example_name="local-real-agents-kimi-shell-wrapper-smoke.py",
        description="Local Codex plus Claude-on-Kimi smoke DAG using an explicit `target.shell` Kimi wrapper.",
    ),
)

_BUNDLED_TEMPLATE_FILES = {template.name: template.example_name for template in _BUNDLED_TEMPLATES}
_BUNDLED_TEMPLATE_SUPPORT_FILES = {template.name: template.support_files for template in _BUNDLED_TEMPLATES}
_BUNDLED_TEMPLATE_RENDERERS = {
    "codex-repo-sweep-batched": _render_codex_repo_sweep_batched_template,
}


def load_default_pipeline() -> str:
    example_path = bundled_example_path("airflow_like.py")
    if example_path.exists():
        return example_path.read_text(encoding="utf-8")
    raise FileNotFoundError("default pipeline example not found")


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


def bundled_template_support_files(name: str) -> tuple[str, ...]:
    try:
        return _BUNDLED_TEMPLATE_SUPPORT_FILES[name]
    except KeyError as exc:
        available = ", ".join(f"`{template}`" for template in bundled_template_names())
        raise ValueError(
            f"unknown bundled template `{name}` (available: {available}; see `agentflow templates`)"
        ) from exc


def render_bundled_template(name: str, values: Mapping[str, str] | None = None) -> RenderedBundledTemplate:
    template_values = dict(values or {})

    renderer = _BUNDLED_TEMPLATE_RENDERERS.get(name)
    if renderer is not None:
        return renderer(template_values)

    template_path = bundled_template_path(name)
    if template_values:
        raise ValueError(f"template `{name}` does not accept `--set` values")

    rendered_support_files = tuple(
        RenderedBundledTemplateFile(
            relative_path=relative_path,
            content=(template_path.parent / relative_path).resolve().read_text(encoding="utf-8"),
        )
        for relative_path in bundled_template_support_files(name)
    )
    return RenderedBundledTemplate(
        content=template_path.read_text(encoding="utf-8"),
        support_files=rendered_support_files,
    )


def load_bundled_template(name: str, values: Mapping[str, str] | None = None) -> str:
    return render_bundled_template(name, values=values).content


def default_smoke_pipeline_path() -> str:
    return str(bundled_example_path("local-real-agents-kimi-smoke.py"))
