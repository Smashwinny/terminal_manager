from terminal_manager.tabs import TabGroup, TerminalTab, select_tab
from unittest.mock import Mock, patch
import subprocess

from terminal_manager.tabs import _worker, scan_tab_groups
from terminal_manager.model import WindowInfo


class Selection:
    def __init__(self) -> None:
        self.selected = 0
        self.calls = 0

    def isChildSelected(self, index: int) -> bool:
        return self.selected == index

    def selectChild(self, index: int) -> bool:
        self.calls += 1
        self.selected = index
        return True


class Selector:
    def __init__(self, selection: Selection) -> None:
        self.selection = selection

    def querySelection(self) -> Selection:
        return self.selection


def test_cached_tab_switch_and_repeat_click() -> None:
    selection = Selection()
    group = TabGroup(
        "0x0000002a",
        (TerminalTab(0, "main", True), TerminalTab(1, "hidden", False)),
        Selector(selection),
    )
    assert select_tab(group, 1)
    assert select_tab(group, 1)
    assert selection.calls == 1


def test_native_worker_crash_or_timeout_is_contained() -> None:
    with patch("terminal_manager.tabs.subprocess.run", return_value=Mock(returncode=-11, stdout="")):
        assert _worker({}) is None
    with patch("terminal_manager.tabs.subprocess.run", side_effect=subprocess.TimeoutExpired("worker", 6)):
        assert _worker({}) is None


def test_tab_worker_returns_only_serializable_identity() -> None:
    window = WindowInfo("0x2a", 0, 123, 0, 0, 800, 600, "gnome-terminal", "", "main")
    with patch("terminal_manager.tabs._worker", return_value=[{"window_id": "0x2a", "tabs": [{"index": 0, "title": "main", "selected": True}, {"index": 1, "title": "hidden", "selected": False}]}]):
        group = scan_tab_groups([window])[0]
    assert group.selector == "0x2a"
    with patch("terminal_manager.tabs._worker", return_value=True) as worker:
        assert select_tab(group, 1)
        assert worker.call_args.args[0]["select"] == "0x2a"
