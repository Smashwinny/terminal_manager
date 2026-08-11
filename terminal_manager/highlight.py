from __future__ import annotations

import tkinter as tk


PURPLE = "#7c6cff"


def flash_geometry(geometry: tuple[int, int, int, int]) -> str:
    x, y, width, height = geometry
    return f"{width}x{height}+{x}+{y}"


class WindowHighlighter:
    """Briefly tint a terminal purple without changing its profile or TTY."""

    def __init__(self, root: tk.Tk, duration_ms: int = 720) -> None:
        self.root = root
        self.duration_ms = duration_ms
        self.hide_job: str | None = None
        self.overlay = tk.Toplevel(root)
        self.overlay.withdraw()
        self.overlay.overrideredirect(True)
        self.overlay.configure(background=PURPLE, cursor="arrow")
        self.overlay.attributes("-topmost", True)
        try:
            self.overlay.attributes("-alpha", 0.42)
            self.overlay.attributes("-type", "splash")
        except tk.TclError:
            pass

    def flash(self, geometry: tuple[int, int, int, int]) -> None:
        if self.hide_job is not None:
            self.root.after_cancel(self.hide_job)
        self.overlay.geometry(flash_geometry(geometry))
        self.overlay.deiconify()
        self.overlay.lift()
        self.hide_job = self.root.after(self.duration_ms, self.hide)

    def hide(self) -> None:
        self.hide_job = None
        self.overlay.withdraw()
