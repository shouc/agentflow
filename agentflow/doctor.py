from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


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


def _check_executable(name: str) -> DoctorCheck:
    path = shutil.which(name)
    if path:
        return DoctorCheck(name=name, status="ok", detail=f"Found `{name}` at `{path}`.")
    return DoctorCheck(name=name, status="failed", detail=f"`{name}` is not on PATH.")


def _bash_login_file(home: Path) -> Path | None:
    for filename in (".bash_profile", ".bash_login", ".profile"):
        candidate = home / filename
        if candidate.exists():
            return candidate
    return None


def _check_bash_login_startup(home: Path) -> DoctorCheck:
    login_file = _bash_login_file(home)
    if login_file is None:
        return DoctorCheck(
            name="bash_login_startup",
            status="warning",
            detail="No `~/.bash_profile`, `~/.bash_login`, or `~/.profile` was found for bash login shells.",
        )

    text = login_file.read_text(encoding="utf-8", errors="ignore")
    if ".bashrc" in text:
        return DoctorCheck(
            name="bash_login_startup",
            status="ok",
            detail=f"Bash login shells use `~/{login_file.name}`, and it references `~/.bashrc`.",
        )
    return DoctorCheck(
        name="bash_login_startup",
        status="warning",
        detail=f"Bash login shells use `~/{login_file.name}`, but it does not reference `~/.bashrc`.",
    )


def _check_kimi_shell_helper(home: Path | None = None) -> DoctorCheck:
    env = os.environ.copy()
    if home is not None:
        env["HOME"] = str(home)
    result = subprocess.run(
        ["bash", "-lic", f"type {shlex.quote('kimi')}"] ,
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )
    if result.returncode == 0:
        return DoctorCheck(
            name="kimi_shell_helper",
            status="ok",
            detail="`kimi` is available in `bash -lic` for the bundled smoke pipeline.",
        )
    return DoctorCheck(
        name="kimi_shell_helper",
        status="failed",
        detail="`kimi` is unavailable in `bash -lic`; add it to your bash startup files before running the bundled smoke pipeline.",
    )


def build_local_smoke_doctor_report(home: Path | None = None) -> DoctorReport:
    resolved_home = home or Path.home()
    checks = [
        _check_executable("codex"),
        _check_executable("claude"),
        _check_bash_login_startup(resolved_home),
        _check_kimi_shell_helper(resolved_home),
    ]
    if any(check.status == "failed" for check in checks):
        status = "failed"
    elif any(check.status == "warning" for check in checks):
        status = "warning"
    else:
        status = "ok"
    return DoctorReport(status=status, checks=checks)
