"""Python DSL helpers for building AgentFlow pipelines."""

from __future__ import annotations

from copy import deepcopy
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
import json
from types import TracebackType
from typing import Any

from agentflow.specs import AgentKind, LocalTarget, NodeSpec, PipelineSpec


_CURRENT_DAG: ContextVar["DAG | None"] = ContextVar("_CURRENT_DAG", default=None)


@dataclass
class NodeBuilder:
    dag: "DAG"
    id: str
    agent: AgentKind
    prompt: str
    kwargs: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.dag._register(self)

    def __repr__(self) -> str:
        return f"NodeBuilder(id={json.dumps(self.id)}, agent={json.dumps(self.agent.value)})"

    def __rshift__(self, other: "NodeBuilder | list[NodeBuilder]") -> "NodeBuilder | list[NodeBuilder]":
        if isinstance(other, list):
            for item in other:
                item.depends_on.append(self.id)
            return other
        other.depends_on.append(self.id)
        return other

    def __rrshift__(self, other: list["NodeBuilder"]) -> "NodeBuilder":
        if isinstance(other, list):
            for item in other:
                self.depends_on.append(item.id)
            return self
        raise TypeError(f"unsupported dependency source {type(other)!r}")

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent": self.agent,
            "prompt": self.prompt,
            "depends_on": list(self.depends_on),
            **_normalize_node_kwargs(self.kwargs),
        }

    def to_spec(self) -> NodeSpec:
        return NodeSpec.model_validate(self.to_payload())


class DAG:
    def __init__(
        self,
        name: str,
        *,
        description: str | None = None,
        working_dir: str = ".",
        concurrency: int = 4,
        fail_fast: bool = False,
        node_defaults: dict[str, Any] | None = None,
        agent_defaults: dict[str | AgentKind, dict[str, Any]] | None = None,
        local_target_defaults: dict[str, Any] | LocalTarget | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.working_dir = working_dir
        self.concurrency = concurrency
        self.fail_fast = fail_fast
        self.node_defaults = node_defaults
        self.agent_defaults = agent_defaults
        self.local_target_defaults = local_target_defaults
        self._nodes: dict[str, NodeBuilder] = {}
        self._token: Token[DAG | None] | None = None

    def __repr__(self) -> str:
        return f"DAG(name={json.dumps(self.name)}, nodes={len(self._nodes)})"

    def __enter__(self) -> "DAG":
        self._token = _CURRENT_DAG.set(self)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._token is not None:
            _CURRENT_DAG.reset(self._token)

    def _register(self, node: NodeBuilder) -> None:
        if node.id in self._nodes:
            raise ValueError(f"node {node.id!r} already exists")
        self._nodes[node.id] = node

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
        }
        if self.description is not None:
            payload["description"] = self.description
        payload["working_dir"] = self.working_dir
        payload["concurrency"] = self.concurrency
        payload["fail_fast"] = self.fail_fast
        if self.node_defaults is not None:
            payload["node_defaults"] = _normalize_node_defaults(self.node_defaults)
        if self.agent_defaults:
            payload["agent_defaults"] = _normalize_agent_defaults(self.agent_defaults)
        if self.local_target_defaults is not None:
            payload["local_target_defaults"] = self.local_target_defaults
        payload["nodes"] = [node.to_payload() for node in self._nodes.values()]
        return payload

    def to_spec(self) -> PipelineSpec:
        return PipelineSpec.model_validate(self.to_payload())

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_payload(), indent=indent)


def _normalize_local_target(value: Any) -> Any:
    if not isinstance(value, dict):
        return deepcopy(value)
    if "kind" in value:
        return deepcopy(value)
    return {"kind": "local", **deepcopy(value)}


def _normalize_node_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    if "target" not in kwargs:
        return deepcopy(kwargs)

    normalized = deepcopy({key: value for key, value in kwargs.items() if key != "target"})
    normalized["target"] = _normalize_local_target(kwargs["target"])
    return normalized


def _normalize_node_defaults(defaults: dict[str, Any] | None) -> dict[str, Any] | None:
    if defaults is None:
        return None
    return _normalize_node_kwargs(defaults)


def _normalize_agent_defaults(
    defaults: dict[str | AgentKind, dict[str, Any]] | None,
) -> dict[str | AgentKind, dict[str, Any]] | None:
    if defaults is None:
        return None
    return {
        agent: _normalize_node_kwargs(agent_defaults)
        for agent, agent_defaults in defaults.items()
    }


def _current_dag() -> DAG:
    dag = _CURRENT_DAG.get()
    if dag is None:
        raise RuntimeError("No active DAG context. Use `with DAG(...):`.")
    return dag


def _node(agent: AgentKind, *, task_id: str, prompt: str, **kwargs: Any) -> NodeBuilder:
    return NodeBuilder(dag=_current_dag(), id=task_id, agent=agent, prompt=prompt, kwargs=kwargs)


# ---------------------------------------------------------------------------
# Fanout & merge
# ---------------------------------------------------------------------------


