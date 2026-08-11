from unittest.mock import patch

from terminal_manager.activity import WindowActivityTracker, changed_ratio
from terminal_manager.model import WindowInfo


WINDOW = WindowInfo("0x0000002a", 0, 1, 0, 0, 800, 600, "XTerm.XTerm", "host", "test")


def test_changed_ratio() -> None:
    assert changed_ratio(b"aaaa", b"aaaa") == 0
    assert changed_ratio(b"aaaa", b"abaa") == 0.25


@patch("terminal_manager.activity._capture_window")
@patch("terminal_manager.activity.time.monotonic", side_effect=[0.0, 2.0, 7.0])
def test_activity_threshold_and_hold(_clock, capture) -> None:
    tracker = WindowActivityTracker(threshold=0.05, active_hold_seconds=4.0)
    capture.side_effect = [b"a" * 100, b"a" * 90 + b"b" * 10, b"a" * 90 + b"b" * 10]

    assert tracker.update([WINDOW])[WINDOW.window_id].status == "observing"
    assert tracker.update([WINDOW])[WINDOW.window_id].status == "active"
    assert tracker.update([WINDOW])[WINDOW.window_id].status == "static"


@patch("terminal_manager.activity._capture_window", return_value=None)
def test_capture_failure_is_unknown(_capture) -> None:
    state = WindowActivityTracker().update([WINDOW])[WINDOW.window_id]
    assert state.status == "unknown"

