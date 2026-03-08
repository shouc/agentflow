from __future__ import annotations

import os
import re
import shlex
from typing import Any


_BASH_SUPPORTED_LONG_FLAGS = {
    "--debug",
    "--debugger",
    "--dump-po-strings",
    "--dump-strings",
    "--help",
    "--login",
    "--noediting",
    "--noprofile",
    "--norc",
    "--posix",
    "--pretty-print",
    "--restricted",
    "--verbose",
    "--version",
}
_BASH_LONG_FLAGS_WITH_VALUE = {"--init-file", "--rcfile"}
_BASH_UNSUPPORTED_LONG_FLAG_DETAILS = {
    "--command": "Bash does not support `--command`; use `-c` or omit it and let AgentFlow add `-c`.",
    "--interactive": "Bash does not support `--interactive`; use `-i` or set `target.shell_interactive: true`.",
}
_COMMAND_POSITION_PREFIX_TOKENS = {"builtin", "command", "env", "nohup", "sudo", "time"}
_ENV_ASSIGNMENT_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
_SHELL_CONTROL_TOKENS = {"&&", "||", "|", ";", "do", "then", "elif"}


def _target_value(target: Any, key: str) -> Any:
    if isinstance(target, dict):
        return target.get(key)
    return getattr(target, key, None)


def _split_shell_parts(command: str | None) -> list[str]:
    if not command:
        return []
    try:
        return shlex.split(command)
    except ValueError:
        return []


def _is_command_flag(part: str) -> bool:
    return part == "--command" or (part.startswith("-") and not part.startswith("--") and "c" in part[1:])


def _looks_like_env_assignment(token: str) -> bool:
    return bool(_ENV_ASSIGNMENT_PATTERN.match(token))


def _token_resets_command_position(token: str) -> bool:
    stripped = token.strip()
    if stripped in _SHELL_CONTROL_TOKENS:
        return True
    return stripped.endswith((";", "&&", "||", "|"))


def shell_init_commands(shell_init: Any) -> tuple[str, ...]:
    if isinstance(shell_init, str):
        normalized = shell_init.strip()
        return (normalized,) if normalized else ()
    if isinstance(shell_init, (list, tuple)):
        return tuple(command.strip() for command in shell_init if isinstance(command, str) and command.strip())
    return ()


def render_shell_init(shell_init: Any) -> str | None:
    commands = shell_init_commands(shell_init)
    if not commands:
        return None
    return " && ".join(commands)


def shell_init_uses_kimi_helper(shell_init: Any) -> bool:
    return any(shell_command_uses_kimi_helper(command) for command in shell_init_commands(shell_init))


def _looks_like_kimi_token(token: str) -> bool:
    stripped = token.strip().lstrip("({[").rstrip(";|&)}]\n\r\t ")
    if not stripped:
        return False
    return os.path.basename(stripped) == "kimi"


def invalid_bash_long_option_error(command: str | None) -> str | None:
    tokens = _split_shell_parts(command)
    for index, token in enumerate(tokens):
        if os.path.basename(token) != "bash":
            continue

        position = index + 1
        while position < len(tokens):
            arg = tokens[position]
            if arg == "--":
                return None
            if arg.startswith("--") and "=" in arg:
                option_name, _ = arg.split("=", 1)
                if option_name in _BASH_UNSUPPORTED_LONG_FLAG_DETAILS:
                    return _BASH_UNSUPPORTED_LONG_FLAG_DETAILS[option_name]
                if option_name in _BASH_LONG_FLAGS_WITH_VALUE:
                    return (
                        f"Bash does not support `{option_name}=...`; "
                        f"pass `{option_name}` and its value as separate arguments."
                    )
                if option_name in _BASH_SUPPORTED_LONG_FLAGS:
                    return f"Bash does not support `{option_name}=...`; use `{option_name}` without `=`."
            if arg in _BASH_UNSUPPORTED_LONG_FLAG_DETAILS:
                return _BASH_UNSUPPORTED_LONG_FLAG_DETAILS[arg]
            if arg in _BASH_LONG_FLAGS_WITH_VALUE:
                position += 2
                continue
            if arg in _BASH_SUPPORTED_LONG_FLAGS:
                position += 1
                continue
            if not arg.startswith("-") or arg == "-":
                return None
            if arg.startswith("--"):
                position += 1
                continue
            if "c" in arg[1:]:
                return None
            position += 1
        return None
    return None


