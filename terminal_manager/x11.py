from __future__ import annotations

import os
import shutil
import subprocess
import time
import ctypes
import ctypes.util
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
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow"], text=True, capture_output=True, timeout=2, check=True
        )
        return normalize_window_id(int(result.stdout.strip()))
    except (subprocess.SubprocessError, ValueError) as exc:
        raise X11Error("无法读取当前活动窗口") from exc


def focus_window(window_id: str, *, shake: bool = True, sync: bool = True) -> None:
    require_x11()
    wid = normalize_window_id(window_id)
    # wmctrl switches desktop when necessary; xdotool then raises and focuses it.
    subprocess.run(["wmctrl", "-i", "-a", wid], timeout=3, check=False)
    subprocess.run(["xdotool", "windowraise", wid], timeout=2, check=False)
    activate = ["xdotool", "windowactivate"]
    if sync:
        activate.append("--sync")
    activate.append(wid)
    subprocess.run(activate, timeout=3, check=False)
    if shake:
        shake_window(wid)


class _ClientData(ctypes.Union):
    _fields_ = [("b", ctypes.c_char * 20), ("s", ctypes.c_short * 10), ("l", ctypes.c_long * 5)]


class _ClientMessage(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("window", ctypes.c_ulong),
        ("message_type", ctypes.c_ulong),
        ("format", ctypes.c_int),
        ("data", _ClientData),
    ]


class _XEvent(ctypes.Union):
    _fields_ = [("type", ctypes.c_int), ("xclient", _ClientMessage), ("padding", ctypes.c_long * 24)]


def begin_window_move(window_id: str | int) -> bool:
    """Ask the X11 window manager to perform a native interactive move."""
    library = ctypes.util.find_library("X11")
    if not library:
        return False
    x11 = ctypes.CDLL(library)
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    x11.XDefaultRootWindow.restype = ctypes.c_ulong
    x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    x11.XInternAtom.restype = ctypes.c_ulong
    x11.XQueryPointer.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_uint),
    ]
    x11.XUngrabPointer.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    x11.XSendEvent.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_int,
        ctypes.c_long,
        ctypes.POINTER(_XEvent),
    ]
    x11.XFlush.argtypes = [ctypes.c_void_p]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    display = x11.XOpenDisplay(None)
    if not display:
        return False
    try:
        root = x11.XDefaultRootWindow(display)
        atom = x11.XInternAtom(display, b"_NET_WM_MOVERESIZE", False)
        root_return = ctypes.c_ulong()
        child_return = ctypes.c_ulong()
        root_x = ctypes.c_int()
        root_y = ctypes.c_int()
        window_x = ctypes.c_int()
        window_y = ctypes.c_int()
        mask = ctypes.c_uint()
        if not x11.XQueryPointer(
            display,
            root,
            ctypes.byref(root_return),
            ctypes.byref(child_return),
            ctypes.byref(root_x),
            ctypes.byref(root_y),
            ctypes.byref(window_x),
            ctypes.byref(window_y),
            ctypes.byref(mask),
        ):
            return False
        event = _XEvent()
        event.xclient.type = 33  # ClientMessage
        event.xclient.display = display
        event.xclient.window = int(normalize_window_id(window_id), 16)
        event.xclient.message_type = atom
        event.xclient.format = 32
        event.xclient.data.l[:] = (root_x.value, root_y.value, 8, 1, 1)  # MOVE, button 1
        x11.XUngrabPointer(display, 0)
        sent = x11.XSendEvent(display, root, False, (1 << 20) | (1 << 19), ctypes.byref(event))
        x11.XFlush(display)
        return bool(sent)
    finally:
        x11.XCloseDisplay(display)


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
