from terminal_manager.tabs import TabGroup, TerminalTab, select_tab


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
