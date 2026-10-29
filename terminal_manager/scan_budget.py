"""Rate-limit expensive background discovery independently of UI refreshes."""
from dataclasses import dataclass
import time


@dataclass
class ScanBudget:
    interval: float = 10.0
    minimum_gap: float = 2.0
    last_started: float = float("-inf")
    next_due: float = 0.0
    signature: object = None

    def start(self, signature: object = None, *, force: bool = False) -> bool:
        now = time.monotonic()
        if now - self.last_started < self.minimum_gap:
            return False
        if not force and signature == self.signature and now < self.next_due:
            return False
        self.signature = signature
        self.last_started = now
        self.next_due = now + self.interval
        return True

    def finish(self) -> None:
        # Slow or timed-out scans must not immediately restart on the next UI
        # tick. Keep at least 90% idle time, capped at a minute of cooldown.
        now = time.monotonic()
        self.next_due = max(self.next_due, now + min(60.0, (now - self.last_started) * 9))
