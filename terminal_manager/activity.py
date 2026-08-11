from __future__ import annotations

import time
from dataclasses import dataclass, field

from .model import WindowInfo


# Codex currently rotates these one-character title prefixes while it works.
# Unknown animations are learned below, so a future Codex spinner does not
# require an application release as long as it keeps the same title protocol.
CODEX_SPINNER_PREFIXES = frozenset("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
WAITING_PREFIXES = frozenset(("!", "！", "❗", "⚠"))
WAITING_TITLE_MARKERS = ("[ ! ]", "[！]", "[!]", "❗", "⚠")


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
    candidate_body: str = ""
    candidate_prefixes: set[str] = field(default_factory=set)


class WindowActivityTracker:
    """Classify Codex state from its terminal-title status prefix.

    Learning is deliberately conservative: an unknown prefix is accepted as a
    spinner only after three different one-character prefixes rotate while the
    rest of the title remains identical. Scrolling terminal contents cannot
    affect this signal.
    """

    def __init__(self, learning_threshold: int = 3) -> None:
        self.learning_threshold = max(2, learning_threshold)
        self.learned_spinner_prefixes: set[str] = set()
        self._history: dict[str, _History] = {}

    def update(self, windows: list[WindowInfo]) -> dict[str, ActivityState]:
        now = time.monotonic()
        states: dict[str, ActivityState] = {}
        live_ids = {window.window_id for window in windows}

        for window in windows:
            prefix, body = split_status_prefix(window.title)
            previous = self._history.get(window.window_id)
            if previous is None:
                status = self._classify(prefix)
                previous = _History(prefix, body, status, now)
                self._history[window.window_id] = previous
            else:
                previous.samples += 1
                self._learn_animation(previous, prefix, body)
                status = self._classify(prefix)
                if status != previous.status:
                    previous.status = status
                    previous.status_since = now
                previous.prefix = prefix
                previous.body = body

            states[window.window_id] = ActivityState(
                previous.status,
                max(0.0, now - previous.status_since),
                previous.samples,
                prefix,
                prefix in self.learned_spinner_prefixes,
            )

        for stale_id in set(self._history) - live_ids:
            del self._history[stale_id]
        return states

    def _classify(self, prefix: str) -> str:
        if prefix in WAITING_PREFIXES:
            return "waiting"
        if prefix in CODEX_SPINNER_PREFIXES or prefix in self.learned_spinner_prefixes:
            return "active"
        return "static"

    def _learn_animation(self, history: _History, prefix: str, body: str) -> None:
        if not prefix or not body or body != history.body or prefix == history.prefix:
            history.candidate_body = body
            history.candidate_prefixes.clear()
            return
        if history.candidate_body != body:
            history.candidate_body = body
            history.candidate_prefixes = {history.prefix}
        history.candidate_prefixes.add(prefix)
        if len(history.candidate_prefixes) >= self.learning_threshold:
            self.learned_spinner_prefixes.update(history.candidate_prefixes)


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
