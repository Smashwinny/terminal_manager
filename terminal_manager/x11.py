from __future__ import annotations

import os
import shutil
import subprocess
import time
import logging
from typing import Iterable

from .model import WindowInfo, normalize_window_id


class X11Error(RuntimeError):
    pass


log = logging.getLogger("terminal_manager.x11")


def window_exists(window_id: str) -> bool:
    try:
        result = subprocess.run(["xprop", "-id", normalize_window_id(window_id), "WM_CLASS"], capture_output=True, text=True, timeout=1)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def window_role(window_id: str) -> str:
    try:
        result = subprocess.run(["xprop", "-id", window_id, "WM_WINDOW_ROLE"], capture_output=True, text=True, timeout=1)
        return result.stdout.partition(" = ")[2].strip().strip('"') if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _operate(command: list[str], wid: str, timeout: float = 2) -> None:
    started = time.monotonic()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("window=%s op=%s failure=%s elapsed=%.3f", wid, command[0:2], type(exc).__name__, time.monotonic() - started)
        raise X11Error("目标窗口响应超时或操作失败，已停止本次操作") from exc
    log.info("window=%s op=%s rc=%s elapsed=%.3f", wid, command[0:2], result.returncode, time.monotonic() - started)
    if result.returncode:
        raise X11Error("目标窗口已失效或拒绝操作，已停止本次操作")


def require_x11() -> None:
    if not os.environ.get("DISPLAY"):
        raise X11Error("未检测到 DISPLAY；Terminal Manager 当前需要 Linux X11 桌面会话。")
    missing = [tool for tool in ("wmctrl", "xdotool", "xprop") if not shutil.which(tool)]
    if missing:
        raise X11Error("缺少窗口控制工具：" + ", ".join(missing))


def parse_wmctrl_line(line: str) -> WindowInfo | None:
    parts = line.rstrip("\n").split(None, 9)
    if len(parts) < 9:
        return None
    if len(parts) == 9:
        parts.append("")
    try:
        return WindowInfo(
            window_id=normalize_window_id(parts[0]),
            desktop=int(parts[1]),
            pid=int(parts[2]),
            x=int(parts[3]),
            y=int(parts[4]),
            width=int(parts[5]),
            height=int(parts[6]),
            wm_class=parts[7],
            host=parts[8],
            title=parts[9],
        )
    except ValueError:
        return None


def list_windows() -> list[WindowInfo]:
    require_x11()
    try:
        result = subprocess.run(
            ["wmctrl", "-lpGx"], text=True, capture_output=True, timeout=3, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise X11Error("wmctrl 读取窗口列表超时") from exc
    if result.returncode != 0:
        raise X11Error(result.stderr.strip() or "wmctrl 无法读取窗口列表")
    windows = [parse_wmctrl_line(line) for line in result.stdout.splitlines()]
    return [window for window in windows if window and window.is_terminal]


def active_window_id() -> str:
    require_x11()
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow"], text=True, capture_output=True, timeout=2, check=True
        )
        return normalize_window_id(int(result.stdout.strip()))
    except (subprocess.SubprocessError, ValueError) as exc:
        raise X11Error("无法读取当前活动窗口") from exc


def window_title(window_id: str) -> str | None:
    require_x11()
    try:
        result = subprocess.run(
            ["xdotool", "getwindowname", normalize_window_id(window_id)],
            text=True,
            capture_output=True,
            timeout=1,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ""
    return result.stdout.rstrip("\n") if result.returncode == 0 else None


def focus_window(window_id: str, *, shake: bool = True, sync: bool = True) -> None:
    require_x11()
    wid = normalize_window_id(window_id)
    if not window_exists(wid):
        raise X11Error("目标窗口不存在或响应超时")
    _operate(["wmctrl", "-i", "-a", wid], wid, 3)
    _operate(["xdotool", "windowraise", wid], wid)
    activate = ["xdotool", "windowactivate"]
    if sync:
        activate.append("--sync")
    activate.append(wid)
    _operate(activate, wid, 3)
    if shake:
        shake_window(wid)


def window_is_above(window_id: str) -> bool:
    """Return whether EWMH already marks a window as always-on-top."""
    wid = normalize_window_id(window_id)
    try:
        result = subprocess.run(
            ["xprop", "-id", wid, "_NET_WM_STATE"],
            text=True,
            capture_output=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and "_NET_WM_STATE_ABOVE" in result.stdout


def set_window_above(window_id: str, enabled: bool) -> bool:
    """Add or remove the EWMH always-on-top state for one exact window."""
    require_x11()
    wid = normalize_window_id(window_id)
    operation = "add,above" if enabled else "remove,above"
    if not window_exists(wid):
        return False
    _operate(["wmctrl", "-i", "-r", wid, "-b", operation], wid, 3)
    return True


def shake_window(window_id: str) -> None:
    """Give a focused window a short horizontal shake and restore its position.

    Relative moves avoid geometry/frame-coordinate differences between window
    managers. The deltas sum to zero, and the finally block compensates for any
    successful partial sequence if xdotool fails midway. Maximized windows are
    normally immovable, in which case the window manager simply ignores this.
    """
    wid = normalize_window_id(window_id)
    deltas = (10, -20, 18, -16, 12, -8, 4)
    applied = 0
    try:
        for delta in deltas:
            _operate(["xdotool", "windowmove", "--relative", wid, str(delta), "0"], wid, 1)
            applied += delta
            time.sleep(0.04)
    finally:
        if applied and window_exists(wid):
            _operate(["xdotool", "windowmove", "--relative", wid, str(-applied), "0"], wid, 1)


def find_window(window_id: str, windows: Iterable[WindowInfo]) -> WindowInfo | None:
    wanted = normalize_window_id(window_id)
    return next((window for window in windows if window.window_id == wanted), None)
