from __future__ import annotations

import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .model import WindowInfo


@dataclass(frozen=True)
class ActivityState:
    status: str
    changed_ratio: float
    seconds_since_change: float | None
    samples: int


@dataclass
class _History:
    sample: bytes
    last_change: float
    samples: int
    has_change: bool = False


class WindowActivityTracker:
    """Classify terminal windows by recent visual output changes."""

    def __init__(self, threshold: float = 0.0005, active_hold_seconds: float = 4.0) -> None:
        self.threshold = threshold
        self.active_hold_seconds = active_hold_seconds
        self._history: dict[str, _History] = {}

    def update(self, windows: list[WindowInfo]) -> dict[str, ActivityState]:
        now = time.monotonic()
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(windows)))) as pool:
            captures = list(pool.map(_capture_window, windows))
        states: dict[str, ActivityState] = {}
        live_ids = {window.window_id for window in windows}
        for window, sample in zip(windows, captures):
            if not sample:
                states[window.window_id] = ActivityState("unknown", 0.0, None, 0)
                continue
            previous = self._history.get(window.window_id)
            if previous is None:
                self._history[window.window_id] = _History(sample, now, 1)
                states[window.window_id] = ActivityState("observing", 0.0, None, 1)
                continue
            ratio = changed_ratio(previous.sample, sample)
            previous.sample = sample
            previous.samples += 1
            if ratio >= self.threshold:
                previous.last_change = now
                previous.has_change = True
            age = max(0.0, now - previous.last_change)
            status = "active" if previous.has_change and age <= self.active_hold_seconds else "static"
            states[window.window_id] = ActivityState(status, ratio, age, previous.samples)
        for stale_id in set(self._history) - live_ids:
            del self._history[stale_id]
        return states


def _capture_window(window: WindowInfo) -> bytes | None:
    try:
        result = subprocess.run(
            ["xwd", "-silent", "-id", window.window_id],
            capture_output=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 or not result.stdout:
        return None
    # One byte per pixel is enough to detect redraws and keeps comparisons cheap.
    return result.stdout[::4]


def changed_ratio(before: bytes, after: bytes) -> float:
    length = min(len(before), len(after))
    if not length:
        return 1.0 if before != after else 0.0
    changed = sum(left != right for left, right in zip(before[:length], after[:length]))
    changed += abs(len(before) - len(after))
    return changed / max(len(before), len(after))
