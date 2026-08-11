from __future__ import annotations

from dataclasses import dataclass, field

from .model import WindowInfo


@dataclass(frozen=True)
class TerminalTab:
    index: int
    title: str
    selected: bool

    def signal_id(self, window_id: str) -> str:
        return f"{window_id}:tab:{self.index}"


@dataclass(frozen=True)
class TabGroup:
    window_id: str
    tabs: tuple[TerminalTab, ...]
    selector: object = field(repr=False, compare=False)

    @property
    def selected(self) -> TerminalTab:
        return next((tab for tab in self.tabs if tab.selected), self.tabs[0])


def scan_tab_groups(windows: list[WindowInfo]) -> list[TabGroup]:
    """Read existing GNOME Terminal tabs through AT-SPI.

    AT-SPI exposes hidden tabs without focusing or redrawing their terminal.
    Other terminal applications simply return no groups.
    """
    try:
        import pyatspi
    except ImportError:
        return []

    gnome_windows = [window for window in windows if "gnome-terminal" in window.wm_class.lower()]
    if not gnome_windows:
        return []
    desktop = pyatspi.Registry.getDesktop(0)
    app = next((item for item in desktop if item.name == "gnome-terminal-server"), None)
    if app is None:
        return []

    unmatched = list(gnome_windows)
    groups: list[TabGroup] = []
    for frame in app:
        tab_list = _find_role(frame, pyatspi.ROLE_PAGE_TAB_LIST)
        window = _match_window(frame, unmatched, pyatspi)
        if window is None:
            continue
        unmatched.remove(window)
        # Match every frame before filtering. This disambiguates windows with
        # identical active titles (a common case for shell tabs).
        if tab_list is None or tab_list.childCount < 2:
            continue
        try:
            selection = tab_list.querySelection()
            tabs = tuple(
                TerminalTab(index, child.name or f"标签 {index + 1}", selection.isChildSelected(index))
                for index, child in enumerate(tab_list)
            )
        except (LookupError, NotImplementedError, RuntimeError):
            continue
        groups.append(TabGroup(window.window_id, tabs, tab_list))
    return groups


def select_tab(group: TabGroup, index: int) -> bool:
    """Select a cached GNOME Terminal tab without rescanning the desktop."""
    try:
        if not 0 <= index < len(group.tabs):
            return False
        selection = group.selector.querySelection()
        if selection.isChildSelected(index):
            return True
        return bool(selection.selectChild(index))
    except (LookupError, NotImplementedError, RuntimeError):
        return False


def _find_role(node: object, role: int, depth: int = 0) -> object | None:
    if node.getRole() == role:
        return node
    if depth >= 3:
        return None
    for child in node:
        found = _find_role(child, role, depth + 1)
        if found is not None:
            return found
    return None


def _match_window(frame: object, windows: list[WindowInfo], pyatspi: object) -> WindowInfo | None:
    if not windows:
        return None
    try:
        bounds = frame.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
    except (LookupError, NotImplementedError, RuntimeError):
        return next((window for window in windows if window.title == frame.name), None)

    def score(window: WindowInfo) -> int:
        # GNOME/GTK reports logical desktop coordinates while wmctrl can report
        # monitor-scaled positions on mixed/HiDPI desktops. Window sizes remain
        # logical on the affected setup, so test the common position scales.
        position = min(
            abs(window.x - bounds.x * scale) + abs(window.y - bounds.y * scale)
            for scale in (1, 2, 3)
        )
        geometry = position + abs(window.width - bounds.width) + abs(window.height - bounds.height)
        title_penalty = 0 if window.title == frame.name else 200
        return geometry + title_penalty

    best = min(windows, key=score)
    return best if score(best) < 500 else None
