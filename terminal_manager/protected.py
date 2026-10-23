"""Independent per-task tmux servers; reconnect never creates or reruns a task."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

from .model import ShellInfo
from .store import _atomic_private_json, load_shells, save_shell, state_dir


class ProtectionError(RuntimeError):
    pass


def task_path(task_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", task_id):
        raise ProtectionError("无效的保活任务 ID")
    return state_dir().parent / "protected" / f"{task_id}.json"


def run(args: list[str], *, timeout: float = 4, check: bool = True) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProtectionError(f"任务服务未响应：{exc}") from exc
    if check and result.returncode:
        raise ProtectionError(result.stderr.strip() or "任务服务命令执行失败")
    return result


def tmux_prefix() -> list[str]:
    executable = shutil.which("tmux")
    if executable:
        return [executable]
    local = Path.home() / ".local/share/terminal-manager/tools/usr"
    if (local / "bin/tmux").exists():
        return ["env", f"LD_LIBRARY_PATH={local / 'lib/x86_64-linux-gnu'}", str(local / "bin/tmux")]
    raise ProtectionError("保活模式需要 tmux，请安装：sudo apt install tmux")


def boot_id() -> str:
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def load_task(task_id: str) -> dict:
    try:
        task = json.loads(task_path(task_id).read_text())
    except (OSError, ValueError) as exc:
        raise ProtectionError("找不到保活任务清单") from exc
    if not isinstance(task, dict):
        raise ProtectionError("保活任务清单格式无效")
    if task.get("boot_id") != boot_id():
        raise ProtectionError("任务属于上一次系统启动，原进程已无法重连；可以从恢复清单打开目录。")
    if task.get("ended"):
        raise ProtectionError("该任务已经明确结束")
    if task.get("id") != task_id or task.get("unit") != f"terminal-manager-task-{task_id}.service":
        raise ProtectionError("保活任务身份记录无效")
    if not isinstance(task.get("socket"), str) or not isinstance(task.get("server_pid"), int):
        raise ProtectionError("保活任务连接记录无效")
    return task


def tmux(task: dict, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    # -N prohibits implicit server creation during every query/reconnect.
    return run([*tmux_prefix(), "-N", "-S", task["socket"], *args], check=check)


def inspect_task(task_id: str) -> dict:
    task = load_task(task_id)
    result = tmux(task, "display-message", "-p", "-t", "task", "#{pid}\t#{pane_pid}\t#{pane_dead}\t#{pane_tty}\t#{pane_current_path}\t#{pane_title}")
    fields = result.stdout.rstrip("\n").split("\t", 5)
    if len(fields) != 6 or fields[0] != str(task["server_pid"]):
        raise ProtectionError("保活服务器身份变化，停止自动连接")
    if fields[2] == "1":
        raise ProtectionError("任务 Shell 已退出；保留了屏幕内容，但不会自动重新执行任务")
    clients = tmux(task, "list-clients", "-F", "#{client_pid}\t#{client_tty}")
    connected = dict(line.split("\t", 1) for line in clients.stdout.splitlines() if "\t" in line)
    views = []
    for path in (task_path(task_id).parent / "views").glob(f"{task_id}-*.json"):
        try:
            view = json.loads(path.read_text())
            if connected.get(str(view["pid"])) == view["tty"]:
                views.append(view)
            elif time.time() - view.get("created_at", 0) > 10:
                path.unlink(missing_ok=True)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return {**task, "pane_pid": int(fields[1]), "pane_tty": fields[3], "cwd": fields[4], "title": fields[5], "client_ttys": list(connected.values()), "views": views}


def create_task(directory: str, name: str) -> str:
    directory_path = Path(directory).resolve()
    if not directory_path.is_dir():
        raise ProtectionError("目录不存在")
    prefix = tmux_prefix()
    task_id = uuid.uuid4().hex
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "terminal-manager"
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    runtime.chmod(0o700)
    socket = runtime / f"{task_id}.sock"
    unit = f"terminal-manager-task-{task_id}.service"
    config = task_path(task_id).with_suffix(".conf")
    config.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Configuration is application-owned, with no user tmux hooks or plugins.
    config.write_text("set -g exit-unattached off\nset -g destroy-unattached off\nset -g remain-on-exit on\nset -g set-titles on\nset -g set-titles-string '#{pane_title}'\nset -g status off\nset -g history-limit 20000\n")
    config.chmod(0o600)
    task = {"id": task_id, "name": name, "cwd": str(directory_path), "socket": str(socket), "unit": unit, "boot_id": boot_id(), "ended": False, "server_pid": 0}
    _atomic_private_json(task_path(task_id), task)
    try:
        run(["systemd-run", "--user", f"--unit={unit}", "--property=Type=exec", "--property=Restart=no", "--property=KillMode=control-group", "--property=TimeoutStopSec=5s", *prefix, "-D", "-S", str(socket), "-f", str(config)])
        for _ in range(40):
            if socket.exists():
                break
            time.sleep(0.05)
        shell = os.environ.get("SHELL", "/bin/bash")
        tmux(task, "new-session", "-d", "-s", "task", "-c", str(directory_path), shell)
        task["server_pid"] = int(tmux(task, "display-message", "-p", "-t", "task", "#{pid}").stdout.strip())
        _atomic_private_json(task_path(task_id), task)
        now = time.time()
        save_shell(ShellInfo(task_id[:12], "", 0, "", name, "disconnected", "任务保活", "", str(directory_path), None, "", now, now, task_id))
    except Exception:
        run(["systemctl", "--user", "stop", unit], check=False, timeout=8)
        task["ended"] = True
        _atomic_private_json(task_path(task_id), task)
        raise
    return task_id


def open_task(task_id: str) -> None:
    inspect_task(task_id)
    if not shutil.which("gnome-terminal"):
        raise ProtectionError("当前保活窗口入口需要 GNOME Terminal")
    view_id = uuid.uuid4().hex[:12]
    run(["gnome-terminal", "--window", f"--role=terminal-manager-{task_id}-{view_id}", "--", sys.executable, "-m", "terminal_manager.protected", "attach", task_id, "--view", view_id], timeout=8)


def end_task(task_id: str) -> None:
    task = load_task(task_id)
    run(["systemctl", "--user", "stop", task["unit"]], timeout=8)
    task["ended"] = True
    _atomic_private_json(task_path(task_id), task)


def main() -> None:
    parser = argparse.ArgumentParser(description="保活任务：关闭窗口保持运行，重连不重复执行命令")
    sub = parser.add_subparsers(dest="action", required=True)
    new = sub.add_parser("new")
    new.add_argument("directory")
    new.add_argument("--name", default="保活任务")
    new.add_argument("--detached", action="store_true")
    for action in ("attach", "open", "end"):
        entry = sub.add_parser(action)
        entry.add_argument("id")
        if action == "attach":
            entry.add_argument("--view")
        if action == "end":
            entry.add_argument("--confirm", action="store_true", required=True)
    sub.add_parser("list")
    args = parser.parse_args()
    try:
        if args.action == "new":
            task_id = create_task(args.directory, args.name)
            print(task_id, flush=True)
            if not args.detached:
                open_task(task_id)
        elif args.action == "list":
            for path in (state_dir().parent / "protected").glob("*.json"):
                task_id = path.stem
                if re.fullmatch(r"[0-9a-f]{32}", task_id):
                    try:
                        state = inspect_task(task_id)
                        status = "已连接" if state["client_ttys"] else "已断开，任务存活"
                    except ProtectionError as exc:
                        status = str(exc)
                    print(task_id, status)
        elif args.action == "open":
            open_task(args.id)
        elif args.action == "end":
            end_task(args.id)
        else:
            task = inspect_task(args.id)
            if args.view:
                if not re.fullmatch(r"[0-9a-f]{12}", args.view):
                    raise ProtectionError("窗口连接标识无效")
                view = {"pid": os.getpid(), "tty": os.ttyname(0), "role": f"terminal-manager-{args.id}-{args.view}", "created_at": time.time()}
                _atomic_private_json(task_path(args.id).parent / "views" / f"{args.id}-{args.view}.json", view)
            command = [*tmux_prefix(), "-N", "-S", task["socket"], "attach-session", "-t", "task"]
            os.execvp(command[0], command)
    except ProtectionError as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
