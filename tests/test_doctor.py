from __future__ import annotations

import os
import subprocess
from pathlib import Path

from agentflow.doctor import build_bash_login_shell_bridge_recommendation, build_local_smoke_doctor_report


_KIMI_HELPER_OK_DETAIL = (
    "`kimi` is available in `bash -lic`, exports `ANTHROPIC_API_KEY`, "
    "sets `ANTHROPIC_BASE_URL=https://api.kimi.com/coding/`, keeps both `claude` and `codex` available, "
    "and confirms `codex login status` succeeds for the bundled smoke pipeline."
)


def test_local_smoke_doctor_report_ok_with_profile_bridge(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".profile").write_text('if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n', encoding="utf-8")
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    monkeypatch.setattr("agentflow.doctor.shutil.which", lambda name: f"/tmp/{name}")
    monkeypatch.setattr(
        "agentflow.doctor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr=""),
    )

    report = build_local_smoke_doctor_report(home=home)

    assert report.status == "ok"
    assert report.as_dict() == {
        "status": "ok",
        "checks": [
            {"name": "codex", "status": "ok", "detail": "Found `codex` at `/tmp/codex`."},
            {"name": "claude", "status": "ok", "detail": "Found `claude` at `/tmp/claude`."},
            {
                "name": "bash_login_startup",
                "status": "ok",
                "detail": "Bash login shells fall back to `~/.profile` because neither `~/.bash_profile` nor `~/.bash_login` exists, and it references `~/.bashrc`.",
            },
            {
                "name": "kimi_shell_helper",
                "status": "ok",
                "detail": _KIMI_HELPER_OK_DETAIL,
            },
        ],
    }


def test_local_smoke_doctor_report_ok_with_quoted_home_prefix_bridge(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".profile").write_text('if [ -f "$HOME"/.bashrc ]; then . "$HOME"/.bashrc; fi\n', encoding="utf-8")
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    monkeypatch.setattr("agentflow.doctor.shutil.which", lambda name: f"/tmp/{name}")
    monkeypatch.setattr(
        "agentflow.doctor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr=""),
    )

    report = build_local_smoke_doctor_report(home=home)

    assert report.status == "ok"
    assert report.as_dict()["checks"][2] == {
        "name": "bash_login_startup",
        "status": "ok",
        "detail": "Bash login shells fall back to `~/.profile` because neither `~/.bash_profile` nor `~/.bash_login` exists, and it references `~/.bashrc`.",
    }


def test_local_smoke_doctor_report_ok_with_absolute_home_bridge(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".profile").write_text(f'if [ -f "{home}/.bashrc" ]; then . "{home}/.bashrc"; fi\n', encoding="utf-8")
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    monkeypatch.setattr("agentflow.doctor.shutil.which", lambda name: f"/tmp/{name}")
    monkeypatch.setattr(
        "agentflow.doctor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr=""),
    )

    report = build_local_smoke_doctor_report(home=home)

    assert report.status == "ok"
    assert report.as_dict()["checks"][2] == {
        "name": "bash_login_startup",
        "status": "ok",
        "detail": "Bash login shells fall back to `~/.profile` because neither `~/.bash_profile` nor `~/.bash_login` exists, and it references `~/.bashrc`.",
    }


def test_local_smoke_doctor_report_follows_transitive_profile_bridge(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".bash_profile").write_text(
        'if [ -f "$HOME/.profile" ]; then . "$HOME/.profile"; fi\n',
        encoding="utf-8",
    )
    (home / ".profile").write_text(
        'if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n',
        encoding="utf-8",
    )
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    monkeypatch.setattr("agentflow.doctor.shutil.which", lambda name: f"/tmp/{name}")
    monkeypatch.setattr(
        "agentflow.doctor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr=""),
    )

    report = build_local_smoke_doctor_report(home=home)

    assert report.status == "ok"
    assert report.as_dict()["checks"][2] == {
        "name": "bash_login_startup",
        "status": "ok",
        "detail": "Bash login shells use `~/.bash_profile`, and it reaches `~/.bashrc` via `~/.profile`.",
    }


