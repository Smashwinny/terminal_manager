from unittest.mock import Mock, patch

from terminal_manager.x11 import shake_window


@patch("terminal_manager.x11.time.sleep")
@patch("terminal_manager.x11.subprocess.run")
def test_shake_deltas_restore_original_position(run: Mock, sleep: Mock) -> None:
    run.return_value.returncode = 0
    shake_window("0x123")

    moves = [call.args[0] for call in run.call_args_list]
    assert sum(int(command[-2]) for command in moves) == 0
    assert all(command[:3] == ["xdotool", "windowmove", "--relative"] for command in moves)
    assert sleep.call_count == 7


@patch("terminal_manager.x11.time.sleep")
@patch("terminal_manager.x11.subprocess.run")
def test_shake_compensates_after_partial_failure(run: Mock, _sleep: Mock) -> None:
    run.side_effect = [Mock(returncode=0), Mock(returncode=0), Mock(returncode=1), Mock(returncode=0)]
    shake_window("0x123")

    moves = [call.args[0] for call in run.call_args_list]
    assert [int(command[-2]) for command in moves] == [10, -20, 18, 10]
    assert sum(int(command[-2]) for command in moves) == 18
