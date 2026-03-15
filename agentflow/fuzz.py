from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import re
from typing import Any, Literal, Mapping

from agentflow.defaults import default_fuzz_campaign_preset_name
from agentflow.dsl import NodeBuilder, codex, fanout_batches, fanout_group_by, fanout_matrix
from agentflow.fuzz_presets import build_codex_fuzz_campaign_matrix_payload, codex_fuzz_campaign_preset_names

_DEFAULT_BUCKET_COUNT = 4
_DEFAULT_BATCH_SIZE = 16
_DEFAULT_SEED_START = 4101
_DEFAULT_SEED_LABEL_PREFIX = "seed_"
_DEFAULT_SEED_LABEL_WIDTH = 3
_DEFAULT_LABEL_TEMPLATE = "{{ shard.target }} / {{ shard.sanitizer }} / {{ shard.focus }} / {{ shard.bucket }}"
_DEFAULT_WORKSPACE_TEMPLATE = "agents/{{ shard.target }}_{{ shard.sanitizer }}_{{ shard.bucket }}_{{ shard.suffix }}"
_DEFAULT_CAMPAIGN_LAYOUT = "batched"
_DEFAULT_CODEX_MODEL = "gpt-5-codex"
_DEFAULT_CRASH_REGISTRY_PATH = "crashes/README.md"
_DEFAULT_NOTES_PATH = "docs/campaign_notes.md"
_DEFAULT_INIT_SUCCESS_TOKEN = "INIT_OK"
_DEFAULT_CODEX_SEARCH_ARGS = [
    "--search",
    "-c",
    'model_reasoning_effort="high"',
]
_GROUPED_REDUCER_FIELDS = ("target", "corpus")
_TASK_PREFIX_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

CodexFuzzCampaignLayout = Literal["flat", "batched", "grouped"]


@dataclass(frozen=True)
class CodexFuzzCampaignNodes:
    """The nodes registered by `codex_fuzz_campaign()` inside the active DAG."""

    init: NodeBuilder
    fuzzer: NodeBuilder
    merge: NodeBuilder
    reducer: NodeBuilder | None = None


