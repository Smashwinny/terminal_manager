import subprocess
from unittest.mock import patch

import pytest

from terminal_manager.x11 import X11Error, list_windows, parse_wmctrl_line, set_window_above, window_is_above


def test_parse_wmctrl_line_with_title_spaces() -> None:
    line = "0x03a00007  0  2214  10 20 1200 800 gnome-terminal-server.Gnome-terminal host My ROS Shell"
    window = parse_wmctrl_line(line)
    assert window is not None
    assert window.window_id == "0x03a00007"
    assert window.pid == 2214
    assert window.title == "My ROS Shell"
    assert window.width == 1200


def test_parse_wmctrl_rejects_short_line() -> None:
    assert parse_wmctrl_line("0x01 0") is None


def test_list_windows_converts_timeout_to_recoverable_x11_error() -> None:
    with (
        patch("terminal_manager.x11.require_x11"),
        patch(
            "terminal_manager.x11.subprocess.run",
            side_effect=subprocess.TimeoutExpired(["wmctrl", "-lpGx"], 3),
        ),
        pytest.raises(X11Error, match="超时"),
    ):
        list_windows()


def test_window_above_uses_exact_ewmh_operations() -> None:
    with patch("terminal_manager.x11.require_x11"), patch("terminal_manager.x11.subprocess.run") as run:
        run.return_value.returncode = 0
        assert set_window_above("0x1", True)
        assert run.call_args.args[0] == ["wmctrl", "-i", "-r", "0x00000001", "-b", "add,above"]
        assert set_window_above("0x1", False)
        assert run.call_args.args[0] == ["wmctrl", "-i", "-r", "0x00000001", "-b", "remove,above"]


def test_existing_above_state_is_detected() -> None:
    with patch("terminal_manager.x11.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = "_NET_WM_STATE(ATOM) = _NET_WM_STATE_ABOVE"
        assert window_is_above("0x1")


def test_focus_timeout_is_a_recoverable_x11_error() -> None:
    with (
        patch("terminal_manager.x11.require_x11"),
        patch("terminal_manager.x11.subprocess.run", side_effect=subprocess.TimeoutExpired(["wmctrl"], 3)),
        pytest.raises(X11Error, match="响应超时"),
    ):
        from terminal_manager.x11 import focus_window

        focus_window("0x1")