def test_local_smoke_doctor_report_follows_transitive_quoted_home_bridge(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".bash_profile").write_text(
        'if [ -f "${HOME}"/.profile ]; then . "${HOME}"/.profile; fi\n',
        encoding="utf-8",
    )
    (home / ".profile").write_text(
        'if [ -f "${HOME}"/.bashrc ]; then . "${HOME}"/.bashrc; fi\n',
        encoding="utf-8",
    )
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    monkeypatch.setattr("agentflow.doctor.shutil.which", lambda name: f"/tmp/{name}")
    monkeypatch.setattr(
        "agentflow.doctor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr=""),
    )

    report = build_local_smoke_doctor_report(home=home)

    assert report.status == "ok"
    assert report.as_dict()["checks"][2] == {
        "name": "bash_login_startup",
        "status": "ok",
        "detail": "Bash login shells use `~/.bash_profile`, and it reaches `~/.bashrc` via `~/.profile`.",
    }


def test_local_smoke_doctor_report_follows_transitive_absolute_home_bridge(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".bash_profile").write_text(
        f'if [ -f "{home}/.profile" ]; then . "{home}/.profile"; fi\n',
        encoding="utf-8",
    )
    (home / ".profile").write_text(
        f'if [ -f "{home}/.bashrc" ]; then . "{home}/.bashrc"; fi\n',
        encoding="utf-8",
    )
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    monkeypatch.setattr("agentflow.doctor.shutil.which", lambda name: f"/tmp/{name}")
    monkeypatch.setattr(
        "agentflow.doctor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr=""),
    )

    report = build_local_smoke_doctor_report(home=home)

    assert report.status == "ok"
    assert report.as_dict()["checks"][2] == {
        "name": "bash_login_startup",
        "status": "ok",
        "detail": "Bash login shells use `~/.bash_profile`, and it reaches `~/.bashrc` via `~/.profile`.",
    }


def test_local_smoke_doctor_report_keeps_custom_home_bridge_when_kimi_fails(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".bash_profile").write_text(
        'if [ -f "$HOME/.bash_agentflow" ]; then . "$HOME/.bash_agentflow"; fi\n',
        encoding="utf-8",
    )
    (home / ".bash_agentflow").write_text(
        'if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n',
        encoding="utf-8",
    )
    (home / ".bashrc").write_text("# bridge present\n", encoding="utf-8")

    monkeypatch.setattr("agentflow.doctor.shutil.which", lambda name: f"/tmp/{name}")
    monkeypatch.setattr(
        "agentflow.doctor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=11, stdout="", stderr=""),
    )

    report = build_local_smoke_doctor_report(home=home)

    assert report.status == "failed"
    assert report.as_dict()["checks"][2] == {
        "name": "bash_login_startup",
        "status": "ok",
        "detail": "Bash login shells use `~/.bash_profile`, and it reaches `~/.bashrc` via `~/.bash_agentflow`.",
    }


def test_local_smoke_doctor_report_accepts_runtime_ready_shell_when_referenced_bashrc_is_missing(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".profile").write_text('if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n', encoding="utf-8")

    monkeypatch.setattr("agentflow.doctor.shutil.which", lambda name: f"/tmp/{name}")
    monkeypatch.setattr(
        "agentflow.doctor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr=""),
    )

    report = build_local_smoke_doctor_report(home=home)

    assert report.as_dict()["checks"][2] == {
        "name": "bash_login_startup",
        "status": "ok",
        "detail": (
            "Bash login shells fall back to `~/.profile` because neither `~/.bash_profile` nor `~/.bash_login` exists, and `bash -lic` already exposes `kimi`, `claude`, and `codex`; "
            "a `~/.bashrc` bridge is not required for the bundled smoke pipeline."
        ),
    }


