from __future__ import annotations

import time
import tkinter as tk
import threading
import uuid
from pathlib import Path
from tkinter import messagebox, ttk

from . import __version__
from .activity import ActivityState, WindowActivityTracker
from .dialogs import RegistrationDialog
from .highlight import WindowHighlighter, can_highlight_tty
from .model import STATUS_LABELS, ShellInfo, WindowInfo
from .store import load_shells, load_tty_bindings, remove_shell, save_shell, save_tty_binding
from .tabs import TabGroup, TerminalTab, scan_tab_groups, select_tab
from .thermal import HOT_ACCENT, HOT_ROW, ThermalTracker, blend_color, mean_temperature, visual_temperature
from .tty_probe import probe_visible_tty, terminal_tty_cwds
from .x11 import X11Error, active_window_id, find_window, focus_window, list_windows


STATUS_COLORS = {
    "idle": "#94a3b8",
    "running": "#46d483",
    "stopped": "#fbbf55",
    "ended": "#fb7185",
    "unknown": "#c4a7ff",
    "observing": "#c4a7ff",
    "active": "#46d483",
    "waiting": "#fbbf55",
    "static": "#94a3b8",
    "unbound": "#f0a95b",
    "window": "#67b7ff",
}

STATUS_DOTS = {status: "●" for status in STATUS_COLORS}

PALETTE = {
    "bg": "#080d18",
    "surface": "#101827",
    "surface_2": "#151f31",
    "surface_3": "#1b273b",
    "border": "#26354d",
    "text": "#f2f6ff",
    "muted": "#8fa1ba",
    "subtle": "#64748b",
    "accent": "#7c6cff",
    "accent_hover": "#9185ff",
    "cyan": "#47c8ff",
}


class TerminalManagerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.window_icon: tk.PhotoImage | None = None
        icon_path = Path(__file__).parent / "assets" / "terminal-manager.png"
        try:
            self.window_icon = tk.PhotoImage(file=icon_path)
            self.root.iconphoto(True, self.window_icon)
        except tk.TclError:
            pass
        self.root.title(f"Terminal Manager {__version__}")
        self.root.geometry("1180x720")
        self.root.minsize(860, 520)
        self.root.configure(background=PALETTE["bg"])
        self.items: dict[str, tuple[ShellInfo | None, WindowInfo | None]] = {}
        self.windows: list[WindowInfo] = []
        self.activities: dict[str, ActivityState] = {}
        self.activity_tracker = WindowActivityTracker()
        self.tab_activity_tracker = WindowActivityTracker()
        self.thermal_tracker = ThermalTracker()
        self.thermal_levels: dict[str, float] = {}
        self.tab_groups: dict[str, TabGroup] = {}
        self.tty_bindings = load_tty_bindings()
        self.tab_items: dict[str, tuple[TabGroup, int]] = {}
        self._tab_scan_result: list[TabGroup] | None = None
        self._tab_scan_thread: threading.Thread | None = None
        self._tab_group_misses: dict[str, int] = {}
        self._last_layout_rows: int | None = None
        self._group_click_job: str | None = None
        self.metric_highlight: str | None = None
        self.focused_item_id: str | None = None
        self._observed_active_item: str | None = None
        self._focus_clear_job: str | None = None
        self._focus_saved_tags: tuple[str, ...] | None = None
        self.refresh_job: str | None = None
        self.search_var = tk.StringVar()
        self.thermal_enabled = tk.BooleanVar(value=True)
        self.search_var.trace_add("write", lambda *_args: self.refresh())
        self._build_ui()
        self.window_highlighter = WindowHighlighter(root)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.refresh()

    def _close(self) -> None:
        self.window_highlighter.hide()
        self.root.destroy()

    def _build_ui(self) -> None:
        self._configure_styles()
        container = ttk.Frame(self.root, style="App.TFrame", padding=(24, 20, 24, 22))
        container.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(container, style="App.TFrame")
        header.pack(fill=tk.X, pady=(0, 18))
        brand = ttk.Frame(header, style="App.TFrame")
        brand.pack(side=tk.LEFT)
        self.logo = tk.Label(
            brand,
            text=">_",
            font=("Ubuntu Mono", 17, "bold"),
            foreground="#ffffff",
            background=PALETTE["accent"],
            padx=10,
            pady=7,
        )
        self.logo.pack(side=tk.LEFT, padx=(0, 13))
        titles = ttk.Frame(brand, style="App.TFrame")
        titles.pack(side=tk.LEFT)
        ttk.Label(titles, text="Terminal Manager", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(titles, text="你的 Shell，一眼看清 · 一键抵达", style="Subtitle.TLabel").pack(anchor=tk.W, pady=(2, 0))

        header_actions = ttk.Frame(header, style="App.TFrame")
        header_actions.pack(side=tk.RIGHT)
        self.thermal_toggle = tk.Frame(header_actions, background=PALETTE["bg"], cursor="hand2")
        self.thermal_toggle.pack(side=tk.LEFT, padx=(0, 12))
        self.thermal_indicator = tk.Canvas(
            self.thermal_toggle,
            width=16,
            height=16,
            background=PALETTE["bg"],
            highlightthickness=0,
            borderwidth=0,
            cursor="hand2",
        )
        self.thermal_indicator.pack(side=tk.LEFT)
        self.thermal_label = tk.Label(
            self.thermal_toggle,
            text="渲染",
            foreground=PALETTE["muted"],
            background=PALETTE["bg"],
            font=("Noto Sans CJK SC", 9),
            cursor="hand2",
        )
        self.thermal_label.pack(side=tk.LEFT, padx=(6, 0))
        for widget in (self.thermal_toggle, self.thermal_indicator, self.thermal_label):
            widget.bind("<Button-1>", lambda _event: self._toggle_thermal_rendering())
        self._draw_thermal_toggle()
        ttk.Button(header_actions, text="登记窗口", style="Ghost.TButton", command=self.register_selected).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(header_actions, text="↻  刷新", style="Accent.TButton", command=self.refresh).pack(side=tk.LEFT)

        dashboard = ttk.Frame(container, style="App.TFrame")
        dashboard.pack(fill=tk.X, pady=(0, 16))
        self.metric_values: dict[str, tk.Label] = {}
        self.metric_cards: dict[str, tk.Frame] = {}
        metrics = (
            ("total", "全部终端", PALETTE["cyan"]),
            ("waiting", "等待用户", STATUS_COLORS["waiting"]),
            ("running", "正在输出", STATUS_COLORS["active"]),
            ("idle", "静态窗口", STATUS_COLORS["static"]),
            ("unregistered", "待注册", STATUS_COLORS["window"]),
        )
        for index, (key, label, color) in enumerate(metrics):
            card = tk.Frame(
                dashboard,
                background=PALETTE["surface"],
                highlightbackground=PALETTE["border"],
                highlightthickness=1,
                padx=16,
                pady=11,
            )
            card.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0 if index == 0 else 6, 0 if index == len(metrics) - 1 else 6))
            top = tk.Frame(card, background=PALETTE["surface"])
            top.pack(fill=tk.X)
            tk.Label(top, text="●", foreground=color, background=PALETTE["surface"], font=("DejaVu Sans", 8)).pack(side=tk.LEFT)
            tk.Label(top, text=label, foreground=PALETTE["muted"], background=PALETTE["surface"], font=("Noto Sans CJK SC", 9)).pack(side=tk.LEFT, padx=(7, 0))
            value = tk.Label(card, text="0", foreground=PALETTE["text"], background=PALETTE["surface"], font=("Ubuntu", 20, "bold"))
            value.pack(anchor=tk.W, pady=(4, 0))
            self.metric_values[key] = value
            self.metric_cards[key] = card
            self._bind_metric_card(card, key)

        surface = tk.Frame(
            container,
            background=PALETTE["surface"],
            highlightbackground=PALETTE["border"],
            highlightthickness=1,
        )
        surface.pack(fill=tk.BOTH, expand=True)

        toolbar = tk.Frame(surface, background=PALETTE["surface"], padx=16, pady=13)
        toolbar.pack(fill=tk.X)
        tk.Label(toolbar, text="Shell 工作区", foreground=PALETTE["text"], background=PALETTE["surface"], font=("Noto Sans CJK SC", 11, "bold")).pack(side=tk.LEFT)
        tk.Label(toolbar, text="点击 ▸ 展开标签 · 双击条目进入窗口", foreground=PALETTE["muted"], background=PALETTE["surface"], font=("Noto Sans CJK SC", 9)).pack(side=tk.LEFT, padx=12)
        search_box = tk.Frame(toolbar, background=PALETTE["surface_2"], padx=10, pady=5)
        search_box.pack(side=tk.RIGHT)
        tk.Label(search_box, text="⌕", foreground=PALETTE["muted"], background=PALETTE["surface_2"], font=("DejaVu Sans", 12)).pack(side=tk.LEFT)
        search = tk.Entry(
            search_box,
            textvariable=self.search_var,
            width=24,
            background=PALETTE["surface_2"],
            foreground=PALETTE["text"],
            insertbackground=PALETTE["text"],
            selectbackground=PALETTE["accent"],
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
            font=("Noto Sans CJK SC", 9),
        )
        search.pack(side=tk.LEFT, padx=(6, 0))

        columns = ("name", "window", "cwd", "status", "last_change", "activity")
        table = ttk.Frame(surface, style="Surface.TFrame")
        table.pack(fill=tk.BOTH, expand=True, padx=1)
        self.tree = ttk.Treeview(
            table,
            columns=columns,
            show="headings",
            selectmode="browse",
            style="Shell.Treeview",
            height=5,
        )
        labels = {
            "name": "名称",
            "window": "窗口",
            "cwd": "目录",
            "status": "状态",
            "last_change": "时长",
            "activity": "标题信号",
        }
        widths = {"name": 205, "window": 225, "cwd": 265, "status": 110, "last_change": 125, "activity": 145}
        for key in columns:
            self.tree.heading(key, text=labels[key])
            self.tree.column(key, width=widths[key], minwidth=70, stretch=key == "window")
        self.scrollbar = ttk.Scrollbar(table, orient=tk.VERTICAL, command=self.tree.yview, style="Dark.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=self.scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        for status, color in STATUS_COLORS.items():
            self.tree.tag_configure(status, foreground=color)
        self.tree.tag_configure("even", background=PALETTE["surface"])
        self.tree.tag_configure("odd", background=PALETTE["surface_2"])
        self.tree.tag_configure("child", background="#0c1524")
        self.tree.tag_configure("metric_match", background="#2c265c", foreground="#ffffff")
        self.tree.tag_configure("focused_shell", background="#6557e8", foreground="#ffffff")
        self.tree.bind("<Double-1>", self._handle_tree_double_click)
        self.tree.bind("<ButtonRelease-1>", self._handle_tree_click)
        self.tree.bind("<<TreeviewSelect>>", self._handle_tree_selection)
        self.tree.bind("<Return>", lambda _event: self.focus_selected())

        footer = tk.Frame(surface, background=PALETTE["surface"], padx=16, pady=13)
        footer.pack(fill=tk.X)
        actions = ttk.Frame(footer, style="Surface.TFrame")
        actions.pack(side=tk.LEFT)
        ttk.Button(actions, text="进入并高亮", style="Accent.TButton", command=self.focus_selected).pack(side=tk.LEFT)
        ttk.Button(actions, text="编辑记录", style="Ghost.TButton", command=self.rename_selected).pack(side=tk.LEFT, padx=8)
        ttk.Button(actions, text="移除记录", style="Danger.TButton", command=self.remove_selected).pack(side=tk.LEFT)
        tk.Label(footer, text="自动刷新  2s", foreground=PALETTE["subtle"], background=PALETTE["surface"], font=("Ubuntu", 9)).pack(side=tk.RIGHT)

        detail_box = tk.Frame(
            container,
            background=PALETTE["surface"],
            highlightbackground=PALETTE["border"],
            highlightthickness=1,
            padx=16,
            pady=13,
        )
        detail_box.pack(fill=tk.X, pady=(14, 0))
        self.detail_accent = tk.Frame(detail_box, background=PALETTE["accent"], width=3)
        self.detail_accent.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))
        detail_content = tk.Frame(detail_box, background=PALETTE["surface"])
        detail_content.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(detail_content, text="状态说明", foreground=PALETTE["text"], background=PALETTE["surface"], font=("Noto Sans CJK SC", 10, "bold")).pack(anchor=tk.W)
        self.details = tk.Label(
            detail_content,
            text="选择一个 Shell 查看说明",
            justify=tk.LEFT,
            anchor=tk.W,
            foreground=PALETTE["muted"],
            background=PALETTE["surface"],
            font=("Noto Sans CJK SC", 9),
        )
        self.details.pack(fill=tk.X, pady=(5, 0))

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        self.style = style
        style.theme_use("clam")
        style.configure("App.TFrame", background=PALETTE["bg"])
        style.configure("Surface.TFrame", background=PALETTE["surface"])
        style.configure("Title.TLabel", background=PALETTE["bg"], foreground=PALETTE["text"], font=("Ubuntu", 18, "bold"))
        style.configure("Subtitle.TLabel", background=PALETTE["bg"], foreground=PALETTE["muted"], font=("Noto Sans CJK SC", 9))
        style.configure("Accent.TButton", background=PALETTE["accent"], foreground="#ffffff", borderwidth=0, padding=(15, 8), font=("Noto Sans CJK SC", 9, "bold"))
        style.map("Accent.TButton", background=[("active", PALETTE["accent_hover"]), ("pressed", "#6657e8")])
        style.configure("Ghost.TButton", background=PALETTE["surface_2"], foreground=PALETTE["text"], borderwidth=0, padding=(14, 8), font=("Noto Sans CJK SC", 9))
        style.map("Ghost.TButton", background=[("active", PALETTE["surface_3"]), ("pressed", PALETTE["border"])])
        style.configure("Danger.TButton", background=PALETTE["surface_2"], foreground="#fb8da0", borderwidth=0, padding=(14, 8), font=("Noto Sans CJK SC", 9))
        style.map("Danger.TButton", background=[("active", "#3a2030")])
        style.configure("Shell.Treeview", background=PALETTE["surface"], fieldbackground=PALETTE["surface"], foreground=PALETTE["text"], borderwidth=0, relief="flat", rowheight=43, font=("Noto Sans CJK SC", 9))
        style.configure("Shell.Treeview.Heading", background=PALETTE["surface_3"], foreground=PALETTE["muted"], borderwidth=0, relief="flat", padding=(10, 10), font=("Noto Sans CJK SC", 9, "bold"))
        style.map("Shell.Treeview", background=[], foreground=[])
        style.map("Shell.Treeview.Heading", background=[("active", PALETTE["surface_3"])])
        style.configure(
            "Dark.Vertical.TScrollbar",
            background=PALETTE["accent"],
            troughcolor=PALETTE["surface"],
            borderwidth=0,
            relief="flat",
            arrowsize=0,
            width=8,
        )

    def refresh(self) -> None:
        if self.refresh_job is not None:
            self.root.after_cancel(self.refresh_job)
            self.refresh_job = None
        selected_shell_id = None
        expanded_windows = {
            item.removeprefix("group:")
            for item in self.tree.get_children()
            if item.startswith("group:") and self.tree.item(item, "open")
        }
        selection = self.tree.selection()
        if selection:
            selected_shell_id = selection[0]
        try:
            self.windows = list_windows()
            self._harvest_tab_scan()
            self._request_tab_scan()
            self.activities = self.activity_tracker.update(self.windows)
            error = ""
        except X11Error as exc:
            self.windows = []
            self.activities = {}
            error = str(exc)

        shells = load_shells()
        tty_cwds = terminal_tty_cwds()

        self.tree.delete(*self.tree.get_children())
        self.items.clear()
        self.tab_items.clear()
        query = self.search_var.get().strip().lower()
        row_index = 0
        records_by_window = {info.window_id: info for info in shells}
        used_record_ids: set[str] = set()
        rows: list[tuple[ShellInfo | None, WindowInfo | None, ActivityState | None, str, str]] = []
        for window in self.windows:
            info = records_by_window.get(window.window_id)
            if info:
                used_record_ids.add(info.shell_id)
            activity = self.activities.get(window.window_id)
            status = activity.status if activity else "unknown"
            name = info.name if info else (window.title or "终端窗口")
            rows.append((info, window, activity, status, name))
        for info in shells:
            if info.shell_id not in used_record_ids:
                rows.append((info, None, None, "ended", info.name))

        rows.sort(key=lambda row: activity_sort_key(row[2], row[3], row[4]))
        tab_signals = []
        for group in self.tab_groups.values():
            window = find_window(group.window_id, self.windows)
            if not window:
                continue
            for tab in group.tabs:
                tab_signals.append(tab_window_signal(window, tab))
        tab_activities = self.tab_activity_tracker.update(tab_signals)

        thermal_statuses = {
            window_id: activity.status for window_id, activity in self.activities.items()
        }
        for group in self.tab_groups.values():
            for tab in group.tabs:
                if tab.selected:
                    continue
                signal_id = tab.signal_id(group.window_id)
                tab_activity = tab_activities.get(signal_id)
                if tab_activity:
                    thermal_statuses[signal_id] = tab_activity.status
        self.thermal_levels = self.thermal_tracker.update(thermal_statuses)

        for info, window, activity, status, name in rows:
            window_title = window.title if window else f"{info.window_id}（未找到）" if info else "窗口不存在"
            searchable = " ".join((name, status, STATUS_LABELS.get(status, ""), window_title)).lower()
            if query and query not in searchable:
                continue
            group = self.tab_groups.get(window.window_id) if window else None
            iid = f"group:{window.window_id}" if group else f"shell:{info.shell_id}" if info else f"window:{window.window_id}"
            tab_key = f"tab:{group.selected.index}" if group else "main"
            cwd = self._directory_for(info, window, tab_key, tty_cwds)
            self.items[iid] = (info, window)
            registered_prefix = "" if info else "未登记 · "
            self.tree.insert(
                "",
                tk.END,
                iid=iid,
                values=(
                    f"{'▾' if window and window.window_id in expanded_windows else '▸'}  {name}" if group else name,
                    f"GNOME Terminal · {len(group.tabs)} 个标签" if group else registered_prefix + window_title,
                    display_directory(cwd),
                    status_text(status),
                    age_text(activity),
                    signal_text(activity),
                ),
                tags=self._row_tags(
                    status,
                    row_index,
                    info is None,
                    window.window_id if window else "",
                    item_id=iid,
                    temperature=self.thermal_levels.get(window.window_id, 0.0) if window else 0.0,
                ),
                open=bool(window and window.window_id in expanded_windows),
            )
            row_index += 1
            if group and window:
                for tab in group.tabs:
                    if tab.selected:
                        continue
                    child_id = f"tab:{window.window_id}:{tab.index}"
                    child_activity = tab_activities.get(tab.signal_id(window.window_id))
                    child_status = child_activity.status if child_activity else "static"
                    child_title = tab.title or f"标签 {tab.index + 1}"
                    child_cwd = self._directory_for(info, window, f"tab:{tab.index}", tty_cwds)
                    self.items[child_id] = (info, window)
                    self.tab_items[child_id] = (group, tab.index)
                    self.tree.insert(
                        iid,
                        tk.END,
                        iid=child_id,
                        text="",
                        values=(
                            f"      └─  {child_title}",
                            f"同一窗口 · 标签 {tab.index + 1}",
                            display_directory(child_cwd),
                            status_text(child_status),
                            age_text(child_activity),
                            signal_text(child_activity),
                        ),
                        tags=self._row_tags(
                            child_status,
                            None,
                            info is None,
                            window.window_id,
                            item_id=child_id,
                            temperature=self.thermal_levels.get(tab.signal_id(window.window_id), 0.0),
                            child=True,
                        ),
                    )

        registered_window_ids = {info.window_id for info in shells}
        unregistered = sum(1 for window in self.windows if window.window_id not in registered_window_ids)
        total = len(rows)
        running = sum(1 for state in self.activities.values() if state.status == "active")
        waiting = sum(1 for state in self.activities.values() if state.status == "waiting")
        idle = sum(1 for state in self.activities.values() if state.status == "static")
        values = {"total": total, "waiting": waiting, "running": running, "idle": idle, "unregistered": unregistered}
        for key, value in values.items():
            self.metric_values[key].configure(text=str(value))
        self._update_metric_cards()
        self._apply_thermal_theme(mean_temperature(self.thermal_levels))
        if error:
            self.details.configure(text=error)
        active_item = None
        try:
            active_id = active_window_id()
            active_item = item_id_for_window(self.items, active_id)
            if active_item:
                if active_item != self._observed_active_item:
                    self._flash_workspace_item(active_item)
                self._observed_active_item = active_item
            else:
                self._observed_active_item = None
        except (X11Error, ValueError):
            pass
        self._apply_focused_shell_highlight()
        item_to_select = active_item or selected_shell_id
        if item_to_select and self.tree.exists(item_to_select):
            self.tree.selection_set(item_to_select)
            self.tree.focus(item_to_select)
            if active_item:
                self.tree.see(item_to_select)
        if self.focused_item_id is None:
            self._sync_selected_style()
        self.update_details()
        self._adapt_window_height()
        self.refresh_job = self.root.after(2000, self.refresh)

    def _directory_for(
        self,
        shell: ShellInfo | None,
        window: WindowInfo | None,
        tab_key: str,
        tty_cwds: dict[str, str],
    ) -> str:
        window_id = window.window_id if window else shell.window_id if shell else ""
        tty = self.tty_bindings.get(window_id, {}).get(tab_key, "")
        if tty in tty_cwds:
            return tty_cwds[tty]
        if shell and shell.tty in tty_cwds:
            return tty_cwds[shell.tty]
        return shell.cwd if shell and shell.cwd else ""

    def selected(self) -> tuple[str, ShellInfo | None, WindowInfo | None] | None:
        selection = self.tree.selection()
        if not selection:
            return None
        iid = selection[0]
        shell, window = self.items[iid]
        return iid, shell, window

    def _handle_tree_selection(self, _event: tk.Event) -> None:
        self.update_details()
        if self.focused_item_id is None:
            self._sync_selected_style()

    def _sync_selected_style(self) -> None:
        selection = self.tree.selection()
        background = PALETTE["surface"]
        foreground = PALETTE["text"]
        if selection and self.tree.exists(selection[0]):
            for tag in self.tree.item(selection[0], "tags"):
                configured = self.tree.tag_configure(tag)
                background = configured.get("background") or background
                foreground = configured.get("foreground") or foreground
        self.style.map(
            "Shell.Treeview",
            background=[("selected", background)],
            foreground=[("selected", foreground)],
        )

    def _handle_tree_click(self, event: tk.Event) -> None:
        item_id = self.tree.identify_row(event.y)
        if item_id.startswith("group:") and self.tree.identify_column(event.x) == "#1":
            bounds = self.tree.bbox(item_id, "name")
            if bounds and event.x - bounds[0] <= 38:
                self._schedule_group_click(lambda: self._toggle_group(item_id))
                return
            self._schedule_group_click(self.focus_selected)
            return
        if item_id in self.tab_items and self.tree.identify_region(event.x, event.y) == "cell":
            self.root.after_idle(self.focus_selected)
        elif item_id and self.tree.identify_column(event.x) == "#1" and self.tree.identify_region(event.x, event.y) == "cell":
            self.root.after_idle(self.focus_selected)

    def _handle_tree_double_click(self, event: tk.Event) -> str | None:
        item_id = self.tree.identify_row(event.y)
        if item_id.startswith("group:") and self.tree.identify_column(event.x) == "#1":
            self._cancel_group_click()
            self.tree.selection_set(item_id)
            self.tree.focus(item_id)
            self.root.after_idle(self.focus_selected)
            return "break"
        self.focus_selected()
        return None

    def _schedule_group_click(self, callback) -> None:
        self._cancel_group_click()
        self._group_click_job = self.root.after(240, lambda: self._run_group_click(callback))

    def _run_group_click(self, callback) -> None:
        self._group_click_job = None
        callback()

    def _cancel_group_click(self) -> None:
        if self._group_click_job is not None:
            self.root.after_cancel(self._group_click_job)
            self._group_click_job = None

    def _toggle_group(self, item_id: str) -> None:
        if not self.tree.exists(item_id):
            return
        previous_height = self.root.winfo_height()
        opened = not bool(self.tree.item(item_id, "open"))
        self.tree.item(item_id, open=opened)
        values = list(self.tree.item(item_id, "values"))
        if values:
            label = values[0]
            if label.startswith(("▸  ", "▾  ")):
                label = label[3:]
            values[0] = f"{'▾' if opened else '▸'}  {label}"
            self.tree.item(item_id, values=values)
        self._adapt_window_height(
            force=True,
            minimum_height=previous_height if opened else None,
        )

    def _bind_metric_card(self, widget: tk.Widget, key: str) -> None:
        widget.configure(cursor="hand2")
        widget.bind("<Button-1>", lambda _event, metric=key: self._set_metric_highlight(metric))
        for child in widget.winfo_children():
            self._bind_metric_card(child, key)

    def _set_metric_highlight(self, key: str) -> None:
        self.metric_highlight = None if self.metric_highlight == key else key
        self.refresh()

    def _update_metric_cards(self) -> None:
        for key, card in self.metric_cards.items():
            selected = key == self.metric_highlight
            background = "#2c265c" if selected else PALETTE["surface"]
            card.configure(
                background=background,
                highlightbackground=PALETTE["accent"] if selected else PALETTE["border"],
                highlightthickness=2 if selected else 1,
            )
            self._set_widget_background(card, background)

    def _set_widget_background(self, widget: tk.Widget, background: str) -> None:
        for child in widget.winfo_children():
            try:
                child.configure(background=background)
            except tk.TclError:
                pass
            self._set_widget_background(child, background)

    def _row_tags(
        self,
        status: str,
        row_index: int | None,
        unregistered: bool,
        window_id: str,
        *,
        item_id: str,
        temperature: float,
        child: bool = False,
    ) -> tuple[str, ...]:
        if metric_matches(self.metric_highlight, status, unregistered):
            return ("metric_match",)
        if self.thermal_enabled.get():
            heat_tag = f"heat:{item_id}"
            cold_background = "#0c1524" if child else PALETTE["surface_2"] if row_index is not None and row_index % 2 else PALETTE["surface"]
            self.tree.tag_configure(
                heat_tag,
                background=blend_color(cold_background, HOT_ROW, visual_temperature(temperature)),
                foreground=blend_color(
                    STATUS_COLORS.get(status, PALETTE["text"]),
                    "#ffffff",
                    visual_temperature(temperature),
                ),
            )
            return (heat_tag,)
        tags: list[str] = [status]
        if child:
            tags.append("child")
        elif row_index is not None:
            tags.append("even" if row_index % 2 == 0 else "odd")
        return tuple(tags)

    def _toggle_thermal_rendering(self) -> None:
        self.thermal_enabled.set(not self.thermal_enabled.get())
        self._draw_thermal_toggle()
        self.refresh()

    def _draw_thermal_toggle(self) -> None:
        self.thermal_indicator.delete("all")
        self.thermal_indicator.create_oval(2, 2, 14, 14, outline=PALETTE["muted"], width=1)
        if self.thermal_enabled.get():
            self.thermal_indicator.create_oval(6, 6, 10, 10, fill=PALETTE["muted"], outline="")

    def _apply_thermal_theme(self, project_temperature: float) -> None:
        enabled = self.thermal_enabled.get()
        temperature = visual_temperature(project_temperature) if enabled else 0.0
        accent = blend_color(PALETTE["accent"], HOT_ACCENT, temperature)
        hover = blend_color(PALETTE["accent_hover"], "#ff5964", temperature)
        self.logo.configure(background=accent)
        self.detail_accent.configure(background=accent)
        self._draw_thermal_toggle()
        self.style.configure("Accent.TButton", background=accent)
        self.style.map("Accent.TButton", background=[("active", hover), ("pressed", accent)])
        self.style.configure("Dark.Vertical.TScrollbar", background=accent)

    def _adapt_window_height(
        self,
        *,
        force: bool = False,
        minimum_height: int | None = None,
    ) -> None:
        visible_rows = 0
        for item_id in self.tree.get_children():
            visible_rows += 1
            if self.tree.item(item_id, "open"):
                visible_rows += len(self.tree.get_children(item_id))
        visible_rows = max(1, visible_rows)
        if not force and visible_rows == self._last_layout_rows:
            return
        self._last_layout_rows = visible_rows
        desired_height = max(640, 455 + visible_rows * 43)
        current_y = self.root.winfo_y()
        maximum_height = max(520, self.root.winfo_screenheight() - current_y - 55)
        target_height = min(desired_height, maximum_height)
        if minimum_height is not None:
            # Expanding must never shrink the existing window. If there is no
            # room below, keep its size and let the list scroll instead.
            target_height = max(minimum_height, target_height)
        overflow = desired_height > maximum_height
        self.tree.configure(height=visible_rows)
        if overflow:
            if not self.scrollbar.winfo_ismapped():
                self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        elif self.scrollbar.winfo_ismapped():
            self.scrollbar.pack_forget()
        width = max(1180, self.root.winfo_width())
        # A size-only geometry request leaves placement entirely untouched.
        # Reapplying winfo_x/y here is incorrect on decorated X11 windows:
        # Tk reports client coordinates while the window manager positions the
        # outer frame, producing a title-bar-sized downward jump.
        self.root.geometry(f"{width}x{target_height}")

    def focus_selected(self) -> None:
        selected = self.selected()
        if not selected:
            return
        iid, shell, window = selected
        tab_target = self.tab_items.get(iid)
        if tab_target:
            group, tab_index = tab_target
            if not select_tab(group, tab_index):
                self._tab_scan_result = None
                self._request_tab_scan()
                self.details.configure(text="标签列表刚刚发生变化，正在后台刷新；请再点击一次。")
                return
        window_id = window.window_id if window else shell.window_id if shell else ""
        if not window_id:
            return
        self._flash_workspace_item(iid)
        self.root.update_idletasks()
        try:
            focus_window(window_id, shake=tab_target is None, sync=tab_target is None)
        except X11Error as exc:
            messagebox.showerror("无法进入终端", str(exc), parent=self.root)
            return
        group = self.tab_groups.get(window_id)
        if tab_target:
            tab_key = f"tab:{tab_target[1]}"
        elif group:
            tab_key = f"tab:{group.selected.index}"
        else:
            tab_key = "main"

        tty = self.tty_bindings.get(window_id, {}).get(tab_key, "")
        if not can_highlight_tty(tty):
            tty = ""
        if not tty:
            self.details.configure(text="首次识别该标签，正在建立高亮关联…")
            self.root.update_idletasks()
            tty = probe_visible_tty(window_id) or ""
            if tty:
                self._remember_tty(window_id, tab_key, tty)
        if tty:
            self.window_highlighter.flash(tty)
        else:
            self.window_highlighter.hide()
            self.details.configure(text="未能自动识别该标签的 TTY；聚焦和震动仍然可用。")

    def _remember_tty(self, window_id: str, tab_key: str, tty: str) -> None:
        self.tty_bindings.setdefault(window_id, {})[tab_key] = tty
        save_tty_binding(window_id, tab_key, tty)

    def _apply_focused_shell_highlight(self) -> None:
        for item_id in self.items:
            if item_id == self.focused_item_id:
                self.tree.item(item_id, tags=("focused_shell",))

    def _flash_workspace_item(self, item_id: str, duration_ms: int = 1100) -> None:
        if self._focus_clear_job is not None:
            self.root.after_cancel(self._focus_clear_job)
        if self.focused_item_id and self._focus_saved_tags and self.tree.exists(self.focused_item_id):
            self.tree.item(self.focused_item_id, tags=self._focus_saved_tags)
        self.focused_item_id = item_id
        self._focus_saved_tags = tuple(self.tree.item(item_id, "tags")) if self.tree.exists(item_id) else None
        self._apply_focused_shell_highlight()
        self.style.map(
            "Shell.Treeview",
            background=[("selected", "#6557e8")],
            foreground=[("selected", "#ffffff")],
        )
        self._focus_clear_job = self.root.after(duration_ms, self._clear_workspace_highlight)

    def _clear_workspace_highlight(self) -> None:
        self._focus_clear_job = None
        self.focused_item_id = None
        self._focus_saved_tags = None
        self.refresh()

    def _harvest_tab_scan(self) -> None:
        if self._tab_scan_result is not None:
            scanned = {group.window_id: group for group in self._tab_scan_result}
            scanned_ids = set(scanned)
            live_windows = {window.window_id for window in self.windows}
            for window_id, old_group in self.tab_groups.items():
                if window_id in scanned or window_id not in live_windows:
                    self._tab_group_misses.pop(window_id, None)
                    continue
                misses = self._tab_group_misses.get(window_id, 0) + 1
                self._tab_group_misses[window_id] = misses
                if misses < 2:
                    scanned[window_id] = old_group
            for window_id in scanned_ids:
                self._tab_group_misses.pop(window_id, None)
            self.tab_groups = scanned
            self._tab_scan_result = None

    def _request_tab_scan(self) -> None:
        if self._tab_scan_thread and self._tab_scan_thread.is_alive():
            return
        windows = list(self.windows)

        def scan() -> None:
            self._tab_scan_result = scan_tab_groups(windows)

        self._tab_scan_thread = threading.Thread(target=scan, daemon=True, name="terminal-tab-scan")
        self._tab_scan_thread.start()

    def update_details(self) -> None:
        selected = self.selected()
        if not selected:
            self.details.configure(text="选择一个 Shell 查看说明")
            return
        iid, shell, window = selected
        window_id = window.window_id if window else shell.window_id if shell else ""
        activity = self.activities.get(window_id)
        if activity:
            text = activity_explanation(activity)
            if shell:
                text += f"\n用途名称“{shell.name}”仅保存在管理器中，与 Shell/TTY 无关。"
            else:
                text += "\n该窗口尚未命名；点击“登记窗口”只需记录用途名称。"
        else:
            text = "暂时无法取得该窗口的画面活动；窗口可能已经关闭。"
        if not window:
            text += "\n当前窗口 ID 已不存在；Shell 可能结束或窗口已经关闭。"
        elif iid in self.tab_items:
            text += "\n这是同一终端窗口中的隐藏标签；单击即可切换到该标签。"
        self.details.configure(text=text)

    def rename_selected(self) -> None:
        selected = self.selected()
        if not selected:
            return
        _iid, shell, window = selected
        if not shell:
            self.register_selected()
            return
        self.edit_record(shell, window)

    def register_selected(self) -> None:
        selected = self.selected()
        if not selected:
            messagebox.showinfo("登记窗口", "请先在列表中选择一个终端窗口。", parent=self.root)
            return
        iid, shell, window = selected
        if iid in self.tab_items:
            messagebox.showinfo("隐藏标签", "隐藏标签暂时沿用所属窗口的管理记录。", parent=self.root)
            return
        if shell:
            self.edit_record(shell, window)
            return
        if not window:
            return
        self.edit_record(None, window)

    def edit_record(self, shell: ShellInfo | None, window: WindowInfo | None) -> None:
        if not window and shell:
            window = find_window(shell.window_id, self.windows)
        if not window:
            messagebox.showerror("窗口不存在", "当前记录对应的终端窗口已经关闭。", parent=self.root)
            return
        dialog = RegistrationDialog(
            self.root,
            title="编辑终端记录" if shell else "登记终端窗口",
            initial_name=shell.name if shell else (window.title or "终端窗口"),
            palette=PALETTE,
        )
        if not dialog.result:
            return
        name = dialog.result
        now = time.time()
        if shell is None:
            shell = ShellInfo(
                shell_id=uuid.uuid4().hex[:12],
                window_id=window.window_id,
                shell_pid=0,
                tty="",
                name=name,
                status="unbound",
                status_detail="仅记录名称",
                command="",
                cwd="",
                foreground_pid=None,
                process_state="",
                registered_at=now,
                last_seen=now,
            )
        shell.name = name
        shell.window_id = window.window_id
        shell.status = "unbound"
        shell.status_detail = "Codex 状态由终端窗口标题识别"
        shell.command = ""
        shell.cwd = ""
        shell.last_seen = now
        save_shell(shell)
        self.refresh()

    def remove_selected(self) -> None:
        selected = self.selected()
        if not selected:
            return
        _iid, shell, _window = selected
        if not shell:
            messagebox.showinfo("未注册窗口", "该条目没有注册记录可移除。", parent=self.root)
            return
        if messagebox.askyesno("移除记录", f"从总览移除“{shell.name}”？\n不会关闭 Shell 或终止任务。", parent=self.root):
            remove_shell(shell.shell_id)
            self.refresh()

