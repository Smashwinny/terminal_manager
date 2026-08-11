from unittest.mock import patch

from terminal_manager.activity import WindowActivityTracker, split_status_prefix
from terminal_manager.model import WindowInfo


def window(title: str) -> WindowInfo:
    return WindowInfo("0x0000002a", 0, 1, 0, 0, 800, 600, "XTerm.XTerm", "host", title)


def test_split_status_prefix() -> None:
    assert split_status_prefix("⠹ hulk") == ("⠹", "hulk")
    assert split_status_prefix("[ ! ] Action Required | hulk") == ("!", "Action Required | hulk")
    assert split_status_prefix("mobile ledger") == ("", "mobile ledger")


@patch("terminal_manager.activity.time.monotonic", side_effect=[0.0, 2.0, 7.0])
def test_known_codex_states(_clock) -> None:
    tracker = WindowActivityTracker(static_grace_seconds=0)
    assert tracker.update([window("⠹ hulk")])["0x0000002a"].status == "active"
    waiting = tracker.update([window("! hulk")])["0x0000002a"]
    assert waiting.status == "waiting"
    assert waiting.seconds_in_status == 0
    static = tracker.update([window("hulk")])["0x0000002a"]
    assert static.status == "static"


def test_unknown_rotating_prefix_is_learned() -> None:
    tracker = WindowActivityTracker(learning_threshold=3)
    assert tracker.update([window("◐ project")])["0x0000002a"].status == "static"
    assert tracker.update([window("◓ project")])["0x0000002a"].status == "static"
    learned = tracker.update([window("◑ project")])["0x0000002a"]
    assert learned.status == "active"
    assert learned.learned_prefix
    assert {"◐", "◓", "◑"} <= tracker.learned_spinner_prefixes


def test_title_rename_is_not_learned_as_animation() -> None:
    tracker = WindowActivityTracker(learning_threshold=3)
    tracker.update([window("A project")])
    tracker.update([window("B another-project")])
    state = tracker.update([window("C third-project")])["0x0000002a"]
    assert state.status == "static"
    assert not tracker.learned_spinner_prefixes


@patch("terminal_manager.activity.time.monotonic", side_effect=[0.0, 1.0, 2.0])
def test_blank_title_transition_does_not_flash_static(_clock) -> None:
    tracker = WindowActivityTracker(static_grace_seconds=3.0)
    assert tracker.update([window("⠹ hulk")])["0x0000002a"].status == "active"
    transition = tracker.update([window("hulk")])["0x0000002a"]
    assert transition.status == "active"
    assert transition.prefix == "⠹"
    assert tracker.update([window("[ ! ] Action Required | hulk")])["0x0000002a"].status == "waiting"


@patch("terminal_manager.activity.time.monotonic", side_effect=[0.0, 1.0, 5.0])
def test_real_static_state_is_applied_after_grace(_clock) -> None:
    tracker = WindowActivityTracker(static_grace_seconds=3.0)
    tracker.update([window("⠹ hulk")])
    assert tracker.update([window("hulk")])["0x0000002a"].status == "active"
    assert tracker.update([window("hulk")])["0x0000002a"].status == "static"