def fanout(
    node: NodeBuilder,
    source: int | list[Any] | dict[str, list[Any]],
    *,
    derive: dict[str, Any] | None = None,
    include: list[dict[str, Any]] | None = None,
    exclude: list[dict[str, Any]] | None = None,
) -> NodeBuilder:
    """Fan a node out into many parallel copies.

    *source* selects the expansion mode:

    - ``int``  -- uniform count  (``fanout(node, 128)``)
    - ``list`` -- explicit values (``fanout(node, [{"repo": "api"}, ...])``)
    - ``dict`` -- cartesian matrix (``fanout(node, {"axis": [...], ...})``)

    Every expanded copy gets an ``item`` template variable with these fields:

    ======== ===== ============================================
    Field    Type  Example
    ======== ===== ============================================
    index    int   0, 1, 2, ...
    number   int   1, 2, 3, ... (1-indexed)
    count    int   total copies
    suffix   str   "0", "01", "001" (zero-padded)
    node_id  str   "fuzzer_001"
    value    Any   the raw iteration value
    *(keys)* Any   dict keys from value are lifted
    *(keys)* Any   keys from *derive* are added
    ======== ===== ============================================

    Use ``{{ item.number }}``, ``{{ item.suffix }}``, etc. in prompts
    and target paths.
    """
    if isinstance(source, int):
        mode: dict[str, Any] = {"count": source}
    elif isinstance(source, list):
        mode = {"values": deepcopy(source)}
    elif isinstance(source, dict):
        mode = {"matrix": deepcopy(source)}
    else:
        raise TypeError(f"fanout source must be int, list, or dict; got {type(source).__name__}")

    if include is not None and not isinstance(source, dict):
        raise TypeError("include is only valid for matrix fanout (dict source)")
    if exclude is not None and not isinstance(source, dict):
        raise TypeError("exclude is only valid for matrix fanout (dict source)")

    payload: dict[str, Any] = {"as": "item", **mode}
    if derive is not None:
        payload["derive"] = deepcopy(derive)
    if include is not None:
        payload["include"] = deepcopy(include)
    if exclude is not None:
        payload["exclude"] = deepcopy(exclude)
    node.kwargs["fanout"] = payload
    return node


def merge(
    node: NodeBuilder,
    source: NodeBuilder,
    *,
    by: list[str] | None = None,
    size: int | None = None,
    derive: dict[str, Any] | None = None,
) -> NodeBuilder:
    """Merge (reduce) the results of a prior fanout group.

    Exactly one of *by* or *size* must be given:

    - ``by=["field", ...]`` -- one reducer per unique field combination
    - ``size=N`` -- one reducer per N-item batch

    The ``item`` template variable has all the same fields as a fanout
    ``item``, plus these reducer-specific fields:

    ============= ====== ============================================
    Field         Type   Description
    ============= ====== ============================================
    source_group  str    task_id of the fanout being reduced
    source_count  int    total members in the source fanout
    member_ids    list   node IDs of the members in this group/batch
    members       list   full member objects
    size          int    members in this group/batch
    ============= ====== ============================================

    With ``by=``, the grouping field values are also on ``item``
    (e.g. ``{{ item.target }}``).

    With ``size=``, batch range fields are added:
    ``start_number``, ``end_number``, ``start_index``, ``end_index``,
    ``start_suffix``, ``end_suffix``.

    At runtime, ``item.scope`` provides the aggregated results of the
    source members in this group/batch:

    ============== ====== ============================================
    Field          Type   Description
    ============== ====== ============================================
    scope.ids      list   member node IDs
    scope.size     int    count
    scope.nodes    list   full member objects with status/output
    scope.outputs  list   output strings
    scope.summary  dict   {total, completed, failed, with_output, ...}
    scope.with_output    subset with non-empty output
    scope.without_output subset with empty output
    ============== ====== ============================================

    Use ``{{ item.scope.with_output.nodes }}`` in Jinja2 loops to
    iterate over completed source members.
    """
    if by is not None and size is not None:
        raise TypeError("specify either by= or size=, not both")

    if by is not None:
        mode: dict[str, Any] = {"group_by": {"from": source.id, "fields": list(by)}}
    elif size is not None:
        mode = {"batches": {"from": source.id, "size": size}}
    else:
        raise TypeError("merge() requires either by= or size=")

    payload: dict[str, Any] = {"as": "item", **mode}
    if derive is not None:
        payload["derive"] = deepcopy(derive)
    node.kwargs["fanout"] = payload
    return node


# ---------------------------------------------------------------------------
# Agent helpers
# ---------------------------------------------------------------------------


def codex(*, task_id: str, prompt: str, **kwargs: Any) -> NodeBuilder:
    return _node(AgentKind.CODEX, task_id=task_id, prompt=prompt, **kwargs)


def claude(*, task_id: str, prompt: str, **kwargs: Any) -> NodeBuilder:
    return _node(AgentKind.CLAUDE, task_id=task_id, prompt=prompt, **kwargs)


def kimi(*, task_id: str, prompt: str, **kwargs: Any) -> NodeBuilder:
    return _node(AgentKind.KIMI, task_id=task_id, prompt=prompt, **kwargs)