def status_text(status: str) -> str:
    return f"{STATUS_DOTS.get(status, '●')}  {STATUS_LABELS.get(status, status)}"


def display_directory(cwd: str) -> str:
    if not cwd:
        return "待识别"
    home = str(Path.home())
    return "~" + cwd[len(home) :] if cwd == home or cwd.startswith(home + "/") else cwd


def signal_text(activity: ActivityState | None) -> str:
    if not activity:
        return "无状态信号"
    if activity.status == "waiting":
        return f"{activity.prefix} 需要输入"
    if activity.status == "active":
        source = "已学习动画" if activity.learned_prefix else "Codex 动画"
        return f"{activity.prefix} {source}"
    return "无 Codex 状态图标"


def age_text(activity: ActivityState | None) -> str:
    if not activity:
        return "未知"
    duration = activity.seconds_in_status
    if activity.status == "waiting":
        return "刚需输入" if duration < 0.5 else f"等待 {duration:.1f} 秒"
    if activity.status == "active":
        return "刚开始输出" if duration < 0.5 else f"已输出 {duration:.1f} 秒"
    return "刚静止" if duration < 0.5 else f"静态 {duration:.1f} 秒"


def activity_sort_key(
    activity: ActivityState | None, status: str, name: str
) -> tuple[int, float, str]:
    order = {"waiting": 0, "active": 1, "static": 2}
    return (order.get(status, 3), activity.seconds_in_status if activity else 0.0, name.lower())


