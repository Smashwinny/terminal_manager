from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Iterable

from .model import WindowInfo, normalize_window_id


class X11Error(RuntimeError):
    pass


def require_x11() -> None:
    if not os.environ.get("DISPLAY"):
        raise X11Error("未检测到 DISPLAY；Terminal Manager 当前需要 Linux X11 桌面会话。")
    missing = [tool for tool in ("wmctrl", "xdotool") if not shutil.which(tool)]
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
    try:
        # wmctrl switches desktop when necessary; xdotool then raises and focuses it.
        subprocess.run(["wmctrl", "-i", "-a", wid], timeout=3, check=False)
        subprocess.run(["xdotool", "windowraise", wid], timeout=2, check=False)
        activate = ["xdotool", "windowactivate"]
        if sync:
            activate.append("--sync")
        activate.append(wid)
        subprocess.run(activate, timeout=3, check=False)
    except subprocess.TimeoutExpired as exc:
        raise X11Error("目标窗口响应超时，可能已经关闭") from exc
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
    try:
        result = subprocess.run(
            ["wmctrl", "-i", "-r", wid, "-b", operation],
            timeout=3,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


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
            result = subprocess.run(
                ["xdotool", "windowmove", "--relative", wid, str(delta), "0"],
                timeout=1,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if result.returncode != 0:
                break
            applied += delta
            time.sleep(0.04)
    finally:
        if applied:
            subprocess.run(
                ["xdotool", "windowmove", "--relative", wid, str(-applied), "0"],
                timeout=1,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


def find_window(window_id: str, windows: Iterable[WindowInfo]) -> WindowInfo | None:
    wanted = normalize_window_id(window_id)
    return next((window for window in windows if window.window_id == wanted), None)
