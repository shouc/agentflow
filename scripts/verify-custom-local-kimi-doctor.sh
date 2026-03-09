#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
. "$script_dir/custom-local-kimi-helpers.sh"

python_bin="$(agentflow_repo_python "$repo_root")"

tmpdir="$(mktemp -d)"
stdout_path="$tmpdir/doctor.stdout"

cleanup() {
  local exit_code=$?
  trap - EXIT
  if [ "$exit_code" -eq 0 ]; then
    rm -rf "$tmpdir"
    return
  fi

  if [ -f "$stdout_path" ]; then
    printf "\nagentflow doctor stdout:\n" >&2
    sed -n '1,240p' "$stdout_path" >&2
  fi
  printf "\nkept tempdir for debugging: %s\n" "$tmpdir" >&2
}

trap cleanup EXIT

pipeline_path="$tmpdir/custom-kimi-doctor.yaml"
write_custom_local_kimi_pipeline \
  "$pipeline_path" \
  "custom-kimi-doctor" \
  "Temporary external doctor test for local Codex plus Claude-on-Kimi."

printf "custom doctor pipeline path: %s\n" "$pipeline_path"

(
  cd "$repo_root"
  "$python_bin" -m agentflow doctor "$pipeline_path" --output summary >"$stdout_path"
)

STDOUT_PATH="$stdout_path" "$python_bin" - <<'PY'
import os
from pathlib import Path

stdout_path = Path(os.environ["STDOUT_PATH"])
stdout_text = stdout_path.read_text(encoding="utf-8")

required_fragments = (
    "Doctor: ok",
    "- bash_login_startup: ok - ",
    "- kimi_shell_helper: ok - `kimi` is available in `bash -lic`, exports `ANTHROPIC_API_KEY`, and sets `ANTHROPIC_BASE_URL=https://api.kimi.com/coding/`.",
    "- claude_ready: ok - Node `claude_review` (claude) can launch local Claude after the node shell bootstrap; `claude --version` succeeds in the prepared local shell.",
    "- codex_ready: ok - Node `codex_plan` (codex) can launch local Codex after the node shell bootstrap; `codex --version` succeeds in the prepared local shell.",
    "- codex_auth: ok - Node `codex_plan` (codex) can authenticate local Codex after the node shell bootstrap via `codex login status` or `OPENAI_API_KEY`.",
    "- launch_env_override: ok - Node `codex_plan`: Launch env clears current `OPENAI_BASE_URL` value ",
    "- launch_env_override: ok - Node `claude_review`: Launch env uses configured `ANTHROPIC_BASE_URL` value `https://api.kimi.com/coding/`",
    "- bootstrap_env_override: ok - Node `claude_review`: Local shell bootstrap overrides current `ANTHROPIC_API_KEY` for this node via `target.bootstrap` (`kimi` helper).",
    "Pipeline auto preflight: enabled - local Codex/Claude/Kimi nodes use a `kimi` shell bootstrap.",
    "Pipeline auto preflight matches: codex_plan (codex) via `target.bootstrap`, claude_review (claude) via `target.bootstrap`",
)

for fragment in required_fragments:
    if fragment not in stdout_text:
        raise SystemExit(f"Missing doctor fragment {fragment!r}.\n--- stdout ---\n{stdout_text}")

print("validated agentflow doctor summary for external custom pipeline")
PY
