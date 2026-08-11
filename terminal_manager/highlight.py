from __future__ import annotations

import tkinter as tk

from .model import WindowInfo


PURPLE = "#7c6cff"


def border_geometries(
    window: WindowInfo,
    thickness: int = 6,
    geometry: tuple[int, int, int, int] | None = None,
) -> tuple[str, str, str, str]:
    """Return top, bottom, left and right X11 border geometries."""
    x, y, width, height = geometry or (window.x, window.y, window.width, window.height)
    return (
        f"{width + thickness * 2}x{thickness}+{x - thickness}+{y - thickness}",
        f"{width + thickness * 2}x{thickness}+{x - thickness}+{y + height}",
        f"{thickness}x{height}+{x - thickness}+{y}",
        f"{thickness}x{height}+{x + width}+{y}",
    )


class WindowHighlighter:
    """Draw a focus-free purple outline around an active terminal window."""

    def __init__(self, root: tk.Tk, thickness: int = 6) -> None:
        self.root = root
        self.thickness = thickness
        self.window_id: str | None = None
        self.borders: list[tk.Toplevel] = []
        for _index in range(4):
            border = tk.Toplevel(root)
            border.withdraw()
            border.overrideredirect(True)
            border.configure(background=PURPLE, cursor="arrow")
            border.attributes("-topmost", True)
            try:
                border.attributes("-alpha", 0.96)
                border.attributes("-type", "splash")
            except tk.TclError:
                pass
            self.borders.append(border)

    def show(self, window: WindowInfo, geometry: tuple[int, int, int, int] | None = None) -> None:
        self.window_id = window.window_id
        for border, border_geometry in zip(
            self.borders, border_geometries(window, self.thickness, geometry)
        ):
            border.geometry(border_geometry)
            border.deiconify()
            border.lift()

    def hide(self) -> None:
        self.window_id = None
        for border in self.borders:
            border.withdraw()