def test_local_smoke_doctor_report_accepts_runtime_ready_shell_without_bash_login_file(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    monkeypatch.setattr("agentflow.doctor.shutil.which", lambda name: f"/tmp/{name}")
    monkeypatch.setattr(
        "agentflow.doctor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr=""),
    )

    report = build_local_smoke_doctor_report(home=home)

    assert report.as_dict()["checks"][2] == {
        "name": "bash_login_startup",
        "status": "ok",
        "detail": (
            "No `~/.bash_profile`, `~/.bash_login`, or `~/.profile` was found, but `bash -lic` already exposes "
            "`kimi`, `claude`, and `codex`; a `~/.bashrc` bridge is not required for the bundled smoke pipeline."
        ),
    }


def test_local_smoke_doctor_report_accepts_runtime_ready_shell_when_bash_profile_shadows_profile_bridge(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".bash_profile").write_text('export PATH="$HOME/bin:$PATH"\n', encoding="utf-8")
    (home / ".profile").write_text('if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n', encoding="utf-8")
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    monkeypatch.setattr("agentflow.doctor.shutil.which", lambda name: f"/tmp/{name}")
    monkeypatch.setattr(
        "agentflow.doctor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr=""),
    )

    report = build_local_smoke_doctor_report(home=home)

    assert report.as_dict()["checks"][2] == {
        "name": "bash_login_startup",
        "status": "ok",
        "detail": (
            "Bash login shells use `~/.bash_profile`, and `bash -lic` already exposes `kimi`, `claude`, and "
            "`codex`; a `~/.bashrc` bridge is not required for the bundled smoke pipeline."
        ),
    }


def test_local_smoke_doctor_report_accepts_runtime_ready_shell_with_commented_bashrc_reference(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".profile").write_text(
        '# if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n',
        encoding="utf-8",
    )
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    monkeypatch.setattr("agentflow.doctor.shutil.which", lambda name: f"/tmp/{name}")
    monkeypatch.setattr(
        "agentflow.doctor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr=""),
    )

    report = build_local_smoke_doctor_report(home=home)

    assert report.as_dict()["checks"][2] == {
        "name": "bash_login_startup",
        "status": "ok",
        "detail": (
            "Bash login shells fall back to `~/.profile` because neither `~/.bash_profile` nor `~/.bash_login` exists, and `bash -lic` already exposes `kimi`, `claude`, and `codex`; "
            "a `~/.bashrc` bridge is not required for the bundled smoke pipeline."
        ),
    }


def test_local_smoke_doctor_report_accepts_runtime_ready_shell_with_commented_transitive_bridge(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".bash_profile").write_text(
        '# if [ -f "$HOME/.profile" ]; then . "$HOME/.profile"; fi\n',
        encoding="utf-8",
    )
    (home / ".profile").write_text('if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n', encoding="utf-8")
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    monkeypatch.setattr("agentflow.doctor.shutil.which", lambda name: f"/tmp/{name}")
    monkeypatch.setattr(
        "agentflow.doctor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr=""),
    )

    report = build_local_smoke_doctor_report(home=home)

    assert report.as_dict()["checks"][2] == {
        "name": "bash_login_startup",
        "status": "ok",
        "detail": (
            "Bash login shells use `~/.bash_profile`, and `bash -lic` already exposes `kimi`, `claude`, and "
            "`codex`; a `~/.bashrc` bridge is not required for the bundled smoke pipeline."
        ),
    }


def test_local_smoke_doctor_report_fails_when_kimi_helper_missing(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".bash_profile").write_text("export PATH=\"$HOME/bin:$PATH\"\n", encoding="utf-8")
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    monkeypatch.setattr("agentflow.doctor.shutil.which", lambda name: f"/tmp/{name}")
    monkeypatch.setattr(
        "agentflow.doctor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=11, stdout="", stderr="bash: type: kimi: not found\n"),
    )

    report = build_local_smoke_doctor_report(home=home)

    assert report.status == "failed"
    assert report.as_dict() == {
        "status": "failed",
        "checks": [
            {"name": "codex", "status": "ok", "detail": "Found `codex` at `/tmp/codex`."},
            {"name": "claude", "status": "ok", "detail": "Found `claude` at `/tmp/claude`."},
            {
                "name": "bash_login_startup",
                "status": "warning",
                "detail": "Bash login shells use `~/.bash_profile`, but it does not reference `~/.bashrc`.",
            },
            {
                "name": "kimi_shell_helper",
                "status": "failed",
                "detail": "`kimi` is unavailable in `bash -lic`; add it to your bash startup files before running the bundled smoke pipeline.",
            },
        ],
    }


def test_local_smoke_doctor_report_checks_kimi_helper_in_supplied_home(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".profile").write_text('if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n', encoding="utf-8")
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    monkeypatch.setattr("agentflow.doctor.shutil.which", lambda name: f"/tmp/{name}")

    def fake_run(*args, **kwargs):
        env = kwargs.get("env") or {}
        home_value = env.get("HOME")
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0 if home_value == str(home) else 11,
            stdout="",
            stderr="" if home_value == str(home) else "bash: type: kimi: not found\n",
        )

    monkeypatch.setattr("agentflow.doctor.subprocess.run", fake_run)

    report = build_local_smoke_doctor_report(home=home)

    assert report.status == "ok"
    assert report.as_dict()["checks"][-1] == {
        "name": "kimi_shell_helper",
        "status": "ok",
        "detail": _KIMI_HELPER_OK_DETAIL,
    }


