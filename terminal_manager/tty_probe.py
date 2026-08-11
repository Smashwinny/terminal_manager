from __future__ import annotations

import os
import subprocess
import tempfile
import time
from pathlib import Path

from .highlight import RESET_SEQUENCE, can_highlight_tty, write_tty_sequence


PROBE_SEQUENCE = b"\x1b]11;#ff00fe\x07"


def terminal_ttys() -> list[str]:
    """Return live PTYs belonging to GNOME Terminal sessions."""
    ttys: set[str] = set()
    for process in Path("/proc").glob("[0-9]*"):
        try:
            environment = (process / "environ").read_bytes()
            if b"GNOME_TERMINAL_SCREEN=" not in environment:
                continue
            tty = os.readlink(process / "fd" / "0")
            if can_highlight_tty(tty):
                ttys.add(tty)
        except (OSError, ValueError):
            continue
    return sorted(ttys, key=_tty_number)


def probe_visible_tty(window_id: str, *, settle_seconds: float = 0.045) -> str | None:
    """Learn which PTY is visible by applying and visually detecting a test colour."""
    if not _probe_tools_available():
        return None
    time.sleep(0.06)
    for tty in terminal_ttys():
        try:
            if not write_tty_sequence(tty, PROBE_SEQUENCE):
                continue
            time.sleep(settle_seconds)
            if _window_has_probe_colour(window_id):
                return tty
        finally:
            write_tty_sequence(tty, RESET_SEQUENCE)
    return None


def _probe_tools_available() -> bool:
    from shutil import which

    return bool(which("xwd") and which("ffmpeg"))


def _window_has_probe_colour(window_id: str) -> bool:
    with tempfile.NamedTemporaryFile(prefix="terminal-manager-", suffix=".xwd") as image:
        capture = subprocess.run(
            ["xwd", "-silent", "-id", window_id, "-out", image.name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=False,
        )
        if capture.returncode != 0:
            return False
        decoded = subprocess.run(
            [
                "ffmpeg", "-v", "error", "-i", image.name,
                "-vf", "scale=64:64:flags=neighbor", "-f", "rawvideo",
                "-pix_fmt", "rgb24", "-",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
    pixels = decoded.stdout
    if decoded.returncode != 0 or len(pixels) < 64 * 64 * 3:
        return False
    matches = sum(
        1
        for offset in range(0, len(pixels) - 2, 3)
        if pixels[offset] > 225 and pixels[offset + 1] < 35 and pixels[offset + 2] > 220
    )
    # Transparent or overlapping terminals can leak a small amount of the
    # probe colour from another window. A real terminal background covers well
    # over 1,500 of the 4,096 samples in practice; require a conservative 900.
    return matches >= 900


def _tty_number(tty: str) -> tuple[int, str]:
    try:
        return int(tty.rsplit("/", 1)[1]), tty
    except ValueError:
        return 1_000_000, tty
