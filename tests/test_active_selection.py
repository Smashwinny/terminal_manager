from unittest.mock import Mock, patch

from terminal_manager.app import TerminalManagerApp, item_id_for_window
from terminal_manager.model import ShellInfo, WindowInfo


def test_find_visible_item_for_active_window() -> None:
    window = WindowInfo("0x0000002a", 0, 10, 0, 0, 800, 600, "XTerm.XTerm", "host", "work")
    items = {"window:42": (None, window)}
    assert item_id_for_window(items, "0x0000002a") == "window:42"
    assert item_id_for_window(items, "0x00000099") is None


def test_registered_item_uses_saved_window_when_window_metadata_is_missing() -> None:
    shell = ShellInfo("abc", "0x0000002a", 12, "/dev/pts/1", "work", "idle", "", "bash", "/tmp", 12, "S", 0, 0)
    assert item_id_for_window({"shell:abc": (shell, None)}, "0x0000002a") == "shell:abc"


@patch("terminal_manager.app.active_window_id", return_value="0x0000002a")
def test_double_click_in_same_active_terminal_replays_manager_row(_active_window_id: Mock) -> None:
    app = object.__new__(TerminalManagerApp)
    window = WindowInfo("0x0000002a", 0, 10, 0, 0, 800, 600, "XTerm.XTerm", "host", "work")
    app.items = {"window:42": (None, window)}
    app.tree = Mock()
    app.tree.exists.return_value = True
    app.root = Mock()
    app.pointer_monitor = Mock()
    app.pointer_monitor.drain.return_value = [10.0, 10.2]
    app._observed_active_item = "window:42"
    app._last_pointer_press = None
    app._flash_workspace_item = Mock()
    app.active_poll_job = None

    app._poll_active_window()

    app._flash_workspace_item.assert_called_once_with("window:42")
    assert app._last_pointer_press is None
