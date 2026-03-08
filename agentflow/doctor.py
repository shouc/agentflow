from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

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
_EXPECTED_KIMI_ANTHROPIC_BASE_URL = "https://api.kimi.com/coding/"
_REDACTED = "<redacted>"
_BASH_INTERACTIVE_STDERR_NOISE = (
    "bash: cannot set terminal process group (",
    "bash: no job control in this shell",
)
_DIAGNOSTIC_TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")


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
        for index, token in enumerate(tokens[:-1]):
            if token in {"source", "."}:
                targets.append(tokens[index + 1])
    return tuple(targets)


def _resolve_home_shell_source_target(token: str, home: Path) -> Path | None:
    normalized = token.rstrip(";)")
    if not normalized:
        return None

    resolved_home = home.resolve()
    if normalized.startswith("~/"):
        candidate = (resolved_home / normalized[2:]).resolve()
    elif normalized.startswith("$HOME/"):
        candidate = (resolved_home / normalized[6:]).resolve()
    elif normalized.startswith("${HOME}/"):
        candidate = (resolved_home / normalized[8:]).resolve()
    elif normalized.startswith("$"):
        return None
    else:
        raw_path = Path(normalized)
        candidate = raw_path.resolve() if raw_path.is_absolute() else (resolved_home / raw_path).resolve()

    try:
        candidate.relative_to(resolved_home)
    except ValueError:
        return None
    return candidate


def _shell_sources_file(text: str, filename: str, home: Path | None = None) -> bool:
    if home is None:
        accepted_targets = {
            filename,
            f"~/{filename}",
            f"$HOME/{filename}",
            f"${{HOME}}/{filename}",
        }
        return any(token.rstrip(";)") in accepted_targets for token in _iter_shell_source_targets(text))

    target = (home / filename).resolve()
    return any(
        resolved == target
        for token in _iter_shell_source_targets(text)
        if (resolved := _resolve_home_shell_source_target(token, home)) is not None
    )


def _home_relative_shell_path(home: Path, path: Path) -> str:
    return path.resolve().relative_to(home.resolve()).as_posix()


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


@dataclass(frozen=True)
class DoctorReport:
    status: str
    checks: list[DoctorCheck]

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "checks": [asdict(check) for check in self.checks],
        }


@dataclass(frozen=True)
class ShellBridgeRecommendation:
    target: str
    source: str
    snippet: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def _check_executable(name: str) -> DoctorCheck:
    path = shutil.which(name)
    if path:
        return DoctorCheck(name=name, status="ok", detail=f"Found `{name}` at `{path}`.")
    return DoctorCheck(name=name, status="failed", detail=f"`{name}` is not on PATH.")


def _check_codex_executable(home: Path | None = None) -> DoctorCheck:
    path = shutil.which("codex")
    if path:
        return DoctorCheck(name="codex", status="ok", detail=f"Found `codex` at `{path}`.")

    env = os.environ.copy()
    if home is not None:
        env["HOME"] = str(home)
    try:
        result = subprocess.run(
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


def _check_claude_host_executable() -> DoctorCheck:
    path = shutil.which("claude")
    if path:
        return DoctorCheck(name="claude", status="ok", detail=f"Found `claude` at `{path}`.")
    return DoctorCheck(
        name="claude",
        status="warning",
        detail=(
            "`claude` is not on PATH outside the smoke shell bootstrap; "
            "`bash -lic` plus `kimi` must provide it for the bundled smoke pipeline."
        ),
    )


def _reconcile_claude_host_executable_check(
    claude_check: DoctorCheck,
    kimi_check: DoctorCheck,
) -> DoctorCheck:
    if claude_check.status != "warning" or kimi_check.status != "ok":
        return claude_check

    if (
        claude_check.detail
        != "`claude` is not on PATH outside the smoke shell bootstrap; `bash -lic` plus `kimi` must provide it for the bundled smoke pipeline."
    ):
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
    bashrc_path = (resolved_home / ".bashrc").resolve()
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
        )

    try:
        chain = _bash_startup_chain_to_bashrc(home, login_file)
    except _ShellStartupReadError as exc:
        return DoctorCheck(
            name="bash_login_startup",
            status="warning",
            detail=_bash_startup_read_error_detail(home, login_file, exc),
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
            )
        return DoctorCheck(
            name="bash_login_startup",
            status="warning",
            detail=f"{login_file_clause}, but it does not reference `~/.bashrc`.",
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
        return DoctorCheck(name="bash_login_startup", status="warning", detail=detail)

    if len(chain) == 2:
        return DoctorCheck(
            name="bash_login_startup",
            status="ok",
            detail=f"{login_file_clause}, and it references `~/.bashrc`.",
        )

    return DoctorCheck(
        name="bash_login_startup",
        status="ok",
        detail=(
            f"{login_file_clause}, and it reaches `~/.bashrc` "
            f"via {_format_bash_startup_paths(chain[1:-1])}."
        ),
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
            f"type {shlex.quote('codex')} >/dev/null 2>&1 || exit {_CODEX_AFTER_KIMI_MISSING_EXIT_CODE}",
            (
                "codex login status >/dev/null 2>&1 "
                f"|| exit {_CODEX_LOGIN_STATUS_AFTER_KIMI_FAILED_EXIT_CODE}"
            ),
        ]
    )
    try:
        result = subprocess.run(
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
    if result.returncode == 0:
        return DoctorCheck(
            name="kimi_shell_helper",
            status="ok",
            detail=(
                "`kimi` is available in `bash -lic`, exports `ANTHROPIC_API_KEY`, "
                f"sets `ANTHROPIC_BASE_URL={_EXPECTED_KIMI_ANTHROPIC_BASE_URL}`, "
                "keeps both `claude` and `codex` available, and confirms `codex login status` succeeds "
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
    if result.returncode == _CODEX_AFTER_KIMI_MISSING_EXIT_CODE:
        return DoctorCheck(
            name="kimi_shell_helper",
            status="failed",
            detail=(
                "`kimi` runs in `bash -lic`, but `codex` is unavailable afterwards; "
                "the bundled smoke pipeline will not be able to launch Codex inside that shared Kimi bootstrap."
            ),
        )
    if result.returncode == _CODEX_LOGIN_STATUS_AFTER_KIMI_FAILED_EXIT_CODE:
        return DoctorCheck(
            name="kimi_shell_helper",
            status="failed",
            detail=(
                "`kimi` runs in `bash -lic`, and `codex` is on PATH afterwards, but `codex login status` still "
                "fails; make sure Codex is logged in or `OPENAI_API_KEY` is exported in that shared smoke shell."
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
    if login_file is None:
        return DoctorCheck(
            name="bash_login_startup",
            status="ok",
            detail=(
                "No `~/.bash_profile`, `~/.bash_login`, or `~/.profile` was found, but `bash -lic` already exposes "
                "`kimi`, `claude`, and `codex`; a `~/.bashrc` bridge is not required for the bundled smoke pipeline."
            ),
        )

    return DoctorCheck(
        name="bash_login_startup",
        status="ok",
        detail=(
            f"{_bash_login_file_clause(home, login_file)}, and `bash -lic` already exposes `kimi`, `claude`, and "
            "`codex`; a `~/.bashrc` bridge is not required for the bundled smoke pipeline."
        ),
    )


def build_local_smoke_doctor_report(home: Path | None = None) -> DoctorReport:
    resolved_home = home or Path.home()
    codex_check = _check_codex_executable(resolved_home)
    claude_check = _check_claude_host_executable()
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