def test_local_smoke_doctor_report_accepts_claude_when_bootstrap_already_provides_it(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".profile").write_text('if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n', encoding="utf-8")
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    def fake_which(name: str) -> str | None:
        if name == "codex":
            return "/tmp/codex"
        return None

    monkeypatch.setattr("agentflow.doctor.shutil.which", fake_which)
    monkeypatch.setattr(
        "agentflow.doctor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr=""),
    )

    report = build_local_smoke_doctor_report(home=home)

    assert report.status == "ok"
    assert report.as_dict()["checks"][1] == {
        "name": "claude",
        "status": "ok",
        "detail": "`claude` is not on PATH outside the smoke shell bootstrap, but `bash -lic` plus `kimi` already provides it for the bundled smoke pipeline.",
    }
    assert report.as_dict()["checks"][-1] == {
        "name": "kimi_shell_helper",
        "status": "ok",
        "detail": _KIMI_HELPER_OK_DETAIL,
    }


def test_local_smoke_doctor_report_accepts_codex_when_bootstrap_already_provides_it(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".profile").write_text('if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n', encoding="utf-8")
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    def fake_which(name: str) -> str | None:
        if name == "claude":
            return "/tmp/claude"
        return None

    monkeypatch.setattr("agentflow.doctor.shutil.which", fake_which)
    monkeypatch.setattr(
        "agentflow.doctor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr=""),
    )

    report = build_local_smoke_doctor_report(home=home)

    assert report.status == "ok"
    assert report.as_dict()["checks"][0] == {
        "name": "codex",
        "status": "ok",
        "detail": "`codex` is not on PATH outside the smoke shell bootstrap, but `bash -lic` plus `kimi` already provides it for the bundled smoke pipeline.",
    }


def test_local_smoke_doctor_report_accepts_codex_when_kimi_bootstrap_provides_it(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".profile").write_text('if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n', encoding="utf-8")
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    def fake_which(name: str) -> str | None:
        if name == "claude":
            return "/tmp/claude"
        return None

    def fake_run(*args, **kwargs):
        script = args[0][-1]
        if script.startswith("type codex"):
            return subprocess.CompletedProcess(args=args[0], returncode=10, stdout="", stderr="")
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr("agentflow.doctor.shutil.which", fake_which)
    monkeypatch.setattr("agentflow.doctor.subprocess.run", fake_run)

    report = build_local_smoke_doctor_report(home=home)

    assert report.status == "ok"
    assert report.as_dict()["checks"][0] == {
        "name": "codex",
        "status": "ok",
        "detail": "`codex` is not on PATH outside the smoke shell bootstrap, but `bash -lic` plus `kimi` already provides it for the bundled smoke pipeline.",
    }
    assert report.as_dict()["checks"][-1] == {
        "name": "kimi_shell_helper",
        "status": "ok",
        "detail": _KIMI_HELPER_OK_DETAIL,
    }


