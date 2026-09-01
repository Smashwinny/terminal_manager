from __future__ import annotations

import os
import shutil
import subprocess
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


def recovery_command(directory: Path) -> list[str] | None:
    candidates = (
        ("gnome-terminal", ["gnome-terminal", "--window", f"--working-directory={directory}"]),
        ("kgx", ["kgx", "--working-directory", str(directory)]),
        ("konsole", ["konsole", "--new-tab", "--workdir", str(directory)]),
        ("xfce4-terminal", ["xfce4-terminal", "--window", f"--working-directory={directory}"]),
        ("tilix", ["tilix", "--new-process", f"--working-directory={directory}"]),
    )
    for executable, command in candidates:
        if shutil.which(executable):
            return command
    return None


def launch_recovery_terminal(directory: Path) -> tuple[bool, str]:
    command = recovery_command(directory)
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
