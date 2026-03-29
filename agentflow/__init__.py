"""AgentFlow public package surface."""

from agentflow.dsl import (
    DAG,
    claude,
    codex,
    fanout,
    kimi,
    merge,
)


def create_app(*args, **kwargs):
    from agentflow.app import create_app as _create_app

    return _create_app(*args, **kwargs)


__all__ = [
    "DAG",
    "claude",
    "codex",
    "fanout",
    "kimi",
    "merge",
    "create_app",
]