def _is_kimi_probe_argument(tokens: list[str], index: int) -> bool:
    if index <= 0:
        return False

    previous = tokens[index - 1]
    if previous in {"type", "which", "hash"}:
        return True

    if index > 1 and previous.startswith("-") and tokens[index - 2] in {"type", "which", "hash"}:
        return True

    if previous in {"-v", "-V"} and index > 1 and tokens[index - 2] == "command":
        return True

    return False


def target_uses_bash(target: Any) -> bool:
    shell = _target_value(target, "shell")
    if not isinstance(shell, str) or not shell.strip():
        return False
    return any(os.path.basename(part) == "bash" for part in _split_shell_parts(shell))


def target_uses_interactive_bash(target: Any) -> bool:
    if bool(_target_value(target, "shell_interactive")):
        return True

    shell = _target_value(target, "shell")
    shell_parts = _split_shell_parts(shell if isinstance(shell, str) else None)
    if not shell_parts:
        return False

    for index, part in enumerate(shell_parts):
        if os.path.basename(part) != "bash":
            continue

        interactive = False
        for arg in shell_parts[index + 1 :]:
            if arg.startswith("--"):
                if arg == "--command":
                    return interactive
                continue
            if not arg.startswith("-") or arg == "-":
                return interactive
            if "i" in arg[1:]:
                interactive = True
            if "c" in arg[1:]:
                return interactive
        return interactive

    return False


def shell_command_uses_kimi_helper(command: str | None) -> bool:
    if not isinstance(command, str) or not command.strip():
        return False

    tokens = _split_shell_parts(command)
    expects_command = True
    prefix_allows_options = False
    for index, token in enumerate(tokens):
        if _looks_like_kimi_token(token) and not _is_kimi_probe_argument(tokens, index):
            if expects_command:
                return True
        if index > 0 and _is_command_flag(tokens[index - 1]) and shell_command_uses_kimi_helper(token):
            return True
        if expects_command:
            if token in _COMMAND_POSITION_PREFIX_TOKENS:
                prefix_allows_options = True
                continue
            if _looks_like_env_assignment(token):
                continue
            if prefix_allows_options and (token == "--" or token.startswith("-")):
                continue
            expects_command = False
            prefix_allows_options = False
        if _token_resets_command_position(token):
            expects_command = True
            prefix_allows_options = False
    return False


def _kimi_bootstrap_without_interactive_bash_warning(source: str) -> str:
    if source == "target.shell_init":
        return (
            "`shell_init: kimi` uses bash without interactive startup; helpers from `~/.bashrc` are usually "
            "unavailable. Set `target.shell_interactive: true` or use `bash -lic`."
        )
    return (
        "`target.shell` uses `kimi` with bash without interactive startup; helpers from `~/.bashrc` are usually "
        "unavailable. Add `-i`, set `target.shell_interactive: true`, or use `bash -lic`."
    )


def kimi_shell_init_requires_interactive_bash_warning(target: Any) -> str | None:
    if not target_uses_bash(target):
        return None
    if target_uses_interactive_bash(target):
        return None

    shell_init = _target_value(target, "shell_init")
    if shell_init_uses_kimi_helper(shell_init):
        return _kimi_bootstrap_without_interactive_bash_warning("target.shell_init")

    shell = _target_value(target, "shell")
    if shell_command_uses_kimi_helper(shell if isinstance(shell, str) else None):
        return _kimi_bootstrap_without_interactive_bash_warning("target.shell")

    return None
