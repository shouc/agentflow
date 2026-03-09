#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
python_bin="${AGENTFLOW_PYTHON:-}"

if [ -z "$python_bin" ]; then
  if [ -x "$repo_root/.venv/bin/python" ]; then
    python_bin="$repo_root/.venv/bin/python"
  else
    python_bin="python3"
  fi
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

pipeline_path="$tmpdir/custom-kimi-smoke.yaml"
cat >"$pipeline_path" <<'YAML'
name: custom-kimi-smoke
description: Temporary external real-agent smoke test for local Codex plus Claude-on-Kimi.
working_dir: .
concurrency: 2
local_target_defaults:
  bootstrap: kimi
nodes:
  - id: codex_plan
    agent: codex
    env:
      OPENAI_BASE_URL: ""
    prompt: |
      Reply with exactly: codex ok
    timeout_seconds: 180
    success_criteria:
      - kind: output_contains
        value: codex ok

  - id: claude_review
    agent: claude
    provider: kimi
    prompt: |
      Reply with exactly: claude ok
    timeout_seconds: 180
    success_criteria:
      - kind: output_contains
        value: claude ok
YAML

printf "custom pipeline path: %s\n" "$pipeline_path"

(
  cd "$repo_root"
  "$python_bin" -m agentflow check-local "$pipeline_path" --output summary
)
