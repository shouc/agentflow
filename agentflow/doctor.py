from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from agentflow.agents.kimi import default_kimi_executable
from agentflow.env import merge_env_layers
from agentflow.local_shell import (
    kimi_shell_init_requires_bash_warning,
    kimi_shell_init_requires_interactive_bash_warning,
)
from agentflow.prepared import PreparedExecution, build_execution_paths
from agentflow.runners.local import LocalRunner
from agentflow.specs import AgentKind, LocalTarget, provider_uses_kimi_anthropic_auth, resolve_provider
from agentflow.utils import looks_sensitive_key


_BASH_LOGIN_FILENAMES = (".bash_profile", ".bash_login", ".profile")
_CODEX_IN_SHELL_MISSING_EXIT_CODE = 10
_KIMI_HELPER_MISSING_EXIT_CODE = 11
_CLAUDE_IN_SHELL_MISSING_EXIT_CODE = 12
_KIMI_API_KEY_MISSING_EXIT_CODE = 13
_CODEX_AFTER_KIMI_MISSING_EXIT_CODE = 14
_KIMI_BASE_URL_MISSING_EXIT_CODE = 15
_KIMI_BASE_URL_MISMATCH_EXIT_CODE = 16
_CODEX_LOGIN_STATUS_AFTER_KIMI_FAILED_EXIT_CODE = 17
_CLAUDE_AFTER_KIMI_VERSION_FAILED_EXIT_CODE = 18
_CODEX_AFTER_KIMI_VERSION_FAILED_EXIT_CODE = 19
_EXPECTED_KIMI_ANTHROPIC_BASE_URL = "https://api.kimi.com/coding/"
_REDACTED = "<redacted>"
_BASH_INTERACTIVE_STDERR_NOISE = (
    "bash: cannot set terminal process group (",
    "bash: initialize_job_control: no job control in background:",
    "bash: no job control in this shell",
)
_DEFAULT_DOCTOR_SUBPROCESS_TIMEOUT_SECONDS = 15.0
_DIAGNOSTIC_TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
_ENV_ASSIGNMENT_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
_SHELL_COMMAND_BOUNDARY_TOKENS = {"&&", "||", "|", ";", "do", "then", "elif"}
_COMMAND_POSITION_PREFIX_TOKENS = {"builtin", "command", "env", "exec", "nohup", "sudo", "time"}


