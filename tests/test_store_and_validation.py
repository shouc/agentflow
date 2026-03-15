from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from agentflow.specs import LocalTarget, PipelineSpec, RunEvent, RunRecord
from agentflow.store import RunStore


def test_pipeline_validation_rejects_cycles():
    with pytest.raises(ValueError, match="cycle detected"):
        PipelineSpec.model_validate(
            {
                "name": "cycle",
                "working_dir": ".",
                "nodes": [
                    {"id": "a", "agent": "codex", "prompt": "a", "depends_on": ["b"]},
                    {"id": "b", "agent": "codex", "prompt": "b", "depends_on": ["a"]},
                ],
            }
        )


def test_pipeline_validation_rejects_codex_kimi_provider_alias():
    with pytest.raises(ValueError, match="provider 'kimi' is not supported for codex nodes"):
        PipelineSpec.model_validate(
            {
                "name": "invalid-provider",
                "working_dir": ".",
                "nodes": [
                    {"id": "plan", "agent": "codex", "prompt": "plan", "provider": "kimi"},
                ],
            }
        )


@pytest.mark.parametrize(
    ("target_patch", "expected_field"),
    [
        ({"shell_login": True}, "shell_login"),
        ({"shell_interactive": True}, "shell_interactive"),
        ({"shell_init": "kimi"}, "shell_init"),
        ({"shell_init": ["kimi"]}, "shell_init"),
    ],
)
def test_pipeline_validation_rejects_local_shell_bootstrap_without_shell(target_patch, expected_field):
    with pytest.raises(ValueError, match=rf"{expected_field}.*target\.shell"):
        PipelineSpec.model_validate(
            {
                "name": "invalid-local-shell-target",
                "working_dir": ".",
                "nodes": [
                    {
                        "id": "plan",
                        "agent": "claude",
                        "prompt": "plan",
                        "target": {"kind": "local", **target_patch},
                    },
                ],
            }
        )


@pytest.mark.parametrize(
    ("shell", "expected_message"),
    [
        ("bash --command 'kimi && {command}'", r"unsupported bash long option.*--command.*use `-c`"),
        ("bash --command='kimi && {command}'", r"unsupported bash long option.*--command.*use `-c`"),
        (
            "env BASH_ENV=/tmp/kimi.env bash --interactive -c 'kimi && {command}'",
            r"unsupported bash long option.*--interactive.*target\.shell_interactive",
        ),
        (
            "bash --rcfile=\"$HOME/.bashrc\" -ic 'kimi && {command}'",
            r"unsupported bash long option.*--rcfile=.*pass `--rcfile` and its value as separate arguments",
        ),
        (
            "bash --login=1 -c 'kimi && {command}'",
            r"unsupported bash long option.*--login=.*use `--login` without `=`",
        ),
    ],
)
def test_pipeline_validation_rejects_unsupported_bash_long_options(shell, expected_message):
    with pytest.raises(ValueError, match=expected_message):
        PipelineSpec.model_validate(
            {
                "name": "invalid-bash-long-options",
                "working_dir": ".",
                "nodes": [
                    {
                        "id": "plan",
                        "agent": "claude",
                        "prompt": "plan",
                        "target": {"kind": "local", "shell": shell, "shell_init": "kimi"},
                    },
                ],
            }
        )


def test_pipeline_validation_accepts_supported_bash_long_options_with_separate_value():
    pipeline = PipelineSpec.model_validate(
        {
            "name": "valid-bash-long-options",
            "working_dir": ".",
            "nodes": [
                {
                    "id": "plan",
                    "agent": "claude",
                    "prompt": "plan",
                    "target": {
                        "kind": "local",
                        "shell": "bash --rcfile $HOME/.bashrc -ic 'kimi && {command}'",
                        "shell_init": "kimi",
                    },
                },
            ],
        }
    )

    assert pipeline.nodes[0].target.shell == "bash --rcfile $HOME/.bashrc -ic 'kimi && {command}'"


@pytest.mark.parametrize(
    "shell",
    [
        "bash -lc 'echo pre'",
        "env BASH_ENV=/tmp/shell.env bash -lc 'echo pre'",
    ],
)
def test_pipeline_validation_rejects_shell_command_payload_without_command_placeholder(shell):
    with pytest.raises(ValueError, match=r"shell command payload.*\{command\}"):
        PipelineSpec.model_validate(
            {
                "name": "invalid-shell-command-payload",
                "working_dir": ".",
                "nodes": [
                    {
                        "id": "plan",
                        "agent": "claude",
                        "prompt": "plan",
                        "target": {"kind": "local", "shell": shell},
                    },
                ],
            }
        )


