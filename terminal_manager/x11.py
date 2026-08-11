from __future__ import annotations

import os
import shutil
import subprocess
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
    result = subprocess.run(
        ["wmctrl", "-lpGx"], text=True, capture_output=True, timeout=3, check=False
    )
    if result.returncode != 0:
        raise X11Error(result.stderr.strip() or "wmctrl 无法读取窗口列表")
    windows = [parse_wmctrl_line(line) for line in result.stdout.splitlines()]
    return [window for window in windows if window and window.is_terminal]


def active_window_id() -> str:
    require_x11()
    result = subprocess.run(
        ["xdotool", "getactivewindow"], text=True, capture_output=True, timeout=2, check=True
    )
    return normalize_window_id(int(result.stdout.strip()))


def focus_window(window_id: str) -> None:
    require_x11()
    wid = normalize_window_id(window_id)
    # wmctrl switches desktop when necessary; xdotool then raises and focuses it.
    subprocess.run(["wmctrl", "-i", "-a", wid], timeout=3, check=False)
    subprocess.run(["xdotool", "windowraise", wid], timeout=2, check=False)
    subprocess.run(["xdotool", "windowactivate", "--sync", wid], timeout=3, check=False)


def find_window(window_id: str, windows: Iterable[WindowInfo]) -> WindowInfo | None:
    wanted = normalize_window_id(window_id)
    return next((window for window in windows if window.window_id == wanted), None)

