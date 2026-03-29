"""Generate installation scripts for agent CLIs on cloud instances."""
from __future__ import annotations


def agent_install_script(agents: list[str]) -> str:
    """Return a bash script that installs the requested agent CLIs.

    Supported agents: codex, claude, kimi.
    """
    lines = ["#!/bin/bash", "set -euo pipefail", "export DEBIAN_FRONTEND=noninteractive", ""]

    # Install common dependencies
    lines.append("# Install Node.js (needed for codex)")
    lines.append("if ! command -v node &>/dev/null; then")
    lines.append("  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -")
    lines.append("  apt-get install -y nodejs")
    lines.append("fi")
    lines.append("")

    for agent in agents:
        if agent == "codex":
            lines.append("# Install Codex CLI")
            lines.append("if ! command -v codex &>/dev/null; then")
            lines.append("  npm install -g @openai/codex")
            lines.append("fi")
        elif agent == "claude":
            lines.append("# Install Claude Code CLI")
            lines.append("if ! command -v claude &>/dev/null; then")
            lines.append("  npm install -g @anthropic-ai/claude-code")
            lines.append("fi")
        elif agent == "kimi":
            lines.append("# Install Kimi CLI")
            lines.append("if ! command -v kimi &>/dev/null; then")
            lines.append("  pip3 install kimi-cli || pip install kimi-cli")
            lines.append("fi")
        lines.append("")

    lines.append("echo 'Agent installation complete'")
    return "\n".join(lines)


def agent_dockerfile(agents: list[str], base_image: str = "ubuntu:24.04") -> str:
    """Return a Dockerfile that installs the requested agent CLIs."""
    lines = [f"FROM {base_image}", ""]
    lines.append("RUN apt-get update && apt-get install -y curl python3 python3-pip git && rm -rf /var/lib/apt/lists/*")
    lines.append("")
    lines.append("# Install Node.js")
    lines.append("RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt-get install -y nodejs")
    lines.append("")

    for agent in agents:
        if agent == "codex":
            lines.append("RUN npm install -g @openai/codex")
        elif agent == "claude":
            lines.append("RUN npm install -g @anthropic-ai/claude-code")
        elif agent == "kimi":
            lines.append("RUN pip3 install kimi-cli")

    lines.append("")
    lines.append("WORKDIR /workspace")
    lines.append('ENTRYPOINT ["/bin/bash", "-c"]')
    return "\n".join(lines)