def test_local_smoke_doctor_report_fails_when_kimi_helper_does_not_export_api_key(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".profile").write_text('if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n', encoding="utf-8")
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    monkeypatch.setattr("agentflow.doctor.shutil.which", lambda name: f"/tmp/{name}")
    monkeypatch.setattr(
        "agentflow.doctor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=13, stdout="", stderr=""),
    )

    report = build_local_smoke_doctor_report(home=home)

    assert report.status == "failed"
    assert report.as_dict()["checks"][-1] == {
        "name": "kimi_shell_helper",
        "status": "failed",
        "detail": "`kimi` runs in `bash -lic`, but it does not export `ANTHROPIC_API_KEY`; the bundled smoke pipeline will not be able to authenticate Claude-on-Kimi.",
    }


def test_local_smoke_doctor_report_fails_when_kimi_helper_does_not_export_base_url(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".profile").write_text('if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n', encoding="utf-8")
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    monkeypatch.setattr("agentflow.doctor.shutil.which", lambda name: f"/tmp/{name}")
    monkeypatch.setattr(
        "agentflow.doctor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=15, stdout="", stderr=""),
    )

    report = build_local_smoke_doctor_report(home=home)

    assert report.status == "failed"
    assert report.as_dict()["checks"][-1] == {
        "name": "kimi_shell_helper",
        "status": "failed",
        "detail": "`kimi` runs in `bash -lic`, but it does not export `ANTHROPIC_BASE_URL`; the bundled smoke pipeline will not be able to route Claude through Kimi.",
    }


def test_local_smoke_doctor_report_fails_when_kimi_helper_exports_wrong_base_url(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".profile").write_text('if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n', encoding="utf-8")
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    monkeypatch.setattr("agentflow.doctor.shutil.which", lambda name: f"/tmp/{name}")
    monkeypatch.setattr(
        "agentflow.doctor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=16,
            stdout="https://open.bigmodel.cn/api/anthropic\n",
            stderr="",
        ),
    )

    report = build_local_smoke_doctor_report(home=home)

    assert report.status == "failed"
    assert report.as_dict()["checks"][-1] == {
        "name": "kimi_shell_helper",
        "status": "failed",
        "detail": "`kimi` runs in `bash -lic`, but `ANTHROPIC_BASE_URL` is `https://open.bigmodel.cn/api/anthropic` instead of `https://api.kimi.com/coding/`; the bundled smoke pipeline will not be able to route Claude through Kimi.",
    }


def test_local_smoke_doctor_report_fails_when_claude_is_missing_in_bash_shell(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".profile").write_text('if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n', encoding="utf-8")
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    monkeypatch.setattr("agentflow.doctor.shutil.which", lambda name: f"/tmp/{name}")
    monkeypatch.setattr(
        "agentflow.doctor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=12, stdout="", stderr="bash: type: claude: not found\n"),
    )

    report = build_local_smoke_doctor_report(home=home)

    assert report.status == "failed"
    assert report.as_dict()["checks"][-1] == {
        "name": "kimi_shell_helper",
        "status": "failed",
        "detail": "`kimi` runs in `bash -lic`, but `claude` is unavailable afterwards; the bundled smoke pipeline will not be able to launch Claude-on-Kimi.",
    }


def test_local_smoke_doctor_report_fails_when_codex_is_missing_after_kimi_bootstrap(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".profile").write_text('if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n', encoding="utf-8")
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    monkeypatch.setattr("agentflow.doctor.shutil.which", lambda name: f"/tmp/{name}")
    monkeypatch.setattr(
        "agentflow.doctor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=14, stdout="", stderr="bash: type: codex: not found\n"),
    )

    report = build_local_smoke_doctor_report(home=home)

    assert report.status == "failed"
    assert report.as_dict()["checks"][-1] == {
        "name": "kimi_shell_helper",
        "status": "failed",
        "detail": "`kimi` runs in `bash -lic`, but `codex` is unavailable afterwards; the bundled smoke pipeline will not be able to launch Codex inside that shared Kimi bootstrap.",
    }


