# Background and Sources

Why AgentFlow is shaped the way it is, plus upstream references that informed the adapters and runtime behavior.

## Why this shape

This project was built in this repo, and the integrations were informed by:

- OpenAI Codex CLI patterns in `reference/codex`
- Claude Code web and stream patterns in `reference/claude-code-telegram`
- Moonshot Kimi CLI protocol and UI patterns in `reference/kimi-cli`

Those references shaped the trace parsers, adapter contracts, and frontend event model.


## Reference sources

- `https://developers.openai.com/codex/security`
- `https://docs.anthropic.com/en/docs/claude-code/sdk`
- `https://github.com/openai/codex`
- `https://github.com/RichardAtCT/claude-code-telegram`
- `https://github.com/MoonshotAI/kimi-cli`