def metric_matches(metric: str | None, status: str, unregistered: bool) -> bool:
    if metric is None:
        return False
    if metric == "total":
        return True
    if metric == "waiting":
        return status == "waiting"
    if metric == "running":
        return status == "active"
    if metric == "idle":
        return status == "static"
    if metric == "unregistered":
        return unregistered
    return False


def activity_explanation(activity: ActivityState) -> str:
    duration = activity.seconds_in_status
    if activity.status == "waiting":
        return f"等待用户：Codex 在窗口标题中显示“{activity.prefix}”，已等待 {duration:.1f} 秒。"
    if activity.status == "active":
        source = "自动学习到的动画前缀" if activity.learned_prefix else "Codex 标准动画前缀"
        return f"正在输出：窗口标题正在显示{source}“{activity.prefix}”，已持续 {duration:.1f} 秒。"
    if activity.status == "static":
        return f"静态/空闲：窗口标题没有 Codex 状态图标，已持续 {duration:.1f} 秒。"
    return "无法从窗口标题判断当前状态。"


def item_id_for_window(
    items: dict[str, tuple[ShellInfo | None, WindowInfo | None]], window_id: str
) -> str | None:
    for item_id, (shell, window) in items.items():
        linked_window_id = window.window_id if window else shell.window_id if shell else ""
        if linked_window_id == window_id:
            return item_id
    return None


def tab_window_signal(window: WindowInfo, tab: TerminalTab) -> WindowInfo:
    return WindowInfo(
        tab.signal_id(window.window_id),
        window.desktop,
        window.pid,
        window.x,
        window.y,
        window.width,
        window.height,
        window.wm_class,
        window.host,
        tab.title,
    )


def main() -> None:
    root = tk.Tk()
    try:
        TerminalManagerApp(root)
    except X11Error as exc:
        root.withdraw()
        messagebox.showerror("Terminal Manager 无法启动", str(exc))
        raise SystemExit(1) from exc
    root.mainloop()


if __name__ == "__main__":
    main()