def test_local_smoke_doctor_report_fails_when_codex_is_not_logged_in_after_kimi_bootstrap(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".profile").write_text('if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n', encoding="utf-8")
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    monkeypatch.setattr("agentflow.doctor.shutil.which", lambda name: f"/tmp/{name}")
    monkeypatch.setattr(
        "agentflow.doctor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=17, stdout="", stderr="Not logged in\n"),
    )

    report = build_local_smoke_doctor_report(home=home)

    assert report.status == "failed"
    assert report.as_dict()["checks"][-1] == {
        "name": "kimi_shell_helper",
        "status": "failed",
        "detail": "`kimi` runs in `bash -lic`, and `codex` is on PATH afterwards, but `codex login status` still fails; make sure Codex is logged in or `OPENAI_API_KEY` is exported in that shared smoke shell.",
    }


def test_local_smoke_doctor_report_fails_when_bash_cannot_launch(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".profile").write_text('if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n', encoding="utf-8")
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    monkeypatch.setattr("agentflow.doctor.shutil.which", lambda name: f"/tmp/{name}")

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("bash not found")

    monkeypatch.setattr("agentflow.doctor.subprocess.run", fake_run)

    report = build_local_smoke_doctor_report(home=home)

    assert report.status == "failed"
    assert report.as_dict() == {
        "status": "failed",
        "checks": [
            {"name": "codex", "status": "ok", "detail": "Found `codex` at `/tmp/codex`."},
            {"name": "claude", "status": "ok", "detail": "Found `claude` at `/tmp/claude`."},
            {
                "name": "bash_login_startup",
                "status": "ok",
                "detail": "Bash login shells fall back to `~/.profile` because neither `~/.bash_profile` nor `~/.bash_login` exists, and it references `~/.bashrc`.",
            },
            {
                "name": "kimi_shell_helper",
                "status": "failed",
                "detail": "Could not launch `bash -lic` to verify `kimi`, `claude`, and `codex`: bash not found",
            },
        ],
    }


def test_local_smoke_doctor_report_redacts_sensitive_unknown_kimi_stderr(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".profile").write_text('if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n', encoding="utf-8")
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    monkeypatch.setattr("agentflow.doctor.shutil.which", lambda name: f"/tmp/{name}")
    monkeypatch.setattr(
        "agentflow.doctor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout="",
            stderr=(
                "bash: cannot set terminal process group (1234): Inappropriate ioctl for device\n"
                "bash: no job control in this shell\n"
                "export ANTHROPIC_API_KEY=super-secret\n"
                "Authorization: Bearer top-secret\n"
                "kimi bootstrap failed\n"
            ),
        ),
    )

    report = build_local_smoke_doctor_report(home=home)

    assert report.status == "failed"
    assert report.as_dict()["checks"][-1] == {
        "name": "kimi_shell_helper",
        "status": "failed",
        "detail": "`kimi` failed inside `bash -lic`: export ANTHROPIC_API_KEY=<redacted>\nAuthorization: <redacted>\nkimi bootstrap failed",
    }


def test_local_smoke_doctor_report_redacts_sensitive_unknown_codex_stderr(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".profile").write_text('if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n', encoding="utf-8")
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    def fake_which(name: str):
        if name == "claude":
            return "/tmp/claude"
        return None

    def fake_run(*args, **kwargs):
        command = args[0]
        if command[:2] == ["bash", "-lic"] and "type codex" in command[2]:
            return subprocess.CompletedProcess(
                args=command,
                returncode=1,
                stdout="",
                stderr='OPENAI_API_KEY="super-secret"\n',
            )
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("agentflow.doctor.shutil.which", fake_which)
    monkeypatch.setattr("agentflow.doctor.subprocess.run", fake_run)

    report = build_local_smoke_doctor_report(home=home)

    assert report.status == "failed"
    assert report.as_dict()["checks"][0] == {
        "name": "codex",
        "status": "failed",
        "detail": "`codex` is not on PATH, and `bash -lic` failed while looking for it: OPENAI_API_KEY=<redacted>",
    }


