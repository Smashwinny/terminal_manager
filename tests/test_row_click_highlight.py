from types import SimpleNamespace
from unittest.mock import Mock

from terminal_manager.app import TerminalManagerApp


def test_repeated_click_on_selected_row_replays_highlight_each_time() -> None:
    app = object.__new__(TerminalManagerApp)
    app.tree = Mock()
    app.tree.identify_row.return_value = "window:0x00000001"
    app.tree.identify_region.return_value = "cell"
    app.tree.identify_column.return_value = "#2"
    app.tree.exists.return_value = True
    app._flash_workspace_item = Mock()
    event = SimpleNamespace(x=100, y=50)

    app._handle_tree_press(event)
    app._handle_tree_press(event)

    assert app._flash_workspace_item.call_count == 2
    app.tree.selection_set.assert_called_with("window:0x00000001")
    app.tree.focus.assert_called_with("window:0x00000001")


def test_double_click_explicitly_replays_highlight() -> None:
    app = object.__new__(TerminalManagerApp)
    app.tree = Mock()
    app.tree.identify_row.return_value = "window:0x00000001"
    app.tree.identify_column.return_value = "#2"
    app._replay_clicked_row = Mock()
    app.focus_selected = Mock()
    event = SimpleNamespace(x=100, y=50)

    app._handle_tree_double_click(event)

    app._replay_clicked_row.assert_called_once_with("window:0x00000001", event)
    app.focus_selected.assert_called_once_with(pin=True)
