from __future__ import annotations

from pathlib import Path

import pytest

from agentflow.local_shell import (
    kimi_shell_init_requires_interactive_bash_warning,
    shell_init_exports_env_var,
    shell_template_exports_env_var_before_command,
    shell_command_uses_kimi_helper,
    target_uses_interactive_bash,
)


@pytest.mark.parametrize(
    "command",
    [
        "bash -lc 'command -v kimi >/dev/null && {command}'",
        "bash -lc 'type kimi >/dev/null 2>&1; {command}'",
        "bash -lc 'which kimi >/dev/null; {command}'",
        "bash -lc 'builtin type kimi >/dev/null 2>&1; {command}'",
        "echo kimi",
        "printf '%s\\n' kimi",
        "bash -lc 'echo kimi && {command}'",
        "bash -lc 'printf kimi && {command}'",
    ],
)
def test_shell_command_uses_kimi_helper_ignores_probe_commands(command: str):
    assert shell_command_uses_kimi_helper(command) is False


@pytest.mark.parametrize(
    "command",
    [
        "bash -lc 'command -v kimi >/dev/null && kimi && {command}'",
        "bash -lc 'type kimi >/dev/null 2>&1; kimi; {command}'",
        "bash -lc 'which kimi >/dev/null; kimi && {command}'",
        'eval "$(kimi)"',
        'eval `kimi`',
        'source <(kimi)',
        "bash -lc 'eval \"$(kimi)\" && {command}'",
        "bash -lc 'eval `kimi` && {command}'",
        "bash -lc 'source <(kimi) && {command}'",
    ],
)
def test_shell_command_uses_kimi_helper_detects_actual_bootstrap_after_probe(command: str):
    assert shell_command_uses_kimi_helper(command) is True


def test_kimi_shell_init_requires_interactive_bash_warning_ignores_probe_only_shell():
    target = {
        "kind": "local",
        "shell": "bash -lc 'command -v kimi >/dev/null && {command}'",
    }

    assert kimi_shell_init_requires_interactive_bash_warning(target) is None


def test_kimi_shell_init_requires_interactive_bash_warning_supports_shell_init_lists():
    target = {
        "kind": "local",
        "shell": "bash",
        "shell_init": ["command -v kimi >/dev/null 2>&1", "kimi"],
    }

    assert kimi_shell_init_requires_interactive_bash_warning(target) == (
        "`shell_init: kimi` uses bash without interactive startup; helpers from `~/.bashrc` are usually "
        "unavailable. Set `target.shell_interactive: true` or use `bash -lic`."
    )


def test_kimi_shell_init_requires_interactive_bash_warning_ignores_plain_text_kimi_output():
    target = {
        "kind": "local",
        "shell": "bash",
        "shell_init": "echo kimi",
    }

    assert kimi_shell_init_requires_interactive_bash_warning(target) is None


def test_kimi_shell_init_requires_interactive_bash_warning_detects_eval_style_shell_wrapper():
    target = {
        "kind": "local",
        "shell": "bash -lc 'eval \"$(kimi)\" && {command}'",
    }

    assert kimi_shell_init_requires_interactive_bash_warning(target) == (
        "`target.shell` uses `kimi` with bash without interactive startup; helpers from `~/.bashrc` are usually "
        "unavailable. Add `-i`, set `target.shell_interactive: true`, or use `bash -lic`."
    )


def test_kimi_shell_init_requires_interactive_bash_warning_detects_backtick_eval_shell_wrapper():
    target = {
        "kind": "local",
        "shell": "bash -lc 'eval `kimi` && {command}'",
    }

    assert kimi_shell_init_requires_interactive_bash_warning(target) == (
        "`target.shell` uses `kimi` with bash without interactive startup; helpers from `~/.bashrc` are usually "
        "unavailable. Add `-i`, set `target.shell_interactive: true`, or use `bash -lic`."
    )


def test_kimi_shell_init_requires_interactive_bash_warning_explains_explicit_bashrc_source_in_shell_wrapper(
    tmp_path: Path,
):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".bashrc").write_text(
        "case $- in\n    *i*) ;;\n      *) return;;\nesac\n\nkimi(){ :; }\n",
        encoding="utf-8",
    )
    target = {
        "kind": "local",
        "shell": "bash -lc 'source ~/.bashrc && kimi && {command}'",
    }

    assert kimi_shell_init_requires_interactive_bash_warning(target, home=home) == (
        "`target.shell` sources `~/.bashrc` before `kimi`, but `~/.bashrc` returns early for non-interactive "
        "bash on this host, so helpers defined later still do not load. Add `-i`, set `target.shell_interactive: true`, "
        "use `bash -lic`, or move the bootstrap into a login-sourced file."
    )