def test_pipeline_validation_applies_local_target_defaults_to_local_nodes():
    pipeline = PipelineSpec.model_validate(
        {
            "name": "local-target-defaults",
            "working_dir": ".",
            "local_target_defaults": {
                "shell": "bash",
                "shell_login": True,
                "shell_interactive": True,
                "shell_init": ["command -v kimi >/dev/null 2>&1", "kimi"],
            },
            "nodes": [
                {"id": "plan", "agent": "codex", "prompt": "plan"},
                {
                    "id": "review",
                    "agent": "claude",
                    "prompt": "review",
                    "target": {"cwd": "review-work", "shell_init": "custom-kimi"},
                },
                {
                    "id": "remote",
                    "agent": "kimi",
                    "prompt": "remote",
                    "target": {"kind": "container", "image": "python:3.12"},
                },
            ],
        }
    )

    assert pipeline.local_target_defaults is not None
    assert pipeline.nodes[0].target.shell == "bash"
    assert pipeline.nodes[0].target.shell_init == ["command -v kimi >/dev/null 2>&1", "kimi"]
    assert pipeline.nodes[1].target.shell == "bash"
    assert pipeline.nodes[1].target.cwd == "review-work"
    assert pipeline.nodes[1].target.shell_init == "custom-kimi"
    assert pipeline.nodes[2].target.kind == "container"


def test_pipeline_validation_expands_kimi_bootstrap_shorthand():
    pipeline = PipelineSpec.model_validate(
        {
            "name": "local-bootstrap-shorthand",
            "working_dir": ".",
            "local_target_defaults": {
                "bootstrap": "kimi",
            },
            "nodes": [
                {"id": "plan", "agent": "codex", "prompt": "plan"},
                {
                    "id": "review",
                    "agent": "claude",
                    "prompt": "review",
                    "target": {"bootstrap": "kimi", "cwd": "review-work"},
                },
            ],
        }
    )

    assert pipeline.local_target_defaults is not None
    assert pipeline.local_target_defaults.bootstrap == "kimi"
    assert pipeline.local_target_defaults.shell == "bash"
    assert pipeline.local_target_defaults.shell_login is True
    assert pipeline.local_target_defaults.shell_interactive is True
    assert pipeline.local_target_defaults.shell_init == ["command -v kimi >/dev/null 2>&1", "kimi"]
    assert pipeline.nodes[0].target.bootstrap == "kimi"
    assert pipeline.nodes[0].target.shell == "bash"
    assert pipeline.nodes[0].target.shell_login is True
    assert pipeline.nodes[0].target.shell_interactive is True
    assert pipeline.nodes[0].target.shell_init == ["command -v kimi >/dev/null 2>&1", "kimi"]
    assert pipeline.nodes[1].target.bootstrap == "kimi"
    assert pipeline.nodes[1].target.cwd == "review-work"
    assert pipeline.nodes[1].target.shell == "bash"
    assert pipeline.nodes[1].target.shell_init == ["command -v kimi >/dev/null 2>&1", "kimi"]


def test_pipeline_validation_expands_fanout_nodes_and_group_dependencies():
    pipeline = PipelineSpec.model_validate(
        {
            "name": "fanout-validation",
            "working_dir": ".",
            "local_target_defaults": {
                "bootstrap": "kimi",
            },
            "nodes": [
                {
                    "id": "fuzz",
                    "fanout": {
                        "count": 3,
                        "as": "shard",
                    },
                    "agent": "codex",
                    "prompt": "fuzz {{ shard.number }}/{{ shard.count }} in {{ shard.node_id }}",
                },
                {
                    "id": "merge",
                    "agent": "codex",
                    "depends_on": ["fuzz"],
                    "prompt": "merge",
                },
            ],
        }
    )

    assert pipeline.fanouts == {"fuzz": ["fuzz_0", "fuzz_1", "fuzz_2"]}
    assert [node.id for node in pipeline.nodes] == ["fuzz_0", "fuzz_1", "fuzz_2", "merge"]
    assert pipeline.nodes[0].prompt == "fuzz 1/3 in fuzz_0"
    assert pipeline.nodes[1].prompt == "fuzz 2/3 in fuzz_1"
    assert pipeline.nodes[2].prompt == "fuzz 3/3 in fuzz_2"
    assert pipeline.nodes[0].target.bootstrap == "kimi"
    assert pipeline.nodes[1].target.bootstrap == "kimi"
    assert pipeline.node_map["merge"].depends_on == ["fuzz_0", "fuzz_1", "fuzz_2"]


