from __future__ import annotations

import queue
import shutil
import subprocess
import threading
import time


class PointerPressMonitor:
    """Observe global XI2 left-button presses without grabbing input."""

    def __init__(self) -> None:
        self._events: queue.SimpleQueue[float] = queue.SimpleQueue()
        self._process: subprocess.Popen[str] | None = None

    def start(self) -> bool:
        if not shutil.which("xinput") or not shutil.which("stdbuf"):
            return False
        try:
            self._process = subprocess.Popen(
                ["stdbuf", "-oL", "xinput", "test-xi2", "--root"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except OSError:
            return False
        threading.Thread(target=self._read_events, daemon=True).start()
        return True

    def _read_events(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        raw_press = False
        for line in process.stdout:
            stripped = line.strip()
            if stripped.startswith("EVENT type 15 (RawButtonPress)"):
                raw_press = True
                continue
            if raw_press and stripped.startswith("detail:"):
                if stripped.removeprefix("detail:").strip() == "1":
                    self._events.put(time.monotonic())
                raw_press = False
            elif stripped.startswith("EVENT type"):
                raw_press = False

    def drain(self) -> list[float]:
        events: list[float] = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                return events

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is not None and process.poll() is None:
            process.terminate()

