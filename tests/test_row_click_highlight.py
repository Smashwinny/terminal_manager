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
    app._suppress_group_release = False
    app.tab_items = {}
    app._flash_workspace_item = Mock()
    event = SimpleNamespace(x=100, y=50)

    app._handle_tree_click(event)
    app._handle_tree_click(event)

    assert app._flash_workspace_item.call_count == 2
    app.tree.selection_set.assert_called_with("window:0x00000001")
    app.tree.focus.assert_called_with("window:0x00000001")