def test_pipeline_validation_rejects_invalid_fanout_alias():
    with pytest.raises(ValueError, match=r"fanout\.as.*valid template variable name"):
        PipelineSpec.model_validate(
            {
                "name": "bad-fanout",
                "working_dir": ".",
                "nodes": [
                    {
                        "id": "fuzz",
                        "fanout": {
                            "count": 2,
                            "as": "bad-alias",
                        },
                        "agent": "codex",
                        "prompt": "hi",
                    }
                ],
            }
        )


def test_pipeline_validation_rejects_fanout_group_id_collision_with_normal_node():
    with pytest.raises(ValueError, match=r"duplicate node ids: \['fuzz'\]"):
        PipelineSpec.model_validate(
            {
                "name": "fanout-id-collision",
                "working_dir": ".",
                "nodes": [
                    {
                        "id": "fuzz",
                        "fanout": {
                            "count": 2,
                        },
                        "agent": "codex",
                        "prompt": "fanout",
                    },
                    {
                        "id": "fuzz",
                        "agent": "codex",
                        "prompt": "plain",
                    },
                ],
            }
        )


def test_pipeline_validation_merges_extra_shell_init_into_kimi_bootstrap_shorthand():
    pipeline = PipelineSpec.model_validate(
        {
            "name": "local-bootstrap-shell-init-merge",
            "working_dir": ".",
            "local_target_defaults": {
                "bootstrap": "kimi",
            },
            "nodes": [
                {
                    "id": "review",
                    "agent": "claude",
                    "prompt": "review",
                    "target": {
                        "shell_init": ["export EXTRA_FLAG=1"],
                    },
                }
            ],
        }
    )

    assert pipeline.nodes[0].target.bootstrap == "kimi"
    assert pipeline.nodes[0].target.shell == "bash"
    assert pipeline.nodes[0].target.shell_login is True
    assert pipeline.nodes[0].target.shell_interactive is True
    assert pipeline.nodes[0].target.shell_init == [
        "export EXTRA_FLAG=1",
        "command -v kimi >/dev/null 2>&1",
        "kimi",
    ]


def test_pipeline_validation_allows_per_node_opt_out_from_inherited_kimi_bootstrap_defaults():
    pipeline = PipelineSpec.model_validate(
        {
            "name": "local-bootstrap-opt-out",
            "working_dir": ".",
            "local_target_defaults": LocalTarget.model_validate(
                {
                    "bootstrap": "kimi",
                    "cwd": "shared-work",
                }
            ),
            "nodes": [
                {"id": "shared", "agent": "claude", "prompt": "shared"},
                {
                    "id": "plain",
                    "agent": "codex",
                    "prompt": "plain",
                    "target": {"bootstrap": None},
                },
            ],
        }
    )

    shared_target = pipeline.nodes[0].target
    plain_target = pipeline.nodes[1].target

    assert shared_target.bootstrap == "kimi"
    assert shared_target.shell == "bash"
    assert shared_target.shell_login is True
    assert shared_target.shell_interactive is True
    assert shared_target.shell_init == ["command -v kimi >/dev/null 2>&1", "kimi"]
    assert shared_target.cwd == "shared-work"

    assert plain_target.bootstrap is None
    assert plain_target.shell is None
    assert plain_target.shell_login is False
    assert plain_target.shell_interactive is False
    assert plain_target.shell_init is None
    assert plain_target.cwd == "shared-work"


