from unittest.mock import patch

from terminal_manager.activity import SignalLearningSession, WindowActivityTracker, has_waiting_body_marker, split_status_prefix
from terminal_manager.model import WindowInfo


def window(title: str) -> WindowInfo:
    return WindowInfo("0x0000002a", 0, 1, 0, 0, 800, 600, "XTerm.XTerm", "host", title)


def test_split_status_prefix() -> None:
    assert split_status_prefix("⠹ hulk") == ("⠹", "hulk")
    assert split_status_prefix("[ ! ] Action Required | hulk") == ("!", "Action Required | hulk")
    assert split_status_prefix("mobile ledger") == ("", "mobile ledger")


def test_waiting_body_marker_survives_missing_icon() -> None:
    tracker = WindowActivityTracker(static_grace_seconds=0)
    state = tracker.update([window("Action Required | mobile ledger")])["0x0000002a"]
    assert state.status == "waiting"
    assert has_waiting_body_marker("等待用户输入 | 手机记账")


def test_ordinary_title_is_not_learned_as_waiting() -> None:
    tracker = WindowActivityTracker(static_grace_seconds=0)
    assert tracker.update([window("A project")])["0x0000002a"].status == "static"


@patch("terminal_manager.activity.time.monotonic", side_effect=[0.0, 2.0, 7.0])
def test_known_codex_states(_clock) -> None:
    tracker = WindowActivityTracker(static_grace_seconds=0)
    assert tracker.update([window("⠹ hulk")])["0x0000002a"].status == "active"
    waiting = tracker.update([window("! hulk")])["0x0000002a"]
    assert waiting.status == "waiting"
    assert waiting.seconds_in_status == 0
    static = tracker.update([window("hulk")])["0x0000002a"]
    assert static.status == "static"


def test_claude_working_prefix_uses_same_active_state_as_codex() -> None:
    tracker = WindowActivityTracker(static_grace_seconds=0)
    for prefix in "⠁⠂⠄⠈⠐⠠⡀⢀":
        state = tracker.update([window(f"{prefix} Claude project")])["0x0000002a"]
        assert state.status == "active"


def test_claude_without_reliable_waiting_signal_falls_back_to_static() -> None:
    tracker = WindowActivityTracker(static_grace_seconds=0)
    assert tracker.update([window("✳ Claude project")])["0x0000002a"].status == "static"
    waiting = tracker.update([window("Action Required | Claude project")])["0x0000002a"]
    assert waiting.status == "waiting"


def test_explicit_waiting_text_overrides_learned_blank_static_prefix() -> None:
    tracker = WindowActivityTracker(learned_static_prefixes={""}, static_grace_seconds=0)
    state = tracker.update([window("Action Required | project")])["0x0000002a"]
    assert state.status == "waiting"


def test_unknown_rotating_prefix_is_learned() -> None:
    session = SignalLearningSession(threshold=3)
    assert not session.observe("◐ project")
    assert not session.observe("◓ project")
    assert session.observe("◑ project")
    tracker = WindowActivityTracker(learned_prefixes=session.prefixes, static_grace_seconds=0)
    learned = tracker.update([window("◐ project")])["0x0000002a"]
    assert learned.status == "active" and learned.learned_prefix


def test_manual_learning_collects_both_claude_frames() -> None:
    session = SignalLearningSession()
    assert not session.observe("⠂ Claude project")
    assert session.observe("⠐ Claude project")
    assert session.prefixes == {"⠂", "⠐"}


def test_static_star_is_not_mixed_with_claude_animation() -> None:
    session = SignalLearningSession()
    assert not session.observe("✳ Claude project")
    assert not session.observe("⠂ Claude project")
    assert session.prefixes == {"⠂"}
    assert session.observe("⠐ Claude project")


def test_title_rename_is_not_learned_as_animation() -> None:
    session = SignalLearningSession(threshold=3)
    session.observe("A project")
    session.observe("B another-project")
    assert not session.observe("C third-project")
    assert session.prefixes == {"C"}


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
