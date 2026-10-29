from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import subprocess
import sys

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


def scan_tab_groups(windows: list[WindowInfo]) -> list[TabGroup] | None:
    """Keep AT-SPI/GI native state outside the Tk process."""
    if not any("gnome-terminal" in w.wm_class.lower() for w in windows):
        return []
    response = _worker({"windows": [asdict(w) for w in windows]})
    if not isinstance(response, list):
        return None
    try:
        return [TabGroup(group["window_id"], tuple(TerminalTab(**tab) for tab in group["tabs"]), group["window_id"]) for group in response]
    except (KeyError, TypeError):
        return None


def _worker(payload):
    try:
        result = subprocess.run([sys.executable, "-m", "terminal_manager.tabs"], input=json.dumps(payload), capture_output=True, text=True, timeout=6)
        return json.loads(result.stdout) if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def _scan_tab_groups_native(windows: list[WindowInfo]) -> list[TabGroup]:
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
    # Menus and VTE contents cannot contain a notebook. Touching these remote
    # accessibility objects makes the terminal's main thread do needless work.
    skip_roles = {pyatspi.ROLE_MENU_BAR, pyatspi.ROLE_MENU, pyatspi.ROLE_TERMINAL}
    for frame in app:
        window = _match_window(frame, unmatched, pyatspi)
        if window is None:
            continue
        unmatched.remove(window)
        tab_list = _find_role(frame, pyatspi.ROLE_PAGE_TAB_LIST, skip_roles=skip_roles,
                              preferred_roles={pyatspi.ROLE_FILLER})
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
    """Select a tab, resolving native accessibility objects in the worker."""
    if isinstance(group.selector, str):
        if not 0 <= index < len(group.tabs):
            return False
        return _worker({"select": group.window_id, "index": index, "count": len(group.tabs)}) is True
    try:
        if not 0 <= index < len(group.tabs):
            return False
        selection = group.selector.querySelection()
        if selection.isChildSelected(index):
            return True
        return bool(selection.selectChild(index))
    except (LookupError, NotImplementedError, RuntimeError):
        return False


def _find_role(node: object, role: int, depth: int = 0, *, skip_roles: set | None = None,
               preferred_roles: set | None = None) -> object | None:
    # Breadth-first search reaches the shallow notebook before traversing
    # header-bar buttons, menus, or page contents. Iteration itself is IPC.
    level = [(node, node.getRole())]
    for current_depth in range(depth, 4):
        expandable = []
        # Check the whole level before expanding anything: a notebook later
        # in this level should avoid IPC for all earlier header-bar children.
        for current, current_role in level:
            if current_role == role:
                return current
            if current_role not in (skip_roles or ()):
                expandable.append((current, current_role))
        if current_depth == 3:
            break
        # GNOME puts its notebook in a filler sibling of the header panels.
        # Prefer it, but retain other containers for different GTK layouts.
        expandable.sort(key=lambda item: item[1] not in (preferred_roles or ()))
        level = []
        for parent, _ in expandable:
            for child in parent:
                child_role = child.getRole()
                if child_role == role:
                    return child
                level.append((child, child_role))
    return None


def _match_window(frame: object, windows: list[WindowInfo], pyatspi: object) -> WindowInfo | None:
    if not windows:
        return None
    # Accessible.name is a remote property, not a cheap Python attribute.
    # Read once per frame, not once for every candidate window (O(n²) IPC).
    title = frame.name
    try:
        bounds = frame.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
    except (LookupError, NotImplementedError, RuntimeError):
        return next((window for window in windows if window.title == title), None)

    def score(window: WindowInfo) -> int:
        # GNOME/GTK reports logical desktop coordinates while wmctrl can report
        # monitor-scaled positions on mixed/HiDPI desktops. Window sizes remain
        # logical on the affected setup, so test the common position scales.
        position = min(
            abs(window.x - bounds.x * scale) + abs(window.y - bounds.y * scale)
            for scale in (1, 2, 3)
        )
        geometry = position + abs(window.width - bounds.width) + abs(window.height - bounds.height)
        title_penalty = 0 if window.title == title else 200
        return geometry + title_penalty

    best = min(windows, key=score)
    return best if score(best) < 500 else None


def main() -> None:
    from .x11 import list_windows
    payload = json.load(sys.stdin)
    if "select" in payload:
        # Rescan in the worker: a stale native accessibility object must never
        # be kept in Tk or used after a terminal server has restarted.
        groups = _scan_tab_groups_native(list_windows())
        group = next((g for g in groups if g.window_id == payload["select"]), None)
        # Titles change continuously with Agent output; they are not identities.
        valid = group is not None and len(group.tabs) == payload["count"]
        result = bool(valid and select_tab(group, payload["index"]))
    else:
        groups = _scan_tab_groups_native([WindowInfo(**w) for w in payload["windows"]])
        result = [{"window_id": g.window_id, "tabs": [asdict(t) for t in g.tabs]} for g in groups]
    print(json.dumps(result))


if __name__ == "__main__":
    main()