def test_pipeline_validation_opt_out_drops_customized_kimi_shell_defaults():
    pipeline = PipelineSpec.model_validate(
        {
            "name": "local-bootstrap-custom-opt-out",
            "working_dir": ".",
            "local_target_defaults": LocalTarget.model_validate(
                {
                    "bootstrap": "kimi",
                    "cwd": "shared-work",
                    "shell_init": ["export EXTRA_FLAG=1"],
                }
            ),
            "nodes": [
                {"id": "shared", "agent": "claude", "prompt": "shared"},
                {
                    "id": "plain",
                    "agent": "codex",
                    "prompt": "plain",
                    "target": {"bootstrap": None},
                },
            ],
        }
    )

    shared_target = pipeline.nodes[0].target
    plain_target = pipeline.nodes[1].target

    assert shared_target.bootstrap == "kimi"
    assert shared_target.shell == "bash"
    assert shared_target.shell_login is True
    assert shared_target.shell_interactive is True
    assert shared_target.shell_init == [
        "export EXTRA_FLAG=1",
        "command -v kimi >/dev/null 2>&1",
        "kimi",
    ]
    assert shared_target.cwd == "shared-work"

    assert plain_target.bootstrap is None
    assert plain_target.shell is None
    assert plain_target.shell_login is False
    assert plain_target.shell_interactive is False
    assert plain_target.shell_init is None
    assert plain_target.cwd == "shared-work"


@pytest.mark.parametrize(
    ("target_patch", "expected_message"),
    [
        (
            {"bootstrap": "kimi", "shell": "sh"},
            r"target\.bootstrap: kimi.*requires bash-style shell bootstrap.*target\.shell.*`sh`",
        ),
        (
            {"bootstrap": "kimi", "shell": "bash", "shell_interactive": False},
            r"target\.bootstrap: kimi.*requires interactive bash startup",
        ),
        (
            {"bootstrap": "kimi", "shell": "bash --noprofile -lic '{command}'"},
            r"target\.bootstrap: kimi.*--noprofile",
        ),
        (
            {"bootstrap": "kimi", "shell": "bash --norc -ic '{command}'", "shell_login": False},
            r"target\.bootstrap: kimi.*--norc",
        ),
    ],
)
def test_pipeline_validation_rejects_incompatible_kimi_bootstrap_overrides(target_patch, expected_message):
    with pytest.raises(ValueError, match=expected_message):
        PipelineSpec.model_validate(
            {
                "name": "invalid-kimi-bootstrap-override",
                "working_dir": ".",
                "nodes": [
                    {
                        "id": "review",
                        "agent": "claude",
                        "prompt": "review",
                        "target": {"kind": "local", **target_patch},
                    },
                ],
            }
        )


def test_pipeline_validation_rejects_non_bash_shell_overriding_local_kimi_bootstrap_defaults():
    with pytest.raises(ValueError, match=r"target\.bootstrap: kimi.*requires bash-style shell bootstrap.*`sh`"):
        PipelineSpec.model_validate(
            {
                "name": "invalid-kimi-bootstrap-default-override",
                "working_dir": ".",
                "local_target_defaults": {
                    "bootstrap": "kimi",
                },
                "nodes": [
                    {
                        "id": "review",
                        "agent": "claude",
                        "prompt": "review",
                        "target": {"kind": "local", "shell": "sh"},
                    },
                ],
            }
        )


def test_pipeline_validation_rejects_unknown_local_bootstrap():
    with pytest.raises(ValidationError, match=r"target\.bootstrap.*must be `kimi`"):
        PipelineSpec.model_validate(
            {
                "name": "invalid-local-bootstrap",
                "working_dir": ".",
                "nodes": [
                    {
                        "id": "plan",
                        "agent": "claude",
                        "prompt": "plan",
                        "target": {"kind": "local", "bootstrap": "other"},
                    },
                ],
            }
        )


def test_pipeline_validation_accepts_shell_init_command_lists():
    pipeline = PipelineSpec.model_validate(
        {
            "name": "valid-shell-init-list",
            "working_dir": ".",
            "nodes": [
                {
                    "id": "plan",
                    "agent": "claude",
                    "prompt": "plan",
                    "target": {
                        "kind": "local",
                        "shell": "bash",
                        "shell_init": [" command -v kimi >/dev/null 2>&1 ", " kimi "],
                    },
                },
            ],
        }
    )

    assert pipeline.nodes[0].target.shell_init == ["command -v kimi >/dev/null 2>&1", "kimi"]