def codex_fuzz_campaign_matrix(
    *,
    preset: str | None = None,
    bucket_count: int = _DEFAULT_BUCKET_COUNT,
    as_: str = "shard",
    label_template: str | None = _DEFAULT_LABEL_TEMPLATE,
    workspace_template: str | None = _DEFAULT_WORKSPACE_TEMPLATE,
    seed_start: int = _DEFAULT_SEED_START,
    seed_label_prefix: str = _DEFAULT_SEED_LABEL_PREFIX,
    seed_label_width: int = _DEFAULT_SEED_LABEL_WIDTH,
    extra_axes: Mapping[str, list[Any]] | None = None,
    derive: Mapping[str, Any] | None = None,
    include: list[dict[str, Any]] | None = None,
    exclude: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a preset-backed `fanout.matrix` payload for Codex fuzz campaigns."""

    payload = build_codex_fuzz_campaign_matrix_payload(
        preset=preset,
        bucket_count=bucket_count,
        label_template=label_template,
        workspace_template=workspace_template,
        seed_start=seed_start,
        seed_label_prefix=seed_label_prefix,
        seed_label_width=seed_label_width,
        extra_axes=extra_axes,
        derive=derive,
        include=include,
        exclude=exclude,
    )
    return fanout_matrix(
        payload.matrix,
        as_=as_,
        derive=payload.derive,
        include=payload.include,
        exclude=payload.exclude,
    )


def _positive_int(value: int, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"`{field_name}` must be an integer")
    if value < 1:
        raise ValueError(f"`{field_name}` must be at least 1")
    return value


def _non_empty_text(value: str | None, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"`{field_name}` must be a non-empty string")
    return normalized


def _resolve_codex_fuzz_campaign_layout(layout: str | None) -> CodexFuzzCampaignLayout:
    normalized = str(layout or _DEFAULT_CAMPAIGN_LAYOUT).strip().lower()
    if normalized not in {"flat", "batched", "grouped"}:
        raise ValueError("`layout` must be one of `flat`, `batched`, or `grouped`")
    return normalized  # type: ignore[return-value]


def _normalize_task_prefix(task_prefix: str | None) -> str:
    if task_prefix is None:
        return ""
    normalized = task_prefix.strip()
    if not normalized:
        raise ValueError("`task_prefix` must be a non-empty string when provided")
    if not _TASK_PREFIX_PATTERN.fullmatch(normalized):
        raise ValueError("`task_prefix` must start with a letter or underscore and contain only letters, digits, or `_`")
    return normalized


def _campaign_task_id(base_name: str, *, task_prefix: str) -> str:
    if not task_prefix:
        return base_name
    return f"{task_prefix}_{base_name}"


def _normalize_node_overrides(
    value: Mapping[str, Any] | None,
    *,
    subject: str,
    disallowed: set[str] | None = None,
) -> dict[str, Any]:
    if value is None:
        return {}
    overrides = deepcopy(dict(value))
    blocked = sorted((disallowed or set()).intersection(overrides))
    if blocked:
        joined = ", ".join(f"`{field}`" for field in blocked)
        raise ValueError(f"`{subject}` does not support overriding {joined}")
    return overrides


def _merge_node_kwargs(defaults: Mapping[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    merged = deepcopy(dict(defaults))
    merged.update(deepcopy(dict(overrides)))
    return merged


def _init_directories_for_prompt(*, crash_registry_path: str, notes_path: str) -> str:
    directories = ["crashes"]
    for path in (crash_registry_path, notes_path):
        if "/" not in path:
            continue
        directory = path.rsplit("/", 1)[0].strip()
        if directory and directory not in directories:
            directories.append(directory)
    return " ".join(directories)


def _default_init_prompt(*, crash_registry_path: str, notes_path: str) -> str:
    return (
        "Create the following directory structure silently if it does not already exist:\n"
        f"  mkdir -p {_init_directories_for_prompt(crash_registry_path=crash_registry_path, notes_path=notes_path)}\n"
        f"If {crash_registry_path} is missing or empty, create it with:\n"
        "  # Crash Registry\n"
        "  | Timestamp | Label | Target | Sanitizer | Evidence | Artifact |\n"
        "  |---|---|---|---|---|---|\n"
        f"If {notes_path} is missing or empty, create it with:\n"
        "  # Campaign Notes\n"
        "  Use this file only for cross-shard lessons and retargeting guidance.\n"
        f"Then respond with exactly: {_DEFAULT_INIT_SUCCESS_TOKEN}"
    )


def _default_fuzzer_prompt(
    *,
    campaign_label: str,
    crash_registry_path: str,
    notes_path: str,
) -> str:
    return (
        f"You are Codex fuzz shard {{{{ shard.number }}}} of {{{{ shard.count }}}} in an authorized {campaign_label} campaign.\n\n"
        "Campaign inputs:\n"
        "- Label: {{ shard.label }}\n"
        "- Target: {{ shard.target }}\n"
        "- Corpus family: {{ shard.corpus }}\n"
        "- Sanitizer: {{ shard.sanitizer }}\n"
        "- Strategy focus: {{ shard.focus }}\n"
        "- Seed bucket: {{ shard.bucket }}\n"
        "- Seed: {{ shard.seed }}\n"
        "- Workspace: {{ shard.workspace }}\n\n"
        "Shard contract:\n"
        "- Stay within {{ shard.workspace }} unless you are appending to the shared crash registry or notes.\n"
        "- Treat the preset-backed shard metadata as the source of truth for this run.\n"
        "- Use the label, target family, sanitizer, focus, and seed bucket to keep the campaign reproducible.\n"
        "- Prefer high-signal crashers, assertion failures, memory safety bugs, or logic corruptions.\n"
        f"- Record confirmed findings in `{crash_registry_path}` and copy minimal repro artifacts into `crashes/`.\n"
        f"- Add short cross-shard lessons to `{notes_path}` when they help other shards avoid duplicate work."
    )


def _default_batched_reducer_prompt(*, campaign_label: str) -> str:
    return (
        f"Prepare the maintainer handoff for {campaign_label} batch {{{{ current.number }}}} of {{{{ current.count }}}}.\n\n"
        "Batch coverage:\n"
        "- Source group: {{ current.source_group }}\n"
        "- Total source shards: {{ current.source_count }}\n"
        "- Batch size: {{ current.scope.size }}\n"
        "- Shard range: {{ current.start_number }} through {{ current.end_number }}\n"
        "- Shard ids: {{ current.scope.ids | join(', ') }}\n"
        "- Completed shards: {{ current.scope.summary.completed }}\n"
        "- Failed shards: {{ current.scope.summary.failed }}\n"
        "- Silent shards: {{ current.scope.summary.without_output }}\n\n"
        "Group the strongest findings by target family first, then by sanitizer and focus, and end with the shards that need retargeting.\n\n"
        "{% for shard in current.scope.with_output.nodes %}\n"
        "### {{ shard.label }} :: {{ shard.node_id }} (status: {{ shard.status }})\n"
        "Workspace: {{ shard.workspace }}\n"
        "{{ shard.output }}\n\n"
        "{% endfor %}"
        "{% if current.scope.failed.size %}\n"
        "Failed shards:\n"
        "{% for shard in current.scope.failed.nodes %}\n"
        "- {{ shard.id }} :: {{ shard.label }}\n"
        "{% endfor %}"
        "{% endif %}"
        "{% if not current.scope.with_output.size %}\n"
        "No shard in this batch produced reducer-ready output. Say that explicitly and use the failed shard list to suggest retargeting.\n"
        "{% endif %}"
    )


def _default_grouped_reducer_prompt(*, campaign_label: str, fuzzer_task_id: str) -> str:
    return (
        "Prepare the maintainer handoff for target family {{ current.target }} "
        f"(corpus {{{{ current.corpus }}}}) in the {campaign_label} campaign.\n\n"
        "Campaign snapshot:\n"
        f"- Total shards: {{{{ fanouts.{fuzzer_task_id}.size }}}}\n"
        f"- Completed shards: {{{{ fanouts.{fuzzer_task_id}.summary.completed }}}}\n"
        f"- Failed shards: {{{{ fanouts.{fuzzer_task_id}.summary.failed }}}}\n"
        f"- Silent shards: {{{{ fanouts.{fuzzer_task_id}.summary.without_output }}}}\n"
        "- Scoped reducer shards: {{ current.scope.size }}\n"
        "- Scoped completed shards: {{ current.scope.summary.completed }}\n"
        "- Scoped failed shards: {{ current.scope.summary.failed }}\n"
        "- Scoped shard ids: {{ current.scope.ids | join(', ') }}\n\n"
        "Focus only on {{ current.target }}. Summarize strong or confirmed findings first, then recurring lessons, "
        "then quiet or failed shards that need retargeting.\n\n"
        "{% for shard in current.scope.with_output.nodes %}\n"
        "### {{ shard.label }} :: {{ shard.id }} (status: {{ shard.status }})\n"
        "{{ shard.output }}\n\n"
        "{% endfor %}"
        "{% if current.scope.failed.size %}\n"
        "Failed scoped shards:\n"
        "{% for shard in current.scope.failed.nodes %}\n"
        "- {{ shard.id }} :: {{ shard.label }}\n"
        "{% endfor %}"
        "{% endif %}"
        "{% if not current.scope.with_output.size %}\n"
        "No scoped shard produced reducer-ready output. Say that explicitly and use the failed shard list to suggest retargeting.\n"
        "{% endif %}"
    )


def _default_flat_merge_prompt(*, campaign_label: str, fuzzer_task_id: str) -> str:
    return (
        f"Consolidate this {campaign_label} preset-backed fuzz campaign into a maintainer handoff.\n"
        "Group the findings by target family first, then by sanitizer/focus, and end with seed buckets that need retargeting.\n\n"
        "Campaign status:\n"
        f"- Total shards: {{{{ fanouts.{fuzzer_task_id}.size }}}}\n"
        f"- Completed shards: {{{{ fanouts.{fuzzer_task_id}.summary.completed }}}}\n"
        f"- Failed shards: {{{{ fanouts.{fuzzer_task_id}.summary.failed }}}}\n"
        f"- Silent shards: {{{{ fanouts.{fuzzer_task_id}.summary.without_output }}}}\n\n"
        f"{{% for shard in fanouts.{fuzzer_task_id}.nodes %}}\n"
        "### {{ shard.label }} :: {{ shard.id }} (status: {{ shard.status }})\n"
        "{{ shard.output or '(no output)' }}\n\n"
        "{% endfor %}"
    )


def _default_batched_merge_prompt(
    *,
    campaign_label: str,
    fuzzer_task_id: str,
    reducer_task_id: str,
) -> str:
    return (
        f"Consolidate this {campaign_label} preset-backed fuzz campaign into a maintainer handoff.\n"
        "Start with campaign-wide status, then the strongest batch-level findings, and end with quiet or failed shards that need retargeting.\n\n"
        "Campaign status:\n"
        f"- Total shards: {{{{ fanouts.{fuzzer_task_id}.size }}}}\n"
        f"- Completed shards: {{{{ fanouts.{fuzzer_task_id}.summary.completed }}}}\n"
        f"- Failed shards: {{{{ fanouts.{fuzzer_task_id}.summary.failed }}}}\n"
        f"- Silent shards: {{{{ fanouts.{fuzzer_task_id}.summary.without_output }}}}\n"
        f"- Batch reducers completed: {{{{ fanouts.{reducer_task_id}.summary.completed }}}} / {{{{ fanouts.{reducer_task_id}.size }}}}\n\n"
        f"{{% for batch in fanouts.{reducer_task_id}.with_output.nodes %}}\n"
        "## Batch {{ batch.number }} :: {{ batch.start_number }}-{{ batch.end_number }} (status: {{ batch.status }})\n"
        "{{ batch.output }}\n\n"
        "{% endfor %}"
        f"{{% if fanouts.{reducer_task_id}.without_output.size %}}\n"
        "Batch reducers needing attention:\n"
        f"{{% for batch in fanouts.{reducer_task_id}.without_output.nodes %}}\n"
        "- {{ batch.id }} :: shards {{ batch.start_number }}-{{ batch.end_number }} (status: {{ batch.status }})\n"
        "{% endfor %}"
        "{% endif %}"
    )


def _default_grouped_merge_prompt(
    *,
    campaign_label: str,
    fuzzer_task_id: str,
    reducer_task_id: str,
) -> str:
    return (
        f"Consolidate this hierarchical {campaign_label} preset-backed fuzz campaign into a maintainer handoff.\n"
        "Start with campaign-wide status, then group the strongest findings by target family, and end with failed or quiet shards that need retargeting.\n\n"
        "Campaign status:\n"
        f"- Total shards: {{{{ fanouts.{fuzzer_task_id}.size }}}}\n"
        f"- Completed shards: {{{{ fanouts.{fuzzer_task_id}.summary.completed }}}}\n"
        f"- Failed shards: {{{{ fanouts.{fuzzer_task_id}.summary.failed }}}}\n"
        f"- Silent shards: {{{{ fanouts.{fuzzer_task_id}.summary.without_output }}}}\n"
        f"- Family reducers completed: {{{{ fanouts.{reducer_task_id}.summary.completed }}}} / {{{{ fanouts.{reducer_task_id}.size }}}}\n\n"
        f"{{% for review in fanouts.{reducer_task_id}.with_output.nodes %}}\n"
        "## {{ review.target }} :: {{ review.id }} (status: {{ review.status }})\n"
        "{{ review.output }}\n\n"
        "{% endfor %}"
        f"{{% if fanouts.{fuzzer_task_id}.failed.size %}}\n"
        "Failed shard ids:\n"
        f"{{% for shard in fanouts.{fuzzer_task_id}.failed.nodes %}}\n"
        "- {{ shard.id }} :: {{ shard.label }}\n"
        "{% endfor %}"
        "{% endif %}"
    )


def codex_fuzz_campaign(
    *,
    preset: str | None = None,
    bucket_count: int = _DEFAULT_BUCKET_COUNT,
    layout: CodexFuzzCampaignLayout = _DEFAULT_CAMPAIGN_LAYOUT,
    batch_size: int = _DEFAULT_BATCH_SIZE,
    task_prefix: str | None = None,
    campaign_label: str | None = None,
    label_template: str | None = _DEFAULT_LABEL_TEMPLATE,
    workspace_template: str | None = _DEFAULT_WORKSPACE_TEMPLATE,
    seed_start: int = _DEFAULT_SEED_START,
    seed_label_prefix: str = _DEFAULT_SEED_LABEL_PREFIX,
    seed_label_width: int = _DEFAULT_SEED_LABEL_WIDTH,
    extra_axes: Mapping[str, list[Any]] | None = None,
    derive: Mapping[str, Any] | None = None,
    include: list[dict[str, Any]] | None = None,
    exclude: list[dict[str, Any]] | None = None,
    crash_registry_path: str = _DEFAULT_CRASH_REGISTRY_PATH,
    notes_path: str = _DEFAULT_NOTES_PATH,
    init_prompt: str | None = None,
    fuzzer_prompt: str | None = None,
    reducer_prompt: str | None = None,
    merge_prompt: str | None = None,
    init_kwargs: Mapping[str, Any] | None = None,
    fuzzer_kwargs: Mapping[str, Any] | None = None,
    reducer_kwargs: Mapping[str, Any] | None = None,
    merge_kwargs: Mapping[str, Any] | None = None,
) -> CodexFuzzCampaignNodes:
    """Register a preset-backed Codex fuzz campaign inside the active DAG."""

    resolved_layout = _resolve_codex_fuzz_campaign_layout(layout)
    resolved_task_prefix = _normalize_task_prefix(task_prefix)
    resolved_campaign_label = _non_empty_text(
        campaign_label or preset or default_fuzz_campaign_preset_name(),
        field_name="campaign_label",
    )
    resolved_crash_registry_path = _non_empty_text(crash_registry_path, field_name="crash_registry_path")
    resolved_notes_path = _non_empty_text(notes_path, field_name="notes_path")
    if label_template is None:
        raise ValueError("`label_template` must be set when using `codex_fuzz_campaign()`")
    if workspace_template is None:
        raise ValueError("`workspace_template` must be set when using `codex_fuzz_campaign()`")
    if resolved_layout == "batched":
        batch_size = _positive_int(batch_size, field_name="batch_size")
    if resolved_layout == "flat" and (reducer_prompt is not None or reducer_kwargs):
        raise ValueError("`reducer_prompt` and `reducer_kwargs` are only valid when `layout` uses reducers")

    normalized_init_kwargs = _normalize_node_overrides(
        init_kwargs,
        subject="init_kwargs",
        disallowed={"task_id", "fanout", "prompt"},
    )
    normalized_fuzzer_kwargs = _normalize_node_overrides(
        fuzzer_kwargs,
        subject="fuzzer_kwargs",
        disallowed={"task_id", "fanout", "prompt"},
    )
    normalized_reducer_kwargs = _normalize_node_overrides(
        reducer_kwargs,
        subject="reducer_kwargs",
        disallowed={"task_id", "fanout", "prompt"},
    )
    normalized_merge_kwargs = _normalize_node_overrides(
        merge_kwargs,
        subject="merge_kwargs",
        disallowed={"task_id", "fanout", "prompt"},
    )

    init_task_id = _campaign_task_id("init", task_prefix=resolved_task_prefix)
    fuzzer_task_id = _campaign_task_id("fuzzer", task_prefix=resolved_task_prefix)
    reducer_task_id: str | None = None
    if resolved_layout == "batched":
        reducer_task_id = _campaign_task_id("batch_merge", task_prefix=resolved_task_prefix)
    if resolved_layout == "grouped":
        reducer_task_id = _campaign_task_id("family_merge", task_prefix=resolved_task_prefix)
    merge_task_id = _campaign_task_id("merge", task_prefix=resolved_task_prefix)

    init_node = codex(
        task_id=init_task_id,
        prompt=init_prompt
        or _default_init_prompt(
            crash_registry_path=resolved_crash_registry_path,
            notes_path=resolved_notes_path,
        ),
        **_merge_node_kwargs(
            {
                "tools": "read_write",
                "timeout_seconds": 60,
                "success_criteria": [
                    {
                        "kind": "output_contains",
                        "value": _DEFAULT_INIT_SUCCESS_TOKEN,
                    }
                ],
            },
            normalized_init_kwargs,
        ),
    )

    fuzzer_node = codex(
        task_id=fuzzer_task_id,
        prompt=fuzzer_prompt
        or _default_fuzzer_prompt(
            campaign_label=resolved_campaign_label,
            crash_registry_path=resolved_crash_registry_path,
            notes_path=resolved_notes_path,
        ),
        **_merge_node_kwargs(
            {
                "fanout": codex_fuzz_campaign_matrix(
                    preset=preset,
                    bucket_count=bucket_count,
                    as_="shard",
                    label_template=label_template,
                    workspace_template=workspace_template,
                    seed_start=seed_start,
                    seed_label_prefix=seed_label_prefix,
                    seed_label_width=seed_label_width,
                    extra_axes=extra_axes,
                    derive=derive,
                    include=include,
                    exclude=exclude,
                ),
                "model": _DEFAULT_CODEX_MODEL,
                "tools": "read_write",
                "target": {"cwd": "{{ shard.workspace }}"},
                "timeout_seconds": 3600,
                "retries": 2,
                "retry_backoff_seconds": 2,
                "extra_args": list(_DEFAULT_CODEX_SEARCH_ARGS),
            },
            normalized_fuzzer_kwargs,
        ),
    )

    reducer_node: NodeBuilder | None = None
    if resolved_layout == "batched":
        assert reducer_task_id is not None
        reducer_node = codex(
            task_id=reducer_task_id,
            prompt=reducer_prompt or _default_batched_reducer_prompt(campaign_label=resolved_campaign_label),
            **_merge_node_kwargs(
                {
                    "fanout": fanout_batches(fuzzer_task_id, batch_size, as_="batch"),
                    "model": _DEFAULT_CODEX_MODEL,
                    "tools": "read_only",
                    "timeout_seconds": 300,
                },
                normalized_reducer_kwargs,
            ),
        )
    if resolved_layout == "grouped":
        assert reducer_task_id is not None
        reducer_node = codex(
            task_id=reducer_task_id,
            prompt=reducer_prompt
            or _default_grouped_reducer_prompt(
                campaign_label=resolved_campaign_label,
                fuzzer_task_id=fuzzer_task_id,
            ),
            **_merge_node_kwargs(
                {
                    "fanout": fanout_group_by(fuzzer_task_id, list(_GROUPED_REDUCER_FIELDS), as_="family"),
                    "model": _DEFAULT_CODEX_MODEL,
                    "tools": "read_only",
                    "timeout_seconds": 300,
                },
                normalized_reducer_kwargs,
            ),
        )

    if resolved_layout == "flat":
        merge_prompt_text = merge_prompt or _default_flat_merge_prompt(
            campaign_label=resolved_campaign_label,
            fuzzer_task_id=fuzzer_task_id,
        )
    elif resolved_layout == "batched":
        assert reducer_task_id is not None
        merge_prompt_text = merge_prompt or _default_batched_merge_prompt(
            campaign_label=resolved_campaign_label,
            fuzzer_task_id=fuzzer_task_id,
            reducer_task_id=reducer_task_id,
        )
    else:
        assert reducer_task_id is not None
        merge_prompt_text = merge_prompt or _default_grouped_merge_prompt(
            campaign_label=resolved_campaign_label,
            fuzzer_task_id=fuzzer_task_id,
            reducer_task_id=reducer_task_id,
        )
    merge_node = codex(
        task_id=merge_task_id,
        prompt=merge_prompt_text,
        **_merge_node_kwargs(
            {
                "model": _DEFAULT_CODEX_MODEL,
                "tools": "read_only",
                "timeout_seconds": 300,
            },
            normalized_merge_kwargs,
        ),
    )

    init_node >> fuzzer_node
    if reducer_node is None:
        fuzzer_node >> merge_node
    else:
        fuzzer_node >> reducer_node
        reducer_node >> merge_node

    return CodexFuzzCampaignNodes(init=init_node, fuzzer=fuzzer_node, reducer=reducer_node, merge=merge_node)


__all__ = [
    "CodexFuzzCampaignNodes",
    "codex_fuzz_campaign",
    "codex_fuzz_campaign_matrix",
    "codex_fuzz_campaign_preset_names",
]
