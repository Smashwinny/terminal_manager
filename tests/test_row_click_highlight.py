from types import SimpleNamespace
from unittest.mock import Mock

from terminal_manager.app import TerminalManagerApp


def test_single_click_highlights_only_when_switching_rows() -> None:
    app = object.__new__(TerminalManagerApp)
    app.tree = Mock()
    app.tree.identify_row.return_value = "window:0x00000001"
    app.tree.identify_region.return_value = "cell"
    app.tree.identify_column.return_value = "#2"
    app.tree.exists.return_value = True
    app.tree.selection.side_effect = [(), ("window:0x00000001",)]
    app._flash_workspace_item = Mock()
    event = SimpleNamespace(x=100, y=50)

    app._handle_tree_press(event)
    app._handle_tree_press(event)

    assert app._flash_workspace_item.call_count == 1
    app.tree.selection_set.assert_called_with("window:0x00000001")
    app.tree.focus.assert_called_with("window:0x00000001")


def test_double_click_explicitly_replays_highlight() -> None:
    app = object.__new__(TerminalManagerApp)
    app.tree = Mock()
    app.tree.identify_row.return_value = "window:0x00000001"
    app.tree.identify_column.return_value = "#2"
    app._cancel_group_click = Mock()
    app._suppress_group_release = False
    app._replay_clicked_row = Mock()
    app.focus_selected = Mock()
    event = SimpleNamespace(x=100, y=50)

    app._handle_tree_double_click(event)

    app._replay_clicked_row.assert_called_once_with("window:0x00000001", event)
    app._cancel_group_click.assert_called_once_with()
    assert app._suppress_group_release is True
    app.focus_selected.assert_called_once_with(pin=True, replay_highlight=False)


def test_regular_row_release_waits_for_double_click_window() -> None:
    app = object.__new__(TerminalManagerApp)
    app.tree = Mock()
    app.tree.identify_row.return_value = "window:0x00000001"
    app.tree.identify_column.return_value = "#1"
    app.tree.identify_region.return_value = "cell"
    app.tab_items = {}
    app._suppress_group_release = False
    app._schedule_group_click = Mock()
    app.focus_selected = Mock()
    event = SimpleNamespace(x=100, y=50)

    app._handle_tree_click(event)

    app._schedule_group_click.assert_called_once()
    app.focus_selected.assert_not_called()