def test_local_smoke_doctor_report_warns_when_login_file_is_unreadable(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    login_file = home / ".bash_profile"
    login_file.write_text('if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n', encoding="utf-8")
    os.chmod(login_file, 0)

    monkeypatch.setattr("agentflow.doctor.shutil.which", lambda name: f"/tmp/{name}")
    monkeypatch.setattr(
        "agentflow.doctor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=11, stdout="", stderr=""),
    )

    report = build_local_smoke_doctor_report(home=home)

    assert report.status == "failed"
    assert report.as_dict()["checks"][2] == {
        "name": "bash_login_startup",
        "status": "warning",
        "detail": (
            "Bash login shells use `~/.bash_profile`, but AgentFlow could not read `~/.bash_profile` while "
            "checking whether login shells reach `~/.bashrc`: Permission denied."
        ),
    }


def test_shell_bridge_recommendation_targets_profile_when_no_login_file_exists(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()

    recommendation = build_bash_login_shell_bridge_recommendation(home=home)

    assert recommendation is not None
    assert recommendation.as_dict() == {
        "target": "~/.profile",
        "source": "~/.bashrc",
        "snippet": 'if [ -f "$HOME/.bashrc" ]; then\n  . "$HOME/.bashrc"\nfi\n',
        "reason": (
            "No `~/.bash_profile`, `~/.bash_login`, or `~/.profile` was found for bash login shells, "
            "so create a minimal startup file that reaches `~/.bashrc`."
        ),
    }


def test_shell_bridge_recommendation_targets_active_login_file_when_bridge_is_missing(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".bash_profile").write_text('export PATH="$HOME/bin:$PATH"\n', encoding="utf-8")

    recommendation = build_bash_login_shell_bridge_recommendation(home=home)

    assert recommendation is not None
    assert recommendation.as_dict() == {
        "target": "~/.bash_profile",
        "source": "~/.bashrc",
        "snippet": 'if [ -f "$HOME/.bashrc" ]; then\n  . "$HOME/.bashrc"\nfi\n',
        "reason": "Bash login shells use `~/.bash_profile`, but it does not reference `~/.bashrc`.",
    }


def test_shell_bridge_recommendation_reuses_shadowed_profile_bridge(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".bash_profile").write_text('export PATH="$HOME/bin:$PATH"\n', encoding="utf-8")
    (home / ".profile").write_text('if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n', encoding="utf-8")
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    recommendation = build_bash_login_shell_bridge_recommendation(home=home)

    assert recommendation is not None
    assert recommendation.as_dict() == {
        "target": "~/.bash_profile",
        "source": "~/.profile",
        "snippet": 'if [ -f "$HOME/.profile" ]; then\n  . "$HOME/.profile"\nfi\n',
        "reason": (
            "Bash login shells use `~/.bash_profile`, so `~/.profile` will never run even though it references "
            "`~/.bashrc`; add the same bridge to the active login file."
        ),
    }


def test_shell_bridge_recommendation_is_none_when_login_chain_already_reaches_bashrc(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".profile").write_text('if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n', encoding="utf-8")
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    recommendation = build_bash_login_shell_bridge_recommendation(home=home)

    assert recommendation is None


def test_shell_bridge_recommendation_is_none_when_custom_home_bridge_reaches_bashrc(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".bash_profile").write_text(
        'if [ -f "$HOME/.bash_agentflow" ]; then . "$HOME/.bash_agentflow"; fi\n',
        encoding="utf-8",
    )
    (home / ".bash_agentflow").write_text(
        'if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n',
        encoding="utf-8",
    )
    (home / ".bashrc").write_text("kimi(){ :; }\n", encoding="utf-8")

    recommendation = build_bash_login_shell_bridge_recommendation(home=home)

    assert recommendation is None


def test_shell_bridge_recommendation_handles_unreadable_login_file(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    login_file = home / ".bash_profile"
    login_file.write_text('export PATH="$HOME/bin:$PATH"\n', encoding="utf-8")
    os.chmod(login_file, 0)

    recommendation = build_bash_login_shell_bridge_recommendation(home=home)

    assert recommendation is not None
    assert recommendation.as_dict() == {
        "target": "~/.bash_profile",
        "source": "~/.bashrc",
        "snippet": 'if [ -f "$HOME/.bashrc" ]; then\n  . "$HOME/.bashrc"\nfi\n',
        "reason": (
            "Bash login shells use `~/.bash_profile`, but AgentFlow could not read `~/.bash_profile` while "
            "checking whether login shells reach `~/.bashrc`: Permission denied. Add a direct bridge to the active "
            "login file."
        ),
    }
