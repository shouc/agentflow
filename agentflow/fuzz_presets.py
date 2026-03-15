from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from agentflow.defaults import bundled_fuzz_campaign_presets, default_fuzz_campaign_preset_name

_DEFAULT_BUCKET_COUNT = 4
_DEFAULT_SEED_START = 4101
_DEFAULT_SEED_LABEL_PREFIX = "seed_"
_DEFAULT_SEED_LABEL_WIDTH = 3
_DEFAULT_LABEL_TEMPLATE = "{{ shard.target }} / {{ shard.sanitizer }} / {{ shard.focus }} / {{ shard.bucket }}"
_DEFAULT_WORKSPACE_TEMPLATE = "agents/{{ shard.target }}_{{ shard.sanitizer }}_{{ shard.bucket }}_{{ shard.suffix }}"
_BUILTIN_MATRIX_AXES = {"family", "strategy", "seed_bucket"}


@dataclass(frozen=True)
class CodexFuzzCampaignMatrixPayload:
    matrix: dict[str, list[Any]]
    derive: dict[str, Any] | None = None
    include: list[dict[str, Any]] | None = None
    exclude: list[dict[str, Any]] | None = None


def codex_fuzz_campaign_preset_names() -> tuple[str, ...]:
    """Return the built-in preset names available to preset-backed fuzz helpers."""

    return tuple(preset.name for preset in bundled_fuzz_campaign_presets())


def _resolve_codex_fuzz_campaign_preset_name(preset: str | None) -> str:
    if preset is None:
        return default_fuzz_campaign_preset_name()

    normalized = str(preset).strip()
    if not normalized:
        raise ValueError("`preset` must be a non-empty string")
    if normalized not in codex_fuzz_campaign_preset_names():
        available = ", ".join(f"`{name}`" for name in codex_fuzz_campaign_preset_names())
        raise ValueError(f"`preset` must be one of {available}, got `{normalized}`")
    return normalized


def _positive_int(value: int, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"`{field_name}` must be an integer")
    if value < 1:
        raise ValueError(f"`{field_name}` must be at least 1")
    return value


def build_codex_fuzz_campaign_matrix_payload(
    *,
    preset: str | None = None,
    bucket_count: int = _DEFAULT_BUCKET_COUNT,
    label_template: str | None = _DEFAULT_LABEL_TEMPLATE,
    workspace_template: str | None = _DEFAULT_WORKSPACE_TEMPLATE,
    seed_start: int = _DEFAULT_SEED_START,
    seed_label_prefix: str = _DEFAULT_SEED_LABEL_PREFIX,
    seed_label_width: int = _DEFAULT_SEED_LABEL_WIDTH,
    extra_axes: Mapping[str, list[Any]] | None = None,
    derive: Mapping[str, Any] | None = None,
    include: list[dict[str, Any]] | None = None,
    exclude: list[dict[str, Any]] | None = None,
) -> CodexFuzzCampaignMatrixPayload:
    """Build a preset-backed matrix payload for Codex fuzz campaigns."""

    resolved_preset_name = _resolve_codex_fuzz_campaign_preset_name(preset)
    by_name = {item.name: item for item in bundled_fuzz_campaign_presets()}
    campaign_preset = by_name[resolved_preset_name]

    bucket_count = _positive_int(bucket_count, field_name="bucket_count")
    seed_label_width = _positive_int(seed_label_width, field_name="seed_label_width")
    if isinstance(seed_start, bool) or not isinstance(seed_start, int):
        raise ValueError("`seed_start` must be an integer")

    matrix: dict[str, list[Any]] = {
        "family": [dict(family) for family in campaign_preset.families],
        "strategy": [dict(strategy) for strategy in campaign_preset.strategies],
        "seed_bucket": [
            {
                "bucket": f"{seed_label_prefix}{index + 1:0{seed_label_width}d}",
                "seed": seed_start + index,
            }
            for index in range(bucket_count)
        ],
    }

    if extra_axes is not None:
        for axis_name, axis_values in extra_axes.items():
            if not isinstance(axis_name, str):
                raise ValueError("`extra_axes` keys must be strings")
            normalized_axis = axis_name.strip()
            if not normalized_axis:
                raise ValueError("`extra_axes` keys must not be empty")
            if normalized_axis in _BUILTIN_MATRIX_AXES:
                raise ValueError(
                    f"`extra_axes` cannot override built-in axis `{normalized_axis}`; "
                    "use outer fanout `include`, `exclude`, or `derive` instead"
                )
            if not isinstance(axis_values, list):
                raise ValueError(f"`extra_axes.{normalized_axis}` must be a list")
            if not axis_values:
                raise ValueError(f"`extra_axes.{normalized_axis}` must contain at least one item")
            matrix[normalized_axis] = deepcopy(axis_values)

    derived: dict[str, Any] = {}
    if label_template is not None:
        derived["label"] = label_template
    if workspace_template is not None:
        derived["workspace"] = workspace_template
    if derive is not None:
        derived.update(deepcopy(dict(derive)))

    return CodexFuzzCampaignMatrixPayload(
        matrix=matrix,
        derive=derived or None,
        include=deepcopy(include),
        exclude=deepcopy(exclude),
    )


__all__ = [
    "CodexFuzzCampaignMatrixPayload",
    "build_codex_fuzz_campaign_matrix_payload",
    "codex_fuzz_campaign_preset_names",
]
