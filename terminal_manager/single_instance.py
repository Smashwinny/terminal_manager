from __future__ import annotations

import fcntl
import os
import subprocess
from pathlib import Path
from typing import IO


class SingleInstance:
    """Hold an advisory user-level lock for the lifetime of the application."""

    def __init__(self, path: Path | None = None) -> None:
        state_root = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
        self.path = path or state_root / f"terminal-manager-{os.getuid()}.lock"
        self._file: IO[str] | None = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock_file.close()
            return False
        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(str(os.getpid()))
        lock_file.flush()
        self._file = lock_file
        return True

    def release(self) -> None:
        if self._file is None:
            return
        fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        self._file.close()
        self._file = None


def activate_existing() -> None:
    """Raise the existing manager window without shaking it."""
    subprocess.run(
        ["wmctrl", "-a", "Terminal Manager"],
        timeout=3,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
