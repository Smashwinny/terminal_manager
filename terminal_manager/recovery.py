from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def validate_recovery_directory(value: str) -> tuple[Path | None, str]:
    if not value:
        return None, "没有保存工作目录"
    directory = Path(value)
    if not directory.is_absolute():
        return None, "保存的工作目录不是绝对路径"
    if not directory.is_dir():
        return None, "保存的工作目录不存在"
    if not os.access(directory, os.R_OK | os.X_OK):
        return None, "没有权限访问保存的工作目录"
    return directory, ""


def recovery_command(directory: Path, token: str | None = None, *, codex_session_id: str = "", codex_cwd: str = "", codex_home: str = "") -> list[str] | None:
    resume = None
    if codex_session_id:
        from .codex_sessions import resume_argv
        resume = resume_argv(codex_session_id, codex_cwd or str(directory), codex_home)
    candidates = (
        ("gnome-terminal", ["gnome-terminal", "--window", f"--working-directory={directory}"]),
        ("kgx", ["kgx", "--working-directory", str(directory)]),
        ("konsole", ["konsole", "--new-tab", "--workdir", str(directory)]),
        ("xfce4-terminal", ["xfce4-terminal", "--window", f"--working-directory={directory}"]),
        ("tilix", ["tilix", "--new-process", f"--working-directory={directory}"]),
    )
    for executable, command in candidates:
        if shutil.which(executable):
            if resume and executable != "gnome-terminal":
                continue
            if token and executable == "gnome-terminal":
                command.append(f"--role={token}")
            if resume:
                command.extend(["--", *resume])
            return command
    return None


def launch_recovery_terminal(directory: Path, token: str | None = None, **session) -> tuple[bool, str]:
    try:
        command = recovery_command(directory, token, **session)
    except ValueError as exc:
        return False, str(exc)
    if command is None:
        return False, "没有找到支持按目录启动的终端程序"
    try:
        subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        return True, ""
    except OSError as exc:
        return False, f"启动终端失败：{exc}"


def launch_tracked(entry: dict, token: str) -> tuple[bool, str]:
    """The worker checks launcher exit; a terminal child reports its own exit."""
    directory, error = validate_recovery_directory(entry['cwd'])
    if error:
        return False, error
    try:
        session = {k: entry.get(k, '') for k in ('codex_session_id', 'codex_cwd', 'codex_home')}
        command = recovery_command(directory, token, **session)
        if not command or command[0] != 'gnome-terminal':
            return False, '可靠恢复目前需要 GNOME Terminal；记录已保留'
        split = command.index('--') if '--' in command else len(command)
        child = command[split + 1:] if split < len(command) else [os.environ.get('SHELL', '/bin/bash')]
        argv = [*command[:split], '--', sys.executable, '-m', 'terminal_manager.recovery_child', token, '--', *child]
        result = subprocess.run(argv, capture_output=True, text=True, timeout=8)
        if result.returncode:
            return False, '终端启动失败：' + (result.stderr or result.stdout)[-1200:].strip()
        return True, ''
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