def test_pipeline_validation_rejects_empty_shell_init_list_entries():
    with pytest.raises(ValidationError, match="non-empty strings"):
        PipelineSpec.model_validate(
            {
                "name": "invalid-shell-init-list",
                "working_dir": ".",
                "nodes": [
                    {
                        "id": "plan",
                        "agent": "claude",
                        "prompt": "plan",
                        "target": {
                            "kind": "local",
                            "shell": "bash",
                            "shell_init": ["kimi", "   "],
                        },
                    },
                ],
            }
        )


@pytest.mark.parametrize(
    ("mcp_patch", "expected_message"),
    [
        ({"transport": "stdio"}, "stdio MCP servers require `command`"),
        (
            {"transport": "stdio", "command": "npx", "url": "https://example.com/mcp"},
            "stdio MCP servers do not support `url`",
        ),
        ({"transport": "streamable_http"}, "streamable_http MCP servers require `url`"),
        (
            {"transport": "streamable_http", "url": "https://example.com/mcp", "command": "npx"},
            "streamable_http MCP servers do not support `command`",
        ),
    ],
)
def test_pipeline_validation_rejects_invalid_mcp_server_shape(mcp_patch, expected_message):
    with pytest.raises(ValueError, match=expected_message):
        PipelineSpec.model_validate(
            {
                "name": "invalid-mcp-shape",
                "working_dir": ".",
                "nodes": [
                    {
                        "id": "plan",
                        "agent": "claude",
                        "prompt": "plan",
                        "mcps": [{"name": "github", **mcp_patch}],
                    },
                ],
            }
        )


def test_pipeline_validation_rejects_duplicate_mcp_server_names():
    with pytest.raises(ValueError, match="duplicate MCP server names"):
        PipelineSpec.model_validate(
            {
                "name": "duplicate-mcps",
                "working_dir": ".",
                "nodes": [
                    {
                        "id": "plan",
                        "agent": "claude",
                        "prompt": "plan",
                        "mcps": [
                            {"name": "github", "command": "npx"},
                            {"name": "github", "command": "node"},
                        ],
                    },
                ],
            }
        )


@pytest.mark.parametrize(
    ("pipeline_patch", "node_patch", "expected_loc", "expected_type"),
    [
        ({"concurrency": 0}, {}, ("concurrency",), "greater_than_equal"),
        ({}, {"timeout_seconds": 0}, ("nodes", 0, "timeout_seconds"), "greater_than"),
        ({}, {"retries": -1}, ("nodes", 0, "retries"), "greater_than_equal"),
        ({}, {"retry_backoff_seconds": -0.1}, ("nodes", 0, "retry_backoff_seconds"), "greater_than_equal"),
    ],
)
def test_pipeline_validation_rejects_invalid_numeric_runtime_settings(
    pipeline_patch,
    node_patch,
    expected_loc,
    expected_type,
):
    payload = {
        "name": "invalid-runtime-settings",
        "working_dir": ".",
        "nodes": [
            {
                "id": "plan",
                "agent": "codex",
                "prompt": "plan",
                **node_patch,
            }
        ],
        **pipeline_patch,
    }

    with pytest.raises(ValidationError) as exc_info:
        PipelineSpec.model_validate(payload)

    assert exc_info.value.errors()[0]["loc"] == expected_loc
    assert exc_info.value.errors()[0]["type"] == expected_type


@pytest.mark.asyncio
async def test_store_loads_runs_and_artifacts_from_disk(tmp_path):
    pipeline = PipelineSpec.model_validate(
        {
            "name": "persisted",
            "working_dir": str(tmp_path),
            "nodes": [{"id": "alpha", "agent": "codex", "prompt": "hi"}],
        }
    )
    original = RunStore(tmp_path / "runs")
    record = RunRecord(id="run-1", pipeline=pipeline)
    await original.create_run(record)
    await original.append_event("run-1", RunEvent(run_id="run-1", type="run_started"))
    await original.write_artifact_text("run-1", "alpha", "output.txt", "hello persisted")

    reloaded = RunStore(tmp_path / "runs")
    assert reloaded.get_run("run-1").pipeline.name == "persisted"
    assert reloaded.get_events("run-1")[0].type == "run_started"
    assert reloaded.read_artifact_text("run-1", "alpha", "output.txt") == "hello persisted"


def test_store_expands_user_in_base_dir(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    store = RunStore("~/agentflow-runs")

    assert store.base_dir == home / "agentflow-runs"
    assert store.base_dir.exists()
