from __future__ import annotations

import os


# OSC 11 changes the terminal background; OSC 111 restores the profile value.
# OSC 12/112 do the same for the cursor so it remains visible while previewing.
HIGHLIGHT_SEQUENCE = b"\x1b]11;#3b3275\x07\x1b]12;#ffffff\x07"
RESET_SEQUENCE = b"\x1b]111\x07\x1b]112\x07"


def can_preview_tty(tty: str) -> bool:
    return tty.startswith("/dev/pts/") and os.path.exists(tty) and os.access(tty, os.W_OK)


def set_tty_preview(tty: str, enabled: bool) -> bool:
    """Temporarily color a terminal via its output channel.

    This writes only terminal display control sequences. It does not inject
    keyboard input or execute a shell command. Returning False lets the UI hide
    associations that cannot provide a verifiable visual preview.
    """
    if not can_preview_tty(tty):
        return False
    flags = os.O_WRONLY | os.O_NONBLOCK | getattr(os, "O_NOCTTY", 0)
    try:
        fd = os.open(tty, flags)
        try:
            os.write(fd, HIGHLIGHT_SEQUENCE if enabled else RESET_SEQUENCE)
        finally:
            os.close(fd)
        return True
    except OSError:
        return False

