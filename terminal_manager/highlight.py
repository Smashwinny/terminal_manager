from __future__ import annotations

import os
import tkinter as tk


# This is the original, user-confirmed association-preview colour. OSC 11
# changes only VTE's background; text, cursor, geometry and input stay intact.
HIGHLIGHT_SEQUENCE = b"\x1b]11;#3b3275\x07\x1b]12;#ffffff\x07"
RESET_SEQUENCE = b"\x1b]111\x07\x1b]112\x07"


def can_highlight_tty(tty: str) -> bool:
    return tty.startswith("/dev/pts/") and os.path.exists(tty) and os.access(tty, os.W_OK)


def write_tty_sequence(tty: str, sequence: bytes) -> bool:
    if not can_highlight_tty(tty):
        return False
    flags = os.O_WRONLY | os.O_NONBLOCK | getattr(os, "O_NOCTTY", 0)
    try:
        fd = os.open(tty, flags)
        try:
            os.write(fd, sequence)
        finally:
            os.close(fd)
        return True
    except OSError:
        return False


def set_tty_highlight(tty: str, enabled: bool) -> bool:
    return write_tty_sequence(tty, HIGHLIGHT_SEQUENCE if enabled else RESET_SEQUENCE)


class WindowHighlighter:
    """Temporarily change a confirmed terminal TTY's native background."""

    def __init__(self, root: tk.Tk, duration_ms: int = 900) -> None:
        self.root = root
        self.duration_ms = duration_ms
        self.tty: str | None = None
        self.reset_job: str | None = None

    def flash(self, tty: str) -> bool:
        self.hide()
        if not set_tty_highlight(tty, True):
            return False
        self.tty = tty
        self.reset_job = self.root.after(self.duration_ms, self.hide)
        return True

    def hide(self) -> None:
        if self.reset_job is not None:
            self.root.after_cancel(self.reset_job)
            self.reset_job = None
        if self.tty:
            set_tty_highlight(self.tty, False)
            self.tty = None
