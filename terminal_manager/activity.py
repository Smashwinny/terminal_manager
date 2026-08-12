from __future__ import annotations

import time
from dataclasses import dataclass

from .model import WindowInfo


# Codex currently rotates these one-character title prefixes while it works.
# Unknown animations are learned below, so a future Codex spinner does not
# require an application release as long as it keeps the same title protocol.
CODEX_SPINNER_PREFIXES = frozenset("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
# Claude Code moves one Braille dot while processing. Its current animation can
# expose only two distinct frames (for example ⠂ and ⠐), so the generic
# three-frame learner cannot discover it reliably. A sampled frame may also
# appear stationary; every single-dot Braille cell is therefore active.
CLAUDE_WORKING_PREFIXES = frozenset("⠁⠂⠄⠈⠐⠠⡀⢀")
WAITING_PREFIXES = frozenset(("!", "！", "❗", "⚠"))
WAITING_TITLE_MARKERS = ("[ ! ]", "[！]", "[!]", "❗", "⚠")
WAITING_BODY_MARKERS = (
    "action required",
    "waiting for input",
    "waiting for user",
    "user input required",
    "需要用户输入",
    "等待用户输入",
)


@dataclass(frozen=True)
class ActivityState:
    status: str
    seconds_in_status: float
    samples: int
    prefix: str = ""
    learned_prefix: bool = False


@dataclass
class _History:
    prefix: str
    body: str
    status: str
    status_since: float
    samples: int = 1
    pending_static_since: float | None = None


class WindowActivityTracker:
    """Classify Codex state from its terminal-title status prefix.

    Learning is deliberately conservative: an unknown prefix is accepted as a
    spinner only after three different one-character prefixes rotate while the
    rest of the title remains identical. Scrolling terminal contents cannot
    affect this signal.
    """

    def __init__(
        self,
        static_grace_seconds: float = 6.0,
        learned_prefixes: set[str] | None = None,
        learned_waiting_prefixes: set[str] | None = None,
        learned_static_prefixes: set[str] | None = None,
    ) -> None:
        self.static_grace_seconds = max(0.0, static_grace_seconds)
        self.learned_spinner_prefixes: set[str] = set(learned_prefixes or ())
        self.learned_waiting_prefixes = set(learned_waiting_prefixes or ())
        self.learned_static_prefixes = set(learned_static_prefixes or ())
        self._history: dict[str, _History] = {}

    def update(self, windows: list[WindowInfo]) -> dict[str, ActivityState]:
        now = time.monotonic()
        states: dict[str, ActivityState] = {}
        live_ids = {window.window_id for window in windows}

        for window in windows:
            prefix, body = split_status_prefix(window.title)
            previous = self._history.get(window.window_id)
            if previous is None:
                status = self._classify(prefix, body)
                previous = _History(prefix, body, status, now)
                self._history[window.window_id] = previous
            else:
                previous.samples += 1
                status = self._classify(prefix, body)
                display_prefix = prefix
                if status == "static" and previous.status in ("active", "waiting"):
                    if previous.pending_static_since is None:
                        previous.pending_static_since = now
                    if now - previous.pending_static_since < self.static_grace_seconds:
                        status = previous.status
                        display_prefix = previous.prefix
                else:
                    previous.pending_static_since = None
                if status != previous.status:
                    previous.status = status
                    previous.status_since = now
                if display_prefix == prefix:
                    previous.prefix = prefix
                previous.body = body

            states[window.window_id] = ActivityState(
                previous.status,
                max(0.0, now - previous.status_since),
                previous.samples,
                previous.prefix,
                previous.prefix in self.learned_spinner_prefixes,
            )

        for stale_id in set(self._history) - live_ids:
            del self._history[stale_id]
        return states

    def _classify(self, prefix: str, body: str) -> str:
        if has_waiting_body_marker(body):
            return "waiting"
        if prefix in self.learned_waiting_prefixes:
            return "waiting"
        if prefix in self.learned_static_prefixes:
            return "static"
        if prefix in self.learned_spinner_prefixes:
            return "active"
        if prefix in WAITING_PREFIXES:
            return "waiting"
        if (
            prefix in CODEX_SPINNER_PREFIXES
            or prefix in CLAUDE_WORKING_PREFIXES
        ):
            return "active"
        return "static"

class SignalLearningSession:
    """Collect unknown animation frames from one explicitly selected window."""

    def __init__(self, threshold: int = 2) -> None:
        self.threshold = max(2, threshold)
        self.body = ""
        self.prefixes: set[str] = set()
        self.kind = ""

    def observe(self, title: str) -> bool:
        prefix, body = split_status_prefix(title)
        if not prefix or not body:
            return False
        if prefix in WAITING_PREFIXES:
            return False
        if prefix in CODEX_SPINNER_PREFIXES:
            kind = "codex"
        elif prefix in CLAUDE_WORKING_PREFIXES:
            kind = "claude"
        else:
            kind = "unknown"
        if (self.body and body != self.body) or (self.kind and kind != self.kind):
            self.prefixes.clear()
        self.body = body
        self.kind = kind
        self.prefixes.add(prefix)
        return len(self.prefixes) >= self.threshold


def split_status_prefix(title: str) -> tuple[str, str]:
    """Return a possible one-character status prefix and the stable title body."""
    cleaned = title.strip()
    for marker in WAITING_TITLE_MARKERS:
        if cleaned.startswith(marker):
            body = cleaned[len(marker) :].lstrip()
            return "!", body or cleaned
    first, separator, body = cleaned.partition(" ")
    if separator and len(first) == 1 and body:
        return first, body
    return "", cleaned


def has_waiting_body_marker(body: str) -> bool:
    normalized = " ".join(body.casefold().split())
    return any(marker in normalized for marker in WAITING_BODY_MARKERS)
