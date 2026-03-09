.DEFAULT_GOAL := help

.PHONY: help test inspect-local doctor-local smoke-local check-local toolchain-local doctor-local-custom doctor-local-custom-shell-init inspect-local-custom inspect-local-custom-shell-init check-local-custom check-local-custom-shell-init run-local-custom run-local-custom-shell-init verify-local

PYTHON := $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

help:
	@printf '%s\n' \
	  'Available targets:' \
	  '  python        Prefer .venv/bin/python when available, else python3' \
	  '  test          Run the Python test suite' \
	  '  toolchain-local Verify `bash -lic` + `kimi` still exposes local codex and claude and report bash startup' \
	  '  verify-local  Run the full local Codex + Claude-on-Kimi verification stack across external doctor, inspect, check-local, and run paths' \
	  '  doctor-local-custom Verify a temporary external Codex + Claude-on-Kimi pipeline through `agentflow doctor`' \
	  '  doctor-local-custom-shell-init Verify a temporary external Codex + Claude-on-Kimi `shell_init: kimi` pipeline through `agentflow doctor`' \
	  '  inspect-local-custom Verify a temporary external Codex + Claude-on-Kimi pipeline through `agentflow inspect`' \
	  '  inspect-local-custom-shell-init Verify a temporary external Codex + Claude-on-Kimi `shell_init: kimi` pipeline through `agentflow inspect`' \
	  '  check-local-custom Verify a temporary external Codex + Claude-on-Kimi pipeline through `agentflow check-local`' \
	  '  check-local-custom-shell-init Verify a temporary external Codex + Claude-on-Kimi `shell_init: kimi` pipeline through `agentflow check-local`' \
	  '  run-local-custom Verify a temporary external Codex + Claude-on-Kimi pipeline through `agentflow run`' \
	  '  run-local-custom-shell-init Verify a temporary external Codex + Claude-on-Kimi `shell_init: kimi` pipeline through `agentflow run`' \
	  '  inspect-local Inspect the bundled local Kimi-backed smoke pipeline' \
	  '  doctor-local  Check local Codex/Claude/Kimi smoke prerequisites' \
	  '  smoke-local   Run the bundled local Codex + Claude-on-Kimi smoke test' \
	  '  check-local   Run the single-pass doctor-then-smoke CLI shortcut'

test:
	$(PYTHON) -m pytest -q

toolchain-local:
	bash scripts/verify-local-kimi-shell.sh

verify-local:
	bash scripts/verify-local-kimi-stack.sh

doctor-local-custom:
	bash scripts/verify-custom-local-kimi-doctor.sh

doctor-local-custom-shell-init:
	AGENTFLOW_KIMI_PIPELINE_MODE=shell-init bash scripts/verify-custom-local-kimi-doctor.sh

inspect-local-custom:
	bash scripts/verify-custom-local-kimi-inspect.sh

inspect-local-custom-shell-init:
	AGENTFLOW_KIMI_PIPELINE_MODE=shell-init bash scripts/verify-custom-local-kimi-inspect.sh

check-local-custom:
	bash scripts/verify-custom-local-kimi-pipeline.sh

check-local-custom-shell-init:
	bash scripts/verify-custom-local-kimi-shell-init.sh

run-local-custom:
	bash scripts/verify-custom-local-kimi-run.sh

run-local-custom-shell-init:
	AGENTFLOW_KIMI_PIPELINE_MODE=shell-init bash scripts/verify-custom-local-kimi-run.sh

inspect-local:
	$(PYTHON) -m agentflow inspect examples/local-real-agents-kimi-smoke.yaml --output summary

doctor-local:
	$(PYTHON) -m agentflow doctor examples/local-real-agents-kimi-smoke.yaml --output summary

smoke-local:
	$(PYTHON) -m agentflow smoke --show-preflight

check-local:
	$(PYTHON) -m agentflow check-local
