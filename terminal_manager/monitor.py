from __future__ import annotations

import argparse
import os
import shlex
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

from .model import ShellInfo
from .store import load_shells, remove_shell, save_shell
from .x11 import X11Error, active_window_id


PROCESS_STATES = {
    "R": "正在执行",
    "S": "休眠/等待事件",
    "D": "不可中断等待",
    "T": "已暂停",
    "t": "跟踪暂停",
    "Z": "僵尸进程",
    "X": "已结束",
    "I": "内核空闲",
}


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def proc_stat(pid: int) -> tuple[str, str]:
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        close = text.rfind(")")
        command = text[text.find("(") + 1 : close]
        state = text[close + 2 :].split()[0]
        return command, state
    except (OSError, IndexError):
        return "", "X"


def proc_cmdline(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes().rstrip(b"\0")
        args = raw.split(b"\0")
        return " ".join(shlex.quote(arg.decode(errors="replace")) for arg in args)
    except OSError:
        return ""


def proc_cwd(pid: int) -> str:
    try:
        return os.readlink(f"/proc/{pid}/cwd")
    except OSError:
        return ""


def proc_tpgid(pid: int) -> int | None:
    """Read the terminal foreground process group from Linux /proc.

    /proc/<pid>/stat field 8 is tpgid. After removing pid and the parenthesized
    comm field, it is index 5 in the remaining fields.
    """
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        close = text.rfind(")")
        value = int(text[close + 2 :].split()[5])
        return value if value > 0 else None
    except (OSError, ValueError, IndexError):
        return None


def foreground_pgid(tty: str, shell_pid: int | None = None) -> int | None:
    try:
        fd = os.open(tty, os.O_RDONLY | os.O_NONBLOCK)
        try:
            return os.tcgetpgrp(fd)
        finally:
            os.close(fd)
    except OSError:
        return proc_tpgid(shell_pid) if shell_pid else None


def refresh(info: ShellInfo) -> ShellInfo:
    now = time.time()
    if not process_exists(info.shell_pid):
        info.status = "ended"
        info.status_detail = "Shell 进程已经结束"
        info.foreground_pid = None
        info.process_state = "X"
        info.last_seen = now
        return info

    pgid = foreground_pgid(info.tty, info.shell_pid)
    info.foreground_pid = pgid
    target_pid = pgid or info.shell_pid
    short_command, state = proc_stat(target_pid)
    info.process_state = state
    info.cwd = proc_cwd(target_pid) or proc_cwd(info.shell_pid) or info.cwd
    info.command = proc_cmdline(target_pid) or short_command or info.command
    if pgid is None:
        info.status = "unknown"
        info.status_detail = "无法读取终端前台进程组"
    elif pgid == safe_getpgid(info.shell_pid):
        info.status = "idle"
        info.status_detail = "Shell 位于前台，通常表示正在等待命令"
        info.command = short_command or Path(os.environ.get("SHELL", "shell")).name
    elif state in ("T", "t"):
        info.status = "stopped"
        info.status_detail = PROCESS_STATES.get(state, "进程已暂停")
    else:
        info.status = "running"
        detail = PROCESS_STATES.get(state, f"进程状态 {state}")
        info.status_detail = f"前台进程存在；内核状态：{detail}"
    info.last_seen = now
    return info


def safe_getpgid(pid: int) -> int | None:
    try:
        return os.getpgid(pid)
    except ProcessLookupError:
        return None


def monitor_loop(shell_id: str, interval: float = 1.5) -> None:
    while True:
        matches = [item for item in load_shells() if item.shell_id == shell_id]
        if not matches:
            return
        info = refresh(matches[0])
        save_shell(info)
        if info.status == "ended":
            return
        time.sleep(interval)


def register_main() -> None:
    parser = argparse.ArgumentParser(description="注册当前 Shell 到 Terminal Manager")
    parser.add_argument("--name", help="总览中显示的名称")
    parser.add_argument("--foreground", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--shell-id", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.foreground:
        if not args.shell_id:
            parser.error("--foreground 需要 --shell-id")
        monitor_loop(args.shell_id)
        return

    if not sys.stdin.isatty():
        raise SystemExit("请在需要管理的交互式 Shell 中运行此命令。")
    shell_pid = os.getppid()
    tty = os.ttyname(sys.stdin.fileno())
    try:
        window_id = active_window_id()
    except (X11Error, subprocess.SubprocessError, ValueError) as exc:
        raise SystemExit(f"无法取得当前终端窗口：{exc}") from exc

    # One live registration per shell. Re-registering updates its name/window.
    existing = next((item for item in load_shells() if item.shell_pid == shell_pid), None)
    shell_id = existing.shell_id if existing else uuid.uuid4().hex[:12]
    now = time.time()
    info = ShellInfo(
        shell_id=shell_id,
        window_id=window_id,
        shell_pid=shell_pid,
        tty=tty,
        name=args.name or (existing.name if existing else Path(proc_cwd(shell_pid) or "Shell").name),
        status="idle",
        status_detail="监测器正在启动",
        command=Path(os.environ.get("SHELL", "shell")).name,
        cwd=proc_cwd(shell_pid),
        foreground_pid=shell_pid,
        process_state="S",
        registered_at=existing.registered_at if existing else now,
        last_seen=now,
    )
    save_shell(info)
    subprocess.Popen(
        [sys.executable, "-m", "terminal_manager.monitor", "--foreground", "--shell-id", shell_id],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    print(f"已注册：{info.name}（Shell {shell_pid}，窗口 {window_id}）")


def unregister_main() -> None:
    parser = argparse.ArgumentParser(description="从 Terminal Manager 注销 Shell")
    parser.add_argument("shell_id", nargs="?", help="默认注销当前 Shell")
    args = parser.parse_args()
    shell_pid = os.getppid()
    shell_id = args.shell_id
    if not shell_id:
        match = next((item for item in load_shells() if item.shell_pid == shell_pid), None)
        shell_id = match.shell_id if match else None
    if not shell_id or not remove_shell(shell_id):
        raise SystemExit("没有找到对应的注册记录。")
    print(f"已注销：{shell_id}")


if __name__ == "__main__":
    register_main()