def test_kimi_shell_init_requires_interactive_bash_warning_explains_explicit_bashrc_source_before_shell_init(
    tmp_path: Path,
):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".bashrc").write_text(
        "[[ $- != *i* ]] && return\n\nkimi(){ :; }\n",
        encoding="utf-8",
    )
    target = {
        "kind": "local",
        "shell": "bash -lc 'source ~/.bashrc && {command}'",
        "shell_init": ["command -v kimi >/dev/null 2>&1", "kimi"],
    }

    assert kimi_shell_init_requires_interactive_bash_warning(target, home=home) == (
        "`target.shell` sources `~/.bashrc` before `shell_init`, but `~/.bashrc` returns early for non-interactive "
        "bash on this host, so helpers defined later still do not load. Add `-i`, set `target.shell_interactive: true`, "
        "use `bash -lic`, or move the bootstrap into a login-sourced file."
    )


def test_kimi_shell_init_requires_interactive_bash_warning_keeps_generic_warning_without_detected_bashrc_guard(
    tmp_path: Path,
):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")
    target = {
        "kind": "local",
        "shell": "bash -lc 'source ~/.bashrc && kimi && {command}'",
    }

    assert kimi_shell_init_requires_interactive_bash_warning(target, home=home) == (
        "`target.shell` uses `kimi` with bash without interactive startup; helpers from `~/.bashrc` are usually "
        "unavailable. Add `-i`, set `target.shell_interactive: true`, or use `bash -lic`."
    )


def test_shell_init_exports_env_var_detects_exported_provider_key():
    assert shell_init_exports_env_var(["export ANTHROPIC_API_KEY=test-shell-key"], "ANTHROPIC_API_KEY") is True


def test_shell_init_exports_env_var_ignores_non_exported_assignment():
    assert shell_init_exports_env_var(["ANTHROPIC_API_KEY=test-shell-key"], "ANTHROPIC_API_KEY") is False


def test_shell_init_exports_env_var_detects_split_assignment_then_export():
    assert (
        shell_init_exports_env_var(
            ["ANTHROPIC_API_KEY=test-shell-key", "export ANTHROPIC_API_KEY"],
            "ANTHROPIC_API_KEY",
        )
        is True
    )


def test_shell_template_exports_env_var_before_command_detects_nested_export():
    assert (
        shell_template_exports_env_var_before_command(
            "bash -lc 'export ANTHROPIC_API_KEY=test-shell-key && {command}'",
            "ANTHROPIC_API_KEY",
        )
        is True
    )


def test_shell_template_exports_env_var_before_command_detects_split_assignment_then_export():
    assert (
        shell_template_exports_env_var_before_command(
            "bash -lc 'ANTHROPIC_API_KEY=test-shell-key && export ANTHROPIC_API_KEY && {command}'",
            "ANTHROPIC_API_KEY",
        )
        is True
    )


@pytest.mark.parametrize(
    "shell",
    [
        "bash --rcfile ~/.bashrc -ic '{command}'",
        "bash --init-file ~/.bashrc -ic '{command}'",
    ],
)
def test_target_uses_interactive_bash_skips_long_options_with_values(shell: str):
    target = {
        "kind": "local",
        "shell": shell,
    }

    assert target_uses_interactive_bash(target) is True


@pytest.mark.parametrize(
    "shell",
    [
        "bash --rcfile ~/.bashrc -ic 'source ~/.bashrc && {command}'",
        "bash --init-file ~/.bashrc -ic 'source ~/.bashrc && {command}'",
    ],
)
def test_kimi_shell_init_requires_interactive_bash_warning_accepts_interactive_bash_with_long_option_values(shell: str):
    target = {
        "kind": "local",
        "shell": shell,
        "shell_init": ["command -v kimi >/dev/null 2>&1", "kimi"],
    }

    assert kimi_shell_init_requires_interactive_bash_warning(target) is None
