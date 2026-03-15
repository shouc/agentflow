# Examples Guide

Use this page to choose a starter without reading every bundled YAML file.

## Maintainer sweeps

| Starter | Use it when | Key features |
| --- | --- | --- |
| `codex-fanout-repo-sweep` | You want a small repo review fanout and a simple merge. | 8 Codex shards, one planning step, one final reducer. |
| `codex-repo-sweep-batched` | You want a large repo audit or review sweep that should scale to 64 or 128 shards without producing one unreadable final merge. | `node_defaults`, `agent_defaults`, `fanout.batches`, staged reducers. |

## Fuzzing swarms

| Starter | Use it when | Key features |
| --- | --- | --- |
| `codex-fuzz-swarm` | The campaign is homogeneous and you only need a single final reducer. | `fanout.count`, shared init, resize with `--set shards=...`. |
| `codex-fuzz-batched` | The campaign is homogeneous, but a single reducer would be too noisy. | `fanout.batches`, `current.scope`, scoped intermediate reducers. |
| `codex-fuzz-matrix` | The shard roster is a clean cartesian product. | `fanout.matrix`. |
| `codex-fuzz-matrix-derived` | The matrix also needs reusable labels or workdirs. | `fanout.derive`. |
| `codex-fuzz-matrix-curated` | The matrix is mostly regular, but you need a few exclusions or bespoke shards. | `fanout.exclude`, `fanout.include`, `fanout.derive`. |
| `codex-fuzz-matrix-manifest` | The matrix axes should live outside the main pipeline file, but you still want a realistic preset to start from. | `fanout.matrix_path`, rendered support manifest, `preset=...` scaffolding. |
| `codex-fuzz-preset-batched` | You want a preset-backed 128-shard campaign to stay in one YAML file without sidecar manifests. | `fanout.preset`, `fanout.batches`, preset-driven `label` / `workspace`. |
| `codex-fuzz-catalog` | Every shard needs explicit per-row metadata that is awkward to derive, but you want a preset-generated CSV as the starting point. | `fanout.values_path`, rendered CSV catalog, `preset=...` scaffolding. |
| `codex-fuzz-catalog-batched` | Every shard needs explicit per-row metadata, but reducer families are not meaningful. | `fanout.values_path`, `fanout.batches`, rendered CSV catalog, `preset=...` scaffolding. |
| `codex-fuzz-hierarchical-grouped` | Reducer families should be derived automatically from shard metadata. | `fanout.group_by`, `current.scope`, scoped reducers from the shard fanout, `preset=...` scaffolding. |
| `codex-fuzz-hierarchical-manifest` | Reducer families should stay in a maintainer-owned sidecar roster. | `fanout.matrix_path` plus `values_path`, `preset=...` scaffolding. |

The fixed `*-128` examples are reference snapshots when you want to inspect a full large DAG directly from the repo instead of rendering one with `agentflow init`. That now includes the browser-oriented [`codex-fuzz-browser-128`](../examples/fuzz/codex-fuzz-browser-128.yaml) reference.

## Python DAGs

| Example | Use it when | Key features |
| --- | --- | --- |
| `airflow_like.py` | You want the smallest Python-authored DAG reference. | Static dependencies with `plan >> [implement, review]`. |
| `airflow_like_fuzz_batched.py` | You want a 128-shard Codex swarm authored from Python instead of YAML templates. | `DAG(node_defaults=..., agent_defaults=..., fail_fast=...)`, `fanout_count(...)`, `fanout_batches(...)`, `dag.to_yaml()`. |
| `airflow_like_fuzz_campaign.py` | You want the shortest preset-backed Python path to a production-shaped 128-shard Codex campaign. | `codex_fuzz_campaign(...)`, built-in `protocol-stack` roster, grouped reducers, one helper call. |
| `airflow_like_fuzz_preset_batched.py` | You want a preset-backed 128-shard Codex campaign from Python without rewriting the full matrix axes. | `codex_fuzz_campaign_matrix(...)`, built-in `browser-surface` roster, `fanout_batches(...)`, `dag.to_yaml()`. |
| `airflow_like_fuzz_catalog_batched.py` | You want a 128-shard Python DAG backed by a CSV shard catalog plus neutral staged reducers. | `fanout_values_path(...)`, `fanout_batches(...)`, `dag.to_yaml()`. |
| `airflow_like_fuzz_grouped.py` | You want a 128-shard grouped Codex campaign from Python with reducer-local summaries. | `fanout_matrix(...)`, `fanout_group_by(...)`, `current.scope`. |

## Local smoke flows

| Starter | Use it when | Key features |
| --- | --- | --- |
| `local-kimi-smoke` | You want the shortest real-agent local smoke path. | `bootstrap: kimi`. |
| `local-kimi-shell-init-smoke` | You want the explicit shell-init equivalent of the bundled smoke. | `shell: bash`, `shell_login`, `shell_interactive`, `shell_init: kimi`. |
| `local-kimi-shell-wrapper-smoke` | You want the same flow expressed as an explicit shell wrapper. | `target.shell` wrapper with `{command}` injection. |

## Practical rules

- Start with `codex-fanout-repo-sweep` for small repo reviews and move to `codex-repo-sweep-batched` once you need 32+ Codex workers or staged reducers.
- Start with `codex-fuzz-swarm` for homogeneous campaigns, then move to `codex-fuzz-batched` when the final reducer becomes too large to read.
- Use `codex-fuzz-preset-batched` when the roster already matches a built-in preset and you want the 128-shard staged-reducer shape without maintaining sidecar manifests.
- Use the matrix starters when shard metadata is derivable, and use the catalog starters when every shard needs explicit maintainer-owned metadata.
- Use `agentflow template-presets` plus `--set preset=...` when you want a realistic starting roster such as `browser-surface` or `protocol-stack` before hand-tuning the generated manifests or CSV files.
- Use `airflow_like_fuzz_campaign.py` when you want the helper to register the whole preset-backed campaign shape for you instead of wiring `init`, `fuzzer`, reducers, and `merge` by hand.
- Use `airflow_like_fuzz_preset_batched.py` when you want those same preset rosters directly from Python instead of going through a rendered YAML scaffold first.
- Use `codex-fuzz-catalog-batched` when the catalog rows need intermediate reducers but there is no stable family field worth grouping on.
- Prefer the manifest-backed starters when the shard roster or reducer roster should live in sidecar files that non-authors can edit.