def _object_value(obj: object, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _status_value(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "")


def _coerce_local_target(target: object) -> LocalTarget | None:
    if _status_value(_object_value(target, "kind")).lower() != "local":
        return None

    payload = {
        "kind": "local",
        "cwd": _object_value(target, "cwd"),
        "shell": _object_value(target, "shell"),
        "shell_login": bool(_object_value(target, "shell_login", False)),
        "shell_interactive": bool(_object_value(target, "shell_interactive", False)),
        "shell_init": _object_value(target, "shell_init"),
    }
    return LocalTarget.model_validate(payload)


def _strip_shell_comments(line: str) -> str:
    quote: str | None = None
    escaped = False
    result: list[str] = []
    for char in line:
        if escaped:
            result.append(char)
            escaped = False
            continue
        if char == "\\" and quote != "'":
            result.append(char)
            escaped = True
            continue
        if char in {'"', "'"}:
            result.append(char)
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
            continue
        if char == "#" and quote is None:
            break
        result.append(char)
    return "".join(result)


def _looks_like_env_assignment(token: str) -> bool:
    return bool(_ENV_ASSIGNMENT_PATTERN.match(token))


def _token_resets_command_position(token: str) -> bool:
    stripped = token.strip()
    if stripped in _SHELL_COMMAND_BOUNDARY_TOKENS:
        return True
    return stripped.endswith((";", "&&", "||", "|"))


def _iter_shell_source_targets(text: str) -> tuple[str, ...]:
    targets: list[str] = []
    for raw_line in text.splitlines():
        line = _strip_shell_comments(raw_line).strip()
        if not line:
            continue
        try:
            tokens = shlex.split(line, posix=True)
        except ValueError:
            tokens = line.split()

        expects_command = True
        for index, token in enumerate(tokens):
            if expects_command:
                if _token_resets_command_position(token):
                    continue
                if _looks_like_env_assignment(token) or token in _COMMAND_POSITION_PREFIX_TOKENS:
                    continue
                if token in {"source", "."}:
                    if index + 1 < len(tokens):
                        targets.append(tokens[index + 1])
                    expects_command = False
                    continue
                expects_command = False

            if _token_resets_command_position(token):
                expects_command = True
    return tuple(targets)


def _resolve_home_shell_source_target(token: str, home: Path) -> Path | None:
    normalized = token.rstrip(";)")
    if not normalized:
        return None

    resolved_home = home.resolve()
    if normalized == "~":
        candidate = resolved_home
    elif normalized.startswith("~/"):
        candidate = resolved_home / normalized[2:]
    elif normalized.startswith("$HOME/"):
        candidate = resolved_home / normalized[6:]
    elif normalized.startswith("${HOME}/"):
        candidate = resolved_home / normalized[8:]
    elif normalized.startswith("$"):
        return None
    else:
        raw_path = Path(normalized)
        candidate = raw_path if raw_path.is_absolute() else resolved_home / raw_path

    candidate = Path(os.path.normpath(str(candidate)))

    try:
        candidate.relative_to(resolved_home)
    except ValueError:
        return None
    return candidate


def _shell_sources_file(text: str, filename: str, home: Path | None = None) -> bool:
    if home is None:
        accepted_targets = {
            f"~/{filename}",
            f"$HOME/{filename}",
            f"${{HOME}}/{filename}",
        }
        return any(token.rstrip(";)") in accepted_targets for token in _iter_shell_source_targets(text))

    target = Path(os.path.normpath(str(home.resolve() / filename)))
    return any(
        resolved == target
        for token in _iter_shell_source_targets(text)
        if (resolved := _resolve_home_shell_source_target(token, home)) is not None
    )


def _home_relative_shell_path(home: Path, path: Path) -> str:
    normalized_home = home.resolve()
    normalized_path = Path(os.path.normpath(str(path if path.is_absolute() else normalized_home / path)))
    return normalized_path.relative_to(normalized_home).as_posix()


def _shell_startup_read_error(home: Path, path: Path, exc: OSError) -> _ShellStartupReadError:
    try:
        display_path = f"~/{_home_relative_shell_path(home, path)}"
    except ValueError:
        display_path = str(path)
    detail = (exc.strerror or str(exc)).strip()
    return _ShellStartupReadError(display_path, detail)


def _is_bash_interactive_stderr_noise(line: str) -> bool:
    return any(line.startswith(prefix) for prefix in _BASH_INTERACTIVE_STDERR_NOISE)


def _redact_sensitive_diagnostic_line(line: str) -> str:
    for match in _DIAGNOSTIC_TOKEN_PATTERN.finditer(line):
        key = match.group(0)
        if not looks_sensitive_key(key):
            continue
        separator_index = match.end()
        while separator_index < len(line) and line[separator_index] in {" ", "\t", '"', "'"}:
            separator_index += 1
        if separator_index >= len(line) or line[separator_index] not in {"=", ":"}:
            continue
        separator = line[separator_index]
        spacing = " " if separator == ":" else ""
        return f"{line[:separator_index + 1]}{spacing}{_REDACTED}"
    return line


def _format_shell_diagnostic(stderr: str) -> str:
    sanitized_lines = []
    for raw_line in stderr.splitlines():
        line = raw_line.strip()
        if not line or _is_bash_interactive_stderr_noise(line):
            continue
        sanitized_lines.append(_redact_sensitive_diagnostic_line(line))
    return "\n".join(sanitized_lines).strip()


def _first_nonempty_output_line(*streams: str | None) -> str | None:
    for stream in streams:
        if not isinstance(stream, str):
            continue
        for raw_line in stream.splitlines():
            line = raw_line.strip()
            if line:
                return line
    return None


class _DoctorSubprocessTimeout(RuntimeError):
    def __init__(self, command_text: str, timeout_seconds: float):
        super().__init__(command_text)
        self.command_text = command_text
        self.timeout_seconds = timeout_seconds


def _doctor_subprocess_timeout_seconds() -> float:
    raw_value = os.getenv("AGENTFLOW_DOCTOR_TIMEOUT_SECONDS")
    if raw_value is None:
        return _DEFAULT_DOCTOR_SUBPROCESS_TIMEOUT_SECONDS
    try:
        parsed = float(raw_value)
    except ValueError:
        return _DEFAULT_DOCTOR_SUBPROCESS_TIMEOUT_SECONDS
    if parsed <= 0:
        return _DEFAULT_DOCTOR_SUBPROCESS_TIMEOUT_SECONDS
    return parsed


def _format_timeout_seconds(value: float) -> str:
    if float(value).is_integer():
        return f"{int(value)}s"
    return f"{value:g}s"


def _doctor_timeout_detail(command_text: str, timeout_seconds: float | None = None) -> str:
    resolved_timeout = timeout_seconds or _doctor_subprocess_timeout_seconds()
    return f"`{command_text}` timed out after {_format_timeout_seconds(resolved_timeout)}"


def _doctor_command_text(command: list[str]) -> str:
    if len(command) == 3 and command[0] == "bash" and command[1].startswith("-") and "c" in command[1]:
        return f"bash {command[1]} '<inline shell probe>'"
    return shlex.join(command)


def _run_doctor_subprocess(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    timeout_seconds = _doctor_subprocess_timeout_seconds()
    try:
        return subprocess.run(command, timeout=timeout_seconds, **kwargs)
    except subprocess.TimeoutExpired as exc:
        raise _DoctorSubprocessTimeout(_doctor_command_text(command), timeout_seconds) from exc


def _probe_executable_version(path: str) -> tuple[str | None, float | None]:
    try:
        result = _run_doctor_subprocess(
            [path, "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None, None
    except _DoctorSubprocessTimeout as exc:
        return None, exc.timeout_seconds

    if result.returncode != 0:
        return None, None

    return _first_nonempty_output_line(result.stdout, result.stderr), None


def _executable_ok_check(name: str, path: str) -> DoctorCheck:
    version, timeout_seconds = _probe_executable_version(path)
    if timeout_seconds is not None:
        return DoctorCheck(
            name=name,
            status="warning",
            detail=f"Found `{name}` at `{path}`, but {_doctor_timeout_detail(f'{name} --version', timeout_seconds)}.",
            context={"path": path, "version_timeout_seconds": timeout_seconds},
        )
    if not version:
        return DoctorCheck(name=name, status="ok", detail=f"Found `{name}` at `{path}`.")
    return DoctorCheck(
        name=name,
        status="ok",
        detail=f"Found `{name}` at `{path}` (version `{version}`).",
        context={"path": path, "version": version},
    )


class _ShellStartupReadError(RuntimeError):
    def __init__(self, path: str, detail: str):
        super().__init__(detail)
        self.path = path
        self.detail = detail


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    detail: str
    context: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
        }
        if self.context is not None:
            payload["context"] = dict(self.context)
        return payload


@dataclass(frozen=True)
class DoctorReport:
    status: str
    checks: list[DoctorCheck]

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "checks": [check.as_dict() for check in self.checks],
        }


@dataclass(frozen=True)
class ShellBridgeRecommendation:
    target: str
    source: str
    snippet: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def _dict_env(env: object) -> dict[str, str]:
    if not isinstance(env, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in env.items()
        if value is not None
    }


def _has_nonempty_env_value(env: object, key: str) -> bool:
    if not isinstance(env, dict):
        return False
    return bool(str(env.get(key, "")).strip())


def _local_codex_auth_check_detail(node_id: str) -> str:
    return (
        f"Node `{node_id}` (codex) cannot authenticate local Codex after the node shell bootstrap; "
        "`codex login status` fails and `OPENAI_API_KEY` is not set in the current environment, `node.env`, or `provider.env`."
    )


def _local_codex_auth_ok_check_detail(node_id: str) -> str:
    return (
        f"Node `{node_id}` (codex) can authenticate local Codex after the node shell bootstrap via "
        "`codex login status` or `OPENAI_API_KEY`."
    )


def _local_codex_ready_check_detail(node_id: str, executable: str) -> str:
    return (
        f"Node `{node_id}` (codex) cannot launch local Codex after the node shell bootstrap; "
        f"`{executable} --version` fails in the prepared local shell."
    )


def _local_codex_ready_ok_check_detail(node_id: str, executable: str) -> str:
    return (
        f"Node `{node_id}` (codex) can launch local Codex after the node shell bootstrap; "
        f"`{executable} --version` succeeds in the prepared local shell."
    )


def _local_claude_ready_check_detail(node_id: str, executable: str) -> str:
    return (
        f"Node `{node_id}` (claude) cannot launch local Claude after the node shell bootstrap; "
        f"`{executable} --version` fails in the prepared local shell."
    )


def _local_claude_ready_ok_check_detail(node_id: str, executable: str) -> str:
    return (
        f"Node `{node_id}` (claude) can launch local Claude after the node shell bootstrap; "
        f"`{executable} --version` succeeds in the prepared local shell."
    )


def _local_kimi_ready_check_detail(node_id: str, probe_command: str) -> str:
    return (
        f"Node `{node_id}` (kimi) cannot launch the local Kimi bridge after the node shell bootstrap; "
        f"`{probe_command}` fails in the prepared local shell."
    )


def _local_kimi_ready_ok_check_detail(node_id: str, probe_command: str) -> str:
    return (
        f"Node `{node_id}` (kimi) can launch the local Kimi bridge after the node shell bootstrap; "
        f"`{probe_command}` succeeds in the prepared local shell."
    )


def _local_probe_timeout_detail(node_id: str, agent: str, command_text: str, timeout_seconds: float) -> str:
    return (
        f"Node `{node_id}` ({agent}) cannot finish the local preflight probe after the node shell bootstrap; "
        f"{_doctor_timeout_detail(command_text, timeout_seconds)} in the prepared local shell."
    )


def _node_pipeline_workdir(node: object, pipeline: object | None = None) -> Path:
    working_path = _object_value(node, "working_path")
    if working_path is None and pipeline is not None:
        working_path = _object_value(pipeline, "working_path")
    if working_path is None:
        return Path.cwd().resolve()
    return Path(str(working_path)).expanduser().resolve()


def _codex_auth_probe_command(executable: str) -> list[str]:
    probe_script = (
        "import os\n"
        "import subprocess\n"
        "import sys\n"
        "if os.getenv('OPENAI_API_KEY', '').strip():\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(subprocess.run([sys.argv[1], 'login', 'status']).returncode)\n"
    )
    return [sys.executable, "-c", probe_script, executable]


def _prepared_codex_auth_execution(node: object, pipeline: object | None = None) -> tuple[PreparedExecution, object] | None:
    agent = _status_value(_object_value(node, "agent")).lower()
    if agent != AgentKind.CODEX.value:
        return None

    target = _coerce_local_target(_object_value(node, "target"))
    if target is None:
        return None
    pipeline_workdir = _node_pipeline_workdir(node, pipeline)
    paths = build_execution_paths(
        base_dir=Path.cwd() / ".agentflow" / "doctor",
        pipeline_workdir=pipeline_workdir,
        run_id="doctor",
        node_id=str(_object_value(node, "id", "codex")),
        node_target=target,
        create_runtime_dir=False,
    )
    provider = resolve_provider(_object_value(node, "provider"), AgentKind.CODEX)
    env = merge_env_layers(_object_value(provider, "env"), _object_value(node, "env"))
    if kimi_shell_init_requires_bash_warning(target) is not None:
        return None
    if kimi_shell_init_requires_interactive_bash_warning(target, cwd=paths.host_workdir, env=env) is not None:
        return None

    executable = str(_object_value(node, "executable") or "codex")
    prepared = PreparedExecution(
        command=_codex_auth_probe_command(executable),
        env=env,
        cwd=str(paths.host_workdir),
        trace_kind="final",
    )
    return prepared, paths


def _prepared_codex_readiness_execution(
    node: object,
    pipeline: object | None = None,
) -> tuple[PreparedExecution, object, str] | None:
    agent = _status_value(_object_value(node, "agent")).lower()
    if agent != AgentKind.CODEX.value:
        return None

    target = _coerce_local_target(_object_value(node, "target"))
    if target is None:
        return None
    pipeline_workdir = _node_pipeline_workdir(node, pipeline)
    paths = build_execution_paths(
        base_dir=Path.cwd() / ".agentflow" / "doctor",
        pipeline_workdir=pipeline_workdir,
        run_id="doctor",
        node_id=str(_object_value(node, "id", "codex")),
        node_target=target,
        create_runtime_dir=False,
    )
    provider = resolve_provider(_object_value(node, "provider"), AgentKind.CODEX)
    env = merge_env_layers(_object_value(provider, "env"), _object_value(node, "env"))
    if kimi_shell_init_requires_bash_warning(target) is not None:
        return None
    if kimi_shell_init_requires_interactive_bash_warning(target, cwd=paths.host_workdir, env=env) is not None:
        return None

    executable = str(_object_value(node, "executable") or "codex")
    prepared = PreparedExecution(
        command=[executable, "--version"],
        env=env,
        cwd=str(paths.host_workdir),
        trace_kind="final",
    )
    return prepared, paths, executable


def _should_probe_local_claude(node: object, pipeline: object | None = None) -> bool:
    agent = _status_value(_object_value(node, "agent")).lower()
    if agent != AgentKind.CLAUDE.value:
        return False

    target = _coerce_local_target(_object_value(node, "target"))
    if target is None:
        return False

    pipeline_workdir = _node_pipeline_workdir(node, pipeline)
    paths = build_execution_paths(
        base_dir=Path.cwd() / ".agentflow" / "doctor",
        pipeline_workdir=pipeline_workdir,
        run_id="doctor",
        node_id=str(_object_value(node, "id", "claude")),
        node_target=target,
        create_runtime_dir=False,
    )
    provider = resolve_provider(_object_value(node, "provider"), AgentKind.CLAUDE)
    env = merge_env_layers(_object_value(provider, "env"), _object_value(node, "env"))
    if kimi_shell_init_requires_bash_warning(target) is not None:
        return False
    if kimi_shell_init_requires_interactive_bash_warning(target, cwd=paths.host_workdir, env=env) is not None:
        return False
    return True


def _prepared_claude_readiness_execution(
    node: object,
    pipeline: object | None = None,
) -> tuple[PreparedExecution, object, str] | None:
    if not _should_probe_local_claude(node, pipeline):
        return None

    target = _coerce_local_target(_object_value(node, "target"))
    if target is None:
        return None

    pipeline_workdir = _node_pipeline_workdir(node, pipeline)
    paths = build_execution_paths(
        base_dir=Path.cwd() / ".agentflow" / "doctor",
        pipeline_workdir=pipeline_workdir,
        run_id="doctor",
        node_id=str(_object_value(node, "id", "claude")),
        node_target=target,
        create_runtime_dir=False,
    )
    provider = resolve_provider(_object_value(node, "provider"), AgentKind.CLAUDE)
    env = merge_env_layers(_object_value(provider, "env"), _object_value(node, "env"))
    executable = str(_object_value(node, "executable") or "claude")
    prepared = PreparedExecution(
        command=[executable, "--version"],
        env=env,
        cwd=str(paths.host_workdir),
        trace_kind="final",
    )
    return prepared, paths, executable


def _prepared_kimi_readiness_execution(
    node: object,
    pipeline: object | None = None,
) -> tuple[PreparedExecution, object, str] | None:
    agent = _status_value(_object_value(node, "agent")).lower()
    if agent != AgentKind.KIMI.value:
        return None

    target = _coerce_local_target(_object_value(node, "target"))
    if target is None:
        return None
    pipeline_workdir = _node_pipeline_workdir(node, pipeline)
    paths = build_execution_paths(
        base_dir=Path.cwd() / ".agentflow" / "doctor",
        pipeline_workdir=pipeline_workdir,
        run_id="doctor",
        node_id=str(_object_value(node, "id", "kimi")),
        node_target=target,
        create_runtime_dir=False,
    )
    provider = resolve_provider(_object_value(node, "provider"), AgentKind.KIMI)
    env = merge_env_layers(_object_value(provider, "env"), _object_value(node, "env"))
    if kimi_shell_init_requires_bash_warning(target) is not None:
        return None
    if kimi_shell_init_requires_interactive_bash_warning(target, cwd=paths.host_workdir, env=env) is not None:
        return None

    executable = str(_object_value(node, "executable") or default_kimi_executable(paths))
    probe_command = [executable, "-c", "import agentflow.remote.kimi_bridge"]
    prepared = PreparedExecution(
        command=probe_command,
        env=env,
        cwd=str(paths.host_workdir),
        trace_kind="final",
    )
    return prepared, paths, shlex.join(probe_command)


def _can_authenticate_local_codex(node: object, pipeline: object | None = None) -> tuple[bool, str | None]:
    prepared_with_paths = _prepared_codex_auth_execution(node, pipeline)
    if prepared_with_paths is None:
        return True, None

    prepared, paths = prepared_with_paths

    try:
        launch_plan = LocalRunner().plan_execution(
            SimpleNamespace(target=_coerce_local_target(_object_value(node, "target"))),
            prepared,
            paths,
        )
    except Exception:
        return False, None

    env = os.environ.copy()
    env.update(launch_plan.env)
    try:
        result = _run_doctor_subprocess(
            launch_plan.command,
            check=False,
            capture_output=True,
            cwd=launch_plan.cwd,
            env=env,
            text=True,
        )
    except OSError:
        return False, None
    except _DoctorSubprocessTimeout as exc:
        return False, _local_probe_timeout_detail(
            str(_object_value(node, "id", "codex")),
            AgentKind.CODEX.value,
            exc.command_text,
            exc.timeout_seconds,
        )
    return result.returncode == 0, None


def _can_launch_local_codex(node: object, pipeline: object | None = None) -> tuple[bool, str | None, str | None]:
    prepared_with_paths = _prepared_codex_readiness_execution(node, pipeline)
    if prepared_with_paths is None:
        return True, None, None

    prepared, paths, executable = prepared_with_paths

    try:
        launch_plan = LocalRunner().plan_execution(
            SimpleNamespace(target=_coerce_local_target(_object_value(node, "target"))),
            prepared,
            paths,
        )
    except Exception:
        return False, executable, None

    env = os.environ.copy()
    env.update(launch_plan.env)
    try:
        result = _run_doctor_subprocess(
            launch_plan.command,
            check=False,
            capture_output=True,
            cwd=launch_plan.cwd,
            env=env,
            text=True,
        )
    except OSError:
        return False, executable, None
    except _DoctorSubprocessTimeout as exc:
        return False, executable, _local_probe_timeout_detail(
            str(_object_value(node, "id", "codex")),
            AgentKind.CODEX.value,
            exc.command_text,
            exc.timeout_seconds,
        )
    return result.returncode == 0, executable, None


def _can_launch_local_claude(node: object, pipeline: object | None = None) -> tuple[bool, str | None, str | None]:
    prepared_with_paths = _prepared_claude_readiness_execution(node, pipeline)
    if prepared_with_paths is None:
        return True, None, None

    prepared, paths, executable = prepared_with_paths

    try:
        launch_plan = LocalRunner().plan_execution(
            SimpleNamespace(target=_coerce_local_target(_object_value(node, "target"))),
            prepared,
            paths,
        )
    except Exception:
        return False, executable, None

    env = os.environ.copy()
    env.update(launch_plan.env)
    try:
        result = _run_doctor_subprocess(
            launch_plan.command,
            check=False,
            capture_output=True,
            cwd=launch_plan.cwd,
            env=env,
            text=True,
        )
    except OSError:
        return False, executable, None
    except _DoctorSubprocessTimeout as exc:
        return False, executable, _local_probe_timeout_detail(
            str(_object_value(node, "id", "claude")),
            AgentKind.CLAUDE.value,
            exc.command_text,
            exc.timeout_seconds,
        )
    return result.returncode == 0, executable, None


def _can_launch_local_kimi(node: object, pipeline: object | None = None) -> tuple[bool, str | None, str | None]:
    prepared_with_paths = _prepared_kimi_readiness_execution(node, pipeline)
    if prepared_with_paths is None:
        return True, None, None

    prepared, paths, probe_command = prepared_with_paths

    try:
        launch_plan = LocalRunner().plan_execution(
            SimpleNamespace(target=_coerce_local_target(_object_value(node, "target"))),
            prepared,
            paths,
        )
    except Exception:
        return False, probe_command, None

    env = os.environ.copy()
    env.update(launch_plan.env)
    try:
        result = _run_doctor_subprocess(
            launch_plan.command,
            check=False,
            capture_output=True,
            cwd=launch_plan.cwd,
            env=env,
            text=True,
        )
    except OSError:
        return False, probe_command, None
    except _DoctorSubprocessTimeout as exc:
        return False, probe_command, _local_probe_timeout_detail(
            str(_object_value(node, "id", "kimi")),
            AgentKind.KIMI.value,
            exc.command_text,
            exc.timeout_seconds,
        )
    return result.returncode == 0, probe_command, None


def build_pipeline_local_claude_readiness_checks(pipeline: object) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    for node in _object_value(pipeline, "nodes", []) or []:
        agent = _status_value(_object_value(node, "agent")).lower()
        if agent != AgentKind.CLAUDE.value:
            continue

        ready, executable, failure_detail = _can_launch_local_claude(node, pipeline)
        if ready:
            continue

        node_id = str(_object_value(node, "id", "claude"))
        checks.append(
            DoctorCheck(
                name="claude_ready",
                status="failed",
                detail=failure_detail or _local_claude_ready_check_detail(node_id, executable or "claude"),
            )
        )
    return checks


def build_pipeline_local_claude_readiness_info_checks(pipeline: object) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    for node in _object_value(pipeline, "nodes", []) or []:
        if _prepared_claude_readiness_execution(node, pipeline) is None:
            continue

        ready, executable, failure_detail = _can_launch_local_claude(node, pipeline)
        if not ready:
            continue

        node_id = str(_object_value(node, "id", "claude"))
        checks.append(
            DoctorCheck(
                name="claude_ready",
                status="ok",
                detail=failure_detail or _local_claude_ready_ok_check_detail(node_id, executable or "claude"),
            )
        )
    return checks


def build_pipeline_local_kimi_readiness_checks(pipeline: object) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    for node in _object_value(pipeline, "nodes", []) or []:
        agent = _status_value(_object_value(node, "agent")).lower()
        if agent != AgentKind.KIMI.value:
            continue

        ready, probe_command, failure_detail = _can_launch_local_kimi(node, pipeline)
        if ready:
            continue

        node_id = str(_object_value(node, "id", "kimi"))
        checks.append(
            DoctorCheck(
                name="kimi_ready",
                status="failed",
                detail=failure_detail
                or _local_kimi_ready_check_detail(node_id, probe_command or "python -c 'import agentflow.remote.kimi_bridge'"),
            )
        )
    return checks


def build_pipeline_local_kimi_readiness_info_checks(pipeline: object) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    for node in _object_value(pipeline, "nodes", []) or []:
        if _prepared_kimi_readiness_execution(node, pipeline) is None:
            continue

        ready, probe_command, failure_detail = _can_launch_local_kimi(node, pipeline)
        if not ready:
            continue

        node_id = str(_object_value(node, "id", "kimi"))
        checks.append(
            DoctorCheck(
                name="kimi_ready",
                status="ok",
                detail=failure_detail
                or _local_kimi_ready_ok_check_detail(
                    node_id,
                    probe_command or "python -c 'import agentflow.remote.kimi_bridge'",
                ),
            )
        )
    return checks


def build_pipeline_local_codex_readiness_checks(pipeline: object) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    for node in _object_value(pipeline, "nodes", []) or []:
        agent = _status_value(_object_value(node, "agent")).lower()
        if agent != AgentKind.CODEX.value:
            continue

        ready, executable, failure_detail = _can_launch_local_codex(node, pipeline)
        if ready:
            continue

        node_id = str(_object_value(node, "id", "codex"))
        checks.append(
            DoctorCheck(
                name="codex_ready",
                status="failed",
                detail=failure_detail or _local_codex_ready_check_detail(node_id, executable or "codex"),
            )
        )
    return checks


def build_pipeline_local_codex_readiness_info_checks(pipeline: object) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    for node in _object_value(pipeline, "nodes", []) or []:
        if _prepared_codex_readiness_execution(node, pipeline) is None:
            continue

        ready, executable, failure_detail = _can_launch_local_codex(node, pipeline)
        if not ready:
            continue

        node_id = str(_object_value(node, "id", "codex"))
        checks.append(
            DoctorCheck(
                name="codex_ready",
                status="ok",
                detail=failure_detail or _local_codex_ready_ok_check_detail(node_id, executable or "codex"),
            )
        )
    return checks


def build_pipeline_local_codex_auth_checks(pipeline: object) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    for node in _object_value(pipeline, "nodes", []) or []:
        agent = _status_value(_object_value(node, "agent")).lower()
        if agent != AgentKind.CODEX.value:
            continue

        target = _coerce_local_target(_object_value(node, "target"))
        if target is None:
            continue

        ready, _, _ = _can_launch_local_codex(node, pipeline)
        if not ready:
            continue

        authenticated, failure_detail = _can_authenticate_local_codex(node, pipeline)
        if authenticated:
            continue

        node_id = str(_object_value(node, "id", "codex"))
        checks.append(
            DoctorCheck(
                name="codex_auth",
                status="failed",
                detail=failure_detail or _local_codex_auth_check_detail(node_id),
            )
        )
    return checks


def build_pipeline_local_codex_auth_info_checks(pipeline: object) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    for node in _object_value(pipeline, "nodes", []) or []:
        agent = _status_value(_object_value(node, "agent")).lower()
        if agent != AgentKind.CODEX.value:
            continue

        if _prepared_codex_auth_execution(node, pipeline) is None:
            continue

        ready, _, _ = _can_launch_local_codex(node, pipeline)
        if not ready:
            continue

        authenticated, failure_detail = _can_authenticate_local_codex(node, pipeline)
        if not authenticated:
            continue

        node_id = str(_object_value(node, "id", "codex"))
        checks.append(
            DoctorCheck(
                name="codex_auth",
                status="ok",
                detail=failure_detail or _local_codex_auth_ok_check_detail(node_id),
            )
        )
    return checks


def _check_executable(name: str) -> DoctorCheck:
    path = shutil.which(name)
    if path:
        return _executable_ok_check(name, path)
    return DoctorCheck(name=name, status="failed", detail=f"`{name}` is not on PATH.")


def _check_codex_executable(home: Path | None = None) -> DoctorCheck:
    path = shutil.which("codex")
    if path:
        return _executable_ok_check("codex", path)

    env = os.environ.copy()
    if home is not None:
        env["HOME"] = str(home)
    try:
        result = _run_doctor_subprocess(
            ["bash", "-lic", f"type {shlex.quote('codex')} >/dev/null 2>&1 || exit {_CODEX_IN_SHELL_MISSING_EXIT_CODE}"],
            check=False,
            capture_output=True,
            env=env,
            text=True,
        )
    except OSError as exc:
        return DoctorCheck(
            name="codex",
            status="failed",
            detail=f"`codex` is not on PATH, and AgentFlow could not launch `bash -lic` to look for it: {exc}",
        )
    except _DoctorSubprocessTimeout as exc:
        return DoctorCheck(
            name="codex",
            status="failed",
            detail=f"`codex` is not on PATH, and {_doctor_timeout_detail(exc.command_text, exc.timeout_seconds)} while looking for it.",
        )

    if result.returncode == 0:
        return DoctorCheck(
            name="codex",
            status="warning",
            detail=(
                "`codex` is not on PATH outside the bundled smoke login shell; "
                "`bash -lic` must provide it for the local smoke pipeline."
            ),
        )
    if result.returncode == _CODEX_IN_SHELL_MISSING_EXIT_CODE:
        return DoctorCheck(
            name="codex",
            status="failed",
            detail="`codex` is not on PATH and is unavailable in `bash -lic`.",
        )
    detail = _format_shell_diagnostic(result.stderr) or f"exit status {result.returncode}"
    return DoctorCheck(
        name="codex",
        status="failed",
        detail=f"`codex` is not on PATH, and `bash -lic` failed while looking for it: {detail}",
    )


def _check_claude_executable(home: Path | None = None) -> DoctorCheck:
    path = shutil.which("claude")
    if path:
        return _executable_ok_check("claude", path)

    env = os.environ.copy()
    if home is not None:
        env["HOME"] = str(home)
    try:
        result = _run_doctor_subprocess(
            ["bash", "-lic", f"type {shlex.quote('claude')} >/dev/null 2>&1 || exit {_CLAUDE_IN_SHELL_MISSING_EXIT_CODE}"],
            check=False,
            capture_output=True,
            env=env,
            text=True,
        )
    except OSError as exc:
        return DoctorCheck(
            name="claude",
            status="failed",
            detail=f"`claude` is not on PATH, and AgentFlow could not launch `bash -lic` to look for it: {exc}",
        )
    except _DoctorSubprocessTimeout as exc:
        return DoctorCheck(
            name="claude",
            status="failed",
            detail=f"`claude` is not on PATH, and {_doctor_timeout_detail(exc.command_text, exc.timeout_seconds)} while looking for it.",
        )

    if result.returncode == 0:
        return DoctorCheck(
            name="claude",
            status="warning",
            detail=(
                "`claude` is not on PATH outside the bundled smoke login shell; "
                "`bash -lic` must provide it for the local smoke pipeline."
            ),
        )
    if result.returncode == _CLAUDE_IN_SHELL_MISSING_EXIT_CODE:
        return DoctorCheck(
            name="claude",
            status="failed",
            detail="`claude` is not on PATH and is unavailable in `bash -lic`.",
        )
    detail = _format_shell_diagnostic(result.stderr) or f"exit status {result.returncode}"
    return DoctorCheck(
        name="claude",
        status="failed",
        detail=f"`claude` is not on PATH, and `bash -lic` failed while looking for it: {detail}",
    )


def _check_claude_host_executable(home: Path | None = None) -> DoctorCheck:
    return _check_claude_executable(home)


def _reconcile_claude_host_executable_check(
    claude_check: DoctorCheck,
    kimi_check: DoctorCheck,
) -> DoctorCheck:
    if kimi_check.status != "ok":
        return claude_check

    accepted_details = {
        "`claude` is not on PATH and is unavailable in `bash -lic`.",
        "`claude` is not on PATH outside the bundled smoke login shell; `bash -lic` must provide it for the local smoke pipeline.",
        "`claude` is not on PATH outside the smoke shell bootstrap; `bash -lic` plus `kimi` must provide it for the bundled smoke pipeline.",
    }
    if claude_check.status not in {"failed", "warning"} or claude_check.detail not in accepted_details:
        return claude_check

    return DoctorCheck(
        name="claude",
        status="ok",
        detail=(
            "`claude` is not on PATH outside the smoke shell bootstrap, but `bash -lic` plus `kimi` already "
            "provides it for the bundled smoke pipeline."
        ),
    )


def _bash_login_file(home: Path) -> Path | None:
    for filename in _BASH_LOGIN_FILENAMES:
        candidate = home / filename
        if candidate.exists():
            return candidate
    return None


def _bash_startup_chain_to_bashrc(
    home: Path,
    startup_file: Path,
    seen: frozenset[str] = frozenset(),
) -> tuple[str, ...] | None:
    name = _home_relative_shell_path(home, startup_file)
    if name in seen:
        return None

    resolved_home = home.resolve()
    bashrc_path = Path(os.path.normpath(str(resolved_home / ".bashrc")))
    try:
        text = startup_file.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        raise _shell_startup_read_error(home, startup_file, exc) from exc
    targets = tuple(
        resolved
        for token in _iter_shell_source_targets(text)
        if (resolved := _resolve_home_shell_source_target(token, resolved_home)) is not None
    )
    if any(target == bashrc_path for target in targets):
        return (name, ".bashrc")

    next_seen = seen | {name}
    for candidate in targets:
        candidate_name = _home_relative_shell_path(resolved_home, candidate)
        if candidate_name in next_seen or candidate == bashrc_path or not candidate.exists():
            continue
        chain = _bash_startup_chain_to_bashrc(resolved_home, candidate, next_seen)
        if chain is not None:
            return (name, *chain)
    return None


def _shadowed_bash_startup_chain_to_bashrc(home: Path, active_startup_name: str) -> tuple[str, ...] | None:
    seen = frozenset({active_startup_name})
    for filename in _BASH_LOGIN_FILENAMES:
        if filename == active_startup_name:
            continue
        candidate = home / filename
        if not candidate.exists():
            continue
        chain = _bash_startup_chain_to_bashrc(home, candidate, seen)
        if chain is not None:
            return chain
    return None


def _format_bash_startup_paths(paths: tuple[str, ...]) -> str:
    formatted = [f"`~/{path}`" for path in paths]
    if len(formatted) == 1:
        return formatted[0]
    if len(formatted) == 2:
        return f"{formatted[0]} and {formatted[1]}"
    return f"{', '.join(formatted[:-1])}, and {formatted[-1]}"


def _render_shell_source_snippet(filename: str) -> str:
    return f'if [ -f "$HOME/{filename}" ]; then\n  . "$HOME/{filename}"\nfi\n'


def _bash_login_file_clause(home: Path, login_file: Path) -> str:
    if login_file.name != ".profile":
        return f"Bash login shells use `~/{login_file.name}`"

    missing_higher_precedence = [
        filename
        for filename in _BASH_LOGIN_FILENAMES[:-1]
        if not (home / filename).exists()
    ]
    if len(missing_higher_precedence) == 2:
        return (
            "Bash login shells fall back to `~/.profile` because "
            "neither `~/.bash_profile` nor `~/.bash_login` exists"
        )
    return "Bash login shells use `~/.profile`"


def _bash_startup_read_error_detail(home: Path, login_file: Path, exc: _ShellStartupReadError) -> str:
    return (
        f"{_bash_login_file_clause(home, login_file)}, but AgentFlow could not read `{exc.path}` while checking "
        f"whether login shells reach `~/.bashrc`: {exc.detail}."
    )


def _bash_startup_chain_context(
    login_file: Path | None,
    *,
    chain: tuple[str, ...] | None = None,
    shadowed_chain: tuple[str, ...] | None = None,
    bashrc_exists: bool | None = None,
    runtime_ready: bool | None = None,
) -> dict[str, Any]:
    startup_chain = [f"~/{part}" for part in chain or ()]
    context: dict[str, Any] = {
        "login_file": None if login_file is None else f"~/{login_file.name}",
        "startup_chain": startup_chain,
        "startup_summary": "none" if not startup_chain else " -> ".join(startup_chain),
        "bashrc_reachable": bool(chain and chain[-1] == ".bashrc"),
    }
    if shadowed_chain is not None:
        shadowed_startup_chain = [f"~/{part}" for part in shadowed_chain]
        context["shadowed_startup_chain"] = shadowed_startup_chain
        context["shadowed_startup_summary"] = " -> ".join(shadowed_startup_chain)
    if bashrc_exists is not None:
        context["bashrc_exists"] = bashrc_exists
    if runtime_ready is not None:
        context["runtime_ready"] = runtime_ready
    return context


def _check_bash_login_startup(home: Path) -> DoctorCheck:
    login_file = _bash_login_file(home)
    if login_file is None:
        return DoctorCheck(
            name="bash_login_startup",
            status="warning",
            detail=(
                "No `~/.bash_profile`, `~/.bash_login`, or `~/.profile` was found for bash login shells; "
                "create one that sources `~/.bashrc` if you expect login shells to load your `kimi` helper."
            ),
            context=_bash_startup_chain_context(login_file),
        )

    try:
        chain = _bash_startup_chain_to_bashrc(home, login_file)
    except _ShellStartupReadError as exc:
        return DoctorCheck(
            name="bash_login_startup",
            status="warning",
            detail=_bash_startup_read_error_detail(home, login_file, exc),
            context=_bash_startup_chain_context(login_file, chain=(login_file.name,)),
        )
    login_file_clause = _bash_login_file_clause(home, login_file)
    if chain is None:
        try:
            shadowed_chain = _shadowed_bash_startup_chain_to_bashrc(home, login_file.name)
        except _ShellStartupReadError as exc:
            return DoctorCheck(
                name="bash_login_startup",
                status="warning",
                detail=_bash_startup_read_error_detail(home, login_file, exc),
                context=_bash_startup_chain_context(login_file, chain=(login_file.name,)),
            )
        if shadowed_chain is not None:
            shadowed_paths = _format_bash_startup_paths(shadowed_chain[:-1])
            pronoun = "it" if len(shadowed_chain) == 2 else "they"
            bridge_detail = "references" if len(shadowed_chain) == 2 else "reach"
            return DoctorCheck(
                name="bash_login_startup",
                status="warning",
                detail=(
                    f"{login_file_clause}, so {shadowed_paths} will never run "
                    f"even though {pronoun} {bridge_detail} `~/.bashrc`; "
                    f"reference `~/.bashrc` or `~/{shadowed_chain[0]}` from `~/{login_file.name}`."
                ),
                context=_bash_startup_chain_context(
                    login_file,
                    chain=(login_file.name,),
                    shadowed_chain=shadowed_chain,
                ),
            )
        return DoctorCheck(
            name="bash_login_startup",
            status="warning",
            detail=f"{login_file_clause}, but it does not reference `~/.bashrc`.",
            context=_bash_startup_chain_context(login_file, chain=(login_file.name,)),
        )

    bashrc_path = home / ".bashrc"
    if not bashrc_path.exists():
        if len(chain) == 2:
            detail = f"{login_file_clause}, and it references `~/.bashrc`, but `~/.bashrc` does not exist."
        else:
            detail = (
                f"{login_file_clause}, and it reaches `~/.bashrc` "
                f"via {_format_bash_startup_paths(chain[1:-1])}, but `~/.bashrc` does not exist."
            )
        return DoctorCheck(
            name="bash_login_startup",
            status="warning",
            detail=detail,
            context=_bash_startup_chain_context(login_file, chain=chain, bashrc_exists=False),
        )

    if len(chain) == 2:
        return DoctorCheck(
            name="bash_login_startup",
            status="ok",
            detail=f"{login_file_clause}, and it references `~/.bashrc`.",
            context=_bash_startup_chain_context(login_file, chain=chain, bashrc_exists=True),
        )

    return DoctorCheck(
        name="bash_login_startup",
        status="ok",
        detail=(
            f"{login_file_clause}, and it reaches `~/.bashrc` "
            f"via {_format_bash_startup_paths(chain[1:-1])}."
        ),
        context=_bash_startup_chain_context(login_file, chain=chain, bashrc_exists=True),
    )


def build_bash_login_shell_bridge_recommendation(home: Path | None = None) -> ShellBridgeRecommendation | None:
    resolved_home = home or Path.home()
    login_file = _bash_login_file(resolved_home)
    if login_file is None:
        return ShellBridgeRecommendation(
            target="~/.profile",
            source="~/.bashrc",
            snippet=_render_shell_source_snippet(".bashrc"),
            reason=(
                "No `~/.bash_profile`, `~/.bash_login`, or `~/.profile` was found for bash login shells, "
                "so create a minimal startup file that reaches `~/.bashrc`."
            ),
        )

    try:
        chain = _bash_startup_chain_to_bashrc(resolved_home, login_file)
    except _ShellStartupReadError as exc:
        return ShellBridgeRecommendation(
            target=f"~/{login_file.name}",
            source="~/.bashrc",
            snippet=_render_shell_source_snippet(".bashrc"),
            reason=f"{_bash_startup_read_error_detail(resolved_home, login_file, exc)} Add a direct bridge to the active login file.",
        )
    if chain is not None:
        return None

    login_file_clause = _bash_login_file_clause(resolved_home, login_file)
    try:
        shadowed_chain = _shadowed_bash_startup_chain_to_bashrc(resolved_home, login_file.name)
    except _ShellStartupReadError as exc:
        return ShellBridgeRecommendation(
            target=f"~/{login_file.name}",
            source="~/.bashrc",
            snippet=_render_shell_source_snippet(".bashrc"),
            reason=f"{_bash_startup_read_error_detail(resolved_home, login_file, exc)} Add a direct bridge to the active login file.",
        )
    if shadowed_chain is not None:
        shadowed_paths = _format_bash_startup_paths(shadowed_chain[:-1])
        pronoun = "it" if len(shadowed_chain) == 2 else "they"
        bridge_detail = "references" if len(shadowed_chain) == 2 else "reach"
        return ShellBridgeRecommendation(
            target=f"~/{login_file.name}",
            source=f"~/{shadowed_chain[0]}",
            snippet=_render_shell_source_snippet(shadowed_chain[0]),
            reason=(
                f"{login_file_clause}, so {shadowed_paths} will never run even though {pronoun} {bridge_detail} "
                "`~/.bashrc`; add the same bridge to the active login file."
            ),
        )

    return ShellBridgeRecommendation(
        target=f"~/{login_file.name}",
        source="~/.bashrc",
        snippet=_render_shell_source_snippet(".bashrc"),
        reason=f"{login_file_clause}, but it does not reference `~/.bashrc`.",
    )


def _check_kimi_shell_helper(home: Path | None = None) -> DoctorCheck:
    env = os.environ.copy()
    if home is not None:
        env["HOME"] = str(home)
    expected_base_url = _EXPECTED_KIMI_ANTHROPIC_BASE_URL.rstrip("/")
    script = "\n".join(
        [
            f"type {shlex.quote('kimi')} >/dev/null 2>&1 || exit {_KIMI_HELPER_MISSING_EXIT_CODE}",
            "kimi >/dev/null || exit $?",
            f'[ -n "${{ANTHROPIC_API_KEY:-}}" ] || exit {_KIMI_API_KEY_MISSING_EXIT_CODE}',
            f'[ -n "${{ANTHROPIC_BASE_URL:-}}" ] || exit {_KIMI_BASE_URL_MISSING_EXIT_CODE}',
            (
                'if [ "${ANTHROPIC_BASE_URL%/}" != "'
                f'{expected_base_url}'
                '" ]; then '
                'printf "%s" "${ANTHROPIC_BASE_URL:-}"; '
                f'exit {_KIMI_BASE_URL_MISMATCH_EXIT_CODE}; '
                'fi'
            ),
            f"type {shlex.quote('claude')} >/dev/null 2>&1 || exit {_CLAUDE_IN_SHELL_MISSING_EXIT_CODE}",
            f"{shlex.quote('claude')} --version >/dev/null 2>&1 || exit {_CLAUDE_AFTER_KIMI_VERSION_FAILED_EXIT_CODE}",
            f"type {shlex.quote('codex')} >/dev/null 2>&1 || exit {_CODEX_AFTER_KIMI_MISSING_EXIT_CODE}",
            f"{shlex.quote('codex')} --version >/dev/null 2>&1 || exit {_CODEX_AFTER_KIMI_VERSION_FAILED_EXIT_CODE}",
            (
                "codex login status >/dev/null 2>&1 || [ -n \"${OPENAI_API_KEY:-}\" ] "
                f"|| exit {_CODEX_LOGIN_STATUS_AFTER_KIMI_FAILED_EXIT_CODE}"
            ),
        ]
    )
    try:
        result = _run_doctor_subprocess(
            ["bash", "-lic", script],
            check=False,
            capture_output=True,
            env=env,
            text=True,
        )
    except OSError as exc:
        return DoctorCheck(
            name="kimi_shell_helper",
            status="failed",
            detail=f"Could not launch `bash -lic` to verify `kimi`, `claude`, and `codex`: {exc}",
        )
    except _DoctorSubprocessTimeout as exc:
        return DoctorCheck(
            name="kimi_shell_helper",
            status="failed",
            detail=(
                f"`kimi` verification in `bash -lic` did not finish: "
                f"{_doctor_timeout_detail(exc.command_text, exc.timeout_seconds)}."
            ),
        )
    if result.returncode == 0:
        return DoctorCheck(
            name="kimi_shell_helper",
            status="ok",
            detail=(
                "`kimi` is available in `bash -lic`, exports `ANTHROPIC_API_KEY`, "
                f"sets `ANTHROPIC_BASE_URL={_EXPECTED_KIMI_ANTHROPIC_BASE_URL}`, "
                "keeps both `claude` and `codex` available, and confirms Codex authentication is ready via `codex login status` or `OPENAI_API_KEY` "
                "for the bundled smoke pipeline."
            ),
        )
    if result.returncode == _KIMI_HELPER_MISSING_EXIT_CODE:
        return DoctorCheck(
            name="kimi_shell_helper",
            status="failed",
            detail="`kimi` is unavailable in `bash -lic`; add it to your bash startup files before running the bundled smoke pipeline.",
        )
    if result.returncode == _CLAUDE_IN_SHELL_MISSING_EXIT_CODE:
        return DoctorCheck(
            name="kimi_shell_helper",
            status="failed",
            detail=(
                "`kimi` runs in `bash -lic`, but `claude` is unavailable afterwards; "
                "the bundled smoke pipeline will not be able to launch Claude-on-Kimi."
            ),
        )
    if result.returncode == _CLAUDE_AFTER_KIMI_VERSION_FAILED_EXIT_CODE:
        return DoctorCheck(
            name="kimi_shell_helper",
            status="failed",
            detail=(
                "`kimi` runs in `bash -lic`, and `claude` is on PATH afterwards, but `claude --version` still "
                "fails; the bundled smoke pipeline will not be able to launch Claude-on-Kimi."
            ),
        )
    if result.returncode == _CODEX_AFTER_KIMI_MISSING_EXIT_CODE:
        return DoctorCheck(
            name="kimi_shell_helper",
            status="failed",
            detail=(
                "`kimi` runs in `bash -lic`, but `codex` is unavailable afterwards; "
                "the bundled smoke pipeline will not be able to launch Codex inside that shared Kimi bootstrap."
            ),
        )
    if result.returncode == _CODEX_AFTER_KIMI_VERSION_FAILED_EXIT_CODE:
        return DoctorCheck(
            name="kimi_shell_helper",
            status="failed",
            detail=(
                "`kimi` runs in `bash -lic`, and `codex` is on PATH afterwards, but `codex --version` still "
                "fails; the bundled smoke pipeline will not be able to launch Codex inside that shared Kimi bootstrap."
            ),
        )
    if result.returncode == _CODEX_LOGIN_STATUS_AFTER_KIMI_FAILED_EXIT_CODE:
        return DoctorCheck(
            name="kimi_shell_helper",
            status="failed",
            detail=(
                "`kimi` runs in `bash -lic`, and `codex` is on PATH afterwards, but neither `codex login "
                "status` succeeds nor `OPENAI_API_KEY` is exported; make sure Codex is logged in or "
                "`OPENAI_API_KEY` is exported in that shared smoke shell."
            ),
        )
    if result.returncode == _KIMI_API_KEY_MISSING_EXIT_CODE:
        return DoctorCheck(
            name="kimi_shell_helper",
            status="failed",
            detail=(
                "`kimi` runs in `bash -lic`, but it does not export `ANTHROPIC_API_KEY`; "
                "the bundled smoke pipeline will not be able to authenticate Claude-on-Kimi."
            ),
        )
    if result.returncode == _KIMI_BASE_URL_MISSING_EXIT_CODE:
        return DoctorCheck(
            name="kimi_shell_helper",
            status="failed",
            detail=(
                "`kimi` runs in `bash -lic`, but it does not export `ANTHROPIC_BASE_URL`; "
                "the bundled smoke pipeline will not be able to route Claude through Kimi."
            ),
        )
    if result.returncode == _KIMI_BASE_URL_MISMATCH_EXIT_CODE:
        actual_base_url = result.stdout.strip() or "<empty>"
        return DoctorCheck(
            name="kimi_shell_helper",
            status="failed",
            detail=(
                "`kimi` runs in `bash -lic`, but `ANTHROPIC_BASE_URL` is "
                f"`{actual_base_url}` instead of `{_EXPECTED_KIMI_ANTHROPIC_BASE_URL}`; "
                "the bundled smoke pipeline will not be able to route Claude through Kimi."
            ),
        )
    detail = _format_shell_diagnostic(result.stderr) or f"exit status {result.returncode}"
    return DoctorCheck(
        name="kimi_shell_helper",
        status="failed",
        detail=f"`kimi` failed inside `bash -lic`: {detail}",
    )


def _check_kimi_bootstrap_helper(home: Path | None = None) -> DoctorCheck:
    env = os.environ.copy()
    if home is not None:
        env["HOME"] = str(home)
    expected_base_url = _EXPECTED_KIMI_ANTHROPIC_BASE_URL.rstrip("/")
    script = "\n".join(
        [
            f"type {shlex.quote('kimi')} >/dev/null 2>&1 || exit {_KIMI_HELPER_MISSING_EXIT_CODE}",
            "kimi >/dev/null || exit $?",
            f'[ -n "${{ANTHROPIC_API_KEY:-}}" ] || exit {_KIMI_API_KEY_MISSING_EXIT_CODE}',
            f'[ -n "${{ANTHROPIC_BASE_URL:-}}" ] || exit {_KIMI_BASE_URL_MISSING_EXIT_CODE}',
            (
                'if [ "${ANTHROPIC_BASE_URL%/}" != "'
                f'{expected_base_url}'
                '" ]; then '
                'printf "%s" "${ANTHROPIC_BASE_URL:-}"; '
                f'exit {_KIMI_BASE_URL_MISMATCH_EXIT_CODE}; '
                'fi'
            ),
        ]
    )
    try:
        result = _run_doctor_subprocess(
            ["bash", "-lic", script],
            check=False,
            capture_output=True,
            env=env,
            text=True,
        )
    except OSError as exc:
        return DoctorCheck(
            name="kimi_shell_helper",
            status="failed",
            detail=f"Could not launch `bash -lic` to verify `kimi`: {exc}",
        )
    except _DoctorSubprocessTimeout as exc:
        return DoctorCheck(
            name="kimi_shell_helper",
            status="failed",
            detail=(
                f"`kimi` bootstrap verification in `bash -lic` did not finish: "
                f"{_doctor_timeout_detail(exc.command_text, exc.timeout_seconds)}."
            ),
        )
    if result.returncode == 0:
        return DoctorCheck(
            name="kimi_shell_helper",
            status="ok",
            detail=(
                "`kimi` is available in `bash -lic`, exports `ANTHROPIC_API_KEY`, and sets "
                f"`ANTHROPIC_BASE_URL={_EXPECTED_KIMI_ANTHROPIC_BASE_URL}`."
            ),
        )
    if result.returncode == _KIMI_HELPER_MISSING_EXIT_CODE:
        return DoctorCheck(
            name="kimi_shell_helper",
            status="failed",
            detail="`kimi` is unavailable in `bash -lic`; add it to your bash startup files before running this local Kimi bootstrap.",
        )
    if result.returncode == _KIMI_API_KEY_MISSING_EXIT_CODE:
        return DoctorCheck(
            name="kimi_shell_helper",
            status="failed",
            detail="`kimi` runs in `bash -lic`, but it does not export `ANTHROPIC_API_KEY`.",
        )
    if result.returncode == _KIMI_BASE_URL_MISSING_EXIT_CODE:
        return DoctorCheck(
            name="kimi_shell_helper",
            status="failed",
            detail="`kimi` runs in `bash -lic`, but it does not export `ANTHROPIC_BASE_URL`.",
        )
    if result.returncode == _KIMI_BASE_URL_MISMATCH_EXIT_CODE:
        actual_base_url = result.stdout.strip() or "<empty>"
        return DoctorCheck(
            name="kimi_shell_helper",
            status="failed",
            detail=(
                "`kimi` runs in `bash -lic`, but `ANTHROPIC_BASE_URL` is "
                f"`{actual_base_url}` instead of `{_EXPECTED_KIMI_ANTHROPIC_BASE_URL}`."
            ),
        )
    detail = _format_shell_diagnostic(result.stderr) or f"exit status {result.returncode}"
    return DoctorCheck(
        name="kimi_shell_helper",
        status="failed",
        detail=f"`kimi` failed inside `bash -lic`: {detail}",
    )


def _reconcile_codex_executable_check(
    codex_check: DoctorCheck,
    kimi_check: DoctorCheck,
) -> DoctorCheck:
    if kimi_check.status != "ok":
        return codex_check

    accepted_details = {
        "`codex` is not on PATH and is unavailable in `bash -lic`.",
        "`codex` is not on PATH outside the bundled smoke login shell; `bash -lic` must provide it for the local smoke pipeline.",
        "`codex` is not on PATH outside the smoke shell bootstrap; `bash -lic` plus `kimi` must provide it for the bundled smoke pipeline.",
    }
    if codex_check.status not in {"failed", "warning"} or codex_check.detail not in accepted_details:
        return codex_check

    return DoctorCheck(
        name="codex",
        status="ok",
        detail=(
            "`codex` is not on PATH outside the smoke shell bootstrap, but `bash -lic` plus `kimi` already "
            "provides it for the bundled smoke pipeline."
        ),
    )


def _reconcile_bash_login_startup_check(
    home: Path,
    startup_check: DoctorCheck,
    kimi_check: DoctorCheck,
) -> DoctorCheck:
    if startup_check.status != "warning" or kimi_check.status != "ok":
        return startup_check

    login_file = _bash_login_file(home)
    context = _bash_startup_chain_context(login_file)
    if isinstance(startup_check.context, dict):
        context.update(startup_check.context)
    context["runtime_ready"] = True
    if login_file is None:
        return DoctorCheck(
            name="bash_login_startup",
            status="ok",
            detail=(
                "No `~/.bash_profile`, `~/.bash_login`, or `~/.profile` was found, but `bash -lic` already exposes "
                "`kimi`, `claude`, and `codex`; a `~/.bashrc` bridge is not required for the bundled smoke pipeline."
            ),
            context=context,
        )

    return DoctorCheck(
        name="bash_login_startup",
        status="ok",
        detail=(
            f"{_bash_login_file_clause(home, login_file)}, and `bash -lic` already exposes `kimi`, `claude`, and "
            "`codex`; a `~/.bashrc` bridge is not required for the bundled smoke pipeline."
        ),
        context=context,
    )


def _reconcile_kimi_bootstrap_bash_login_startup_check(
    home: Path,
    startup_check: DoctorCheck,
    kimi_check: DoctorCheck,
) -> DoctorCheck:
    if startup_check.status != "warning" or kimi_check.status != "ok":
        return startup_check

    login_file = _bash_login_file(home)
    context = _bash_startup_chain_context(login_file)
    if isinstance(startup_check.context, dict):
        context.update(startup_check.context)
    context["runtime_ready"] = True
    if login_file is None:
        return DoctorCheck(
            name="bash_login_startup",
            status="ok",
            detail=(
                "No `~/.bash_profile`, `~/.bash_login`, or `~/.profile` was found, but `bash -lic` already exposes "
                "`kimi`; a `~/.bashrc` bridge is not required for this local Kimi bootstrap."
            ),
            context=context,
        )

    return DoctorCheck(
        name="bash_login_startup",
        status="ok",
        detail=(
            f"{_bash_login_file_clause(home, login_file)}, and `bash -lic` already exposes `kimi`; a `~/.bashrc` "
            "bridge is not required for this local Kimi bootstrap."
        ),
        context=context,
    )


def build_local_smoke_doctor_report(home: Path | None = None) -> DoctorReport:
    resolved_home = home or Path.home()
    codex_check = _check_codex_executable(resolved_home)
    claude_check = _check_claude_executable(resolved_home)
    bash_login_check = _check_bash_login_startup(resolved_home)
    kimi_check = _check_kimi_shell_helper(resolved_home)
    codex_check = _reconcile_codex_executable_check(codex_check, kimi_check)
    claude_check = _reconcile_claude_host_executable_check(claude_check, kimi_check)
    bash_login_check = _reconcile_bash_login_startup_check(resolved_home, bash_login_check, kimi_check)
    checks = [
        codex_check,
        claude_check,
        bash_login_check,
        kimi_check,
    ]
    if any(check.status == "failed" for check in checks):
        status = "failed"
    elif any(check.status == "warning" for check in checks):
        status = "warning"
    else:
        status = "ok"
    return DoctorReport(status=status, checks=checks)


def build_local_kimi_bootstrap_doctor_report(home: Path | None = None) -> DoctorReport:
    resolved_home = home or Path.home()
    bash_login_check = _check_bash_login_startup(resolved_home)
    kimi_check = _check_kimi_bootstrap_helper(resolved_home)
    bash_login_check = _reconcile_kimi_bootstrap_bash_login_startup_check(resolved_home, bash_login_check, kimi_check)
    checks = [
        bash_login_check,
        kimi_check,
    ]
    if any(check.status == "failed" for check in checks):
        status = "failed"
    elif any(check.status == "warning" for check in checks):
        status = "warning"
    else:
        status = "ok"
    return DoctorReport(status=status, checks=checks)
