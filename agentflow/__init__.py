"""AgentFlow public package surface."""

from agentflow.dsl import (
    DAG,
    claude,
    codex,
    fanout_batches,
    fanout_count,
    fanout_group_by,
    fanout_matrix,
    fanout_matrix_path,
    fanout_values,
    fanout_values_path,
    kimi,
)
from agentflow.fuzz import CodexFuzzCampaignNodes, codex_fuzz_campaign, codex_fuzz_campaign_matrix, codex_fuzz_campaign_preset_names


def create_app(*args, **kwargs):
    from agentflow.app import create_app as _create_app

    return _create_app(*args, **kwargs)


__all__ = [
    "DAG",
    "claude",
    "CodexFuzzCampaignNodes",
    "codex",
    "codex_fuzz_campaign",
    "codex_fuzz_campaign_matrix",
    "codex_fuzz_campaign_preset_names",
    "fanout_batches",
    "fanout_count",
    "fanout_group_by",
    "fanout_matrix",
    "fanout_matrix_path",
    "fanout_values",
    "fanout_values_path",
    "kimi",
    "create_app",
]
