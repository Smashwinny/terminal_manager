from unittest.mock import call, patch

from terminal_manager.app import TerminalManagerApp


def app() -> TerminalManagerApp:
    instance = object.__new__(TerminalManagerApp)
    instance.pinned_window_id = None
    instance._pinned_was_above = False
    return instance


def test_double_click_pin_moves_between_managed_windows() -> None:
    instance = app()
    with (
        patch("terminal_manager.app.window_is_above", return_value=False),
        patch("terminal_manager.app.set_window_above", return_value=True) as set_above,
    ):
        instance._pin_window("0x00000001")
        instance._pin_window("0x00000002")

    assert set_above.call_args_list == [
        call("0x00000001", True),
        call("0x00000001", False),
        call("0x00000002", True),
    ]
    assert instance.pinned_window_id == "0x00000002"


def test_preexisting_always_on_top_state_is_never_removed() -> None:
    instance = app()
    with (
        patch("terminal_manager.app.window_is_above", return_value=True),
        patch("terminal_manager.app.set_window_above", return_value=True) as set_above,
    ):
        instance._pin_window("0x00000001")
        instance._release_managed_pin()

    set_above.assert_not_called()
    assert instance.pinned_window_id is None
