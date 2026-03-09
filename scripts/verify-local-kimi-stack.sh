#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
. "$script_dir/custom-local-kimi-helpers.sh"
python_bin="$(agentflow_repo_python "$repo_root")"
bundled_smoke_pipeline="$repo_root/examples/local-real-agents-kimi-smoke.yaml"
bundled_shell_init_pipeline="$repo_root/examples/local-real-agents-kimi-shell-init-smoke.yaml"
bundled_shell_wrapper_pipeline="$repo_root/examples/local-real-agents-kimi-shell-wrapper-smoke.yaml"

run_step() {
  local label="$1"
  shift

  printf "\n== %s ==\n" "$label"
  "$@"
}

run_bundled_run_step() {
  local label_suffix="$1"
  local pipeline_path="$2"
  local pipeline_name="$3"
  local expected_trigger="$4"
  local expected_auto_preflight_reason="$5"

  run_step "Bundled run-local${label_suffix}" env \
    AGENTFLOW_BUNDLED_PIPELINE_PATH="$pipeline_path" \
    AGENTFLOW_BUNDLED_PIPELINE_NAME="$pipeline_name" \
    AGENTFLOW_BUNDLED_EXPECTED_TRIGGER="$expected_trigger" \
    AGENTFLOW_BUNDLED_EXPECTED_AUTO_PREFLIGHT_REASON="$expected_auto_preflight_reason" \
    bash "$script_dir/verify-bundled-local-kimi-run.sh"
}

run_step "Shell toolchain" bash "$script_dir/verify-local-kimi-shell.sh"
run_step "Bundled toolchain-local" agentflow_run_with_timeout "$python_bin" "$python_bin" -m agentflow toolchain-local --output summary
run_step "Bundled inspect-local" agentflow_run_with_timeout "$python_bin" "$python_bin" -m agentflow inspect "$bundled_smoke_pipeline" --output summary
run_step "Bundled doctor-local" agentflow_run_with_timeout "$python_bin" "$python_bin" -m agentflow doctor "$bundled_smoke_pipeline" --output summary
run_step "Bundled smoke-local" agentflow_run_with_timeout "$python_bin" "$python_bin" -m agentflow smoke "$bundled_smoke_pipeline" --output summary
run_bundled_run_step "" \
  "$bundled_smoke_pipeline" \
  "local-real-agents-kimi-smoke" \
  "target.bootstrap" \
  "path matches the bundled real-agent smoke pipeline."
run_step "Bundled inspect-local (shell_init)" agentflow_run_with_timeout "$python_bin" "$python_bin" -m agentflow inspect "$bundled_shell_init_pipeline" --output summary
run_step "Bundled doctor-local (shell_init)" agentflow_run_with_timeout "$python_bin" "$python_bin" -m agentflow doctor "$bundled_shell_init_pipeline" --output summary
run_step "Bundled smoke-local (shell_init)" agentflow_run_with_timeout "$python_bin" "$python_bin" -m agentflow smoke "$bundled_shell_init_pipeline" --output summary
run_bundled_run_step " (shell_init)" \
  "$bundled_shell_init_pipeline" \
  "local-real-agents-kimi-shell-init-smoke" \
  "target.shell_init" \
  'local Codex/Claude/Kimi nodes use a `kimi` shell bootstrap.'
run_step "Bundled inspect-local (target.shell)" agentflow_run_with_timeout "$python_bin" "$python_bin" -m agentflow inspect "$bundled_shell_wrapper_pipeline" --output summary
run_step "Bundled doctor-local (target.shell)" agentflow_run_with_timeout "$python_bin" "$python_bin" -m agentflow doctor "$bundled_shell_wrapper_pipeline" --output summary
run_step "Bundled smoke-local (target.shell)" agentflow_run_with_timeout "$python_bin" "$python_bin" -m agentflow smoke "$bundled_shell_wrapper_pipeline" --output summary
run_bundled_run_step " (target.shell)" \
  "$bundled_shell_wrapper_pipeline" \
  "local-real-agents-kimi-shell-wrapper-smoke" \
  "target.shell" \
  'local Codex/Claude/Kimi nodes use a `kimi` shell bootstrap.'
run_step "External custom doctor" bash "$script_dir/verify-custom-local-kimi-doctor.sh"
run_step "External custom doctor (shell_init)" env AGENTFLOW_KIMI_PIPELINE_MODE=shell-init bash "$script_dir/verify-custom-local-kimi-doctor.sh"
run_step "External custom doctor (target.shell)" env AGENTFLOW_KIMI_PIPELINE_MODE=shell-wrapper bash "$script_dir/verify-custom-local-kimi-doctor.sh"
run_step "External custom inspect" bash "$script_dir/verify-custom-local-kimi-inspect.sh"
run_step "External custom inspect (shell_init)" env AGENTFLOW_KIMI_PIPELINE_MODE=shell-init bash "$script_dir/verify-custom-local-kimi-inspect.sh"
run_step "External custom inspect (target.shell)" env AGENTFLOW_KIMI_PIPELINE_MODE=shell-wrapper bash "$script_dir/verify-custom-local-kimi-inspect.sh"
run_step "Bundled check-local" agentflow_run_with_timeout "$python_bin" "$python_bin" -m agentflow check-local --output summary
run_step "External custom check-local" bash "$script_dir/verify-custom-local-kimi-pipeline.sh"
run_step "External custom check-local (shell_init)" bash "$script_dir/verify-custom-local-kimi-shell-init.sh"
run_step "External custom check-local (target.shell)" env AGENTFLOW_KIMI_PIPELINE_MODE=shell-wrapper bash "$script_dir/verify-custom-local-kimi-pipeline.sh"
run_step "External custom run" bash "$script_dir/verify-custom-local-kimi-run.sh"
run_step "External custom run (shell_init)" env AGENTFLOW_KIMI_PIPELINE_MODE=shell-init bash "$script_dir/verify-custom-local-kimi-run.sh"
run_step "External custom run (target.shell)" env AGENTFLOW_KIMI_PIPELINE_MODE=shell-wrapper bash "$script_dir/verify-custom-local-kimi-run.sh"
