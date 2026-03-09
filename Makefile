.DEFAULT_GOAL := help

.PHONY: help test inspect-local doctor-local smoke-local run-local check-local toolchain-local doctor-local-custom doctor-local-custom-shell-init doctor-local-custom-shell-wrapper inspect-local-custom inspect-local-custom-shell-init inspect-local-custom-shell-wrapper check-local-custom check-local-custom-shell-init check-local-custom-shell-wrapper run-local-custom run-local-custom-shell-init run-local-custom-shell-wrapper verify-local

PYTHON := $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

help:
	@printf '%s\n' \
	  'Available targets:' \
	  '  python        Print the Python interpreter used by repo shortcuts (.venv/bin/python when available, else python3)' \
	  '  test          Run the Python test suite' \
	  '  toolchain-local Run `agentflow toolchain-local --output summary` for the local bash/Kimi/Codex/Claude readiness check' \
	  '  verify-local  Run the full local Codex + Claude-on-Kimi verification stack across bundled bootstrap/shell_init/target.shell inspect/doctor/smoke/run coverage, bundled toolchain-local/check-local, plus external custom doctor, inspect, check-local, and run paths (shared timeout via AGENTFLOW_LOCAL_VERIFY_TIMEOUT_SECONDS)' \
	  '  doctor-local-custom Verify a temporary external Codex + Claude-on-Kimi pipeline through `agentflow doctor`' \
	  '  doctor-local-custom-shell-init Verify a temporary external Codex + Claude-on-Kimi `shell_init: kimi` pipeline through `agentflow doctor`' \
	  '  doctor-local-custom-shell-wrapper Verify a temporary external Codex + Claude-on-Kimi `target.shell` wrapper pipeline through `agentflow doctor`' \
	  '  inspect-local-custom Verify a temporary external Codex + Claude-on-Kimi pipeline through `agentflow inspect`' \
	  '  inspect-local-custom-shell-init Verify a temporary external Codex + Claude-on-Kimi `shell_init: kimi` pipeline through `agentflow inspect`' \
	  '  inspect-local-custom-shell-wrapper Verify a temporary external Codex + Claude-on-Kimi `target.shell` wrapper pipeline through `agentflow inspect`' \
	  '  check-local-custom Verify a temporary external Codex + Claude-on-Kimi pipeline through `agentflow check-local`' \
	  '  check-local-custom-shell-init Verify a temporary external Codex + Claude-on-Kimi `shell_init: kimi` pipeline through `agentflow check-local`' \
	  '  check-local-custom-shell-wrapper Verify a temporary external Codex + Claude-on-Kimi `target.shell` wrapper pipeline through `agentflow check-local`' \
	  '  run-local-custom Verify a temporary external Codex + Claude-on-Kimi pipeline through `agentflow run`' \
	  '  run-local-custom-shell-init Verify a temporary external Codex + Claude-on-Kimi `shell_init: kimi` pipeline through `agentflow run`' \
	  '  run-local-custom-shell-wrapper Verify a temporary external Codex + Claude-on-Kimi `target.shell` wrapper pipeline through `agentflow run`' \
	  '  inspect-local Inspect the bundled local Kimi-backed smoke pipeline' \
	  '  doctor-local  Check local Codex/Claude/Kimi smoke prerequisites' \
	  '  smoke-local   Run the bundled local Codex + Claude-on-Kimi smoke test' \
	  '  run-local     Run the bundled local Codex + Claude-on-Kimi pipeline through `agentflow run`' \
	  '  check-local   Run the single-pass doctor-then-smoke CLI shortcut with summary output'

python:
	@$(PYTHON) -c "import sys; print(sys.executable)"

test:
	$(PYTHON) -m pytest -q

toolchain-local:
	$(PYTHON) -m agentflow toolchain-local --output summary

verify-local:
	bash scripts/verify-local-kimi-stack.sh

doctor-local-custom:
	bash scripts/verify-custom-local-kimi-doctor.sh

doctor-local-custom-shell-init:
	AGENTFLOW_KIMI_PIPELINE_MODE=shell-init bash scripts/verify-custom-local-kimi-doctor.sh

doctor-local-custom-shell-wrapper:
	AGENTFLOW_KIMI_PIPELINE_MODE=shell-wrapper bash scripts/verify-custom-local-kimi-doctor.sh

inspect-local-custom:
	bash scripts/verify-custom-local-kimi-inspect.sh

inspect-local-custom-shell-init:
	AGENTFLOW_KIMI_PIPELINE_MODE=shell-init bash scripts/verify-custom-local-kimi-inspect.sh

inspect-local-custom-shell-wrapper:
	AGENTFLOW_KIMI_PIPELINE_MODE=shell-wrapper bash scripts/verify-custom-local-kimi-inspect.sh

check-local-custom:
	bash scripts/verify-custom-local-kimi-pipeline.sh

check-local-custom-shell-init:
	bash scripts/verify-custom-local-kimi-shell-init.sh

check-local-custom-shell-wrapper:
	AGENTFLOW_KIMI_PIPELINE_MODE=shell-wrapper bash scripts/verify-custom-local-kimi-pipeline.sh

run-local-custom:
	bash scripts/verify-custom-local-kimi-run.sh

run-local-custom-shell-init:
	AGENTFLOW_KIMI_PIPELINE_MODE=shell-init bash scripts/verify-custom-local-kimi-run.sh

run-local-custom-shell-wrapper:
	AGENTFLOW_KIMI_PIPELINE_MODE=shell-wrapper bash scripts/verify-custom-local-kimi-run.sh

inspect-local:
	$(PYTHON) -m agentflow inspect examples/local-real-agents-kimi-smoke.yaml --output summary

doctor-local:
	$(PYTHON) -m agentflow doctor examples/local-real-agents-kimi-smoke.yaml --output summary

smoke-local:
	$(PYTHON) -m agentflow smoke --show-preflight

run-local:
	$(PYTHON) -m agentflow run examples/local-real-agents-kimi-smoke.yaml --output summary

check-local:
	$(PYTHON) -m agentflow check-local --output summary
