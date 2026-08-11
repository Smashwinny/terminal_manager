from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


TERMINAL_CLASS_MARKERS = (
    "gnome-terminal",
    "org.gnome.terminal",
    "kgx",
    "konsole",
    "tilix",
    "terminator",
    "xfce4-terminal",
    "alacritty",
    "kitty",
    "wezterm",
    "foot",
    "xterm",
    "urxvt",
    "waveterm",
)


@dataclass(frozen=True)
class WindowInfo:
    window_id: str
    desktop: int
    pid: int
    x: int
    y: int
    width: int
    height: int
    wm_class: str
    host: str
    title: str

    @property
    def is_terminal(self) -> bool:
        # Titles are user-controlled and may contain the word "terminal".
        # WM_CLASS is the stable, application-provided discriminator.
        value = self.wm_class.lower()
        return any(marker in value for marker in TERMINAL_CLASS_MARKERS)


@dataclass
class ShellInfo:
    shell_id: str
    window_id: str
    shell_pid: int
    tty: str
    name: str
    status: str
    status_detail: str
    command: str
    cwd: str
    foreground_pid: Optional[int]
    process_state: str
    registered_at: float
    last_seen: float


STATUS_LABELS = {
    "idle": "空闲",
    "running": "运行中",
    "stopped": "已暂停",
    "ended": "已结束",
    "unknown": "未知",
    "unbound": "已记录",
    "observing": "正在采样",
    "active": "正在输出",
    "waiting": "等待用户",
    "static": "静态/空闲",
    "window": "未注册",
}


def normalize_window_id(value: str | int) -> str:
    if isinstance(value, int):
        return f"0x{value:08x}"
    value = value.strip().lower()
    try:
        return f"0x{int(value, 16):08x}"
    except ValueError:
        return value
